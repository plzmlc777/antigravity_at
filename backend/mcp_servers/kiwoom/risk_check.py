"""
Kiwoom MCP server risk-manager pre-check stub (Tier 3 real_* tools).

In the pilot, real_* tools are gated by ENV MCP_ALLOW_REAL_TRADES=true.
risk-manager subagent VETO integration is deferred to Sub-task 2D.

KR equity 실거래는 키움 실서버 (api.kiwoom.com) 에 직접 주문이 전송된다 —
ENV gate가 사실상 유일한 차단 layer (pilot 한계).
"""
import logging
from typing import Any, Dict

from .auth import allow_real_trades

logger = logging.getLogger(__name__)


class RealTradeBlocked(PermissionError):
    pass


def check_real_trade_allowed(tool_name: str, args: Dict[str, Any]) -> None:
    if not allow_real_trades():
        raise RealTradeBlocked(
            f"real_* tool '{tool_name}' is disabled. "
            "Set MCP_ALLOW_REAL_TRADES=true and obtain risk-manager VETO clearance first."
        )
    logger.warning("KR REAL_TRADE_PRECHECK passed env gate: tool=%s args=%s", tool_name, args)
    # TODO(track2-2D): invoke risk-manager subagent here. Block on VETO.
