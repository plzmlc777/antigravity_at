"""
Binance Futures Liquidation Collector
- Subscribes to !forceOrder@arr (all market liquidations)
- Appends each event as JSONL to data/liquidations_YYYY-MM-DD.jsonl
- Auto-reconnects with exponential backoff
- Designed to run as a long-lived PM2 service

Stream payload schema (from Binance Futures docs):
{
  "e": "forceOrder",
  "E": 1568014460893,        // event time (ms)
  "o": {
    "s": "BTCUSDT",          // symbol
    "S": "SELL",             // side: SELL = long liquidation, BUY = short liquidation
    "o": "LIMIT",            // order type
    "f": "IOC",              // time in force
    "q": "0.014",            // original qty
    "p": "9910",             // price (what trigger filled at, usually mark proximity)
    "ap": "9910.5",          // avg price (actual fill avg)
    "X": "FILLED",           // status
    "l": "0.014",            // last filled qty
    "z": "0.014",            // accumulated qty
    "T": 1568014460893       // trade time (ms)
  }
}

USD value per liquidation = ap * z

Run:
    python3 scripts/cascade_research/collect_liquidations.py
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import websockets

WS_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("liq-collector")


def output_path_for(ts_ms: int) -> Path:
    """Daily rotation by event timestamp (UTC)."""
    d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
    return DATA_DIR / f"liquidations_{d.isoformat()}.jsonl"


async def stream_loop():
    backoff = 2
    msg_counter = 0
    last_log = datetime.now(timezone.utc)

    while True:
        try:
            logger.info(f"Connecting to {WS_URL}")
            async with websockets.connect(
                WS_URL,
                ping_interval=20,
                ping_timeout=10,
                max_size=2**20,
            ) as ws:
                logger.info("Connected. Streaming liquidations...")
                backoff = 2

                async for raw in ws:
                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if evt.get("e") != "forceOrder":
                        continue

                    o = evt.get("o", {})
                    ts_ms = int(evt.get("E", o.get("T", 0)))
                    if ts_ms == 0:
                        continue

                    # Compact record for storage efficiency
                    rec = {
                        "ts": ts_ms,
                        "sym": o.get("s"),
                        "side": o.get("S"),  # SELL = long liq, BUY = short liq
                        "qty": float(o.get("z", 0)),  # filled qty
                        "px": float(o.get("ap", o.get("p", 0))),  # avg fill price
                        "usd": float(o.get("z", 0)) * float(o.get("ap", o.get("p", 0))),
                    }

                    out = output_path_for(ts_ms)
                    with out.open("a") as f:
                        f.write(json.dumps(rec, separators=(",", ":")) + "\n")

                    msg_counter += 1
                    now = datetime.now(timezone.utc)
                    if (now - last_log).total_seconds() >= 60:
                        logger.info(
                            f"+{msg_counter} liq events in last "
                            f"{(now - last_log).total_seconds():.0f}s "
                            f"(latest: {rec['sym']} {rec['side']} ${rec['usd']:,.0f})"
                        )
                        msg_counter = 0
                        last_log = now

        except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
            logger.warning(f"WS error: {e}. Reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


def main():
    try:
        asyncio.run(stream_loop())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
