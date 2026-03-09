"""
Trading Constants - Single Source of Truth

모든 하드코딩된 문자열 상수를 중앙 관리.
기존 models/live_trading.py의 Enum들과 함께 사용.
"""


# ── Signal Types ──
# DB/API에서 사용되는 매매 신호 (models/live_trading.py SignalType과 동일 값)
class Signal:
    BUY = "BUY"
    SELL = "SELL"


# ── Position Side (전략 config용, lowercase) ──
# 전략 설정, trade_metadata에서 사용
class Side:
    LONG = "long"
    SHORT = "short"
    BOTH = "both"


# ── Trade Metadata Level ──
# trade_metadata.level 필드 값
class Level:
    CLOSE = "CLOSE"
    # Numeric levels (1, 2, 3, ...) are int, not string


# ── AI Symbol Mode ──
# live_bot_sessions.ai_symbol_mode 필드 값
class AiMode:
    STATIC = "static"
    AI = "ai"
    RESET = "reset"


# ── Margin Type (Futures) ──
class Margin:
    CROSSED = "CROSSED"
    ISOLATED = "ISOLATED"


# ── Position Mode (Futures) ──
class PosMode:
    ONE_WAY = "ONE_WAY"
    HEDGE = "HEDGE"


# ── Paper/Real Mode Keys ──
class Mode:
    PAPER = "paper"
    REAL = "real"
