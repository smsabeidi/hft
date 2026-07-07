#!/bin/sh
# Self-healing recorder supervisor — cron runs this every 15 minutes.
# The laptop-sleep failure mode (2026-07-07): processes suspend mid-run and
# fixed 2h cron slots are silently skipped while asleep, so recovery after a
# wake could take up to 2h. This wrapper bounds recovery at 15 minutes: if a
# recorder is already running, do nothing; otherwise start a self-terminating
# run. The disk guard inside record_crypto.py still applies.
cd "$(dirname "$0")/.." || exit 1
pgrep -f "scripts/record_crypto.py" >/dev/null && exit 0
exec /usr/local/bin/python3 scripts/record_crypto.py --minutes 118 >> data/crypto/recorder.log 2>&1
