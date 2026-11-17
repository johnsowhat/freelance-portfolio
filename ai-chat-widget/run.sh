#!/bin/sh
# Starts the chat server with the keys from booking-bot/.env (ANTHROPIC_API_KEY, ADMIN_PASSWORD, optional SLACK/SMTP)
cd "$(dirname "$0")"
set -a; . ../booking-bot/.env; set +a
exec ../booking-bot/.venv/bin/python -u server.py "$@"
