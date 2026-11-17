# AI Lead Handler: Website Form → AI Scoring → Email / Slack

Stop losing leads in your inbox. Every website enquiry is scored by AI as 🔥 hot, 🙂 warm or 🧊 cold, summarised in one line, and lands in your **email, Slack or Telegram** with a **personal reply already drafted**. In email, just hit Reply: it goes straight to the client.

## How it works
1. A visitor fills in the form on your site (name, email or phone, budget, project).
2. AI reads the request against your business profile: what you do, typical prices, what you don't do.
3. You get an alert in seconds (email, Slack and/or Telegram):
   ```
   🔥 New HOT lead
   Master bathroom remodel in South Austin, $20k–$50k, wants to start in January

   👤 Sarah Miller
   ✉️ sarah@example.com
   💰 $20k–$50k

   ✍️ Suggested reply:
   Hi Sarah, thanks for reaching out! A walk-in shower and double vanity sound like a great upgrade...
   ```
4. Every lead is logged to `leads.csv` (opens in Excel / Google Sheets).

## Reliability
- **A lead is never lost**: if AI or a notification channel is down, the lead is still saved, scored with simple budget rules and given a template reply.
- Form validation (name, message, email or phone), size limits, no HTML injection.
- Out-of-scope requests (e.g. roofing for a renovation company) are scored cold and answered politely.

## Run
```bash
ANTHROPIC_API_KEY=... SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... NOTIFY_EMAIL=... python3 app.py
# Slack: SLACK_WEBHOOK_URL=...   Telegram: BOT_TOKEN=... ADMIN_ID=...
# open http://127.0.0.1:8000
python3 app.py test   # self-tests
```
`ANTHROPIC_API_KEY` is optional: without it scoring is rule-based. Edit `BUSINESS`, `ABOUT` and `BUDGETS` at the top of `app.py` for each client. The form can also be embedded into an existing site (WordPress, Webflow, Tilda) by pointing it at `/lead`.

Tech: Python (stdlib HTTP server), Claude API with structured outputs, SMTP email, Slack webhooks, Telegram Bot API, CSV.
