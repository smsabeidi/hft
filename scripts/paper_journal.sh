#!/bin/sh
# Daily one-line journal of the paper books + promotion gate verdict.
# Runs from the system crontab; no Claude session required.
cd "$(dirname "$0")/.." || exit 1
mkdir -p reports
{
  printf '%s ' "$(date -u +%Y-%m-%dT%H:%MZ)"
  /usr/local/bin/python3 scripts/paper_status.py 2>&1 | tail -3 | tr '\n' ' '
  printf '\n'
} >> reports/paper_journal.md
