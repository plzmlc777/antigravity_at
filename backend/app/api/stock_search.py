"""
Stock Search API - AI-powered stock search via Claude Code CLI subprocess

Uses the same Claude Code CLI subprocess pattern as strategy_lab.py.
The agent reads a pre-built stock data context file and returns
recommendations matching the user's natural language query.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import asyncio
import json
import logging
import os
import re
import time
import tempfile

from ..db.session import get_db
from ..models.user import User
from .auth import get_current_user
from ..core.user_context import create_get_user_context_dependency, UserAccountContext

logger = logging.getLogger("stock_search")

router = APIRouter()

# Dependency
get_user_context = create_get_user_context_dependency()


# ============================================================
# Pydantic Schemas
# ============================================================
class StockSearchRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class StockResult(BaseModel):
    code: str
    name: str
    market: str
    reason: str


class StockSearchResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    stocks: Optional[List[StockResult]] = None


# ============================================================
# Helpers
# ============================================================
def _parse_stock_results(text: str) -> List[dict]:
    """Extract [STOCK_RESULTS]...[/STOCK_RESULTS] block from AI response."""
    pattern = r'\[STOCK_RESULTS\]\s*(.*?)\s*\[/STOCK_RESULTS\]'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return []

    lines = match.group(1).strip().split('\n')
    results = []
    for line in lines:
        line = line.strip()
        # Skip header or empty lines
        if not line or line.startswith('CODE|') or line.startswith('---'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 4:
            results.append({
                "code": parts[0],
                "name": parts[1],
                "market": parts[2],
                "reason": parts[3],
            })
    return results


def _slim_stock_data(stocks: list) -> list:
    """Extract only essential fields to reduce context size for LLM."""
    slim = []
    for s in stocks:
        slim.append({
            "code": s.get("code", ""),
            "name": s.get("name", ""),
            "marketName": s.get("marketName", ""),
            "upName": s.get("upName", ""),
            "upSizeName": s.get("upSizeName", ""),
            "companyClassName": s.get("companyClassName", ""),
            "regDay": s.get("regDay", ""),
            "lastPrice": s.get("lastPrice", ""),
            "state": s.get("state", ""),
            "auditInfo": s.get("auditInfo", ""),
            "orderWarning": s.get("orderWarning", ""),
        })
    return slim


# ============================================================
# Token Status Endpoint
# ============================================================
@router.get("/token-status")
async def get_token_status(
    current_user: User = Depends(get_current_user),
):
    """Check Claude CLI OAuth token expiration status."""
    cred_path = os.path.expanduser("~/.claude/.credentials.json")

    if not os.path.exists(cred_path):
        return {"status": "missing", "message": "Credentials file not found"}

    try:
        with open(cred_path, "r") as f:
            data = json.load(f)
        oauth = data.get("claudeAiOauth", {})
        expires_at = oauth.get("expiresAt", 0)
        now_ms = int(time.time() * 1000)
        remaining_ms = expires_at - now_ms

        from ..core.config import get_claude_cli_path
        try:
            get_claude_cli_path()
            cli_installed = True
        except FileNotFoundError:
            cli_installed = False

        return {
            "status": "expired" if remaining_ms <= 0 else "valid",
            "expires_at": expires_at,
            "remaining_ms": max(remaining_ms, 0),
            "cli_installed": cli_installed,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}


# ============================================================
# API Endpoint
# ============================================================
@router.post("/chat", response_model=StockSearchResponse)
async def stock_search_chat(
    request: StockSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: UserAccountContext = Depends(get_user_context),
):
    """
    Chat with Claude Code to search for Korean stocks.
    Uses claude CLI as a subprocess with the stock-searcher agent.
    Pre-fetches stock list from ka10099 and passes as context.
    """
    from ..core.config import get_claude_cli_path

    start_time = time.time()

    try:
        claude_path = get_claude_cli_path()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Claude CLI not found. Install Claude Code first."
        )

    # --- Step 1: Get stock data ---
    if not ctx.has_active_account:
        raise HTTPException(
            status_code=400,
            detail="활성화된 계좌가 없습니다. 계좌를 먼저 설정해주세요."
        )

    token = await ctx.ensure_token()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="키움 API 토큰을 발급할 수 없습니다."
        )

    from ..services.stock_list_service import StockListService
    from ..services.ranking_data_service import RankingDataService

    stock_service = StockListService.get_instance()
    ranking_service = RankingDataService.get_instance()

    try:
        all_stocks, rankings = await asyncio.gather(
            stock_service.get_stock_list(ctx.api_url, token),
            ranking_service.get_rankings(ctx.api_url, token),
        )
    except Exception as e:
        logger.error(f"[StockSearch] Failed to fetch stock/ranking data: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"종목 데이터를 가져올 수 없습니다: {str(e)[:100]}"
        )

    if not all_stocks:
        return StockSearchResponse(
            response="종목 리스트가 비어 있습니다. 잠시 후 다시 시도해주세요.",
            error="Empty stock list"
        )

    # --- Step 2: Write context file ---
    slim_stocks = _slim_stock_data(all_stocks)
    context_data = {
        "query": request.message,
        "stocks": slim_stocks,
        "rankings": rankings,
    }

    context_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', prefix='stock_search_',
            dir='/tmp', delete=False, encoding='utf-8'
        ) as f:
            json.dump(context_data, f, ensure_ascii=False)
            context_file = f.name

        ranking_counts = {k: len(v) for k, v in rankings.items() if v}
        logger.info(
            f"[StockSearch] user={current_user.id}, "
            f"session={request.session_id or 'new'}, "
            f"stocks={len(slim_stocks)}, "
            f"rankings={ranking_counts}, "
            f"context_file={context_file}"
        )

        # --- Step 3: Build and execute Claude CLI ---
        prompt = (
            f"Read the stock data context file at `{context_file}` using the Read tool. "
            f"The file contains a JSON object with 'query', 'stocks', and 'rankings' fields. "
            f"The 'rankings' field contains real-time market ranking data (26 categories): "
            f"volume_top (당일거래량상위), gainers (상승률상위), losers (하락률상위), "
            f"value_top (거래대금상위), foreign_buy (외인순매수), foreign_sell (외인순매도), "
            f"volume_spike (거래량급증), credit_top (신용비율상위), "
            f"bid_balance (호가잔량상위), bid_spike (호가잔량급증), balance_rate_spike (잔량율급증), "
            f"expected_price (예상체결등락률), prev_volume_top (전일거래량상위), "
            f"foreign_consec_buy/sell (외인연속순매매), foreign_limit_exhaust (외인한도소진율), "
            f"foreign_branch_buy/sell (외국계창구매매), same_net_buy/sell (동일순매매), "
            f"intraday_foreign_buy/sell (장중외국인매매), intraday_inst_buy/sell (장중기관매매), "
            f"after_hours_change (시간외단일가등락률), foreign_inst_combined (외국인기관매매상위). "
            f"Use both stock list and ranking data to find stocks matching the user's query.\n\n"
            f"User query: {request.message}"
        )

        cmd = [
            claude_path,
            "-p", prompt,
            "--output-format", "json",
            "--agent", "stock-searcher",
            "--permission-mode", "bypassPermissions",
        ]

        if request.session_id:
            cmd.extend(["--resume", request.session_id])

        env = os.environ.copy()
        for key in ["NODE_CHANNEL_FD", "NODE_CHANNEL_SERIALIZATION_MODE", "NODE_APP_INSTANCE"]:
            env.pop(key, None)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/home/hcpark/antigravity",
            env=env,
            start_new_session=True,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            logger.error("[StockSearch] TIMEOUT after 300s")
            return StockSearchResponse(
                response="",
                error="응답 시간이 초과되었습니다 (5분). 더 간단한 질문을 시도해보세요."
            )

        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else ""
            # Also check stdout for JSON error responses
            raw_out = stdout.decode().strip() if stdout else ""
            if not err_msg and raw_out:
                try:
                    err_data = json.loads(raw_out)
                    if err_data.get("is_error"):
                        err_msg = err_data.get("result", "Unknown error")
                except (json.JSONDecodeError, KeyError):
                    err_msg = err_msg or "Unknown error"
            err_msg = err_msg or "Unknown error"
            # Detect auth expiration
            if "expired" in err_msg.lower() or "authentication" in err_msg.lower():
                logger.error(f"[StockSearch] Auth expired: {err_msg[:200]}")
                return StockSearchResponse(
                    response="",
                    error="Claude CLI 인증이 만료되었습니다. 서버에서 'claude' 재로그인이 필요합니다."
                )
            logger.error(f"[StockSearch] CLI error (rc={proc.returncode}): {err_msg[:300]}")
            return StockSearchResponse(
                response="",
                error=f"Claude CLI error: {err_msg[:200]}"
            )

        # --- Step 4: Parse response ---
        raw = stdout.decode().strip()
        if not raw:
            return StockSearchResponse(response="", error="Empty response from Claude CLI")

        data = json.loads(raw)

        # Check for error in successful exit code (CLI may return 0 with is_error=true)
        if data.get("is_error"):
            err_msg = data.get("result", "Unknown error")
            if "expired" in err_msg.lower() or "authentication" in err_msg.lower():
                logger.error(f"[StockSearch] Auth expired: {err_msg[:200]}")
                return StockSearchResponse(
                    response="",
                    error="Claude CLI 인증이 만료되었습니다. 서버에서 'claude' 재로그인이 필요합니다."
                )
            logger.error(f"[StockSearch] CLI returned error: {err_msg[:300]}")
            return StockSearchResponse(
                response="",
                error=f"Claude CLI error: {err_msg[:200]}"
            )

        response_text = data.get("result", "")
        session_id = data.get("session_id")
        duration_ms = int((time.time() - start_time) * 1000)

        # Parse structured stock results
        parsed_stocks = _parse_stock_results(response_text)

        return StockSearchResponse(
            response=response_text,
            session_id=session_id,
            duration_ms=duration_ms,
            stocks=parsed_stocks if parsed_stocks else None,
        )

    except json.JSONDecodeError as e:
        logger.error(f"[StockSearch] JSON parse error: {e}")
        return StockSearchResponse(response="", error="Failed to parse Claude response")
    except Exception as e:
        logger.error(f"[StockSearch] Unexpected error: {e}")
        return StockSearchResponse(response="", error=str(e)[:200])
    finally:
        # Cleanup temp file
        if context_file and os.path.exists(context_file):
            try:
                os.unlink(context_file)
            except Exception:
                pass
