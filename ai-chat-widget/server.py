"""AI website chat: an embeddable widget that answers from the company's own documents,
captures leads, and notifies the owner by email and Slack. Includes an owner dashboard.

Run:   ANTHROPIC_API_KEY=... ADMIN_PASSWORD=... python3 server.py    then open http://127.0.0.1:8080
Test:  python3 server.py test
Embed on any site:  <script src="https://YOUR-SERVER/widget.js" defer></script>

Optional env: SLACK_WEBHOOK_URL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL,
ALLOWED_ORIGINS (comma-separated sites allowed to embed the chat; default: any), AI_MODEL, PORT.
"""
import base64, html, json, os, re, smtplib, sqlite3, sys, threading, urllib.request
from datetime import datetime
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
BUSINESS = "Evergreen Family Dental"
GREETING = "Hi! 👋 I'm the Evergreen Dental assistant. Ask me about prices, insurance or booking a visit."
AI_MODEL = os.environ.get("AI_MODEL", "claude-opus-5-5")
MAX_MESSAGE = 1000       # characters per visitor message
MAX_PER_SESSION = 30     # visitor messages per conversation: protects the AI bill from abuse
HISTORY = 20             # messages of context sent to the AI

KNOWLEDGE = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "knowledge").glob("*.md")))
SYSTEM = f"""You are the website chat assistant of {BUSINESS}.

Answer ONLY from the company information below. If the answer is not there, say you're not sure and offer
to have the team follow up. Never invent prices, dates, availability or medical advice; for symptoms,
suggest booking a visit (or calling the main number for emergencies).

Style: friendly, plain text, 1–4 short sentences, in the visitor's language.

Leads: when the visitor wants to book, get a quote, or be contacted, ask for their name and an email or
phone number, plus what they need. Once you have them, call save_lead exactly once, then confirm that
the team will reach out within one business day. Don't ask for anything else (no birth dates, no insurance IDs).

<company_information>
{KNOWLEDGE}
</company_information>"""

LEAD_TOOL = {
    "name": "save_lead",
    "description": "Save a visitor who wants to book or be contacted, and notify the clinic team.",
    "strict": True,
    "input_schema": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "contact", "need"],
        "properties": {
            "name": {"type": "string", "description": "Visitor's name"},
            "contact": {"type": "string", "description": "Email or phone number"},
            "need": {"type": "string", "description": "What they want, one line, e.g. 'Invisalign consultation, has Cigna'"},
        },
    },
}

db_lock = threading.Lock()
db = sqlite3.connect(os.environ.get("DB_PATH", str(ROOT / "chat.db")), check_same_thread=False)


def init_db(conn):
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, session TEXT, role TEXT, text TEXT, time TEXT);
      CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY, session TEXT, name TEXT, contact TEXT, need TEXT, time TEXT);
      CREATE INDEX IF NOT EXISTS messages_session ON messages(session);""")
    return conn

init_db(db)
now = lambda: datetime.now().strftime("%Y-%m-%d %H:%M")


# ---- Storage ----
def add_message(session, role, text):
    with db_lock, db:
        db.execute("INSERT INTO messages(session, role, text, time) VALUES(?,?,?,?)", (session, role, text, now()))

def history(session):
    with db_lock:
        rows = db.execute("SELECT role, text FROM messages WHERE session=? ORDER BY id DESC LIMIT ?", (session, HISTORY)).fetchall()
    msgs = [{"role": r, "content": t} for r, t in reversed(rows)]
    while msgs and msgs[0]["role"] != "user":  # the API wants the conversation to start with the visitor
        msgs.pop(0)
    return msgs

def visitor_count(session):
    with db_lock:
        return db.execute("SELECT COUNT(*) FROM messages WHERE session=? AND role='user'", (session,)).fetchone()[0]

def save_lead(session, lead):
    lead = {k: str(lead.get(k, "")).strip()[:300] for k in ("name", "contact", "need")}
    if not lead["name"] or not lead["contact"]:
        return "Not saved: ask the visitor for their name and an email or phone number first."
    with db_lock, db:
        if db.execute("SELECT 1 FROM leads WHERE session=? AND contact=?", (session, lead["contact"])).fetchone():
            return "Already saved earlier. Just confirm to the visitor."
        db.execute("INSERT INTO leads(session, name, contact, need, time) VALUES(?,?,?,?,?)",
                   (session, lead["name"], lead["contact"], lead["need"], now()))
    threading.Thread(target=notify, args=(lead,), daemon=True).start()  # don't make the visitor wait
    return "Saved. The team will reach out within one business day."


# ---- Notifications (email + Slack, both optional) ----
def notify(lead):
    text = f"New lead from the website chat\nName: {lead['name']}\nContact: {lead['contact']}\nNeed: {lead['need']}"
    if url := os.environ.get("SLACK_WEBHOOK_URL"):
        try:
            req = urllib.request.Request(url, json.dumps({"text": "🦷 " + text}).encode(), {"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15).close()
        except Exception as e:
            print("Slack error:", e, flush=True)
    if (host := os.environ.get("SMTP_HOST")) and (to := os.environ.get("NOTIFY_EMAIL")):
        try:
            msg = EmailMessage()
            msg["Subject"], msg["To"] = f"New lead: {lead['name']} ({lead['need'][:60]})", to
            msg["From"] = os.environ.get("SMTP_USER", to)
            msg.set_content(text)
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=20) as s:
                s.starttls()
                if os.environ.get("SMTP_USER"):
                    s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
                s.send_message(msg)
        except Exception as e:
            print("Email error:", e, flush=True)


# ---- Answers ----
def keyword_answer(question):
    """Fallback when AI is off: the knowledge paragraph sharing the most words with the question."""
    words = lambda s: {w for w in re.findall(r"[a-z0-9$]+", s.lower()) if len(w) > 2}
    q = words(question)
    paras = [p.strip() for p in re.split(r"\n(?=#|- )|\n\n", KNOWLEDGE) if len(p.strip()) > 30 and not p.startswith("# ")]
    best = max(paras, key=lambda p: len(q & words(p)), default="")
    if not q or not best or not q & words(best):
        return "I'm not sure about that. Please call us at (503) 555-0142 and the team will help."
    return re.sub(r"^#+ .*\n|^- ", "", best).strip()

def ai_answer(session):
    import anthropic
    client = anthropic.Anthropic()
    msgs = history(session)
    for _ in range(3):  # at most a couple of tool rounds per visitor message
        r = client.beta.messages.create(
            model=AI_MODEL, max_tokens=1024,
            output_config={"effort": "low"},  # short chat answers
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            cache_control={"type": "ephemeral"},  # the long knowledge prompt is reused on every message
            system=SYSTEM, tools=[LEAD_TOOL], messages=msgs,
        )
        if r.stop_reason == "tool_use":
            msgs.append({"role": "assistant", "content": r.content})
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id, "content": save_lead(session, b.input)}
                for b in r.content if b.type == "tool_use"]})
            continue
        if r.stop_reason == "refusal":
            return "Sorry, I can't help with that here. Please call us at (503) 555-0142."
        text = "".join(b.text for b in r.content if b.type == "text").strip()
        if text:
            return text
    return "Thanks! Our team will follow up with you shortly."

def reply(session, message):
    """Visitor message in -> assistant reply out. Never raises."""
    message = message.strip()[:MAX_MESSAGE]
    if not message:
        return "Please type a question 🙂"
    if visitor_count(session) >= MAX_PER_SESSION:
        return "We've chatted a lot! For anything else please call us at (503) 555-0142."
    add_message(session, "user", message)
    answer = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            answer = ai_answer(session)
        except Exception as e:  # out of credit, network: keep the chat useful
            print("AI error:", e, flush=True)
    answer = answer or keyword_answer(message)
    add_message(session, "assistant", answer)
    return answer


# ---- Owner dashboard ----
def dashboard():
    with db_lock:
        leads = db.execute("SELECT time, name, contact, need FROM leads ORDER BY id DESC LIMIT 100").fetchall()
        chats, msgs = db.execute("SELECT COUNT(DISTINCT session), COUNT(*) FROM messages WHERE role='user'").fetchone()
        recent = db.execute("SELECT time, text FROM messages WHERE role='user' ORDER BY id DESC LIMIT 30").fetchall()
    e = lambda s: html.escape(str(s))
    lead_rows = "".join(f"<tr><td>{e(t)}</td><td>{e(n)}</td><td>{e(c)}</td><td>{e(d)}</td></tr>" for t, n, c, d in leads) \
        or '<tr><td colspan="4">No leads yet.</td></tr>'
    q_rows = "".join(f"<li><span>{e(t)}</span> {e(q)}</li>" for t, q in recent) or "<li>No questions yet.</li>"
    rate = f"{len(leads) / chats:.0%}" if chats else "—"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chat dashboard</title><style>
:root{{--bg:#f5f7f6;--card:#fff;--ink:#17201c;--muted:#5f6b66;--line:#dde3e0;--accent:#1f7a5a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111614;--card:#1a211e;--ink:#e9efec;--muted:#9aa8a2;--line:#2c3632;--accent:#4cc495}}}}
body{{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--ink)}}main{{max-width:1000px;margin:0 auto;padding:32px 16px}}
h1{{margin:0 0 20px;font-size:24px}}h2{{font-size:17px;margin:28px 0 10px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}}.kpi b{{display:block;font-size:26px;color:var(--accent)}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:13px}}ul{{list-style:none;margin:0;padding:6px 0}}li{{padding:8px 14px;border-bottom:1px solid var(--line)}}
li span{{color:var(--muted);font-size:13px;margin-right:8px}}</style></head><body><main>
<h1>{e(BUSINESS)} · Chat dashboard</h1>
<div class="kpis"><div class="kpi"><b>{chats}</b>conversations</div><div class="kpi"><b>{msgs}</b>visitor messages</div>
<div class="kpi"><b>{len(leads)}</b>leads</div><div class="kpi"><b>{rate}</b>chat → lead</div></div>
<h2>Leads</h2><div class="box"><table><tr><th>Time</th><th>Name</th><th>Contact</th><th>Need</th></tr>{lead_rows}</table></div>
<h2>Latest visitor questions</h2><div class="box"><ul>{q_rows}</ul></div></main></body></html>"""

def admin_ok(auth_header):
    password = os.environ.get("ADMIN_PASSWORD")
    if not password or not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        return base64.b64decode(auth_header[6:]).decode().split(":", 1)[1] == password
    except Exception:
        return False


# ---- HTTP ----
ALLOWED = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, ctype="text/html; charset=utf-8", extra=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        origin = self.headers.get("Origin")
        if origin and (not ALLOWED or origin in ALLOWED):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):  # CORS preflight from sites that embed the widget
        self.send(204, b"", extra={"Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type"})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self.send(200, (ROOT / "demo.html").read_text(encoding="utf-8"))
        elif path == "/widget.js":
            js = (ROOT / "widget.js").read_text(encoding="utf-8").replace("__GREETING__", json.dumps(GREETING)).replace("__BUSINESS__", json.dumps(BUSINESS))
            self.send(200, js, "application/javascript; charset=utf-8", {"Cache-Control": "public, max-age=300"})
        elif path == "/admin":
            if not admin_ok(self.headers.get("Authorization")):
                return self.send(401, "Login required (set ADMIN_PASSWORD on the server).", extra={"WWW-Authenticate": 'Basic realm="dashboard"'})
            self.send(200, dashboard())
        else:
            self.send(404, "Not found")

    def do_POST(self):
        if self.path != "/api/chat":
            return self.send(404, "Not found")
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 8000)))
            session, message = str(body.get("session", "")), str(body.get("message", ""))
        except Exception:
            return self.send(400, json.dumps({"error": "bad request"}), "application/json")
        if not SESSION_RE.match(session):
            return self.send(400, json.dumps({"error": "bad session"}), "application/json")
        self.send(200, json.dumps({"reply": reply(session, message)}), "application/json")

    def log_message(self, fmt, *args):  # quieter log: skip static files
        if "/api/" in self.path or "/admin" in self.path:
            super().log_message(fmt, *args)


def self_test():
    global db
    db = init_db(sqlite3.connect(":memory:", check_same_thread=False))
    os.environ.pop("ANTHROPIC_API_KEY", None)
    for k in ("SLACK_WEBHOOK_URL", "SMTP_HOST"):
        os.environ.pop(k, None)
    s = "test-session-1"
    assert "Delta Dental" in reply(s, "Do you take Delta Dental insurance?")  # keyword fallback finds the right paragraph
    assert "$4,500" in reply(s, "how much is invisalign")
    assert "not sure" in reply(s, "zzz qqq")
    assert reply(s, "   ") == "Please type a question 🙂" and visitor_count(s) == 3
    assert [m["role"] for m in history(s)][:2] == ["user", "assistant"]
    assert "Not saved" in save_lead(s, {"name": "Ann"})
    assert save_lead(s, {"name": "Ann", "contact": "ann@example.com", "need": "Cleaning"}).startswith("Saved")
    assert "Already" in save_lead(s, {"name": "Ann", "contact": "ann@example.com", "need": "Cleaning"})
    for i in range(MAX_PER_SESSION):
        reply("flood-session", f"question {i}")
    assert "chatted a lot" in reply("flood-session", "one more")  # abuse cap
    os.environ["ADMIN_PASSWORD"] = "pw"
    good = "Basic " + base64.b64encode(b"owner:pw").decode()
    assert admin_ok(good) and not admin_ok("Basic " + base64.b64encode(b"owner:no").decode()) and not admin_ok(None)
    with db_lock, db:
        db.execute("INSERT INTO leads(session,name,contact,need,time) VALUES('x','<b>Eve</b>','e@x.com','Implants','t')")
    page = dashboard()
    assert "&lt;b&gt;Eve" in page and "<b>Eve" not in page and "ann@example.com" in page  # escaped output
    assert SESSION_RE.match("abcDEF12_-") and not SESSION_RE.match("../etc") and not SESSION_RE.match("short")
    print("All tests passed ✅")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        self_test()
    else:
        port = int(os.environ.get("PORT", "8080"))
        ai = "on" if os.environ.get("ANTHROPIC_API_KEY") else "off (keyword answers from the knowledge base)"
        print(f"Demo site: http://127.0.0.1:{port}   Dashboard: http://127.0.0.1:{port}/admin   AI: {ai}", flush=True)
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
