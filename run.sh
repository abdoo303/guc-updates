#!/bin/bash
# Runs the GUC email parser once per calendar day.
# Triggered on every login by launchd — skips if already ran today.

DIR=/Users/macbook/projects/guc-parser
PYTHON="$DIR/.venv/bin/python3"
LAST_RUN_FILE="$DIR/json/last_run.json"
TODAY=$(date +%Y-%m-%d)

# Check if already ran today (skip if --now flag is passed)
if [ "$1" != "--now" ] && [ -f "$LAST_RUN_FILE" ]; then
    LAST=$("$PYTHON" -c "import json; d=json.load(open('$LAST_RUN_FILE')); print(d.get('date',''))")
    if [ "$LAST" = "$TODAY" ]; then
        echo "[$TODAY] Already ran today — skipping. Use --now to force."
        exit 0
    fi
fi

echo "[$TODAY] Starting GUC email parser..."
cd "$DIR"

if "$PYTHON" main.py; then
    "$PYTHON" -c "import json; json.dump({'date': '$TODAY'}, open('$LAST_RUN_FILE', 'w'))"
    echo "[$TODAY] Done. Last run saved."
else
    echo "[$TODAY] Failed — will retry on next run."
fi
