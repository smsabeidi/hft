#!/bin/sh
# Deploy the MQL5 layer into macOS MetaTrader 5 (MetaQuotes Wine wrapper)
# and compile headlessly. Verified working 2026-07-07: the wrapper's own
# wine64 + metaeditor64.exe CLI compile RELATIVE paths from the install dir
# (absolute C:\ paths silently no-op). Zero-warnings bar enforced by eye:
# read the printed Result line.
#
# Usage: scripts/mt5_deploy.sh [ExpertName ...]   (default: InfraShadow)
#
# Note: the Mac terminal is fine for demo/infra bring-up; 24/7 operation
# still wants the Windows VPS — this laptop sleeps.
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5"
MT5="$PREFIX/drive_c/Program Files/MetaTrader 5"
WINE="/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64"

[ -d "$MT5/MQL5" ] || { echo "MT5 (Mac wrapper) not found at $MT5"; exit 1; }

cp "$REPO"/mql5/Include/*.mqh "$MT5/MQL5/Include/"
echo "includes deployed: $(ls "$REPO"/mql5/Include/*.mqh | wc -l | tr -d ' ') files"

for name in "${@:-InfraShadow}"; do
  cp "$REPO/mql5/Experts/$name.mq5" "$MT5/MQL5/Experts/"
  cd "$MT5"
  WINEPREFIX="$PREFIX" "$WINE" ./metaeditor64.exe \
    /compile:"MQL5\\Experts\\$name.mq5" /log:"MQL5\\Experts\\compile.log" \
    2>/dev/null || true
  iconv -f UTF-16LE -t UTF-8 "MQL5/Experts/compile.log" 2>/dev/null | tail -1
  ls -la "MQL5/Experts/$name.ex5" 2>/dev/null || echo "$name: NO .ex5 — compile failed"
  cd "$REPO"
done
