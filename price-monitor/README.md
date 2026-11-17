# Competitor Price Monitor with Daily Email / Slack Reports

Every day it scrapes a shop's full catalogue, compares it with the previous day and sends you a short report plus a CSV file you can open in Excel or Google Sheets.

## The report
```
📊 Price report · Nov 17, 2026
1000 products · average £35.07 · 1000 in stock
Compared with 2026-11-16

📉 Price drops (3):
• Needful Things: £59.39 → £47.51 (-20%)
📈 Price rises (9):
• The Firm: £36.45 → £45.56 (+25%)
📦 Stock changes (3):
• Lord of the Flies: back in stock
🆕 New products (3):
• Outliers: The Story of Success: £14.16
```
(Example output. The demo shop never changes its prices, so `python3 monitor.py demo` creates a sample "yesterday" to show every section.)

## Features
- Walks through every catalogue page politely (pauses between requests)
- Saves a dated CSV snapshot per day: title, price, rating, stock, link
- Detects price changes with %, stock changes, new and removed products
- Sends the report by **email (CSV attached)**, **Slack** and/or **Telegram**, any combination; one broken channel never blocks the others
- Fails loudly if the site layout changes, instead of sending an empty report

## Run
```bash
SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... NOTIFY_EMAIL=... python3 monitor.py
# or SLACK_WEBHOOK_URL=...  or BOT_TOKEN=... ADMIN_ID=...  (nothing set: it just prints the report)
python3 monitor.py test                          # self-tests
```
Daily at 9:00 with cron: `0 9 * * * /path/to/price-monitor/run.sh`

Demo target: [books.toscrape.com](https://books.toscrape.com), a public sandbox shop made for scraping practice. For a real shop, change `BASE` and the `ITEM` pattern at the top of `monitor.py`.

Tech: Python standard library only, no dependencies.
