from __future__ import annotations

from pathlib import Path

import pandas as pd

from hft.crypto.recorder import Recorder, parse_books5, parse_trade

BOOKS5_MSG = {
    "arg": {"channel": "books5", "instId": "BTC-USDT-SWAP"},
    "data": [
        {
            "asks": [["63500.0", "2.5", "0", "4"], ["63500.1", "1.0", "0", "2"]],
            "bids": [["63499.9", "3.1", "0", "5"]],
            "ts": "1751848000123",
            "seqId": 987654,
        }
    ],
}

TRADES_MSG = {
    "arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"},
    "data": [
        {"instId": "BTC-USDT-SWAP", "tradeId": "t1", "px": "63500.0", "sz": "0.5",
         "side": "buy", "ts": "1751848000200"},
        {"instId": "BTC-USDT-SWAP", "tradeId": "t2", "px": "63499.9", "sz": "0.2",
         "side": "sell", "ts": "1751848000201"},
    ],
}


def test_parse_books5_flattens_and_pads():
    row = parse_books5(BOOKS5_MSG, recv_ts_ms=1751848000300.0)
    assert row["ts"] == 1751848000123
    assert row["seq"] == 987654
    assert row["bid1_px"] == 63499.9 and row["bid1_sz"] == 3.1
    assert row["ask1_px"] == 63500.0 and row["ask2_px"] == 63500.1
    # missing depth levels pad with zeros, never crash
    assert row["bid2_px"] == 0.0 and row["ask5_sz"] == 0.0


def test_parse_books5_ignores_handshakes():
    assert parse_books5({"event": "subscribe"}, 0.0) is None


def test_parse_trades_multiple_fills_and_sides():
    rows = parse_trade(TRADES_MSG, recv_ts_ms=1751848000300.0)
    assert len(rows) == 2
    assert rows[0]["side"] == 1 and rows[1]["side"] == -1
    assert rows[0]["px"] == 63500.0
    assert rows[1]["trade_id"] == "t2"


def test_recorder_buffers_and_flushes(tmp_path):
    import json

    rec = Recorder(["BTC-USDT-SWAP"], tmp_path, rotate_minutes=15, max_minutes=None)
    rec._on_message(json.dumps(BOOKS5_MSG))
    rec._on_message(json.dumps(TRADES_MSG))
    rec._on_message("pong")  # heartbeat replies must be ignored
    assert rec.counts == {"books5": 1, "trades": 2}
    written = rec._flush()
    assert len(written) == 2
    books = pd.read_parquet([p for p in written if "books5" in str(p)][0])
    assert len(books) == 1 and books["bid1_px"].iloc[0] == 63499.9
    trades = pd.read_parquet([p for p in written if "trades" in str(p)][0])
    assert len(trades) == 2
    # a second flush with empty buffers writes nothing
    assert rec._flush() == []