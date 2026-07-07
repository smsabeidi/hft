#!/bin/sh
# One-shot bootstrap for the M3 research VM (Ubuntu 22/24, ideally Alibaba
# Cloud Hong Kong — OKX's own region; laptop baseline was 126ms p50, the
# in-region target is 1-5ms).
#
# From the Mac:
#   scp -r ~/Documents/HFT ubuntu@<VM-IP>:~/HFT
#   ssh ubuntu@<VM-IP> 'cd HFT && sh scripts/vm_bootstrap.sh'
#
# What it does: UTC timezone, python venv + deps, self-healing recorder
# cron (15-min supervisor, same design as the Mac), paper-engine cron
# (30-min, both instruments), starts recording immediately, then prints
# the first in-region latency report. Idempotent: safe to re-run.
set -e
cd "$(dirname "$0")/.."
REPO="$(pwd)"
VENV="$HOME/.venv-hft"
PY="$VENV/bin/python"

sudo timedatectl set-timezone UTC || true
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip

[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet pandas numpy scipy pyarrow websockets certifi

mkdir -p "$REPO/data/crypto" "$REPO/data/paper"

# cron: recorder supervisor (15m, inline pgrep guard — no Mac paths),
# paper engine (30m, both books), daily journal
( crontab -l 2>/dev/null | grep -v "record_crypto.py" | grep -v "paper_funding.py" | grep -v "paper_journal" ;
  echo "*/15 * * * * pgrep -f record_crypto.py >/dev/null || cd $REPO && $PY scripts/record_crypto.py --minutes 118 >> data/crypto/recorder.log 2>&1" ;
  echo "*/30 * * * * cd $REPO && $PY scripts/paper_funding.py --once --inst BTC-USDT-SWAP >> data/paper/cron.log 2>&1; $PY scripts/paper_funding.py --once --inst ETH-USDT-SWAP >> data/paper/cron.log 2>&1" ;
  echo "13 10 * * * cd $REPO && $PY scripts/paper_status.py >> reports/paper_journal.md 2>&1"
) | crontab -

# start recording NOW rather than waiting for the first cron slot
pgrep -f record_crypto.py >/dev/null || \
  nohup "$PY" scripts/record_crypto.py --minutes 118 >> data/crypto/recorder.log 2>&1 &

echo "bootstrap complete — recorder starting. First latency numbers in ~60s:"
sleep 60
"$PY" scripts/latency_report.py || echo "(latency report needs a few minutes of data — rerun: $PY scripts/latency_report.py)"
echo ""
echo "next: compare p50 against the laptop's 126ms baseline"
echo "(reports/optimization_pass.md section 3). The C5 data floor now"
echo "accrues 24/7: scripts/coverage_report.py shows the countdown."
