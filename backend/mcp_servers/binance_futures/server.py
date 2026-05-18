"""
Antigravity Binance Futures MCP server — pilot implementation.

Start with:
    PYTHONPATH=/home/hcpark/antigravity/backend \
    MCP_EXCHANGE_ACCOUNT_ID=<row_id> \
    MCP_ALLOW_REAL_TRADES=false \
    /home/hcpark/antigravity/backend/venv/bin/python3 \
        -m mcp_servers.binance_futures.server

Or via .mcp.json (see README.md).

Tier 1 tools (read-only) and Tier 2 tools (paper_*) always run against the
testnet adapter. Tier 3 tools (real_*) are gated by MCP_ALLOW_REAL_TRADES
+ risk-manager VETO (stubbed for the pilot — see risk_check.py).
"""
import logging
import sys

from mcp.server.fastmcp import FastMCP

from . import tool_handlers

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("antigravity-binance-futures")


# ===== Tier 1 — Read-only =====

@mcp.tool()
async def get_funding_rate(symbol: str) -> dict:
    """Get current funding rate for a Binance Futures USDS-M perp.

    Args:
        symbol: e.g. BTCUSDT
    """
    return await tool_handlers.get_funding_rate(symbol)


@mcp.tool()
async def get_ohlcv(symbol: str, interval: str = "1h", count: int = 200) -> list:
    """Get OHLCV candles for a Binance Futures perp.

    Args:
        symbol: e.g. BTCUSDT
        interval: 1m / 5m / 15m / 1h / 4h / 1d
        count: number of candles, max 1000
    """
    return await tool_handlers.get_ohlcv(symbol=symbol, interval=interval, count=count)


@mcp.tool()
async def get_position(symbol: str) -> dict:
    """Get current position state for a symbol.

    Args:
        symbol: e.g. BTCUSDT
    """
    return await tool_handlers.get_position(symbol)


@mcp.tool()
async def get_balance() -> dict:
    """Get current account balance (USDT + asset list)."""
    return await tool_handlers.get_balance()


@mcp.tool()
async def get_outstanding_orders() -> list:
    """List currently open orders."""
    return await tool_handlers.get_outstanding_orders()


@mcp.tool()
async def get_current_price(symbol: str) -> dict:
    """Get the latest mark/last price snapshot.

    Args:
        symbol: e.g. BTCUSDT
    """
    return await tool_handlers.get_current_price(symbol)


@mcp.tool()
async def get_adl_quantile(symbol: str) -> dict:
    """Get the ADL (Auto-Deleverage) quantile rank for a position.

    Args:
        symbol: e.g. BTCUSDT
    """
    return await tool_handlers.get_adl_quantile(symbol)


# ===== Tier 2 — Paper-write (testnet only, enabled by default) =====

@mcp.tool()
async def paper_place_long_order(symbol: str, price: float, quantity: float) -> dict:
    """Submit a LONG order to the PAPER (testnet) account.

    Args:
        symbol: e.g. BTCUSDT
        price: limit price (0 for market)
        quantity: contract size
    """
    return await tool_handlers.paper_place_long_order(symbol=symbol, price=price, quantity=quantity)


@mcp.tool()
async def paper_place_short_order(symbol: str, price: float, quantity: float) -> dict:
    """Submit a SHORT order to the PAPER (testnet) account.

    Args:
        symbol: e.g. BTCUSDT
        price: limit price (0 for market)
        quantity: contract size
    """
    return await tool_handlers.paper_place_short_order(symbol=symbol, price=price, quantity=quantity)


@mcp.tool()
async def paper_close_position(symbol: str) -> dict:
    """Close the entire position for a symbol on the PAPER (testnet) account.

    Args:
        symbol: e.g. BTCUSDT
    """
    return await tool_handlers.paper_close_position(symbol)


@mcp.tool()
async def paper_cancel_order(order_id: str, symbol: str) -> dict:
    """Cancel a specific open order on the PAPER (testnet) account.

    Args:
        order_id: Binance order id
        symbol: e.g. BTCUSDT
    """
    return await tool_handlers.paper_cancel_order(order_id=order_id, symbol=symbol)


# ===== Tier 3 — Real-write (env-gated, risk-manager VETO required) =====

@mcp.tool()
async def real_place_long_order(symbol: str, price: float, quantity: float) -> dict:
    """Submit a LONG order to the REAL Binance Futures account.

    REQUIRES MCP_ALLOW_REAL_TRADES=true and risk-manager VETO clearance.
    Raises PermissionError otherwise.

    Args:
        symbol: e.g. BTCUSDT
        price: limit price (0 for market)
        quantity: contract size
    """
    return await tool_handlers.real_place_long_order(symbol=symbol, price=price, quantity=quantity)


@mcp.tool()
async def real_place_short_order(symbol: str, price: float, quantity: float) -> dict:
    """Submit a SHORT order to the REAL Binance Futures account. ENV-gated.

    Args:
        symbol: e.g. BTCUSDT
        price: limit price (0 for market)
        quantity: contract size
    """
    return await tool_handlers.real_place_short_order(symbol=symbol, price=price, quantity=quantity)


@mcp.tool()
async def real_close_position(symbol: str) -> dict:
    """Close the entire position on the REAL account. ENV-gated.

    Args:
        symbol: e.g. BTCUSDT
    """
    return await tool_handlers.real_close_position(symbol)


@mcp.tool()
async def real_cancel_order(order_id: str, symbol: str) -> dict:
    """Cancel a specific open order on the REAL account. ENV-gated.

    Args:
        order_id: Binance order id
        symbol: e.g. BTCUSDT
    """
    return await tool_handlers.real_cancel_order(order_id=order_id, symbol=symbol)


# ===== Prompts =====

@mcp.prompt()
def macro_brief(symbol: str) -> str:
    """Macro context brief template for a Binance Futures symbol."""
    return (f"Symbol: {symbol}\n"
            "Provide:\n"
            "1. Macro regime assessment (bull/bear/sideways/volatile)\n"
            "2. Three event risks within the next 7 days (date + impact)\n"
            "3. One trading implication (Korean)")


@mcp.prompt()
def signal_precondition(symbol: str) -> str:
    """Pre-flight checklist before submitting a trading signal."""
    return (f"For {symbol}, verify in order:\n"
            "1. Liquidity OK (24h volume vs avg)\n"
            "2. Funding rate within healthy band (-0.05% to +0.05% per 8h)\n"
            "3. No pending high-impact event within 24h (FOMC / earnings / regulation)\n"
            "4. Position size compatible with current balance\n"
            "Respond in Korean with PASS/FAIL per item.")


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
