"""Telegram booking bot for a beauty salon. Pure Python stdlib, no installs.

Run:   BOT_TOKEN=... ADMIN_ID=... python3 bot.py
Test:  python3 bot.py test
"""
import json, os, sqlite3, sys, time, urllib.error, urllib.request
from datetime import date, datetime, timedelta

# ---- Business settings: edit these for each client ----
BUSINESS = "Glow Beauty Studio"
SERVICES = ["Manicure — $30", "Pedicure — $40", "Haircut & styling — $45", "Brows & lashes — $35"]
HOURS = [f"{h:02d}:00" for h in range(10, 19)]  # 10:00 … 18:00
DAYS_AHEAD = 7
CLOSED_WEEKDAYS = {6}  # 6 = Sunday
# What the AI assistant knows about the business. Plain text, edit freely.
SALON_INFO = """Address: 25 Rose Street, Brooklyn, NY. Entrance from the courtyard, 2nd floor.
Open Mon–Sat 10:00–19:00, closed Sunday.
Payment: cash, card, Apple Pay. Free cancellation up to 2 hours before.
Manicure includes gel polish; French or nail art +$10. Pedicure takes about 1 hour.
Brows & lashes: shaping, tint and lash lift. We use hypoallergenic products.
Parking: free street parking. Kids welcome. Gift cards available at the studio."""

TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID")  # owner's Telegram user id: notifications + owner commands
API = f"https://api.telegram.org/bot{TOKEN}/"

ADMIN_HELP = """🛠 Owner commands
/today: today's schedule
/tomorrow: tomorrow's schedule
/block 2026-11-20 14:00 15:00: block hours (no hours = whole day)
/unblock 2026-11-20 14:00: unblock hours (no hours = whole day)
/cancel 12: cancel booking #12 and tell the client"""


def init_db(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bookings(
      id INTEGER PRIMARY KEY, user_id INTEGER, contact TEXT, service TEXT,
      day TEXT, time TEXT, r24 INTEGER DEFAULT 0, r2 INTEGER DEFAULT 0, UNIQUE(day, time))""")
    for col in ("r24", "r2"):  # upgrade databases made by the first version
        try:
            conn.execute(f"ALTER TABLE bookings ADD COLUMN {col} INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
    return conn

db = init_db(sqlite3.connect(os.environ.get("DB_PATH", "bookings.db")))
state = {}  # user_id -> {"service", "day", "time"} while booking. Blocked hours are rows with user_id 0.


# ---- Booking logic ----
def starts(day, t):
    return datetime.fromisoformat(f"{day}T{t}")

def free_slots(day, now=None):
    now = now or datetime.now()
    taken = {r[0] for r in db.execute("SELECT time FROM bookings WHERE day=?", (day,))}
    return [t for t in HOURS if t not in taken and starts(day, t) > now]

def open_days(today=None, now=None):
    today = today or date.today()
    days = (today + timedelta(i) for i in range(DAYS_AHEAD))
    return [d.isoformat() for d in days
            if d.weekday() not in CLOSED_WEEKDAYS and free_slots(d.isoformat(), now)]

def book(user_id, contact, service, day, t, now=None):
    """Returns booking id, or None if the slot was taken meanwhile."""
    left = starts(day, t) - (now or datetime.now())
    # a reminder whose moment already passed at booking time is skipped
    r24, r2 = int(left <= timedelta(hours=24)), int(left <= timedelta(hours=2))
    try:
        with db:
            return db.execute("INSERT INTO bookings(user_id, contact, service, day, time, r24, r2) VALUES(?,?,?,?,?,?,?)",
                              (user_id, contact, service, day, t, r24, r2)).lastrowid
    except sqlite3.IntegrityError:
        return None

def my_bookings(user_id):
    return db.execute("SELECT id, service, day, time FROM bookings WHERE user_id=? AND day>=? ORDER BY day, time",
                      (user_id, date.today().isoformat())).fetchall()

def cancel(user_id, booking_id):
    with db:
        row = db.execute("SELECT service, day, time FROM bookings WHERE id=? AND user_id=?", (booking_id, user_id)).fetchone()
        db.execute("DELETE FROM bookings WHERE id=? AND user_id=?", (booking_id, user_id))
    return row

def due_reminders(now=None):
    """Bookings that need a reminder right now, as (id, user_id, service, day, time, kind). Marks them sent."""
    now = now or datetime.now()
    out = []
    with db:
        rows = db.execute("SELECT id, user_id, service, day, time, r24, r2 FROM bookings "
                          "WHERE user_id!=0 AND (r24=0 OR r2=0) AND day>=?", (now.date().isoformat(),)).fetchall()
        for bid, uid, sv, day, t, r24, r2 in rows:
            left = starts(day, t) - now
            if left <= timedelta(0):
                continue
            if left <= timedelta(hours=2) and not r2:
                db.execute("UPDATE bookings SET r24=1, r2=1 WHERE id=?", (bid,))
                out.append((bid, uid, sv, day, t, "2h"))
            elif left <= timedelta(hours=24) and not r24:
                db.execute("UPDATE bookings SET r24=1 WHERE id=?", (bid,))
                out.append((bid, uid, sv, day, t, "24h"))
    return out


# ---- Owner panel ----
def schedule(day):
    return db.execute("SELECT id, time, service, contact, user_id FROM bookings WHERE day=? ORDER BY time", (day,)).fetchall()

def set_block(day, times, blocked):
    with db:
        for t in times:
            if blocked:
                db.execute("INSERT OR IGNORE INTO bookings(user_id, contact, service, day, time, r24, r2) "
                           "VALUES(0, '', '⛔ Blocked', ?, ?, 1, 1)", (day, t))
            else:
                db.execute("DELETE FROM bookings WHERE day=? AND time=? AND user_id=0", (day, t))

def admin_cancel(booking_id):
    with db:
        row = db.execute("SELECT user_id, service, day, time FROM bookings WHERE id=? AND user_id!=0", (booking_id,)).fetchone()
        db.execute("DELETE FROM bookings WHERE id=? AND user_id!=0", (booking_id,))
    return row

def on_admin(text):
    """Owner command -> reply text."""
    cmd, *args = text.split()
    if cmd in ("/today", "/tomorrow"):
        day = (date.today() + timedelta(days=cmd == "/tomorrow")).isoformat()
        lines = [f"{t}  {sv}" + (f" · {c} (#{i})" if uid else "") for i, t, sv, c, uid in schedule(day)]
        return f"📋 {nice_day(day)}\n" + ("\n".join(lines) or "No bookings yet.")
    if cmd in ("/block", "/unblock") and args:
        try:
            date.fromisoformat(args[0])
        except ValueError:
            return "Date format: 2026-11-20"
        times = args[1:] or HOURS
        if bad := [t for t in times if t not in HOURS]:
            return f"Unknown hour: {', '.join(bad)}. Use: {HOURS[0]} … {HOURS[-1]}"
        set_block(args[0], times, cmd == "/block")
        return f"{'⛔ Blocked' if cmd == '/block' else '✅ Unblocked'}: {nice_day(args[0])} {' '.join(args[1:]) or 'whole day'}"
    if cmd == "/cancel" and args and args[0].isdigit():
        row = admin_cancel(int(args[0]))
        if not row:
            return "Booking not found."
        uid, sv, day, t = row
        api("sendMessage", chat_id=uid, text=f"😔 Sorry, your booking was cancelled by the salon:\n{sv}\n{nice_day(day)} at {t}\n\nPlease pick another time.", reply_markup=MENU)
        return f"❌ Cancelled #{args[0]} and told the client."
    return ADMIN_HELP


# ---- AI assistant (Claude) ----
AI_MODEL = os.environ.get("AI_MODEL", "claude-opus-5-5")
_claude = None

def ai_system_prompt():
    return (f"You are the friendly front-desk assistant of {BUSINESS} in a Telegram chat.\n"
            f"Services and prices:\n" + "\n".join(f"- {s}" for s in SERVICES) +
            f"\nBooking hours: {HOURS[0]}–{HOURS[-1]}.\n\nBusiness info:\n{SALON_INFO}\n\n"
            "Answer in the client's language, in 1–3 short sentences, plain text. "
            "Use only the facts above; if you don't know, say the owner will reply soon. "
            "Don't invent free slots or confirm bookings yourself: to book, the client taps "
            "the 📅 Book an appointment button below your reply.")

def ai_answer(question):
    """Claude's reply to a free-text question, or None when AI is off or unavailable."""
    global _claude
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # imported lazily so the bot still runs without the SDK
        _claude = _claude or anthropic.Anthropic()
        r = _claude.beta.messages.create(
            model=AI_MODEL, max_tokens=1024,
            output_config={"effort": "low"},  # short FAQ answers don't need deep thinking
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=ai_system_prompt(),
            messages=[{"role": "user", "content": question[:1000]}],
        )
        if r.stop_reason == "refusal":
            return None
        return "".join(b.text for b in r.content if b.type == "text").strip() or None
    except Exception as e:  # API down, no credit, bad key: fall back to the menu, never crash
        print("AI error:", e, flush=True)
        return None


# ---- Telegram ----
def api(method, **params):
    req = urllib.request.Request(API + method, json.dumps(params).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.load(r)["result"]
    except urllib.error.HTTPError as e:  # show Telegram's own reason, not just "400 Bad Request"
        raise RuntimeError(f"{method}: {json.load(e).get('description', e)}") from None

def kb(buttons, per_row=1):
    rows = [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}

MENU = kb([("📅 Book an appointment", "book"), ("🗂 My bookings", "my")])
BACK = ("« Menu", "menu")

def nice_day(day):
    return datetime.fromisoformat(day).strftime("%a, %b %d")

def notify_admin(text):
    if ADMIN_ID:
        api("sendMessage", chat_id=ADMIN_ID, text=text)

def send_reminders():
    for bid, uid, sv, day, t, kind in due_reminders():
        when = "in 2 hours" if kind == "2h" else "tomorrow" if day != date.today().isoformat() else "today"
        try:
            api("sendMessage", chat_id=uid, text=f"⏰ Reminder: your appointment is {when}!\n{sv}\n{nice_day(day)} at {t}\n\nCan't make it? Please cancel so someone else can book.",
                reply_markup=kb([("❌ Cancel booking", f"x:{bid}")]))
        except Exception as e:  # client blocked the bot: skip, don't stop the others
            print("reminder failed:", e)

def on_message(msg):
    uid, text = msg["from"]["id"], msg.get("text", "")
    print(f"message from user id {uid}", flush=True)  # handy to find your ADMIN_ID
    if ADMIN_ID and str(uid) == ADMIN_ID and text.startswith("/") and text != "/start":
        return api("sendMessage", chat_id=uid, text=on_admin(text))
    s = state.get(uid)
    if s and "time" in s and not text.startswith("/"):
        state.pop(uid)
        bid = book(uid, text[:200], s["service"], s["day"], s["time"])
        if bid is None:
            return api("sendMessage", chat_id=uid, text="😔 Sorry, that slot was just taken. Please pick another.", reply_markup=MENU)
        when = f"{nice_day(s['day'])} at {s['time']}"
        api("sendMessage", chat_id=uid, text=f"✅ Booked!\n{s['service']}\n{when}\n\nWe'll remind you the day before. See you soon!", reply_markup=MENU)
        return notify_admin(f"🆕 New booking #{bid}\n{s['service']}\n{when}\nClient: {text[:200]}")
    if text and not text.startswith("/") and (answer := ai_answer(text)):
        return api("sendMessage", chat_id=uid, text=answer, reply_markup=MENU)
    hint = "\n\n(You're the owner: send /admin for owner commands.)" if ADMIN_ID and str(uid) == ADMIN_ID else ""
    api("sendMessage", chat_id=uid, text=f"👋 Welcome to {BUSINESS}!\nWhat would you like to do?{hint}", reply_markup=MENU)

def on_callback(cq):
    uid, data, m = cq["from"]["id"], cq["data"], cq["message"]
    try:
        api("answerCallbackQuery", callback_query_id=cq["id"])
    except RuntimeError:
        pass  # button pressed while the bot was off: too old to answer, still handle the press

    def edit(text, markup):
        try:
            api("editMessageText", chat_id=m["chat"]["id"], message_id=m["message_id"], text=text, reply_markup=markup)
        except RuntimeError as e:
            if "not modified" not in str(e):  # same button pressed twice: nothing to change
                raise

    if data == "menu":
        state.pop(uid, None)
        edit("What would you like to do?", MENU)
    elif data == "book":
        edit("Choose a service:", kb([(name, f"s:{i}") for i, name in enumerate(SERVICES)] + [BACK]))
    elif data.startswith("s:"):
        state[uid] = {"service": SERVICES[int(data[2:])]}
        days = open_days()
        edit("Choose a day:" if days else "No free days this week 😔",
             kb([(nice_day(d), f"d:{d}") for d in days] + [BACK], per_row=2))
    elif data.startswith("d:") and uid in state:
        state[uid]["day"] = data[2:]
        edit(f"{nice_day(data[2:])}: choose a time:", kb([(t, f"t:{t}") for t in free_slots(data[2:])] + [BACK], per_row=3))
    elif data.startswith("t:") and "day" in state.get(uid, {}):
        state[uid]["time"] = data[2:]
        edit(f"{state[uid]['service']}\n{nice_day(state[uid]['day'])} at {data[2:]}\n\n"
             "✍️ Send your name and phone number in one message, e.g.:\nAnna, +1 555 123 4567", kb([BACK]))
    elif data == "my":
        rows = my_bookings(uid)
        text = "Your bookings:" if rows else "You have no upcoming bookings."
        edit(text, kb([(f"❌ {nice_day(d)} {t} · {sv.split(' —')[0]}", f"x:{i}") for i, sv, d, t in rows] + [BACK]))
    elif data.startswith("x:"):
        row = cancel(uid, int(data[2:]))
        if row:
            notify_admin(f"❌ Cancelled by client: {row[0]}, {nice_day(row[1])} {row[2]}")
        edit("Booking cancelled." if row else "Booking not found.", MENU)
    else:  # stale button after restart
        edit("What would you like to do?", MENU)

def run():
    if not TOKEN:
        sys.exit("Set BOT_TOKEN first (get it from @BotFather).")
    try:
        me = api("getMe")
    except Exception as e:  # wrong token: stop with a clear message instead of retrying forever
        sys.exit(f"Can't connect with this BOT_TOKEN ({e}). Copy the exact token from @BotFather.")
    print(f"Bot @{me['username']} is running. Ctrl+C to stop.", flush=True)
    offset = 0
    while True:
        try:
            send_reminders()
            for u in api("getUpdates", offset=offset, timeout=30):  # returns at least every 30 s, so reminders stay on time
                offset = u["update_id"] + 1
                if "message" in u:
                    on_message(u["message"])
                elif "callback_query" in u:
                    on_callback(u["callback_query"])
        except KeyboardInterrupt:
            break
        except Exception as e:  # keep the bot alive on network hiccups
            print("error:", e)
            time.sleep(3)


def self_test():
    global db
    db = init_db(sqlite3.connect(":memory:"))
    D = "2030-01-07"  # a Monday
    early = datetime(2030, 1, 7, 0, 0)
    assert len(free_slots(D, early)) == len(HOURS)
    assert free_slots(D, datetime(2030, 1, 7, 17, 30)) == ["18:00"]  # past hours hidden
    assert "2030-01-13" not in open_days(date(2030, 1, 7), early)  # Sunday closed

    bid = book(1, "Ann", SERVICES[0], D, "10:00", now=datetime(2030, 1, 5))
    assert bid and book(2, "Bob", SERVICES[0], D, "10:00") is None  # no double booking
    assert "10:00" not in free_slots(D, early)

    # reminders: none 2 days before, 24h one the day before, 2h one on the day, each once
    assert due_reminders(datetime(2030, 1, 5, 12)) == []
    assert [r[-1] for r in due_reminders(datetime(2030, 1, 6, 11))] == ["24h"]
    assert due_reminders(datetime(2030, 1, 6, 12)) == []
    assert [r[-1] for r in due_reminders(datetime(2030, 1, 7, 8, 30))] == ["2h"]
    assert due_reminders(datetime(2030, 1, 7, 9)) == []
    # booked 1 hour ahead: no reminders at all
    late = book(3, "Cat", SERVICES[1], D, "12:00", now=datetime(2030, 1, 7, 11))
    assert due_reminders(datetime(2030, 1, 7, 11, 5)) == []

    # owner: block whole day, unblock one hour, blocked hours never get reminders
    assert "Blocked" in on_admin("/block 2030-01-08")
    assert free_slots("2030-01-08", early) == []
    on_admin("/unblock 2030-01-08 15:00")
    assert free_slots("2030-01-08", early) == ["15:00"]
    assert due_reminders(datetime(2030, 1, 8, 9)) == []
    assert "Unknown hour" in on_admin("/block 2030-01-08 09:00")
    assert "Date format" in on_admin("/block tomorrow")
    assert "Owner commands" in on_admin("/admin")
    assert admin_cancel(late) and admin_cancel(late) is None

    # AI: prompt carries the salon facts; without a key it stays off instead of crashing
    p = ai_system_prompt()
    assert BUSINESS in p and SERVICES[0] in p and "Address" in p
    key = os.environ.pop("ANTHROPIC_API_KEY", None)
    assert ai_answer("Do you do French manicure?") is None
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key

    assert cancel(2, bid) is None  # can't cancel someone else's
    assert cancel(1, bid) and "10:00" in free_slots(D, early)
    print("All tests passed ✅")


if __name__ == "__main__":
    self_test() if sys.argv[1:] == ["test"] else run()
