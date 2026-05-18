"""DART disclosure type classifier + normalization (Track 3 Sub-task 3B).

Maps raw DART `report_nm` strings to a small Tier S/A/B/C enum used by
research scripts. Encapsulates the messy Korean disclosure naming conventions
in one place so consumers can filter without re-deriving regex grammar.

Tier (per `.claude/plans/track3_dart_pipeline_design.md` §6.1):
- S = paradigm-grade (잠정실적 / 영업실적 정정 / 가이던스)
- A = useful (5% 대량보유 / 자기주식 / 대주주 변동)
- B = informational (정기보고서 / IR / 영업양수도)
- C = noise (안내공시 / 일반)

Entry-side vs exit-side classification follows Lesson #27 (amended): immediate
demand-creating events (e.g. earnings surprise → next-bar gap) vs. delayed/
indirect events (e.g. 5% reporting, 자기주식 매입 집행).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tier(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"


class Side(str, Enum):
    ENTRY_IMMEDIATE = "entry_immediate"  # event itself moves price next bar
    ENTRY_DELAYED = "entry_delayed"      # event signals future demand (e.g. 자기주식 announce)
    EXIT = "exit"                        # event reflects past flow (e.g. 5% report)
    NEUTRAL = "neutral"                  # info-only / cleanup


@dataclass(frozen=True)
class DisclosureKind:
    code: str          # short machine token (e.g. "earnings_prelim_consolidated")
    tier: Tier
    side: Side
    label: str         # human label


# ── Tier S: 잠정실적 + 가이던스 ───────────────────────────────────────────────
EARNINGS_PRELIM_CONSOLIDATED = DisclosureKind(
    "earnings_prelim_consolidated", Tier.S, Side.ENTRY_IMMEDIATE,
    "연결재무제표기준영업(잠정)실적(공정공시)",
)
EARNINGS_PRELIM_STANDALONE = DisclosureKind(
    "earnings_prelim_standalone", Tier.S, Side.ENTRY_IMMEDIATE,
    "영업(잠정)실적(공정공시)",
)
EARNINGS_GUIDANCE_AMEND = DisclosureKind(
    "earnings_guidance_amend", Tier.S, Side.ENTRY_IMMEDIATE,
    "매출액또는손익구조30%(대규모법인은15%)이상변경",
)
# ── Tier A: 자기주식 / 5% / 지분 ─────────────────────────────────────────────
TREASURY_BUYBACK = DisclosureKind(
    "treasury_buyback", Tier.A, Side.ENTRY_DELAYED,
    "주요사항보고서(자기주식취득결정)",
)
TREASURY_DISPOSAL = DisclosureKind(
    "treasury_disposal", Tier.A, Side.ENTRY_DELAYED,
    "주요사항보고서(자기주식처분결정)",
)
FIVE_PCT_REPORT = DisclosureKind(
    "five_pct_report", Tier.A, Side.EXIT,
    "주식등의대량보유상황보고서",
)
EXEC_HOLDING = DisclosureKind(
    "exec_holding", Tier.A, Side.EXIT,
    "임원ㆍ주요주주특정증권등소유상황보고서",
)
# ── Tier B / C ────────────────────────────────────────────────────────────────
PERIODIC_REPORT = DisclosureKind("periodic_report", Tier.B, Side.NEUTRAL, "정기보고서")
EARNINGS_NOTICE = DisclosureKind("earnings_notice", Tier.C, Side.NEUTRAL,
                                  "결산실적공시예고(안내공시)")
OTHER = DisclosureKind("other", Tier.C, Side.NEUTRAL, "기타")


def classify(report_nm: str) -> DisclosureKind:
    """Map raw DART report_nm to a DisclosureKind. Strips amendment prefixes."""
    if not report_nm:
        return OTHER
    nm = report_nm.strip()

    # Strip [기재정정] / [첨부정정] / [정정] prefixes — same event, just amended
    for prefix in ("[기재정정]", "[첨부정정]", "[정정]"):
        if nm.startswith(prefix):
            nm = nm[len(prefix):].strip()

    has_jamjeong = "잠정" in nm and "실적" in nm
    has_gongjeong = "공정공시" in nm

    if has_jamjeong and "연결" in nm:
        return EARNINGS_PRELIM_CONSOLIDATED
    if has_jamjeong and has_gongjeong:
        return EARNINGS_PRELIM_STANDALONE
    if "손익구조" in nm or "매출액또는손익구조" in nm.replace(" ", ""):
        return EARNINGS_GUIDANCE_AMEND

    if "자기주식취득" in nm:
        return TREASURY_BUYBACK
    if "자기주식처분" in nm:
        return TREASURY_DISPOSAL
    if "주식등의대량보유" in nm:
        return FIVE_PCT_REPORT
    if "임원" in nm and "소유상황" in nm:
        return EXEC_HOLDING

    if "결산실적공시예고" in nm or "안내공시" in nm:
        return EARNINGS_NOTICE
    if any(x in nm for x in ("사업보고서", "반기보고서", "분기보고서")):
        return PERIODIC_REPORT

    return OTHER


def is_earnings_event(report_nm: str) -> bool:
    """True if disclosure is a 잠정실적 publication (H1 trigger)."""
    k = classify(report_nm)
    return k in (EARNINGS_PRELIM_CONSOLIDATED, EARNINGS_PRELIM_STANDALONE)


def is_subsidiary_only(report_nm: str) -> bool:
    """True for 자회사의 주요경영사항 variants — parent stock_code is the
    subsidiary's parent, so price impact is diluted. Excluded from H1 core."""
    return "자회사의 주요경영사항" in (report_nm or "")
