# Antigravity Binance Futures MCP Server (Pilot)

Wraps `BinanceFuturesAdapter` as an MCP server (stdio transport) so Claude Code
agents can call read-only and paper-trading tools directly. Real-trading tools
are defined but **gated by `MCP_ALLOW_REAL_TRADES` + risk-manager VETO**.

## Tool inventory

### Tier 1 — Read-only (always enabled, runs against testnet)
- `get_funding_rate(symbol)` → current funding rate
- `get_ohlcv(symbol, interval, count)` → OHLCV candles
- `get_position(symbol)` → position state
- `get_balance()` → USDT + asset balances
- `get_outstanding_orders()` → open orders list
- `get_current_price(symbol)` → latest price snapshot
- `get_adl_quantile(symbol)` → ADL rank

### Tier 2 — Paper-write (testnet only, enabled by default)
- `paper_place_long_order(symbol, price, quantity)`
- `paper_place_short_order(symbol, price, quantity)`
- `paper_close_position(symbol)`
- `paper_cancel_order(order_id, symbol)`

### Tier 3 — Real-write (DISABLED by default)
- `real_place_long_order` / `real_place_short_order` / `real_close_position` / `real_cancel_order`
- Requires `MCP_ALLOW_REAL_TRADES=true` env + risk-manager VETO clearance.

## Prerequisites

```bash
cd /home/hcpark/antigravity/backend
source venv/bin/activate
pip install mcp
```

The `mcp` package (Python SDK) is required and not yet in `requirements.txt`.
Add to `requirements.txt` after pilot acceptance.

## ENV variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `MCP_EXCHANGE_ACCOUNT_ID` | yes | — | DB row id (`exchange_accounts.id`) whose Fernet-encrypted credentials to load. Must be a Binance Futures account. |
| `MCP_ALLOW_REAL_TRADES` | no | `false` | Set to `true` only after risk-manager VETO clearance to enable Tier 3 tools. |
| `PYTHONPATH` | yes | — | Set to `/home/hcpark/antigravity/backend` so the server can import `app.*` modules. |

## Manual launch (for stdio testing)

```bash
PYTHONPATH=/home/hcpark/antigravity/backend \
MCP_EXCHANGE_ACCOUNT_ID=<N> \
MCP_ALLOW_REAL_TRADES=false \
/home/hcpark/antigravity/backend/venv/bin/python3 \
    -m mcp_servers.binance_futures.server
```

The server listens on stdin/stdout for JSON-RPC 2.0 messages.

## Claude Code registration

Add to `~/.claude/settings.json` under `mcpServers` (or to a project-local
`.mcp.json`):

```json
{
  "mcpServers": {
    "antigravity-binance-futures": {
      "command": "/home/hcpark/antigravity/backend/venv/bin/python3",
      "args": ["-m", "mcp_servers.binance_futures.server"],
      "env": {
        "PYTHONPATH": "/home/hcpark/antigravity/backend",
        "MCP_EXCHANGE_ACCOUNT_ID": "1",
        "MCP_ALLOW_REAL_TRADES": "false"
      }
    }
  }
}
```

Restart Claude Code after editing settings.json so the agent registry reloads
the MCP server list.

## Integration test (manual)

After registration, in a new Claude Code session:

1. Call `get_funding_rate("BTCUSDT")` → should return `{"symbol": "BTCUSDT", "funding_rate": <float>}`.
2. Call `get_position("BTCUSDT")` → returns position dict from testnet.
3. Attempt `real_place_long_order(...)` → should raise `PermissionError` because `MCP_ALLOW_REAL_TRADES=false`.
4. Call `paper_place_long_order("BTCUSDT", 0, 0.001)` → submits a tiny market order on testnet (verify in testnet UI).

## Activating Tier 3 (real trades) — DO NOT do this without explicit user approval

Per `.claude/plans/claude_fs_pattern_adoption_track.md` §2 (Track 2 Critical):

1. Run risk-manager subagent on the proposed activation (must return `approved: true`).
2. Migrate the `mcp_audit_log` table (schema in `.claude/plans/track2_mcp_server_design.md` §5.3).
3. Set `MCP_ALLOW_REAL_TRADES=true` in the MCP server env.
4. Restart Claude Code so the env propagates to the spawned MCP server process.
5. Schedule a 24-hour dry-run review before unattended use.

Revoke instantly with `MCP_ALLOW_REAL_TRADES=false` + Claude Code restart.

## Architectural notes

- Process lifecycle: MCP server is a separate process spawned per Claude Code
  session. Crash does not affect the FastAPI backend or PM2-managed live
  trading sessions.
- WebSocket subscriptions are intentionally **not exposed** in the pilot
  (request/response paradigm mismatch). Revisit when MCP SSE transport
  matures.
- Credentials are decrypted inside the MCP server process only; never logged.
- Tool name prefix convention (`paper_*` / `real_*`) is the primary safety
  signal for human reviewers reading session transcripts.
