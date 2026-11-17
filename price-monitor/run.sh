#!/bin/sh
# Runs the price check and sends the report to Telegram (same bot and chat as booking-bot/.env)
cd "$(dirname "$0")"
set -a; . ../booking-bot/.env; set +a
exec python3 monitor.py "$@"
