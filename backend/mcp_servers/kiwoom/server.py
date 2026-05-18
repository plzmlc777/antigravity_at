"""
Antigravity Kiwoom MCP server — pilot implementation (KR equity).

Start with:
    PYTHONPATH=/home/hcpark/antigravity/backend \
    MCP_EXCHANGE_ACCOUNT_ID=<row_id> \
    MCP_ALLOW_REAL_TRADES=false \
    /home/hcpark/antigravity/backend/venv/bin/python3 \
        -m mcp_servers.kiwoom.server

Or via .mcp.json (see README.md).

Tier 1 tools (read-only) and Tier 2 tools (paper_*) always run against
the 모의서버 (mockapi.kiwoom.com). Tier 3 tools (real_*) are gated by
MCP_ALLOW_REAL_TRADES + risk-manager VETO (stubbed for the pilot).
"""
import logging
import sys

from mcp.server.fastmcp import FastMCP

from . import tool_handlers

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("antigravity-kiwoom")


# ===== Tier 1 — Read-only (모의서버 routing, KR market hours only) =====

@mcp.tool()
async def get_kr_current_price(symbol: str) -> dict:
    """Get latest snapshot price for a KR equity (KOSPI/KOSDAQ).

    Args:
        symbol: 6-digit code (e.g. 005930 for 삼성전자)
    """
    return await tool_handlers.get_kr_current_price(symbol)


@mcp.tool()
async def get_kr_minute_candles(symbol: str, interval_minutes: int = 1) -> list:
    """Get minute-level OHLCV candles for a KR equity.

    Args:
        symbol: 6-digit code
        interval_minutes: 1 / 5 / 10 / 15 / 30 / 60
    """
    return await tool_handlers.get_kr_minute_candles(symbol=symbol, interval_minutes=interval_minutes)


@mcp.tool()
async def get_kr_daily_candles(symbol: str, base_dt: str = None) -> list:
    """Get daily OHLCV candles for a KR equity.

    Args:
        symbol: 6-digit code
        base_dt: optional YYYYMMDD anchor (default: most recent trading day)
    """
    return await tool_handlers.get_kr_daily_candles(symbol=symbol, base_dt=base_dt)


@mcp.tool()
async def get_kr_candles(symbol: str, interval: str = "1d", days: int = 30, limit: int = 1000) -> list:
    """Generic candle fetch with interval + history depth.

    Args:
        symbol: 6-digit code
        interval: 1m / 5m / 1d
        days: history depth in days
        limit: max rows (default 1000)
    """
    return await tool_handlers.get_kr_candles(symbol=symbol, interval=interval, days=days, limit=limit)


@mcp.tool()
async def get_kr_balance() -> dict:
    """Get current KR account balance (KRW + 보유 종목 list)."""
    return await tool_handlers.get_kr_balance()


@mcp.tool()
async def get_kr_outstanding_orders() -> list:
    """List 미체결 orders on the KR account."""
    return await tool_handlers.get_kr_outstanding_orders()


@mcp.tool()
async def get_kr_order_executions(order_no: str = "", symbol: str = "") -> list:
    """Get order fill (체결) history.

    Args:
        order_no: optional filter by Kiwoom order_no
        symbol: optional filter by 6-digit code
    """
    return await tool_handlers.get_kr_order_executions(order_no=order_no, symbol=symbol)


# ===== Tier 2 — Paper-write (모의투자 only, enabled by default) =====

@mcp.tool()
async def paper_buy_stock(symbol: str, price: float, quantity: int) -> dict:
    """Submit a BUY order to 모의투자 (mockapi.kiwoom.com).

    Args:
        symbol: 6-digit code
        price: KRW per share (0 = market)
        quantity: number of shares
    """
    return await tool_handlers.paper_buy_stock(symbol=symbol, price=price, quantity=quantity)


@mcp.tool()
async def paper_sell_stock(symbol: str, price: float, quantity: int) -> dict:
    """Submit a SELL order to 모의투자.

    Args:
        symbol: 6-digit code
        price: KRW per share (0 = market)
        quantity: number of shares
    """
    return await tool_handlers.paper_sell_stock(symbol=symbol, price=price, quantity=quantity)


@mcp.tool()
async def paper_cancel_kr_order(order_id: str, symbol: str, quantity: int, origin_order_id: str = "") -> dict:
    """Cancel an outstanding 모의투자 order.

    Args:
        order_id: Kiwoom order_no to cancel
        symbol: 6-digit code
        quantity: shares to cancel
        origin_order_id: optional parent order id for partial cancels
    """
    return await tool_handlers.paper_cancel_kr_order(order_id=order_id, symbol=symbol,
                                                     quantity=quantity, origin_order_id=origin_order_id)


# ===== Tier 3 — Real-write (env-gated, risk-manager VETO required) =====

@mcp.tool()
async def real_buy_stock(symbol: str, price: float, quantity: int) -> dict:
    """Submit a BUY order to the REAL KR account (api.kiwoom.com).

    REQUIRES MCP_ALLOW_REAL_TRADES=true and risk-manager VETO clearance.
    Raises PermissionError otherwise.

    Args:
        symbol: 6-digit code
        price: KRW per share (0 = market)
        quantity: number of shares
    """
    return await tool_handlers.real_buy_stock(symbol=symbol, price=price, quantity=quantity)


@mcp.tool()
async def real_sell_stock(symbol: str, price: float, quantity: int) -> dict:
    """Submit a SELL order to the REAL KR account. ENV-gated.

    Args:
        symbol: 6-digit code
        price: KRW per share (0 = market)
        quantity: number of shares
    """
    return await tool_handlers.real_sell_stock(symbol=symbol, price=price, quantity=quantity)


@mcp.tool()
async def real_cancel_kr_order(order_id: str, symbol: str, quantity: int, origin_order_id: str = "") -> dict:
    """Cancel an outstanding REAL KR order. ENV-gated.

    Args:
        order_id: Kiwoom order_no
        symbol: 6-digit code
        quantity: shares to cancel
        origin_order_id: optional parent order id
    """
    return await tool_handlers.real_cancel_kr_order(order_id=order_id, symbol=symbol,
                                                    quantity=quantity, origin_order_id=origin_order_id)


# ===== Prompts =====

@mcp.prompt()
def kr_earnings_brief(symbol: str) -> str:
    """KR equity 분기 실적 발표 brief 템플릿."""
    return (f"종목: {symbol}\n"
            "다음 항목을 한국어로 작성:\n"
            "1. 최근 분기 영업이익 / 매출 + YoY\n"
            "2. 가이던스 변화 (있다면)\n"
            "3. 다음 분기 실적 발표 예정일\n"
            "4. 핵심 사업부 모멘텀 / 리스크 1줄")


@mcp.prompt()
def kr_signal_precondition(symbol: str) -> str:
    """KR equity 시그널 사전 체크리스트."""
    return (f"종목 {symbol}, 다음을 순서대로 검증:\n"
            "1. KR 장 시간 여부 (09:00~15:30 KST, 점심 휴장 없음)\n"
            "2. 거래량 유동성 (전일 대비 + 5일 평균 대비)\n"
            "3. 외국인/기관 수급 최근 5일\n"
            "4. 3일 이내 실적 발표/이벤트 유무\n"
            "5. 호가 스프레드 정상 범위\n"
            "각 항목 PASS/FAIL + 1줄 사유로 응답.")


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
