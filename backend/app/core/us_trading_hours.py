"""
US Equity Market Trading Hours (NYSE/NASDAQ) — KST 서버 기준.

왜 별도 모듈인가:
    live_engine 의 장중 판정은 KRX 09:00~15:30 KST 하드코딩이다. 미국장은
    (a) 서머타임에 따라 KST 기준 시각이 1시간 통째로 움직이고,
    (b) KST 자정을 넘겨 이틀에 걸치며,
    (c) 휴장일 달력이 KRX 와 전혀 다르다.
    따라서 시각 판정을 한 곳으로 모은다.

정규장 (ET 09:30~16:00):
    서머타임(3월 2주 일 ~ 11월 1주 일): KST 22:30 ~ 익일 05:00
    표준시                            : KST 23:30 ~ 익일 06:00
연장 세션:
    프리마켓 ET 04:00~09:30, 애프터 ET 16:00~20:00 (키움 분봉에 포함되어 내려옴)

DST 는 추측하지 않고 zoneinfo(America/New_York) 로 계산한다.
휴장일은 NYSE 규칙 기반 산출 — 고정일(관측일 이동 포함) + 요일규칙 +
부활절 기반 Good Friday. 조기폐장(ET 13:00)도 반영한다.
"""

import logging
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Optional, Set
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")

PRE_MARKET_OPEN = time(4, 0)
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)
AFTER_MARKET_CLOSE = time(20, 0)

# 정규장 1일 분봉 수. 09:30 시가봉 ~ 16:00 종가동시호가봉을 모두 포함해 391개.
# (실측: 16:00 봉 거래량 9.4M = 종가 동시호가, 16:01 봉은 4.5k로 급감)
REGULAR_MINUTES_PER_DAY = 391
EARLY_CLOSE_MINUTES_PER_DAY = 211


class MarketPhase(str, Enum):
    CLOSED = "closed"
    PRE = "pre"
    REGULAR = "regular"
    AFTER = "after"


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """그 달의 n번째 특정 요일 (weekday: 월=0)."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """그 달의 마지막 특정 요일."""
    if month == 12:
        d = date(year, 12, 31)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    """부활절 (Anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(d: date) -> Optional[date]:
    """고정일 휴장의 관측일. 토요일이면 전 금요일, 일요일이면 다음 월요일."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


_holiday_cache: dict[int, Set[date]] = {}
_early_close_cache: dict[int, Set[date]] = {}


def get_holidays(year: int) -> Set[date]:
    """해당 연도 NYSE 정규 휴장일 (관측일 반영)."""
    if year in _holiday_cache:
        return _holiday_cache[year]

    days = {
        _observed(date(year, 1, 1)),                  # 신정
        _nth_weekday(year, 1, 0, 3),                  # MLK Day (1월 3번째 월)
        _nth_weekday(year, 2, 0, 3),                  # Presidents Day (2월 3번째 월)
        _easter(year) - timedelta(days=2),            # Good Friday
        _last_weekday(year, 5, 0),                    # Memorial Day (5월 마지막 월)
        _nth_weekday(year, 9, 0, 1),                  # Labor Day (9월 1번째 월)
        _nth_weekday(year, 11, 3, 4),                 # Thanksgiving (11월 4번째 목)
        _observed(date(year, 7, 4)),                  # Independence Day
        _observed(date(year, 12, 25)),                # Christmas
    }
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))        # Juneteenth (2022~)

    days = {d for d in days if d is not None and d.year == year}
    _holiday_cache[year] = days
    return days


def get_early_closes(year: int) -> Set[date]:
    """조기폐장일 (ET 13:00 종료): 독립기념일 전날, 추수감사절 다음날, 크리스마스 이브."""
    if year in _early_close_cache:
        return _early_close_cache[year]

    holidays = get_holidays(year)
    candidates = {
        date(year, 7, 3),
        _nth_weekday(year, 11, 3, 4) + timedelta(days=1),   # Black Friday
        date(year, 12, 24),
    }
    days = {d for d in candidates if d.weekday() < 5 and d not in holidays}
    _early_close_cache[year] = days
    return days


def is_trading_day(d: date) -> bool:
    """주말/휴장일이 아닌 정규 거래일 여부 (미국 현지 날짜 기준)."""
    return d.weekday() < 5 and d not in get_holidays(d.year)


def is_early_close(d: date) -> bool:
    return d in get_early_closes(d.year)


def regular_close_time(d: date) -> time:
    return EARLY_CLOSE if is_early_close(d) else REGULAR_CLOSE


def minutes_in_session(d: date) -> int:
    """해당 거래일의 정규장 분봉 개수."""
    return EARLY_CLOSE_MINUTES_PER_DAY if is_early_close(d) else REGULAR_MINUTES_PER_DAY


def now_et(now: datetime = None) -> datetime:
    """현재(또는 주어진) 시각을 ET aware datetime 으로.

    naive datetime 은 KST 서버 로컬 시각으로 간주한다(이 시스템의 기본 규약).
    """
    if now is None:
        return datetime.now(ET)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    return now.astimezone(ET)


def to_us_business_date(ts: datetime) -> date:
    """KST naive 타임스탬프 -> 미국 현지 영업일(ET 날짜).

    KST 22:30~05:00 세션이 ET 로는 같은 날짜에 속한다는 점을 zoneinfo 로 처리.
    """
    return now_et(ts).date()


def get_phase(now: datetime = None) -> MarketPhase:
    """현재 세션 국면."""
    et = now_et(now)
    today = et.date()
    if not is_trading_day(today):
        return MarketPhase.CLOSED

    t = et.time()
    close_t = regular_close_time(today)
    if PRE_MARKET_OPEN <= t < REGULAR_OPEN:
        return MarketPhase.PRE
    # 종가 동시호가(정확히 16:00)까지 정규장으로 본다 — classify_session 주석 참조
    if REGULAR_OPEN <= t <= close_t:
        return MarketPhase.REGULAR
    if close_t < t < AFTER_MARKET_CLOSE:
        return MarketPhase.AFTER
    return MarketPhase.CLOSED


def is_market_open(now: datetime = None, include_extended: bool = False) -> bool:
    """정규장 개장 여부. include_extended=True 면 프리/애프터도 개장으로 본다."""
    phase = get_phase(now)
    if phase == MarketPhase.REGULAR:
        return True
    return include_extended and phase in (MarketPhase.PRE, MarketPhase.AFTER)


def next_open(now: datetime = None) -> datetime:
    """다음 정규장 개장 시각 (KST aware). 이미 개장 중이면 현재 세션의 개장 시각."""
    et = now_et(now)
    today = et.date()

    if is_trading_day(today) and et.time() < REGULAR_OPEN:
        candidate = today
    else:
        candidate = today + timedelta(days=1)
        while not is_trading_day(candidate):
            candidate += timedelta(days=1)

    open_et = datetime.combine(candidate, REGULAR_OPEN, tzinfo=ET)
    return open_et.astimezone(KST)


def session_bounds_kst(business_date: date) -> tuple[datetime, datetime]:
    """미국 영업일의 정규장 시작/종료를 KST naive 로 반환.

    예) 2026-07-30(서머타임) -> (2026-07-30 22:30, 2026-07-31 05:00)
    """
    open_et = datetime.combine(business_date, REGULAR_OPEN, tzinfo=ET)
    close_et = datetime.combine(business_date, regular_close_time(business_date), tzinfo=ET)
    return (
        open_et.astimezone(KST).replace(tzinfo=None),
        close_et.astimezone(KST).replace(tzinfo=None),
    )


def last_completed_business_date(now: datetime = None) -> date:
    """모든 세션이 끝나 값이 확정된 마지막 미국 영업일.

    영업일 D 의 마지막 세션은 오버나이트(ET 20:00 ~ D+1 04:00)다. 따라서 D 는
    ET 기준 D+1 04:00 이 지나야 확정된다. 그 전에 조회한 일봉은 오버나이트가
    진행 중이라 종가가 계속 움직인다 — 백테스트에 넣으면 미래 정보 오염이자
    재현 불가능한 값이 된다.

    실측 근거(2026-07-30, 오버나이트 진행 중 시점):
        SPY +0.54% / QQQ +1.32% / SOXX +3.77% — 정규장 종가 대비 일봉 종가 괴리.
        완결된 날들의 중앙 괴리는 0.04~0.09% 수준.
    """
    et = now_et(now)
    cursor = et.date() if et.time() >= PRE_MARKET_OPEN else et.date() - timedelta(days=1)
    d = cursor - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def classify_session(et_ts: datetime) -> str:
    """ET naive 타임스탬프 -> 세션 구분.

    키움 미국 분봉은 정규장 외에 프리/애프터/오버나이트(Blue Ocean) 체결까지
    함께 내려주므로, 전략이 구간을 골라 쓸 수 있게 태깅한다.

    분봉은 시각 시작 기준(start-stamped)이다. 09:30 봉이 시가 동시호가,
    16:00 봉이 종가 동시호가를 담으므로 정규장은 09:30~16:00 '양끝 포함'
    391봉이다. (실측: 09:30 봉 950k주 vs 09:29 봉 4.6k주 / 16:00 봉 9.4M주
    vs 16:01 봉 4.5k주)
    """
    t = et_ts.time()
    close_t = regular_close_time(et_ts.date())
    if PRE_MARKET_OPEN <= t < REGULAR_OPEN:
        return MarketPhase.PRE.value
    if REGULAR_OPEN <= t <= close_t:
        return MarketPhase.REGULAR.value
    if close_t < t < AFTER_MARKET_CLOSE:
        return MarketPhase.AFTER.value
    return "overnight"


def et_to_kst(et_ts: datetime) -> datetime:
    """ET naive -> KST naive 변환 (DST 는 zoneinfo 가 처리)."""
    return et_ts.replace(tzinfo=ET).astimezone(KST).replace(tzinfo=None)


def kst_to_et(kst_ts: datetime) -> datetime:
    """KST naive -> ET naive 변환."""
    return kst_ts.replace(tzinfo=KST).astimezone(ET).replace(tzinfo=None)


def describe(now: datetime = None) -> dict:
    """운영 로그/대시보드용 한 줄 상태."""
    et = now_et(now)
    phase = get_phase(now)
    nxt = next_open(now)
    return {
        "phase": phase.value,
        "is_open": phase == MarketPhase.REGULAR,
        "et_time": et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "kst_time": et.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "is_trading_day": is_trading_day(et.date()),
        "is_early_close": is_early_close(et.date()),
        "next_open_kst": nxt.strftime("%Y-%m-%d %H:%M:%S"),
    }
