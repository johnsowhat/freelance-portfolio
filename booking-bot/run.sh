#!/bin/sh
# Starts the bot with the keys from .env
cd "$(dirname "$0")"
set -a; . ./.env; set +a
exec .venv/bin/python -u bot.py
