"""
Telegram Notification Service for trading alerts.
"""
import logging
import httpx
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotificationService:
    """Service for sending Telegram notifications."""

    def __init__(self, db: Session, user_id: Optional[int] = None, account_id: Optional[int] = None):
        self.db = db
        self.user_id = user_id
        self.bot_token: Optional[str] = None
        self.chat_id: Optional[str] = None
        self.enabled = False
        self.notify_trades = True
        self.notify_ai_eval = True
        self.notify_errors = True

        if user_id:
            self._load_settings_from_db(user_id, account_id)

    def _load_settings_from_db(self, user_id: int, account_id: Optional[int] = None):
        """Load Telegram settings from a specific account, or fallback to active account."""
        from ..models.account import ExchangeAccount
        from ..core import security

        try:
            if account_id:
                account = self.db.query(ExchangeAccount).filter(
                    ExchangeAccount.id == account_id,
                    ExchangeAccount.user_id == user_id
                ).first()
            else:
                account = self.db.query(ExchangeAccount).filter(
                    ExchangeAccount.user_id == user_id,
                    ExchangeAccount.is_active == True
                ).first()

            if account:
                self.enabled = account.telegram_enabled or False
                self.chat_id = account.telegram_chat_id
                self.notify_trades = account.telegram_notify_trades if account.telegram_notify_trades is not None else True
                self.notify_ai_eval = account.telegram_notify_ai_eval if account.telegram_notify_ai_eval is not None else True
                self.notify_errors = account.telegram_notify_errors if account.telegram_notify_errors is not None else True

                if account.encrypted_telegram_bot_token:
                    self.bot_token = security.decrypt_key(account.encrypted_telegram_bot_token)

                logger.info(f"Telegram settings loaded for user {user_id}, account {account.id}: "
                           f"enabled={self.enabled}, has_token={bool(self.bot_token)}, "
                           f"has_chat_id={bool(self.chat_id)}, notify_ai_eval={self.notify_ai_eval}")

                if self.enabled and self.bot_token and self.chat_id:
                    logger.info(f"Telegram notifications fully configured for user {user_id}")
                else:
                    logger.info(f"Telegram not fully configured for user {user_id}: "
                               f"enabled={self.enabled}, token={bool(self.bot_token)}, chat_id={bool(self.chat_id)}")
            else:
                logger.info(f"No active account found for user {user_id} to load Telegram settings")

        except Exception as e:
            logger.error(f"Failed to load Telegram settings: {e}")

    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return bool(self.enabled and self.bot_token and self.chat_id)

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message via Telegram.

        Args:
            text: Message text (supports HTML formatting)
            parse_mode: 'HTML' or 'Markdown'

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.debug("Telegram not configured, skipping notification")
            return False

        try:
            url = TELEGRAM_API_URL.format(token=self.bot_token)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                })

                if response.status_code == 200:
                    logger.info("Telegram message sent successfully")
                    return True
                else:
                    logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════════════════
    # Pre-built Message Templates
    # ═══════════════════════════════════════════════════════════════════════════

    async def notify_trade_execution(
        self,
        symbol: str,
        side: str,  # 'BUY' or 'SELL'
        quantity: int,
        price: float,
        strategy_name: str,
        is_paper: bool = False,
        pnl: Optional[float] = None,
        return_pct: Optional[float] = None
    ) -> bool:
        """Send trade execution notification."""
        if not self.notify_trades:
            return False

        mode_emoji = "📝" if is_paper else "💰"
        mode_label = "모의" if is_paper else "실거래"
        side_emoji = "🟢" if side == "BUY" else "🔴"
        side_label = "매수" if side == "BUY" else "매도"

        message = f"""
{side_emoji} <b>{side_label} 체결</b> {mode_emoji}

📊 <b>{symbol}</b>
├ 전략: {strategy_name}
├ 수량: {quantity:,}주
├ 가격: {price:,.0f}원
└ 모드: {mode_label}
"""

        if side == "SELL" and pnl is not None:
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            pnl_sign = "+" if pnl >= 0 else ""
            message += f"""
{pnl_emoji} <b>손익</b>
├ 금액: {pnl_sign}{pnl:,.0f}원
└ 수익률: {pnl_sign}{return_pct:.2f}%
"""

        return await self.send_message(message.strip())

    async def notify_ai_evaluation(
        self,
        symbol: str,
        strategy_name: str,
        grade: str,
        cycles_analyzed: int,
        is_paper: bool,
        live_return: float,
        backtest_return: float,
        return_diff: float,
        action: Optional[str] = None,
        key_reason: Optional[str] = None,
        ai_response: Optional[str] = None,
        live_stats: Optional[Dict[str, Any]] = None,
        backtest_stats: Optional[Dict[str, Any]] = None,
        comparison: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send AI evaluation result notification with full details."""
        if not self.notify_ai_eval:
            return False

        mode_label = "모의" if is_paper else "실거래"

        # Grade emoji mapping
        grade_emoji = {
            "A": "🏆", "B": "✅", "C": "⚠️", "D": "🟠", "F": "❌"
        }.get(grade, "❓")

        # Header message
        header = f"""🤖 <b>AI 성과 평가 완료</b>

📊 <b>{symbol}</b> | {strategy_name}
├ 모드: {mode_label}
└ 분석 사이클: {cycles_analyzed}개

{grade_emoji} <b>등급: {grade}</b>"""

        if action:
            action_emoji = {"유지": "✅", "조정": "🔧", "중단": "🛑"}.get(action, "📋")
            header += f"\n{action_emoji} <b>권장: {action}</b>"

        await self.send_message(header.strip())

        # Send detailed stats comparison
        if live_stats and backtest_stats:
            def fmt_val(v, is_pct=False, is_time=False):
                if v is None:
                    return "N/A"
                if is_time:
                    return v if isinstance(v, str) else f"{v}"
                if is_pct:
                    return f"{v:+.2f}%" if isinstance(v, (int, float)) else str(v)
                return f"{v:,.2f}" if isinstance(v, float) else str(v)

            def fmt_diff(live_v, bt_v):
                if live_v is None or bt_v is None:
                    return "N/A"
                diff = live_v - bt_v if isinstance(live_v, (int, float)) and isinstance(bt_v, (int, float)) else 0
                sign = "+" if diff >= 0 else ""
                return f"{sign}{diff:.2f}"

            stats_msg = f"""📊 <b>상세 통계 비교</b>

<b>지표          | 라이브     | 백테스트   | 차이</b>
─────────────────────────────────
수익률      | {fmt_val(live_stats.get('total_return'), True):>8} | {fmt_val(backtest_stats.get('total_return'), True):>8} | {fmt_diff(live_stats.get('total_return'), backtest_stats.get('total_return'))}
승률        | {fmt_val(live_stats.get('win_rate'), True):>8} | {fmt_val(backtest_stats.get('win_rate'), True):>8} | {fmt_diff(live_stats.get('win_rate'), backtest_stats.get('win_rate'))}
거래수      | {fmt_val(live_stats.get('total_trades')):>8} | {fmt_val(backtest_stats.get('total_trades')):>8} | {fmt_diff(live_stats.get('total_trades'), backtest_stats.get('total_trades'))}
Profit Factor | {fmt_val(live_stats.get('profit_factor')):>8} | {fmt_val(backtest_stats.get('profit_factor')):>8} | {fmt_diff(live_stats.get('profit_factor'), backtest_stats.get('profit_factor'))}
Sharpe Ratio | {fmt_val(live_stats.get('sharpe_ratio')):>8} | {fmt_val(backtest_stats.get('sharpe_ratio')):>8} | {fmt_diff(live_stats.get('sharpe_ratio'), backtest_stats.get('sharpe_ratio'))}
MDD         | {fmt_val(live_stats.get('max_drawdown'), True):>8} | {fmt_val(backtest_stats.get('max_drawdown'), True):>8} | {fmt_diff(live_stats.get('max_drawdown'), backtest_stats.get('max_drawdown'))}
평균손익    | {fmt_val(live_stats.get('avg_pnl')):>8} | {fmt_val(backtest_stats.get('avg_pnl')):>8} | {fmt_diff(live_stats.get('avg_pnl'), backtest_stats.get('avg_pnl'))}
최대이익    | {fmt_val(live_stats.get('max_profit')):>8} | {fmt_val(backtest_stats.get('max_profit')):>8} | {fmt_diff(live_stats.get('max_profit'), backtest_stats.get('max_profit'))}
최대손실    | {fmt_val(live_stats.get('max_loss')):>8} | {fmt_val(backtest_stats.get('max_loss')):>8} | {fmt_diff(live_stats.get('max_loss'), backtest_stats.get('max_loss'))}"""

            if live_stats.get('avg_holding_time') or backtest_stats.get('avg_holding_time'):
                stats_msg += f"""
평균보유    | {fmt_val(live_stats.get('avg_holding_time'), is_time=True):>8} | {fmt_val(backtest_stats.get('avg_holding_time'), is_time=True):>8} | -"""

            await self.send_message(stats_msg)

        # Send full AI response if available
        if ai_response:
            MAX_LENGTH = 4000

            full_text = f"📋 <b>AI 분석 전문</b>\n\n{ai_response}"

            # Split into chunks
            chunks = []
            current_chunk = ""

            for line in full_text.split('\n'):
                if len(current_chunk) + len(line) + 1 > MAX_LENGTH:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = line
                else:
                    current_chunk = current_chunk + '\n' + line if current_chunk else line

            if current_chunk:
                chunks.append(current_chunk)

            # Send each chunk
            for i, chunk in enumerate(chunks):
                if i > 0:
                    chunk = f"(계속 {i+1}/{len(chunks)})\n\n{chunk}"
                await self.send_message(chunk.strip())

        return True

    async def notify_error(
        self,
        error_type: str,
        message: str,
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None
    ) -> bool:
        """Send error notification."""
        if not self.notify_errors:
            return False

        context = ""
        if symbol:
            context += f"├ 종목: {symbol}\n"
        if strategy_name:
            context += f"├ 전략: {strategy_name}\n"

        text = f"""
🚨 <b>오류 발생</b>

⚠️ <b>{error_type}</b>
{context}└ {message}
"""

        return await self.send_message(text.strip())

    async def notify_session_start(
        self,
        symbol: str,
        strategy_name: str,
        initial_capital: float,
        is_paper: bool
    ) -> bool:
        """Send session start notification."""
        if not self.notify_trades:
            return False

        mode_emoji = "📝" if is_paper else "💰"
        mode_label = "모의거래" if is_paper else "실거래"

        message = f"""
🚀 <b>라이브 세션 시작</b> {mode_emoji}

📊 <b>{symbol}</b>
├ 전략: {strategy_name}
├ 자본금: {initial_capital:,.0f}원
└ 모드: {mode_label}
"""

        return await self.send_message(message.strip())

    async def notify_session_stop(
        self,
        symbol: str,
        strategy_name: str,
        total_pnl: float,
        total_return: float,
        total_trades: int,
        is_paper: bool
    ) -> bool:
        """Send session stop notification."""
        if not self.notify_trades:
            return False

        mode_label = "모의" if is_paper else "실거래"
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        pnl_sign = "+" if total_pnl >= 0 else ""

        message = f"""
🛑 <b>라이브 세션 종료</b>

📊 <b>{symbol}</b> | {strategy_name}
└ 모드: {mode_label}

{pnl_emoji} <b>최종 성과</b>
├ 손익: {pnl_sign}{total_pnl:,.0f}원
├ 수익률: {pnl_sign}{total_return:.2f}%
└ 총 거래: {total_trades}건
"""

        return await self.send_message(message.strip())


# ═══════════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════════

async def send_telegram_notification(
    db: Session,
    user_id: int,
    notification_type: str,
    account_id: Optional[int] = None,
    **kwargs
) -> bool:
    """
    Convenience function to send notifications.

    Args:
        db: Database session
        user_id: User ID
        notification_type: 'trade', 'ai_eval', 'error', 'session_start', 'session_stop'
        account_id: Specific account to load Telegram settings from
        **kwargs: Arguments for the specific notification type

    Returns:
        True if sent successfully
    """
    service = TelegramNotificationService(db, user_id, account_id=account_id)

    if not service.is_configured():
        return False

    if notification_type == "trade":
        return await service.notify_trade_execution(**kwargs)
    elif notification_type == "ai_eval":
        return await service.notify_ai_evaluation(**kwargs)
    elif notification_type == "error":
        return await service.notify_error(**kwargs)
    elif notification_type == "session_start":
        return await service.notify_session_start(**kwargs)
    elif notification_type == "session_stop":
        return await service.notify_session_stop(**kwargs)
    else:
        logger.warning(f"Unknown notification type: {notification_type}")
        return False


async def test_telegram_connection(bot_token: str, chat_id: str) -> Dict[str, Any]:
    """
    Test Telegram bot connection.

    Returns:
        Dict with 'success' boolean and 'message' string
    """
    try:
        url = TELEGRAM_API_URL.format(token=bot_token)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={
                "chat_id": chat_id,
                "text": "✅ My Auto Trading 알림 연결 테스트 성공!\n\n이제 거래 알림을 받을 수 있습니다.",
                "parse_mode": "HTML"
            })

            if response.status_code == 200:
                return {"success": True, "message": "연결 성공"}
            else:
                error_data = response.json()
                error_msg = error_data.get("description", "Unknown error")
                return {"success": False, "message": f"Telegram API 오류: {error_msg}"}

    except httpx.TimeoutException:
        return {"success": False, "message": "연결 시간 초과"}
    except Exception as e:
        return {"success": False, "message": f"연결 실패: {str(e)}"}
