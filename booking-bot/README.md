# AI Booking Bot for Salons & Clinics (Telegram)

A Telegram receptionist for appointment-based businesses: beauty salons, barbershops, clinics, tutors, fitness trainers.

**Live demo:** [@BookEasyDemo_Bot](https://t.me/BookEasyDemo_Bot) (Glow Beauty Studio, a fictional salon)

## For clients
- 📅 Book in 4 taps: service → day → free time → name & phone
- 🚫 No double bookings, past hours and days off hidden automatically
- ⏰ Automatic reminders **24 h and 2 h before** the visit, with a one-tap cancel button. Fewer no-shows, more revenue.
- 🗂 "My bookings" with cancellation
- 🤖 **AI answers questions 24/7** in the client's language ("Do you do French manicure?", "Where is parking?"), using only the facts the owner provides, never invented ones

## For the owner
- 🔔 Instant notification on every new booking and cancellation
- `/today`, `/tomorrow`: the schedule with client names and phones
- `/block 2026-11-20 14:00 15:00` or a whole day off; `/unblock` to reopen
- `/cancel 12`: cancel a booking and the client is told automatically

## Setup
1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Create `.env` next to `bot.py`:
   ```
   BOT_TOKEN=...
   ADMIN_ID=...            # owner's Telegram user id
   ANTHROPIC_API_KEY=...   # optional: turns on AI answers
   ```
3. ```bash
   python3 -m venv .venv && .venv/bin/pip install anthropic
   ./run.sh
   ```

Customise the business name, services, prices, opening hours and FAQ text at the top of `bot.py`.

Tests: `python3 bot.py test`

Tech: Python (stdlib + Anthropic SDK), Telegram Bot API, SQLite, Claude API.
