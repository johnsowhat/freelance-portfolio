# Automation & AI Bots Portfolio

Small, production-minded tools for local businesses and online shops: Telegram bots, AI assistants, web scraping and daily reports.

| Project | What it does | Stack |
|---|---|---|
| [AI Website Chat](ai-chat-widget/) | A chat bubble for any website (one line of code) that answers visitors from the company's own documents, captures leads and sends them by email and Slack, with an owner dashboard. | Python, Claude API (tool use), JavaScript, Slack, SMTP |
| [AI Booking Bot](booking-bot/) | Clients book appointments in Telegram, get reminders, and ask questions answered by AI 24/7. The owner gets notifications and manages the schedule from Telegram. | Python, Telegram Bot API, Claude API, SQLite |
| [AI Lead Handler](lead-ai/) | Website form where AI scores every lead hot/warm/cold, summarises it and drafts a personal reply, then sends it all to the owner's Telegram. No lead is ever lost. | Python, Claude API, Telegram Bot API |
| [Competitor Price Monitor](price-monitor/) | Scrapes a shop's whole catalogue every day, compares it with yesterday and sends a Telegram report with price drops, rises, stock changes and an Excel-ready CSV. | Python, web scraping, Telegram Bot API |

Both projects come with self-tests (`python3 <file> test`) and need no paid services to try out.

**Need something like this for your business?** Each project is customised per client: your services, your competitor sites, your language, your schedule.
