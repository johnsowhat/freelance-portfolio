#!/bin/sh
# Starts the lead form with the keys from booking-bot/.env (same Telegram bot and chat)
cd "$(dirname "$0")"
set -a; . ../booking-bot/.env; set +a
exec ../booking-bot/.venv/bin/python -u app.py "$@"
