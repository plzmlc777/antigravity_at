# Liquidation Cascade Research

Empirical validation of the "liquidation cascade contrarian" trading thesis.
Collects every Binance Futures forced liquidation in real time, then analyzes
hourly aggregates and price recovery patterns.

## Files

- `collect_liquidations.py` — WebSocket collector. Subscribes to
  `wss://fstream.binance.com/ws/!forceOrder@arr` and appends each event to
  daily JSONL files in `data/`.
- `analyze_liquidations.py` — Reads collected JSONL, classifies cascade tiers,
  finds top hours, and (optionally) measures BTC/ETH price recovery using
  Binance kline REST API.
- `data/liquidations_YYYY-MM-DD.jsonl` — Daily rotated event log.

## ⚠️ Environment requirement

This collector **must run on a server with working egress WebSocket
connectivity to Binance** (e.g. the Mint deployment server).

Verified failing locally on WSL2 — TLS handshake to
`fstream.binance.com` succeeds but no WebSocket frames are delivered
(reproduced with both the `websockets` and `aiohttp` libraries, and
also with the public `btcusdt@aggTrade` stream which is normally
firehose-busy). REST API works fine; the issue is WebSocket frame
delivery only. Likely WSL2 NAT/firewall behavior. Run on the remote
server instead.

## Run as a long-lived PM2 service (on Mint)

A PM2 entry `at-liq-collector` is registered in `ecosystem.config.cjs`
(disabled by default; enabled with `ENABLE_RESEARCH=1`).

    ENABLE_RESEARCH=1 pm2 start ecosystem.config.cjs --only at-liq-collector
    pm2 logs at-liq-collector

To stop:

    pm2 stop at-liq-collector

## Manual run (ad-hoc, only on a host with working WS connectivity)

    backend/venv/bin/python scripts/cascade_research/collect_liquidations.py

## Analyze

After at least a few days of collection:

    # Market-wide tier distribution + top hours
    backend/venv/bin/python scripts/cascade_research/analyze_liquidations.py

    # Single-symbol view
    backend/venv/bin/python scripts/cascade_research/analyze_liquidations.py --symbol BTCUSDT

    # Top 20 + recovery measurement (requires internet)
    backend/venv/bin/python scripts/cascade_research/analyze_liquidations.py --top 20 --recovery

## Tier definitions

Market-wide (default):
- Tier1 Mega: ≥ $500M / hour
- Tier2 Large: ≥ $200M / hour
- Tier3 Medium: ≥ $50M / hour
- Tier4 Small: ≥ $20M / hour

Per-symbol (`--symbol`):
- Tier1 Mega: ≥ $50M / hour
- Tier2 Large: ≥ $20M / hour
- Tier3 Medium: ≥ $5M / hour
- Tier4 Small: ≥ $1M / hour

## Storage estimate

~5–50 events/min on a normal day, ~500–5000/min during cascade events.
A compact JSON record is ~80 bytes → roughly 50–500 MB/month.

## Goal

Validate or refute the cascade-contrarian frequency claims:
- Tier 2 events: month? expected ~3–8/month
- Mean recovery from cascade low to next 6h high: expected 50–80% of drawdown
- Long/Short ratio in cascades: expected ≥ 75% one-sided

After ≥ 2 weeks of data, run `analyze_liquidations.py --recovery` to compare
against the thesis numbers in the chat record.
