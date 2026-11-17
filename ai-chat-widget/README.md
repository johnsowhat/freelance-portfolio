# AI Website Chat that Answers from Your Own Documents

An AI assistant for any website (WordPress, Shopify, Webflow, Wix, plain HTML) that answers visitors' questions **from your company's own information**, turns interested visitors into leads, and sends them to you by **email and Slack**.

Demo: a fictional dental clinic, *Evergreen Family Dental*.

```html
<!-- the whole installation on the client's site -->
<script src="https://your-chat-server.com/widget.js" defer></script>
```

## What visitors get
- 💬 A chat bubble in the corner that answers instantly, 24/7, in their language
- Accurate answers about prices, insurance, hours, services, taken **only** from your documents. No made-up prices or promises; unknown questions go to the team.
- Booking requests captured right in the chat: name, contact, what they need

## What the business owner gets
- 📩 **Every lead by email and Slack** within seconds
- 📊 A password-protected **dashboard** (`/admin`): leads, conversation count, chat→lead conversion, the latest visitor questions (great for spotting what to add to the FAQ)
- ✏️ Easy updates: edit the Markdown files in `knowledge/` (FAQ, prices, policies) and restart. No retraining.

## Built for production
- Widget lives in a Shadow DOM: it can't break the host site's styles, and the site can't break it
- Works on phones, supports dark mode, keyboard and screen-reader friendly
- Abuse protection: message length limit, per-conversation message cap (keeps the AI bill predictable)
- CORS allow-list so only your sites can embed the chat (`ALLOWED_ORIGINS`)
- Never goes silent: if the AI service is unavailable, it falls back to the best-matching answer from your documents
- Prompt caching on the knowledge base keeps per-message cost low
- No HTML injection: all text is escaped in the widget and the dashboard

## Run
```bash
pip install anthropic
ANTHROPIC_API_KEY=... ADMIN_PASSWORD=... python3 server.py
# demo site:  http://127.0.0.1:8080      dashboard: http://127.0.0.1:8080/admin
python3 server.py test    # self-tests
```
Optional: `SLACK_WEBHOOK_URL` (Slack incoming webhook), `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `NOTIFY_EMAIL` (email alerts), `ALLOWED_ORIGINS`, `PORT`.

Tech: Python (stdlib HTTP server, SQLite), Claude API with tool use, vanilla JavaScript widget, Slack webhooks, SMTP.
