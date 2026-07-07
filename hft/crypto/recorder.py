"""Exchange-native market data recorder — phase-3 component 1.

Subscribes to OKX public websocket channels (books5 + trades), stamps local
receive time on every message, and rotates parquet files. "The dataset is the
asset": this recorder's output feeds cost models and the microstructure
families (cross-exchange dislocation, passive MM) that funding capture's
successor rounds need.

Operational notes:
- Latency stamps from a laptop are indicative only (~100ms+); the real
  deployment target is a VM in the exchange's cloud region (1-5ms).
- OKX idles out silent connections: we send 'ping' when nothing arrived for
  20s and expect 'pong'. Reconnect with exponential backoff, resubscribe.
- Files rotate every rotate_minutes to data/crypto/{instId}/{channel}/.
  A max_minutes cap makes unattended runs self-terminating — a recorder
  someone forgot about should stop itself, not fill a disk.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from pathlib import Path

import pandas as pd

OKX_PUBLIC_WS = "wss://ws.okx.com:8443/ws/v5/public"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def parse_books5(msg: dict, recv_ts_ms: float) -> dict | None:
    """Flatten one books5 update to a row. Returns None for non-data messages."""
    data = msg.get("data")
    if not data:
        return None
    d = data[0]
    row = {
        "ts": int(d["ts"]),
        "recv_ts": recv_ts_ms,
        "seq": int(d.get("seqId", -1)),
    }
    for i in range(5):
        for side, key in (("bid", "bids"), ("ask", "asks")):
            levels = d.get(key, [])
            px, sz = (float(levels[i][0]), float(levels[i][1])) if i < len(levels) else (0.0, 0.0)
            row[f"{side}{i + 1}_px"] = px
            row[f"{side}{i + 1}_sz"] = sz
    return row


def parse_trade(msg: dict, recv_ts_ms: float) -> list[dict]:
    """One trades message can carry several fills."""
    out = []
    for d in msg.get("data") or []:
        out.append(
            {
                "ts": int(d["ts"]),
                "recv_ts": recv_ts_ms,
                "px": float(d["px"]),
                "sz": float(d["sz"]),
                "side": 1 if d.get("side") == "buy" else -1,
                "trade_id": str(d.get("tradeId", "")),
            }
        )
    return out


class Recorder:
    def __init__(
        self,
        inst_ids: list[str],
        out_root: Path,
        rotate_minutes: int = 15,
        max_minutes: int | None = 120,
    ):
        self.inst_ids = inst_ids
        self.out_root = Path(out_root)
        self.rotate_minutes = rotate_minutes
        self.max_minutes = max_minutes
        self.buffers: dict[tuple[str, str], list[dict]] = {}
        self.counts: dict[str, int] = {"books5": 0, "trades": 0}
        self._last_rotate = time.time()
        self._start = time.time()

    def _flush(self) -> list[Path]:
        written = []
        stamp = pd.Timestamp.utcnow().strftime("%Y-%m-%d_%H%M%S")
        for (inst, channel), rows in self.buffers.items():
            if not rows:
                continue
            path = self.out_root / inst / channel / f"{stamp}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                pd.DataFrame(rows).to_parquet(path, index=False, compression="zstd")
            except (ImportError, ValueError):  # pyarrow built without zstd
                pd.DataFrame(rows).to_parquet(path, index=False)
            written.append(path)
        self.buffers = {}
        self._last_rotate = time.time()
        return written

    def _on_message(self, raw: str) -> None:
        recv_ms = time.time() * 1000
        if raw == "pong":
            return
        msg = json.loads(raw)
        arg = msg.get("arg") or {}
        channel, inst = arg.get("channel"), arg.get("instId")
        if channel == "books5":
            row = parse_books5(msg, recv_ms)
            if row is not None:
                self.buffers.setdefault((inst, "books5"), []).append(row)
                self.counts["books5"] += 1
        elif channel == "trades":
            rows = parse_trade(msg, recv_ms)
            if rows:
                self.buffers.setdefault((inst, "trades"), []).extend(rows)
                self.counts["trades"] += len(rows)

    async def run(self) -> None:
        import websockets

        subs = [
            {"channel": ch, "instId": inst}
            for inst in self.inst_ids
            for ch in ("books5", "trades")
        ]
        backoff = 1.0
        while True:
            if self.max_minutes and (time.time() - self._start) / 60 >= self.max_minutes:
                break
            try:
                async with websockets.connect(
                    OKX_PUBLIC_WS, ssl=_ssl_context(), open_timeout=20
                ) as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": subs}))
                    backoff = 1.0
                    while True:
                        if self.max_minutes and (time.time() - self._start) / 60 >= self.max_minutes:
                            raise KeyboardInterrupt
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=20)
                            self._on_message(raw)
                        except asyncio.TimeoutError:
                            await ws.send("ping")
                        if time.time() - self._last_rotate >= self.rotate_minutes * 60:
                            for p in self._flush():
                                print(f"wrote {p}")
            except KeyboardInterrupt:
                break
            except Exception as e:  # reconnect path: log, back off, resubscribe
                print(f"reconnect after {type(e).__name__}: {str(e)[:80]} (backoff {backoff:.0f}s)")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
        for p in self._flush():
            print(f"wrote {p}")
        print(f"done: {self.counts['books5']} book updates, {self.counts['trades']} trades")
