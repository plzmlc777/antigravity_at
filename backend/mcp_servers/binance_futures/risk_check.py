"""
MCP server risk-manager pre-check stub (Tier 3 real_* tools).

In the pilot, real_* tools are gated by ENV MCP_ALLOW_REAL_TRADES=true. The
proper risk-manager subagent VETO integration is a separate work item —
this stub enforces the ENV gate and raises PermissionError otherwise.

Future expansion: invoke the risk-manager subagent via Claude Code Agent
dispatch from this module before allowing the order to proceed.
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
    logger.warning("REAL_TRADE_PRECHECK passed env gate: tool=%s args=%s", tool_name, args)
    # TODO(track2-2D): invoke risk-manager subagent here. Block on VETO.
    # For pilot, env gate is the sole real-trade barrier.
