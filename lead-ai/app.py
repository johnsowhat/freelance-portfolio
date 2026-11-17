"""AI lead handler: website form -> AI scores the lead and drafts a reply -> Telegram alert + CSV log.

Run:   BOT_TOKEN=... ADMIN_ID=... ANTHROPIC_API_KEY=... python3 app.py   then open http://127.0.0.1:8000
Test:  python3 app.py test
Without ANTHROPIC_API_KEY it still works, with simple rule-based scoring and a template reply.
"""
import csv, html, json, os, sys, urllib.parse, urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---- Business settings: edit per client ----
BUSINESS = "Brightline Renovation"
ABOUT = """Home renovation company in Austin, TX. Kitchens, bathrooms, flooring, painting.
Typical projects: bathroom $8k–25k, kitchen $20k–60k, painting from $2k. Free on-site estimate within 3 days.
We don't do roofing, pools or commercial buildings."""
BUDGETS = ["Under $5k", "$5k–$20k", "$20k–$50k", "$50k+", "Not sure yet"]

TOKEN, ADMIN_ID = os.environ.get("BOT_TOKEN", ""), os.environ.get("ADMIN_ID")
AI_MODEL = os.environ.get("AI_MODEL", "claude-opus-5-5")
LEADS = Path(__file__).parent / "leads.csv"
FIELDS = ["time", "name", "email", "phone", "budget", "message", "score", "summary", "reply"]
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["score", "summary", "reply"],
          "properties": {"score": {"type": "string", "enum": ["hot", "warm", "cold"]},
                         "summary": {"type": "string"}, "reply": {"type": "string"}}}


# ---- Lead logic ----
def validate(form):
    """Clean form fields -> (lead, None) or (None, error message)."""
    get = lambda k, n: form.get(k, "").strip()[:n]
    lead = {"name": get("name", 100), "email": get("email", 200), "phone": get("phone", 50),
            "budget": get("budget", 30), "message": get("message", 2000)}
    if not lead["name"] or not lead["message"]:
        return None, "Please fill in your name and a short description of the project."
    if not lead["email"] and not lead["phone"]:
        return None, "Please leave an email or a phone number so we can reply."
    if lead["email"] and ("@" not in lead["email"] or "." not in lead["email"].split("@")[-1]):
        return None, "That email address doesn't look right."
    if lead["budget"] not in BUDGETS:
        lead["budget"] = "Not sure yet"
    return lead, None

def rule_qualify(lead):
    """Fallback when AI is off: budget decides the score, reply is a template."""
    score = {"$20k–$50k": "hot", "$50k+": "hot", "$5k–$20k": "warm"}.get(lead["budget"], "cold")
    reply = (f"Hi {lead['name'].split()[0]},\n\nThank you for contacting {BUSINESS}! We've received your request "
             "and will get back to you within one business day to schedule a free on-site estimate.\n\nBest regards,\n" + BUSINESS)
    return {"score": score, "summary": lead["message"][:150], "reply": reply}

def ai_qualify(lead):
    """Claude scores the lead and drafts a personal reply. Falls back to rules on any problem."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return rule_qualify(lead)
    try:
        import anthropic
        r = anthropic.Anthropic().beta.messages.create(
            model=AI_MODEL, max_tokens=2048,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=(f"You qualify incoming website leads for {BUSINESS}.\nAbout the business:\n{ABOUT}\n\n"
                    "score: hot = clear project we do, decent budget, ready soon; warm = real interest but vague or small; "
                    "cold = spam, out of scope or no real project.\n"
                    "summary: one line for the owner: what, where, budget, urgency.\n"
                    "reply: a short, warm email to the client in their language, signed by the team. Mention a free estimate "
                    "if the project fits, or politely say we don't do it. Never promise prices or dates."),
            messages=[{"role": "user", "content": json.dumps(lead, ensure_ascii=False)}],
        )
        if r.stop_reason != "end_turn":
            return rule_qualify(lead)
        out = json.loads(next(b.text for b in r.content if b.type == "text"))
        return out if out.get("score") in ("hot", "warm", "cold") else rule_qualify(lead)
    except Exception as e:  # no credit, network, bad key: the lead is never lost
        print("AI error:", e, flush=True)
        return rule_qualify(lead)

def save(row):
    new = not LEADS.exists()
    with open(LEADS, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)

def notify(row):
    if not (TOKEN and ADMIN_ID):
        return
    icon = {"hot": "🔥", "warm": "🙂", "cold": "🧊"}[row["score"]]
    text = (f"{icon} New {row['score'].upper()} lead\n{row['summary']}\n\n"
            f"👤 {row['name']}\n✉️ {row['email'] or '—'}\n📞 {row['phone'] or '—'}\n💰 {row['budget']}\n\n"
            f"💬 {row['message'][:800]}\n\n✍️ Suggested reply:\n{row['reply'][:1500]}")
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                                 json.dumps({"chat_id": ADMIN_ID, "text": text[:4000]}).encode(),
                                 {"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20).close()
    except Exception as e:  # lead is already saved in the CSV
        print("Telegram error:", e, flush=True)

def handle_lead(form):
    lead, error = validate(form)
    if error:
        return None, error
    row = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), **lead, **ai_qualify(lead)}
    save(row)
    notify(row)
    return row, None


# ---- Web page ----
PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{business}: free estimate</title>
<style>
:root{{--bg:#f6f4ef;--card:#fff;--ink:#1d1d1b;--muted:#6b6860;--accent:#c4572b;--line:#e3dfd6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161512;--card:#211f1b;--ink:#f1eee7;--muted:#a19d93;--accent:#e2774a;--line:#36332d}}}}
*{{box-sizing:border-box}}body{{margin:0;font:16px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--ink)}}
main{{max-width:560px;margin:0 auto;padding:40px 16px}}h1{{font-size:28px;margin:0 0 6px}}p.lead{{color:var(--muted);margin:0 0 24px}}
form,.msg{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px}}
label{{display:block;font-weight:600;font-size:14px;margin:14px 0 6px}}label:first-child{{margin-top:0}}
input,select,textarea{{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:9px;font:inherit;background:var(--bg);color:var(--ink)}}
textarea{{min-height:110px;resize:vertical}}.row{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media (max-width:480px){{.row{{grid-template-columns:1fr}}}}
button{{margin-top:20px;width:100%;padding:13px;border:0;border-radius:9px;background:var(--accent);color:#fff;font:600 16px system-ui;cursor:pointer}}
.err{{color:var(--accent);font-weight:600;margin:0 0 12px}}small{{color:var(--muted)}}
</style></head><body><main>{body}</main></body></html>"""

FORM = """<h1>{business}</h1><p class="lead">Tell us about your project and get a free on-site estimate within 3 days.</p>
<form method="post" action="/lead">{error}
<label for="name">Your name *</label><input id="name" name="name" required maxlength="100" value="{name}">
<div class="row"><div><label for="email">Email</label><input id="email" name="email" type="email" maxlength="200" value="{email}"></div>
<div><label for="phone">Phone</label><input id="phone" name="phone" maxlength="50" value="{phone}"></div></div>
<label for="budget">Budget</label><select id="budget" name="budget">{options}</select>
<label for="message">What would you like to renovate? *</label>
<textarea id="message" name="message" required maxlength="2000">{message}</textarea>
<button type="submit">Get my free estimate</button><p><small>We reply within one business day.</small></p></form>"""

THANKS = """<div class="msg"><h1>Thank you, {name}!</h1><p class="lead">We've got your request and will contact you within one business day.</p>
<p><a href="/">← Back</a></p></div>"""

def render_form(values=None, error=""):
    v = {k: html.escape((values or {}).get(k, "")) for k in ("name", "email", "phone", "message", "budget")}
    options = "".join(f'<option{" selected" if b == v["budget"] else ""}>{html.escape(b)}</option>' for b in BUDGETS)
    body = FORM.format(business=html.escape(BUSINESS), options=options,
                       error=f'<p class="err" role="alert">{html.escape(error)}</p>' if error else "", **{k: v[k] for k in ("name", "email", "phone", "message")})
    return PAGE.format(business=html.escape(BUSINESS), body=body)

class Handler(BaseHTTPRequestHandler):
    def send_page(self, page, status=200):
        data = page.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.send_page(render_form()) if self.path in ("/", "/index.html") else self.send_page("Not found", 404)

    def do_POST(self):
        if self.path != "/lead":
            return self.send_page("Not found", 404)
        length = min(int(self.headers.get("Content-Length") or 0), 20_000)  # cap body size
        form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace")).items()}
        row, error = handle_lead(form)
        if error:
            return self.send_page(render_form(form, error), 400)
        self.send_page(PAGE.format(business=html.escape(BUSINESS), body=THANKS.format(name=html.escape(row["name"].split()[0]))))
        print(f"lead saved: {row['score']} · {row['name']}", flush=True)


def self_test():
    global LEADS
    import tempfile
    LEADS = Path(tempfile.mkdtemp()) / "leads.csv"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    globals()["TOKEN"] = ""  # no Telegram during tests
    assert validate({"name": "Ann"})[1]  # message missing
    assert "email or a phone" in validate({"name": "Ann", "message": "Kitchen"})[1]
    assert "doesn't look right" in validate({"name": "Ann", "message": "x", "email": "ann@"})[1]
    lead, err = validate({"name": " Ann Lee ", "message": "Full kitchen remodel", "email": "ann@mail.com", "budget": "hacked"})
    assert not err and lead["name"] == "Ann Lee" and lead["budget"] == "Not sure yet"
    assert rule_qualify({**lead, "budget": "$50k+"})["score"] == "hot"
    assert rule_qualify(lead)["score"] == "cold" and "Hi Ann" in rule_qualify(lead)["reply"]
    row, err = handle_lead({"name": "Bob", "phone": "+1 512 555 0101", "message": "Bathroom", "budget": "$5k–$20k"})
    assert not err and row["score"] == "warm" and [r["name"] for r in csv.DictReader(open(LEADS))] == ["Bob"]
    page = render_form({"name": "<script>x</script>"}, "oops")
    assert "<script>x" not in page and "&lt;script&gt;" in page and "oops" in page  # no HTML injection
    print("All tests passed ✅")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        self_test()
    else:
        port = int(os.environ.get("PORT", "8000"))
        print(f"Open http://127.0.0.1:{port}  (AI {'on' if os.environ.get('ANTHROPIC_API_KEY') else 'off: rule-based scoring'})", flush=True)
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
