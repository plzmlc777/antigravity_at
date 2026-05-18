# Antigravity Kiwoom MCP Server (Pilot, KR Equity)

Wraps `KiwoomRealAdapter` as a stdio MCP server so Claude Code agents can call
read-only and 모의투자 trading tools directly. Real-trading tools are defined
but **gated by `MCP_ALLOW_REAL_TRADES` + risk-manager VETO**.

Companion to `backend/mcp_servers/binance_futures/` (Track 2 Sub-task 2B).
Identical 3-tier permission architecture, KR-specific tool names and prompts.

## Tool inventory

### Tier 1 — Read-only (always enabled, routes to 모의서버)
- `get_kr_current_price(symbol)` → latest price snapshot
- `get_kr_minute_candles(symbol, interval_minutes)` → minute OHLCV
- `get_kr_daily_candles(symbol, base_dt)` → daily OHLCV
- `get_kr_candles(symbol, interval, days, limit)` → generic fetch
- `get_kr_balance()` → KRW + 보유 종목 list
- `get_kr_outstanding_orders()` → 미체결 orders
- `get_kr_order_executions(order_no, symbol)` → 체결 history

### Tier 2 — Paper-write (모의투자 only, enabled by default)
- `paper_buy_stock(symbol, price, quantity)`
- `paper_sell_stock(symbol, price, quantity)`
- `paper_cancel_kr_order(order_id, symbol, quantity, origin_order_id)`

### Tier 3 — Real-write (DISABLED by default)
- `real_buy_stock` / `real_sell_stock` / `real_cancel_kr_order`
- Requires `MCP_ALLOW_REAL_TRADES=true` env + risk-manager VETO clearance.

## Prerequisites

```bash
cd /home/hcpark/antigravity/backend
source venv/bin/activate
pip install mcp  # shared with binance_futures MCP — install once
```

## ENV variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `MCP_EXCHANGE_ACCOUNT_ID` | yes | — | DB row id (`exchange_accounts.id`) for a Kiwoom account. |
| `MCP_ALLOW_REAL_TRADES` | no | `false` | Set to `true` only after risk-manager VETO to enable Tier 3. |
| `PYTHONPATH` | yes | — | Set to `/home/hcpark/antigravity/backend`. |

## KR-specific notes

- **Market hours**: 09:00–15:30 KST (no lunch break). Tier 1 read tools can hit
  the 모의서버 even outside market hours but live order tools may error.
- **Symbol format**: 6-digit numeric code (e.g. `005930` for 삼성전자, never
  the company name). Per [[feedback_no_stock_guess]] all responses must cite
  API verbatim — no name-to-code guessing.
- **Quantity = integer shares** (Kiwoom does not support fractional shares).
- **Naver JSON 1순위 (외부 뉴스)**: this MCP server only handles trading
  endpoints. News research uses the `market-researcher` subagent
  (with Naver 1순위 rule from Track 1 Day 1 refactor).

## Manual launch

```bash
PYTHONPATH=/home/hcpark/antigravity/backend \
MCP_EXCHANGE_ACCOUNT_ID=<N> \
MCP_ALLOW_REAL_TRADES=false \
/home/hcpark/antigravity/backend/venv/bin/python3 \
    -m mcp_servers.kiwoom.server
```

## Claude Code registration

```json
{
  "mcpServers": {
    "antigravity-kiwoom": {
      "command": "/home/hcpark/antigravity/backend/venv/bin/python3",
      "args": ["-m", "mcp_servers.kiwoom.server"],
      "env": {
        "PYTHONPATH": "/home/hcpark/antigravity/backend",
        "MCP_EXCHANGE_ACCOUNT_ID": "<DB row id of a Kiwoom account>",
        "MCP_ALLOW_REAL_TRADES": "false"
      }
    }
  }
}
```

Both `antigravity-binance-futures` and `antigravity-kiwoom` can coexist under
the same `mcpServers` key with distinct `MCP_EXCHANGE_ACCOUNT_ID` values.

## Integration test (manual)

After registration in a new Claude Code session:

1. `get_kr_current_price("005930")` → `{"price": <int KRW>, ...}` from 모의서버
2. `get_kr_balance()` → 모의투자 balance dict
3. Attempt `real_buy_stock("005930", 60000, 1)` → `PermissionError` (Tier 3 ENV gate)
4. `paper_buy_stock("005930", 60000, 1)` → 모의투자에 1주 주문 (체결 후 `get_kr_balance` 변화 확인)

## Activating Tier 3 (real KR trades)

Same procedure as Binance Futures (see Track 2 Sub-task 2D, deferred to
dedicated session). Critical extras for KR equity:

- KRX 거래 정지 종목 제외 룰 사전 적용 (risk-manager 책임)
- 분할 거래 권고 가격 단위 (1원~1000원 호가 단위) 준수
- 시간외 단일가/종가 단일가 거래 시간대 별도 정책

## Architectural notes

- WebSocket subscriptions (`kiwoom_websocket.py`) intentionally excluded from
  the pilot — same rationale as binance_futures pilot.
- Token refresh: KiwoomBaseAdapter handles token validity check on demand.
  MCP server process holds the adapter; long-running MCP server should refresh
  tokens periodically (TODO: add background refresh task in Sub-task 2D).
- 실거래/모의투자 endpoint 분리: `is_virtual=True` → mockapi.kiwoom.com,
  `is_virtual=False` → api.kiwoom.com. Per-account credentials are independent
  between real and virtual servers; ensure `MCP_EXCHANGE_ACCOUNT_ID` points to
  the correct one.
