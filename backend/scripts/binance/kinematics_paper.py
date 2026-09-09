"""위약 승률 운동학 — 전진 페이퍼 (System-2 시뮬레이션).

## 무엇인가

동결 문서(`runs/research_track/tick_placebo_kinematics_frozen.md` 개정 2)의
규칙을 **실시간으로** 돌려 전진 자료를 만든다. 실계좌를 건드리지 않는다.

연구 하네스와 **완전히 같은 경로**를 쓴다 — 같은 틱 파일, 같은 1분봉, 같은
신호식, 같은 체결 규약(봉 종가). 경로가 갈리면 페이퍼가 연구를 검증하지 못한다.

## 규칙 (동결 · 바꾸지 마라)

    지평 60분 · 창 360분 · 간격 180분 · N_eff = 창/지평 = 6
    밴드  -1.25 <= z_vel <= -0.25      상한이 핵심 — 초판은 상한이 없어 -18.8%
    배제  z_acc >= +0.5
    생존  직전 60분 분당 체결 중앙 >= 5
    슬롯 10 · 자본 분할 · 같은 종목 중복 금지
    보유 120분 · 익절·손절 없음 · 롱만
    앵커 벽시계 5분 격자

## 상태를 파일에 남긴다

프로세스가 죽어도 열린 포지션을 잃지 않는다. 재기동 시 상태를 읽고 이어간다.
⚠ 상태를 메모리에만 두면 PM2 재시작 한 번에 원장이 끊긴다.

## 페이퍼가 답하는 것 / 못 하는 것

  답한다   동결 규칙이 **앞으로도** 같은 부호를 내는가
  못 한다  체결 현실(지정가 대기·슬리피지·수수료 등급). 봉 종가 체결 가정이다

사용:
  python3 -m scripts.binance.kinematics_paper --once      # 한 사이클만
  python3 -m scripts.binance.kinematics_paper             # 상주
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.binance import tickbars

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "kinematics_paper"

# 그림자용 후보 풀에 남길 방향별 상위 개수. 슬롯 2 에는 넘치게 충분하다.
POOL_KEEP = 25

# 손절당한 종목의 재진입 냉각(분). 0 이면 끔 — **기본은 꺼짐**이라
# 기존 갈래의 동작이 바뀌지 않는다. 영구 금지가 아니라 시간 제한이다.
STOP_COOLDOWN_MIN = 0
log = logging.getLogger("kine_paper")

# ── 동결 파라미터 — 이 블록을 고치면 전진 검정이 아니다
# 알림 부제에 찍히는 갈래명. 승격으로 갈래가 바뀌어도 여기가 옛 이름으로
# 남으면 **알림만 조용히 틀린다**(교훈#102). 환경변수로 따라가게 한다.
TRACK_NAME = os.environ.get("KINE_NAME", "운동학")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
SLOTS_DEFAULT, HOLD, STEP = 10, 120, 5
# 숏은 밴드가 거울이다. 집단 검정(최근 24h)에서 숏 쪽 초과가 오히려 컸다 —
#   롱 밴드(-1.25~-0.25) 가중 +0.192%p · 숏 밴드(+0.25~+1.25) **+0.257%p**
# ⚠ 그래도 롱과 손익 구조가 다르다: ① 숏 위약이 음수(-0.245% @120분)라 절대
#   손익이 0.42%p 불리 ② 위쪽 꼬리가 무한(오늘 페이퍼 최고 +7.41%) ③ 펀딩비.
#   그래서 펀딩을 원장에 **기록**한다 — 추측으로 두면 영영 모른다.
FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
FUNDING_HOURS = (0, 8, 16)          # UTC 정산 시각
# ⚠ 슬롯 수만 인자로 연다. 나머지 신호·밴드·보유는 동결분이라 손대지 않는다.
#   슬롯마다 상태·원장을 **따로** 둔다 — 한 디렉터리를 공유하면 서로 덮어쓴다.
SLOTS = SLOTS_DEFAULT


def funding_rates() -> dict:
    """전 종목 최근 펀딩률 — 한 번의 호출로 받는다. 실패하면 빈 표."""
    import json as _j
    import urllib.request
    try:
        with urllib.request.urlopen(FUNDING_URL, timeout=15) as r:
            return {x["symbol"]: float(x.get("lastFundingRate") or 0.0)
                    for x in _j.load(r)}
    except Exception as e:                                      # noqa: BLE001
        log.warning("펀딩률 조회 실패(0 으로 둔다): %s", str(e)[:80])
        return {}


def cooling(st, now) -> set:
    """지금 재진입이 막힌 종목. **만료분은 지우고** 돌려준다.

    ⚠ 안 지우면 상태 파일이 무한히 자란다.
    ⚠ 경계는 `>` 다 — 해제 시각이 되면 그 사이클부터 다시 잡을 수 있다.
    """
    if not st.cooldown:
        return set()
    t = pd.Timestamp(now)
    st.cooldown = {k: v for k, v in st.cooldown.items()
                   if pd.Timestamp(v) > t}
    return set(st.cooldown)


def funding_crossings(a: datetime, b: datetime) -> int:
    """보유 구간이 정산 시각을 몇 번 지나나."""
    n, t = 0, a
    while t < b:
        t += timedelta(hours=1)
        if t.hour in FUNDING_HOURS and t.minute == 0:
            if a < t <= b:
                n += 1
    return n
# ⚠ 수수료는 **왕복**이다 — 진입 한 번, 청산 한 번. 메이커 0.036%/다리.
#   2026-08-31 까지 편도 0.036% 만 빼고 있었다. 연구 하네스는 전부
#   `fee_rt = 0.072`(왕복)를 쓰는데 페이퍼만 절반이라 성적이 부풀었다 —
#   롱숏10 이 280거래에서 +12.10% 로 기록됐지만 실제는 +2.02% 였다.
#   같은 이름의 상수가 한쪽에선 편도, 한쪽에선 왕복으로 쓰인 사고다.
SESS_END = 8          # 아시아 세션 끝 (UTC 시)
MIN_LIVE_TR, FEE_ONE_WAY = 5.0, 0.036
# ⚠ 최대 손절(%). 0 이면 끈다. 14개월 8구성 실측에서 5% 가 최적이고
#   문턱을 올릴수록 단조 악화했다(2026-09-03).
STOP_PCT = 5.0
# 방향 신호(dir·impconf·impanti)의 되돌아보기(분). --dir-min 으로 덮는다.
DIR_MIN = 15
# 확인·역확인의 문턱(%). impconf 는 dir < -DIR_THR, impanti 는 dir > +DIR_THR.
#   2026-09-09 14일 5위상 실측에서 문턱 0 이 가장 나았고 올릴수록 나빠졌다
#   (역확인 >0 +3.28 → >1% +1.84 → >2% +0.67). --dir-thr 로 덮는다.
DIR_THR = 0.0
FEE_PCT = 2 * FEE_ONE_WAY          # 왕복 0.072%

_stop = False


def _sig(*_):
    global _stop
    _stop = True
    log.info("정지 신호 — 상태를 저장하고 끝낸다")


@dataclass
class State:
    equity: float = 1.0
    positions: list = None          # [{symbol, entry_ts, entry_px, exit_ts, stake}]
    n_trades: int = 0
    pending: list = None            # 지연 진입 대기열 [{symbol, sig_ts, enter_at}]
    # 손절당한 종목의 냉각 — {종목: 이 시각까지 재진입 금지(ISO)}
    #
    # ⚠ **상태에 남겨야 한다.** 메모리에만 두면 재기동 한 번에 풀린다.
    cooldown: dict = None

    def __post_init__(self):
        if self.positions is None:
            self.positions = []
        if self.pending is None:
            self.pending = []
        if self.cooldown is None:
            self.cooldown = {}


def load_state(p: Path) -> State:
    if not p.exists():
        return State()
    d = json.loads(p.read_text())
    # ⚠ 옛 상태 파일에는 pending 이 없다 — 없으면 빈 목록이다
    return State(equity=d["equity"], positions=d["positions"],
                 n_trades=d.get("n_trades", 0), pending=d.get("pending", []),
                 cooldown=d.get("cooldown", {}))


def save_state(p: Path, s: State) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=1))
    tmp.replace(p)                  # 원자적 교체 — 쓰다 죽어도 원장이 안 깨진다


def _maxrun(v) -> int:
    """가장 긴 동일값 연속 길이 — 테이커 방향이 얼마나 이어졌나."""
    a = np.asarray(v)
    if a.size == 0:
        return 0
    b = np.flatnonzero(np.diff(a) != 0)
    e = np.concatenate([[-1], b, [a.size-1]])
    return int(np.diff(e).max())


def bars(sym: str, since_ms: int) -> pd.DataFrame | None:
    """최근 구간의 1분봉. **틱은 읽지 않는다 — 접힌 봉을 읽는다.**

    ## 왜 (2026-09-01 · 민트 정지 사고)

    갈래 24개가 각자 521종목의 틱을 5분마다 통째로 풀어 메모리 20 GB 를
    요구했고 **서버가 통째로 멈췄다**. 실계좌가 54분 무방비였다.

    세 단계로 고쳤고, 앞의 둘은 **실측으로 기각된 길**이니 다시 파지 마라.

      ① `read_parquet(filters=)`  — 최고점 그대로(708 → 569 MB). 행묶음이
         1~6개뿐이라 통째로 풀린 뒤 걸러진다.
      ② `assign` 사슬 제거        — **차이 없다**(1,119 → 1,132 MB).
         최고점은 압축 해제 단계에서 이미 찍힌다.
      ③ 흘려읽기(배치 5만행)      — 1,129 → **258 MB**. 창을 두 배로 늘려도
         253 MB 로 안 늘었다. 메모리가 틱 양과 끊겼다.

    그래도 **같은 일을 14번 하는 구조**는 남았다(부하 12~17). 그래서 봉을
    한 번만 만들어 두고(`tickbars` · 수집기 flush 경로) 여기서는 읽기만
    한다. 봉이 없거나 낡았으면 틱에서 접는 ③으로 되돌아간다.

    ⚠ 되돌아가기는 **조용하면 안 된다**. 봉이 안 만들어지고 있는데 갈래가
      혼자 버티면 부하만 오르고 아무도 모른다 — 경고를 남긴다.
    """
    b = None
    try:
        b = tickbars.read_bars(sym, since_ms)
        if b is not None and not _bars_fresh(sym):
            b = None
    except Exception:                                          # noqa: BLE001
        b = None
    if b is None:
        fs = sorted((TICKS / sym).glob("*.parquet"))[-2:]
        if not fs:
            return None
        _warn_fallback(sym)
        try:
            b = tickbars.fold_ticks(fs, since_ms)
        except Exception:                                      # noqa: BLE001
            return None
    if b is None or float(b.ntr.sum()) < 500:
        return None
    return tickbars.finalize(b)



def held_range(sym: str, now: pd.Timestamp) -> tuple[float, float, float] | None:
    """보유 종목의 최근 10분 (저, 고, 마지막) 종가. 못 읽으면 None.

    ## 왜 있나 (2026-09-03 AKEUSDT · §28)

    손절 판정이 `sym in lo_cache` 였다 — **그 사이클에 신호가 안 나온 종목은
    손절을 조용히 건너뛰고 만기까지 갔다.** AKEUSDT 가 진입 대비 **+118%** 를
    지나갔는데 5% 손절이 안 걸렸다. 원장에는 `stopped=False` 로 남아 성공처럼
    보인다.

    ⚠ 하필 **손절이 필요한 순간**에 캐시가 빈다. 큰 역행은 거래량 폭발을
      동반하고, 그때 봉 파이프라인이 밀리거나 `signal_now` 의 되돌아보기
      요구량(imp 는 1500봉)을 못 채운다. 결함이 **가장 위험한 때** 발동한다.

    ⚠ 실거래는 거래소 STOP_MARKET 이라 무조건 발동한다. 그래서 이 결함은
      **페이퍼를 실거래보다 낙관적으로** 만든다 — 대조군으로 못 쓴다.
    """
    since = int((now - timedelta(minutes=30)).timestamp() * 1000)
    try:
        b = bars(sym, since)
    except Exception:                                          # noqa: BLE001
        return None
    if b is None or "cl" not in b or len(b) == 0:
        return None
    c = b.cl.to_numpy(float)
    c = c[np.isfinite(c)][-10:]
    if len(c) == 0:
        return None
    return float(c.min()), float(c.max()), float(c[-1])


_FB_SEEN: set[str] = set()


def _warn_fallback(sym: str) -> None:
    """되돌아가기는 종목당 한 번만 알린다 — 매 주기 521줄을 찍으면 안 읽는다."""
    if sym not in _FB_SEEN:
        _FB_SEEN.add(sym)
        log.warning("%s — 1분봉이 없거나 낡아 틱에서 접는다(메모리·CPU 를 "
                    "더 쓴다). 수집기의 봉 생성을 확인하라. 누적 %d종목",
                    sym, len(_FB_SEEN))


def _bars_fresh(sym: str, slack_s: float = 600.0) -> bool:
    """봉이 틱보다 뒤처지지 않았나. **분 단위로 비교하면 안 된다** —
    거래가 없는 종목은 봉이 정상적으로 오래 비어 있다. 파일 시각을 본다."""
    try:
        bt = max(f.stat().st_mtime for f in (tickbars.BARS / sym).glob("*.parquet"))
        tt = max(f.stat().st_mtime for f in (TICKS / sym).glob("*.parquet"))
    except ValueError:
        return False
    return bt >= tt - slack_s


def signal_now(b: pd.DataFrame, sig: str = "kine") -> dict | None:
    """지금 시점의 z_vel · z_acc · 생존 · 현재가. **후행만** 쓴다.

    ⚠ 되돌아보기 요구량은 **신호마다 다르다**. z_vel 은 790분이 필요하지만
      세션 이월(`sess`)은 아시아 세션 480분 + 여유면 된다. 하나로 묶어두면
      신규 편입 종목이 z_vel 문턱 때문에 5시간을 더 기다린다(2026-09-01 실측:
      신규 162종목이 609분 쌓였는데 790분 문턱에 걸려 신호 0건).
    """
    need = (SESS_END * 60 + 30 if sig == "sess"
            else 1500 if sig in ("imp", "rmz", "impconf", "impanti")  # 하루 후행 중앙값 + 60분 창
            else DIR_MIN + 30 if sig == "dir"   # 방향은 창 + 여유면 된다
            else 150 if sig in ("skew", "ac1")  # 60분 창 + 여유
            else WIN_H + WINDOW + 2 * DELTA + 10)
    if len(b) < need:
        return None
    cl = b.cl
    n = len(cl)
    fw = np.full(n, np.nan)
    c = cl.to_numpy(float)
    fw[:n - WIN_H] = c[WIN_H:] / c[:n - WIN_H] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    # ⚠ shift(WIN_H) — 승부가 끝난 앵커만 쓴다. 빼먹으면 미래참조다.
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    neff = max(WINDOW / WIN_H, 1.0)
    p = rate.clip(0.01, 0.99)
    se = np.sqrt(p * (1 - p) / neff)
    zv = (vel / (se * np.sqrt(2))).iloc[-1]
    za = (acc / (se * 2.0)).iloc[-1]
    live = b.ntr.rolling(60).median().shift(1).iloc[-1]
    # 방향 — 직전 DIR_MIN 분 수익(%). **후행만** 쓴다.
    #   2026-09-09 대표님 제안: "가격이 안 움직인 것보다 이미 역방향으로
    #   움직인 것을 고르는 편이 낫지 않은가". 두 가지로 구현된다 —
    #     dir      정렬 기준 자체를 방향으로 (낮은 쪽 숏)
    #     impconf  imp 최저 순은 두고 **꺾인 것만** 통과
    #   14일 격자에서 둘의 부호가 반대로 나왔다(dir +4.19 / impconf -0.99).
    #   최대통계량 p 0.105 로 통과 못 했으므로 **페이퍼로 나란히 재는 중**이다.
    dirret = (float((c[-1] / c[-1 - DIR_MIN] - 1.0) * 100.0)
              if n >= DIR_MIN + 1 else np.nan)
    # ⚠ sess 는 z_vel 을 안 쓴다. 봉이 790분 미만이면 zv·za 가 NaN 인데
    #   그걸로 걸러내면 세션 갈래가 신규 종목을 영영 못 본다.
    if sig in ("sess", "imp", "skew", "ac1", "rmz", "dir", "impconf",
               "impanti"):
        if not np.isfinite(live):
            return None
    elif not (np.isfinite(zv) and np.isfinite(za) and np.isfinite(live)):
        return None
    # 잡음 지배 점수의 두 재료 (최근 60분) — 순위는 앵커에서 매긴다
    fl60, n60 = b.flip.tail(60).sum(), b.ntr.tail(60).sum()
    dtm60 = b.dtm.tail(60).mean() if "dtm" in b else np.nan
    dts60 = b.dts.tail(60).mean() if "dts" in b else np.nan
    bump = float(fl60 / n60) if n60 > 0 else np.nan
    irr = float(dts60 / dtm60) if (np.isfinite(dtm60) and dtm60 > 0) else np.nan
    # 1시간 되돌림 — 부호를 뒤집어 **큰 값 = 롱**
    rev = float(-(c[-1] / c[-61] - 1.0) * 100.0) if n >= 61 else np.nan
    # 아시아 세션(00:00-08:00 UTC) 수익률 — 세션 이월 신호.
    #   **큰 값 = 그날 아시아에서 많이 오른 종목**. 4년 1,473일 실측에서
    #   아시아 상위를 미주 세션에 롱, 하위를 숏 치는 스프레드가 두 창 모두 양수
    #   (샤프 0.77~1.04 · 연 +42%). 신호는 08:00 UTC 에 끝나고 거래는 13:00 UTC
    #   에 시작하니 **다섯 시간 묵은 신호**인데, 더 신선한 유럽(08-13)보다
    #   잘 맞았다 — 단순 모멘텀이 아니라 시차 이월이라는 근거.
    idx0 = b.index[-1].normalize()
    m_ = (b.index >= idx0) & (b.index < idx0 + pd.Timedelta(hours=SESS_END))
    a_ = b.cl[m_].dropna()
    sess = (float((a_.iloc[-1] / a_.iloc[0] - 1.0) * 100.0)
            if len(a_) >= 240 else np.nan)          # 480분 중 절반은 있어야
    # 가격 충격 계수(아미후드) — |1분 수익| / 1분 거래대금.
    #   **자기 대비**로 본다: 최근 60분 평균 / 하루 후행 중앙값.
    #   수준만 쓰면 시가총액 순위를 다시 그린다.
    #   ⚠ 4.5일 틱 실측에서 최고 칸(보유 480분·상위숏3)이 +7.98% 였는데
    #     같은 구간 무작위 숏도 +2.06% 였다. 방향 ±1 이 둘 다 통과해
    #     **하락장 효과로 판정**했다 — 페이퍼는 그걸 실전에서 가리려는 것이다.
    imp = np.nan
    if "qv" in b and len(b) >= 120:
        ar = np.abs(np.diff(np.log(np.maximum(c, 1e-12)), prepend=np.nan))*100.0
        qv = b.qv.to_numpy(float)
        ai = pd.Series(ar/np.maximum(qv, 1e-9)).rolling(60).mean()
        med = ai.rolling(1440, min_periods=360).median().shift(1).iloc[-1]
        cur = ai.iloc[-1]
        if np.isfinite(cur) and np.isfinite(med) and med > 0:
            imp = float(cur/med)
    # 체결 크기 쏠림 — 90분위 / 중앙값의 최근 60분 평균.
    #   ⚠ 틱 4.6일 실측 최고 칸(보유 480분 · 상위숏3 · 방향+1)이 누적 +4.07%
    #     였는데 같은 다리 무작위도 +2.86% 였다. 초과는 +1.19%p 이고
    #     최대통계량 **p 0.545** 로 통과 못 했다. 방향 ±1 이 둘 다 상위에 있어
    #     하락장 의심이 있다 — 페이퍼는 그걸 가리려는 것이다.
    qskew = np.nan
    if "q90" in b and "qmed" in b and len(b) >= 70:
        r_ = (b.q90/b.qmed.replace(0, np.nan)).rolling(60).mean().iloc[-1]
        if np.isfinite(r_):
            qskew = float(r_)
    # 체결 자기여기 — 분당 체결 수의 **1차 자기상관**(최근 60분).
    #   양수면 체결이 체결을 부른다(정보 거래). 잡거래는 포아송이라 0 근처다.
    #   ⚠ 이미 닫힌 `irr` 은 **봉 안** 간격의 변동계수라 다른 것을 잰다.
    #   ⚠ 틱 4.6일 실측: ac1 방향+1 상위숏3 보유480분 → 위약대비 +0.2586.
    #     최대통계량 **p 0.130** 으로 통과는 못 했다. 다만 방향 비대칭이 있는
    #     유일한 가설이었다(+1 이 -1 의 3배).
    ac1 = np.nan
    if len(b) >= 70:
        x = b.ntr.tail(60).to_numpy(float)
        if len(x) == 60 and np.std(x[1:]) > 0 and np.std(x[:-1]) > 0:
            ac1 = float(np.corrcoef(x[1:], x[:-1])[0, 1])
    # 테이커 최장 연속 — 최근 60분 최대 / 하루 후행 중앙(자기 대비).
    #   ⚠ 틱 4.6일 실측 최고 칸(보유 480분·상위숏3·방향+1) 위약대비 +0.5551 ·
    #     최대통계량 **p 0.030**(다섯 가설 중 유일한 통과) · 날짜t>2 인 칸 7개.
    #   ⚠ 다만 내가 "핵심"이라 선언한 정규화 판본(run_excess, 매수 비율에서
    #     오는 몫을 뺀 것)은 3등이었다 — 이 신호가 잡는 건 "우연을 넘는
    #     지속성"이 아니라 **그냥 연속이 길다는 사실**이다.
    #   ⚠ 방향 ±1 이 둘 다 상위에 있어 하락장 의심이 남는다(교훈#118).
    rmz = np.nan
    if "rmax" in b and len(b) >= 200:
        rm = b.rmax.astype(float)
        cur = rm.tail(60).max()
        med = rm.rolling(1440, min_periods=360).median().shift(1).iloc[-1]
        if np.isfinite(cur) and np.isfinite(med) and med > 0:
            rmz = float(cur/med)
    # ⚠ 손절 판정용 — **경로**를 봐야 한다. 주기(5분) 종가만 보면 그 사이
    #   스친 손절을 놓친다. 최근 10분 1분봉의 최저·최고를 같이 넘긴다
    #   (주기가 5분이라 10분이면 빈틈 없이 덮는다).
    lo10 = float(np.nanmin(c[-10:])) if n >= 10 else float(c[-1])
    hi10 = float(np.nanmax(c[-10:])) if n >= 10 else float(c[-1])
    return {"z_vel": float(zv), "z_acc": float(za), "live": float(live),
            "px": float(c[-1]), "lo10": lo10, "hi10": hi10, "ts": b.index[-1],
            "bump": bump, "irr": irr, "rev": rev, "sess": sess, "imp": imp,
            "qskew": qskew, "ac1": ac1, "rmz": rmz, "dir": dirret}


def _tell(broker, text: str) -> None:
    """실거래 알림. 발송 실패가 **거래를 멈추면 안 된다.**"""
    if broker is None or not callable(getattr(broker, "notify", None)):
        return
    try:
        broker.notify(text)
    except Exception as exc:                                  # noqa: BLE001
        log.error("알림 발송 실패(거래는 계속한다): %s", exc)


def cycle(syms: list[str], st: State, ledger: Path, now: datetime,
          slots: int, short: bool, fr: dict, both: bool = False,
          delay: int = 0, hold: int = HOLD, pick: str = "zvel",
          sig: str = "kine", entry_hour: int = -1, broker=None,
          emit_pool: bool = False, margin_buffer: float = 0.95) -> dict:
    """`broker` 가 None 이면 **순수 페이퍼**다 — 기존 동작 그대로.

    None 이 아니면 진입·청산이 실제 주문으로 나가고, 체결가·수수료를
    거래소에서 받아 원장에 쓴다. 신호·밴드·선별·보유 규칙은 **한 줄도
    달라지지 않는다** — 달라지면 전진 검정과 비교가 깨진다."""
    sig_kind = sig
    since = int((now - timedelta(minutes=WIN_H + WINDOW + 2 * DELTA + 60))
                .timestamp() * 1000)
    if sig_kind in ("imp", "rmz", "impconf", "impanti"):
        # ⚠ 충격 계수·최장 연속은 **하루 후행 중앙값**이 필요하다. 기본 840분으로는
        #   못 만들고 신호가 전부 결측이 된다.
        since = int((now - timedelta(minutes=1560)).timestamp() * 1000)
    if sig_kind == "sess":
        # ⚠ 기본 되돌아보기(약 3.6시간)로는 아시아 세션(00:00-08:00 UTC)을
        #   못 덮는다. 그날 자정까지 늘린다 — 안 늘리면 신호가 전부 결측이 되고
        #   로그는 "후보 0"이라고만 말한다.
        d0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        since = min(since, int(d0.timestamp() * 1000))
    px_cache: dict[str, float] = {}
    lo_cache: dict[str, float] = {}
    hi_cache: dict[str, float] = {}
    cands = []
    for s in syms:
        b = bars(s, since)
        if b is None:
            continue
        sig = signal_now(b, sig_kind)
        if sig is None:
            continue
        px_cache[s] = sig["px"]
        lo_cache[s] = sig.get("lo10", sig["px"])
        hi_cache[s] = sig.get("hi10", sig["px"])
        if sig["live"] < MIN_LIVE_TR:
            continue
        if sig_kind == "rmz":
            # ⚠⚠ 부호 — 실측 최고 칸은 **rmz 가 가장 높은 3종목을 숏**이다.
            #   엔진은 z_vel 이 높은 쪽을 숏 하므로 **그대로** 넣는다.
            if not np.isfinite(sig.get("rmz", np.nan)):
                continue
            cands.append({"symbol": s, "side_short": None,
                          **{**sig, "z_vel": sig["rmz"]}})
            continue
        if sig_kind == "ac1":
            # ⚠⚠ 부호 — 실측 최고 칸은 **ac1 이 가장 높은 3종목을 숏**이다.
            #   엔진은 z_vel 이 높은 쪽을 숏 하므로 **그대로** 넣는다.
            if not np.isfinite(sig.get("ac1", np.nan)):
                continue
            cands.append({"symbol": s, "side_short": None,
                          **{**sig, "z_vel": sig["ac1"]}})
            continue
        if sig_kind == "skew":
            # ⚠⚠ 부호 — 실측 최고 칸은 **qskew 가 가장 높은 3종목을 숏**이다
            #   (체결 크기 분포가 가장 쏠린 종목). 엔진은 z_vel 이 높은 쪽을
            #   숏 하므로 **그대로** 넣는다(뒤집지 않는다).
            #   스프레드에서는 낮은 qskew 가 롱이 된다.
            if not np.isfinite(sig.get("qskew", np.nan)):
                continue
            cands.append({"symbol": s, "side_short": None,
                          **{**sig, "z_vel": sig["qskew"]}})
            continue
        if sig_kind == "imp":
            # ⚠⚠ 부호 — 실측 최고 칸은 **amihud_z 가 가장 낮은 3종목을 숏**이다
            #   (거래는 많은데 가격이 안 움직인 종목). 엔진은 z_vel 이 높은
            #   쪽을 숏 하므로 **부호를 뒤집어** 넣는다.
            #   스프레드 갈래에서는 낮은 z_vel(= 높은 amihud_z)이 롱이 된다.
            if not np.isfinite(sig.get("imp", np.nan)):
                continue
            cands.append({"symbol": s, "side_short": None,
                          **{**sig, "z_vel": -sig["imp"]}})
            continue
        if sig_kind == "dir":
            # ⚠⚠ 부호 — **직전 DIR_MIN 분 수익이 가장 낮은** 3종목을 숏
            #   (이미 꺾인 것을 따라간다 = 모멘텀 지속). 엔진은 z_vel 이 높은
            #   쪽을 숏 하므로 **부호를 뒤집어** 넣는다.
            if not np.isfinite(sig.get("dir", np.nan)):
                continue
            cands.append({"symbol": s, "side_short": None,
                          **{**sig, "z_vel": -sig["dir"]}})
            continue
        if sig_kind == "impconf":
            # imp 최저 순은 그대로 두고 **직전 DIR_MIN 분 수익 < 0 인 것만**
            #   통과시킨다 — 대표님 제안의 '확인' 해석.
            if not np.isfinite(sig.get("imp", np.nan)):
                continue
            if not (np.isfinite(sig.get("dir", np.nan))
                    and sig["dir"] < -DIR_THR):
                continue
            cands.append({"symbol": s, "side_short": None,
                          **{**sig, "z_vel": -sig["imp"]}})
            continue
        if sig_kind == "impanti":
            # **역확인** — imp 최저 순은 두고 직전 DIR_MIN 분이 **여전히 오르는
            #   것만** 통과. 연료(imp)는 탔는데 가격이 아직 오르는 자리다.
            #   확인숏(impconf)의 거울이고, 14일 실측에서 확인숏보다 4배 나았다
            #   (+3.28 vs +0.83) — imp 가 **선행** 신호라 꺾인 뒤엔 늦다는 뜻.
            #   다만 필터 없는 기준(+3.77)은 못 넘었다.
            if not np.isfinite(sig.get("imp", np.nan)):
                continue
            if not (np.isfinite(sig.get("dir", np.nan))
                    and sig["dir"] > DIR_THR):
                continue
            cands.append({"symbol": s, "side_short": None,
                          **{**sig, "z_vel": -sig["imp"]}})
            continue
        if sig_kind == "sess":
            # ⚠⚠ 부호 — 아래 선별은 **z_vel 낮은 순으로 롱**을 고른다.
            #   sess 는 클수록 아시아에서 많이 **오른** 것이고 우리는 그걸
            #   **사고 싶다**. 그래서 부호를 뒤집어 넣는다.
            #   (2026-08-31 되돌림 갈래에서 이 자리를 안 뒤집어 양쪽 다 중간에서
            #    집었고, 로그는 "예약 10 · 롱5 숏5"로 정상처럼 보였다 — 교훈#88.
            #    첫 진입 뒤 원장의 sess 값이 롱은 큰 양수, 숏은 큰 음수인지
            #    **반드시 눈으로 확인할 것**.)
            if not np.isfinite(sig.get("sess", np.nan)):
                continue
            cands.append({"symbol": s, "side_short": None,
                          **{**sig, "z_vel": -sig["sess"]}})
            continue
        if sig_kind == "rev":
            # ⚠ 되돌림 신호에는 **밴드가 없다**. 살아 있는 종목 전부가 후보이고
            #   횡단면 순위로만 롱·숏을 가른다. z_vel 자리에 되돌림을 넣어
            #   아래 선별 로직을 그대로 쓴다(큰 값 = 롱).
            if not np.isfinite(sig.get("rev", np.nan)):
                continue
            # ⚠ 부호 주의 — 아래 선별은 **z_vel 낮은 순**으로 롱을 고른다
            #   (운동학에서 z_vel 이 음수일수록 많이 떨어진 것). rev 는 반대로
            #   클수록 많이 떨어진 것이라 **한 번 더 뒤집어** 넣는다.
            #   안 뒤집으면 양쪽 다 **중간에서** 집는다(2026-08-31 실측 확인).
            cands.append({"symbol": s, "side_short": None,
                          **{**sig, "z_vel": -sig["rev"]}})
            continue
        # 숏은 밴드·가속 조건이 거울이다
        ok_l = (Z_LO <= sig["z_vel"] <= Z_HI and sig["z_acc"] < ACC_MAX)
        ok_s = (-Z_HI <= sig["z_vel"] <= -Z_LO and sig["z_acc"] > -ACC_MAX)
        if both:
            if ok_l:
                cands.append({"symbol": s, "side_short": False, **sig})
            elif ok_s:
                cands.append({"symbol": s, "side_short": True, **sig})
        elif (ok_s if short else ok_l):
            cands.append({"symbol": s, "side_short": short, **sig})

    # ── 손절 · 만기 청산
    #
    # ⚠ **손절은 만기보다 먼저** 본다. 14개월 패널 실측(2026-09-03):
    #     8구성 전부에서 손절 5% 가 거래당을 개선했고 문턱을 올릴수록
    #     단조 악화했다. 최악 거래가 **-160.58%**(숏인데 종목이 2.6배 급등)
    #     였고 3슬롯이면 자본의 -53% 다.
    #       imp short3   -0.0654% → **+0.0879%**  복리 -89.4% → **+114.1%**
    #       ac1 short3   -0.0259% → +0.0223%
    #       낙폭         91.8% → 47.6%
    #     10% 는 발동률 7.7% 로 꼬리를 덜 막는다. 5% 는 18.8% 를 거른다.
    # ⚠ 손절은 **엣지가 아니라 생존 장치**다. 6/8 은 여전히 적자다.
    # ⚠ 체결은 손절가 정확히로 본다(지정가). 갭이 나면 실제는 더 나쁘다 —
    #   백테스트가 못 재는 영역이라 낙관 쪽으로 치우쳐 있다.
    # ── 보유 종목은 **반드시** 시세를 갖춘다 (2026-09-09 수정 · §28)
    #
    # 후보 훑기에서 신호가 안 나온 종목은 위 캐시에 없다. 예전엔 그러면
    # 손절 판정을 **조용히 건너뛰었다.** 보유 중인 것만 따로 읽어 채운다 —
    # 슬롯 수만큼이라 비용이 없다. 그래도 못 읽으면 **크게 남긴다.**
    for _p in st.positions:
        _s = _p["symbol"]
        if _s in px_cache:
            continue
        _r = held_range(_s, now)
        if _r is None:
            log.critical("%s 보유 중인데 시세를 못 읽었다 — **손절 판정 불가**. "
                         "거래소를 직접 확인하라", _s)
            continue
        px_cache[_s], lo_cache[_s], hi_cache[_s] = _r[2], _r[0], _r[1]
        log.warning("%s 신호 캐시에 없어 시세를 직접 읽었다 — 보유 종목 보호", _s)

    closed = []
    keep = []
    # ── 실거래: 거래소 포지션을 **한 번만** 읽는다
    #
    # ⚠ 실거래에서 손절은 봉이 아니라 **거래소가** 판정한다. 우리가 걸어둔
    #   STOP_MARKET 이 트리거되면 포지션이 사라져 있다. 그걸 "청산됐다"로
    #   읽어야 원장이 맞는다.
    # ⚠ 조회 실패는 **빈 결과가 아니다**(교훈#106). None 이면 이번 사이클의
    #   청산을 통째로 미룬다 — 모르는 상태에서 장부를 닫으면 거래소에 남은
    #   포지션이 보호 없는 고아가 된다.
    live_pos = None
    if broker is not None:
        live_pos = broker.positions(strict=True)
        if live_pos is None:
            log.error("거래소 포지션 조회 실패 — **이번 사이클 청산을 미룬다**")
    for p in st.positions:
        sym = p["symbol"]
        if broker is not None and live_pos is None:
            keep.append(p)                     # 모르면 손대지 않는다
            continue
        stop_hit = False
        exch_gone = False
        if broker is not None:
            # 거래소에서 사라졌다 = 손절이 트리거됐거나 누가 수동 청산했다
            exch_gone = sym not in live_pos
        elif STOP_PCT > 0 and sym in lo_cache:
            if p.get("short"):
                stop_hit = hi_cache[sym] >= p["entry_px"] * (1 + STOP_PCT/100.0)
            else:
                stop_hit = lo_cache[sym] <= p["entry_px"] * (1 - STOP_PCT/100.0)
        expired = pd.Timestamp(p["exit_ts"]) <= pd.Timestamp(now)
        if stop_hit or expired or exch_gone:
            px = px_cache.get(p["symbol"])
            if px is None and not exch_gone:
                keep.append(p)                 # 시세 없으면 다음 사이클로 미룬다
                continue
            if broker is not None:
                short_leg = bool(p.get("short"))
                if exch_gone:
                    # ⚠ 체결가를 **추측하지 않는다.** 거래소 체결 내역에서 받는다.
                    fpx, _ = broker.closing_fill(sym, short_leg)
                    if fpx <= 0:
                        log.error("%s 거래소에서 사라졌는데 청산 체결가를 못 "
                                  "찾았다 — 다음 사이클로 미룬다", sym)
                        keep.append(p)
                        continue
                    px = fpx
                    stop_hit = True            # 만기 전이면 손절로 본다
                    if expired:
                        stop_hit = False       # 만기와 겹치면 만기로 본다
                    log.warning("%s 거래소 청산 감지 — 체결가 %.8g (%s)", sym, px,
                                "손절" if stop_hit else "만기")
                else:
                    apx = broker.close(sym, short_leg)
                    if apx is None:
                        log.error("%s 청산 실패 — 다음 사이클로 미룬다", sym)
                        keep.append(p)
                        continue
                    px = apx
                ret = 100.0 * (px / p["entry_px"] - 1.0)
                if short_leg:
                    ret = -ret
            elif stop_hit:
                # 손절가에 나갔다고 본다 — 방향과 무관하게 -STOP_PCT
                ret = -STOP_PCT
                px = p["entry_px"] * ((1 + STOP_PCT/100.0) if p.get("short")
                                      else (1 - STOP_PCT/100.0))
            else:
                ret = 100.0 * (px / p["entry_px"] - 1.0)
                if p.get("short"):
                    ret = -ret
            # 펀딩 — 양수 펀딩률이면 롱이 내고 숏이 받는다
            fnd = (100.0 * p.get("fr", 0.0)
                   * funding_crossings(pd.Timestamp(p["entry_ts"]).to_pydatetime(),
                                       now)
                   * (1.0 if p.get("short") else -1.0))
            # ⚠ 실거래는 **거래소가 실제로 뗀 수수료**를 쓴다. 상수 0.072% 는
            #   실측(왕복 0.100%)보다 낮아, 쓰면 오차가 원장에 영구히 숨는다.
            fee = FEE_PCT
            if broker is not None:
                real = broker.roundtrip_fee_pct(
                    sym, float(p.get("notional_usd", 0.0)),
                    short=bool(p.get("short")))
                if real is not None:
                    fee = real
                else:
                    log.warning("%s 실수수료를 못 재 상수 %.3f%% 로 후퇴한다",
                                sym, FEE_PCT)
            net = ret - fee + fnd
            st.equity += p["stake"] * net / 100.0
            st.n_trades += 1
            # ── 손절당한 종목은 한동안 다시 잡지 않는다
            #
            # 2026-09-07 AKEUSDT: 06:45 숏 진입 → 06:50 손절 -5.147% →
            # **같은 사이클에 같은 방향으로 재진입** → 07:35 손절 -4.313%.
            # 합 -9.46%. 중복 배제가 `현재 보유`만 봐서 방금 닫힌 종목이
            # 곧바로 다시 후보가 됐다. 손절은 "이 종목이 우리 반대로 세게
            # 가는 중"이라는 신호인데, 그 신호를 받은 자리로 되돌아갔다.
            #
            # ⚠ **영구 금지가 아니다.** 만료 시각을 적어 두고 지나면 푼다.
            # ⚠ 상태에 남긴다 — 메모리에만 두면 재기동 한 번에 풀린다.
            if stop_hit and STOP_COOLDOWN_MIN > 0:
                until = now + timedelta(minutes=STOP_COOLDOWN_MIN)
                st.cooldown[sym] = str(until)
                log.warning("%s 손절 — **%d분간 재진입 금지** (해제 %s)",
                            sym, STOP_COOLDOWN_MIN, until.strftime("%m-%d %H:%M"))
            row = {**p, "exit_px": px, "ret_pct": ret, "funding_pct": fnd,
                   "net_pct": net, "closed_ts": str(now),
                   "stopped": bool(stop_hit), "equity_after": st.equity}
            if broker is not None:
                # ⚠ 실거래에만 넣는다. 페이퍼 원장에 칸을 늘리면 가동 중인
                #   전진 검정의 파일이 합집합 스키마로 통째로 다시 써진다 —
                #   대조군을 건드리지 않는다는 원칙(체크리스트 8)에 어긋난다.
                row["fee_pct"] = fee
            closed.append(row)
            # ⚠ 덧붙이기 원장에 **필드를 늘리면 깨진다**. 펀딩 컬럼을 추가하며
            #   12칸 파일에 13칸 행을 붙여 통째로 못 읽게 됐다(2026-08-29).
            #   헤더가 다르면 전체를 읽어 합집합 스키마로 다시 쓴다.
            if broker is not None:
                _tell(broker,
                      f"{'✅' if net > 0 else '❌'} <b>{TRACK_NAME} 청산</b> "
                      f"{'숏' if p.get('short') else '롱'}"
                      f"{' · 손절' if stop_hit else ''}\n"
                      f"{sym} {p['entry_px']:.8g} → {px:.8g}\n"
                      f"순손익 <b>{net:+.3f}%</b> "
                      f"(수익 {ret:+.3f}% · 수수료 {fee:.3f}%)\n"
                      f"자본 {st.equity:.4f} ({(st.equity - 1) * 100:+.2f}%) "
                      f"· 누적 {st.n_trades}건")
            nr = pd.DataFrame([row])
            if ledger.exists():
                try:
                    old_df = pd.read_csv(ledger)
                except Exception:                              # noqa: BLE001
                    old_df = pd.read_csv(ledger, on_bad_lines="skip")
                if list(old_df.columns) != list(nr.columns):
                    pd.concat([old_df, nr], ignore_index=True).to_csv(
                        ledger, index=False)
                else:
                    nr.to_csv(ledger, mode="a", header=False, index=False)
            else:
                nr.to_csv(ledger, index=False)
        else:
            keep.append(p)
    st.positions = keep

    if sig_kind in ("rev", "sess", "imp", "skew", "ac1", "rmz",
                    "dir", "impconf", "impanti") and cands:
        # z_vel 이 낮은 쪽(= 많이 떨어진 쪽)이 롱, 높은 쪽이 숏
        order = sorted(cands, key=lambda x: x["z_vel"])
        h = len(order) // 2
        for k, x in enumerate(order):
            x["side_short"] = (k >= len(order) - h)

    # ── 후보 풀 채집 (그림자용) — **슬롯 여유와 무관하게** 남긴다
    #
    # 실거래가 무엇을 열 수 있었는지를 나중에 재려면, 열지 **못한** 사이클의
    # 후보도 있어야 한다. 슬롯이 막혀 있었던 것도 체결 계층의 비용이다 —
    # 2026-09-05 18:45 처럼 `-1021` 로 청산이 밀리면 다음 사이클 슬롯이
    # 없어서 진입이 통째로 사라지는데, 그 손실이 어디에도 안 남는다.
    #
    # ⚠ 전량을 남기면 하루 10MB 다(후보 342 × 288 사이클). 슬롯이 2 라
    #   양쪽 상위 25개면 충분하고 남는다. 자른 사실을 감추지 않으려고
    #   원래 개수(`n_cands`)를 함께 적는다.
    pool = None
    if emit_pool:
        _pl = sorted((x for x in cands if not x.get("side_short")),
                     key=lambda x: x["z_vel"])[:POOL_KEEP]
        _ps = sorted((x for x in cands if x.get("side_short")),
                     key=lambda x: -x["z_vel"])[:POOL_KEEP]
        pool = [{"s": x["symbol"], "sh": int(bool(x.get("side_short", short))),
                 "px": float(x["px"]), "zv": float(x["z_vel"]),
                 "za": float(x["z_acc"])} for x in (_pl + _ps)]

    # ── 대기열 승격 — 신호 시각 + 지연이 지난 것만 **그때 가격으로** 진입
    #
    # 44시간 실측: 진입 후 첫 30분은 먹힌 구간·중립·잃은 구간이 **전부 음수**
    # (-1.03 / -8.07 / -9.37). 1시간 급락 종목은 아직 떨어지는 중이다.
    # 그 30분을 건너뛰면 보유 60분에서 -1.78 → +4.75, 90분에서 +1.75 → +24.52.
    #
    # ⚠ 승격 때 **재판정하지 않는다.** 신호 시각의 결정을 그대로 집행한다 —
    #   재판정하면 지연 검정이 아니라 다른 규칙이 된다.
    promoted = []
    if delay > 0 and st.pending:
        still = []
        for q in st.pending:
            if pd.Timestamp(q["enter_at"]) > pd.Timestamp(now):
                still.append(q)
                continue
            px = px_cache.get(q["symbol"])
            if px is None:
                # ⚠ 시세를 모르면 **진입하지 않는다**. 추정가로 채우면 성과표가
                #   조용히 오염된다(교훈#107).
                log.info("  대기 %s 시세 없음 — 취소", q["symbol"])
                continue
            # ⚠ `hold` 다. 상수 HOLD 를 쓰면 **`--hold-min` 이 이 경로에서만
            #   조용히 버려진다**. 2026-09-05 실측: UTC01 이 `--hold-min 1440`
            #   으로 넉 달 돌았는데 원장 보유는 전부 **120분**이었다. 인자는
            #   파싱됐고 기동 로그도 "보유 1440분"이라 정상으로 보였다 —
            #   지연(delay>0)이 붙은 갈래만 대기열을 거치기 때문이다(교훈#88).
            st.positions.append({
                "symbol": q["symbol"], "sig_ts": q["sig_ts"],
                "entry_ts": str(now), "entry_px": px,
                "z_vel": q["z_vel"], "z_acc": q["z_acc"],
                "exit_ts": str(now + timedelta(minutes=hold)),
                "stake": st.equity / slots, "short": bool(q["short"]),
                "fr": float(fr.get(q["symbol"], 0.0))})
            promoted.append(q["symbol"])
        if promoted:
            # 인자 도달 증명 — 원장을 열기 전에 로그로 먼저 확인한다
            log.info("  승격 %d건 · 보유 **%d분** 적용(인자 도달 확인)",
                     len(promoted), hold)
        st.pending = still

    # ⚠ 진입 시각 제한 — 하루 한 번만 여는 갈래용. 청산·승격은 항상 돈다.
    if entry_hour >= 0 and not (now.hour == entry_hour and now.minute == 0):
        cands = []

    # ── 빈 슬롯 채움 — z_vel 낮은 순, 중복 금지
    # ⚠ 대기열도 슬롯을 **차지한다**. 안 세면 지연 동안 과다 편입된다.
    held = ({p["symbol"] for p in st.positions}
            | {q["symbol"] for q in st.pending}
            | cooling(st, now))          # 냉각 중인 종목도 못 잡는다
    free = slots - len(st.positions) - len(st.pending)
    opened = []
    blocked = None
    if free > 0 and cands:
        avail = [x for x in cands if x["symbol"] not in held]
        if both:
            # ⚠ 롱·숏 슬롯을 **따로** 채운다. 한쪽만 채우면 시장 중립이 깨진다.
            half = slots // 2
            nl = (sum(1 for p in st.positions if not p.get("short"))
                  + sum(1 for q in st.pending if not q.get("short")))
            ns = len(st.positions) + len(st.pending) - nl
            pl = [x for x in avail if not x["side_short"]]
            ps = [x for x in avail if x["side_short"]]
            if pick == "noise":
                # ⚠ **잡음 지배** — 체결 방향 반전율 + 도착 간격 불규칙성의
                #   앵커 내 순위합. 큰 쪽부터. 두 지표의 눈금이 달라 순위로 합친다.
                def noisy(pool):
                    ok = [x for x in pool
                          if np.isfinite(x.get("bump", np.nan))
                          and np.isfinite(x.get("irr", np.nan))]
                    if len(ok) < half:
                        return []
                    rb = {id(x): r for r, x in enumerate(
                        sorted(ok, key=lambda y: y["bump"]))}
                    ri = {id(x): r for r, x in enumerate(
                        sorted(ok, key=lambda y: y["irr"]))}
                    return sorted(ok, key=lambda y: -(rb[id(y)] + ri[id(y)]))
                L = noisy(pl)[:max(half - nl, 0)]
                S2 = noisy(ps)[:max(half - ns, 0)]
            else:
                L = sorted(pl, key=lambda x: x["z_vel"])[:max(half - nl, 0)]
                S2 = sorted(ps, key=lambda x: -x["z_vel"])[:max(half - ns, 0)]
            c = L + S2
        else:
            # 롱은 z_vel 낮은 순, 숏은 **높은 순** — 밴드 끝에서 먼 쪽부터
            c = sorted(avail,
                       key=lambda x: -x["z_vel"] if short else x["z_vel"])[:free]
        stake = st.equity / slots
        # ⚠ 실거래 사이징 — 지갑을 **사이클당 한 번만** 읽는다. 종목마다
        #   두드리면 레이트리밋을 먹고 같은 사이클의 진입 크기가 서로 달라진다.
        #   문서 §4.2 — 원금의 1/slots 씩 · 복리(지갑이 곧 자본).
        live_notional = 0.0
        if broker is not None:
            w = broker.wallet_balance()
            if w is None:
                log.error("지갑을 못 읽었다 — **이번 사이클 진입을 건너뛴다**")
                c = []
                blocked = "wallet"        # 규칙이 아니라 체결 사고다
            else:
                # ⚠ 지갑을 **딱 나누면 마지막 자리가 못 들어간다.** 1배에서는
                #   명목=증거금이라 6×(w/6)=w 로 여유가 0이고, 앞 다리들이 낸
                #   테이커 수수료·미실현 손실만큼 모자라 `-2019` 로 거절된다.
                #   2026-09-08 균형저울 첫 진입에서 6번째(KASUSDT)가 그렇게
                #   빠져 장부가 롱3+숏2 로 **중립이 깨졌다.** 완충을 둔다.
                live_notional = w * margin_buffer / max(1, int(slots))
        for x in c:
            if delay > 0:
                st.pending.append({
                    "symbol": x["symbol"], "sig_ts": str(now),
                    "enter_at": str(now + timedelta(minutes=delay)),
                    "z_vel": x["z_vel"], "z_acc": x["z_acc"],
                    "short": bool(x.get("side_short", short))})
                opened.append(x)
                continue
            short_leg = bool(x.get("side_short", short))
            entry_px, notional_usd, qty = x["px"], 0.0, 0.0
            if broker is not None:
                r = broker.open(x["symbol"], short_leg, x["px"], live_notional)
                if r is None:
                    # 거절·최소명목 미달 — **장부에 넣지 않는다.** 넣으면
                    # 있지도 않은 포지션을 120분 뒤 청산하려 든다.
                    continue
                entry_px = float(r["price"])
                qty = float(r["quantity"])
                notional_usd = qty * entry_px
                # ⚠ 손절은 진입 **직후**에만 걸 수 있다(-4509). 실패해도
                #   포지션은 이미 열렸으므로 장부에는 넣는다 — 브로커가
                #   "보호 없음"을 크게 알린다.
                armed = broker.arm_stop(x["symbol"], short_leg, entry_px,
                                        STOP_PCT)
                _tell(broker,
                      f"{'🔻' if short_leg else '🔺'} <b>{TRACK_NAME} 진입</b> "
                      f"{'숏' if short_leg else '롱'}\n"
                      f"{x['symbol']} {qty:.8g} @ {entry_px:.8g}\n"
                      f"명목 ${notional_usd:.2f} · z_vel {x['z_vel']:+.2f}\n"
                      f"손절 {STOP_PCT:.1f}% {'등록' if armed else '⚠ 미등록'}")
            p = {"symbol": x["symbol"], "entry_ts": str(now),
                 "entry_px": entry_px, "z_vel": x["z_vel"], "z_acc": x["z_acc"],
                 "exit_ts": str(now + timedelta(minutes=hold)), "stake": stake,
                 "short": short_leg,
                 "fr": float(fr.get(x["symbol"], 0.0))}
            if broker is not None:
                # 실제로 나간 명목·수량을 남긴다. stepSize 내림 때문에
                # 의도한 명목과 다르다 — 그 차이를 재려면 둘 다 있어야 한다.
                p["notional_usd"] = notional_usd
                p["qty"] = qty
                p["want_notional"] = live_notional
                # ⚠ 문서 §6 ① — 슬리피지는 **신호가와 체결가를 둘 다** 남겨야
                #   잰다. 체결가만 남기면 페이퍼와 왜 갈리는지 영영 모른다.
                #   ② 진입 지연도 같다 — entry_ts 는 격자 시각이지 체결 시각이
                #   아니다(사이클이 10~30초 걸린다).
                p["sig_px"] = float(x["px"])
                p["slip_bp"] = (10000.0 * (entry_px - x["px"]) / x["px"]
                                * (-1.0 if short_leg else 1.0))
                p["fill_ts"] = datetime.now(timezone.utc).isoformat()
            st.positions.append(p)
            opened.append(p)
    return {"cands": len(cands), "opened": len(opened), "closed": len(closed),
            "held": len(st.positions), "pending": len(st.pending),
            "promoted": len(promoted), "pool": pool, "blocked": blocked,
            "n_cands": len(cands)}


def _emit_pool(d: Path, now: datetime, r: dict) -> None:
    """사이클 한 줄을 `<dir>/<날짜>/cycles.jsonl` 에 덧붙인다.

    ⚠ **실패해도 사이클을 죽이지 않는다.** 이건 계측이지 거래가 아니다.
      실자금 경로에 새 예외를 들이면 안 된다.
    ⚠ 날짜는 UTC 로 가른다 — 사이클 격자가 UTC 라 그래야 경계가 맞는다.
    """
    try:
        day = d / now.strftime("%Y-%m-%d")
        day.mkdir(parents=True, exist_ok=True)
        row = {"cycle": now.isoformat(), "n_cands": r.get("n_cands", 0),
               "held": r.get("held", 0), "opened": r.get("opened", 0),
               "closed": r.get("closed", 0), "blocked": r.get("blocked"),
               "pool": r.get("pool") or []}
        with (day / "cycles.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception as exc:                                  # noqa: BLE001
        log.warning("후보 풀 기록 실패(거래는 계속한다): %s", exc)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--once", action="store_true")
    p.add_argument("--slots", type=int, default=SLOTS_DEFAULT)
    p.add_argument("--short", action="store_true",
                   help="숏 방향. 밴드·가속·선별이 전부 거울이 된다")
    p.add_argument("--both", action="store_true",
                   help="롱·숏 **동시 보유**. 슬롯을 반씩 나눠 시장 노출을 상쇄한다")
    p.add_argument("--delay-min", type=int, default=0,
                   help="신호 뒤 이만큼 기다렸다 **그때 가격으로** 진입한다. "
                        "44시간 실측에서 첫 30분은 세 구간 전부 음수였다")
    p.add_argument("--hold-min", type=int, default=HOLD,
                   help="보유 분. 기본 120")
    p.add_argument("--stop-pct", type=float, default=5.0,
                   help="최대 손절(%%). 0 이면 끈다. 14개월 실측 최적 5")
    p.add_argument("--pick", default="zvel", choices=["zvel", "noise"],
                   help="선별 기준. noise = 체결 방향 반전율 + 도착 간격 "
                        "불규칙성의 순위합(잡음 지배). **틱에만 있다**")
    p.add_argument("--dir-thr", type=float, default=0.0,
                   help="확인·역확인의 문턱(%%). impconf 는 dir < -thr, "
                        "impanti 는 dir > +thr. 실측 최적 0.")
    p.add_argument("--dir-min", type=int, default=15,
                   help="방향 신호의 되돌아보기(분). dir·impconf 가 쓴다. "
                        "14일 격자에서 15분이 5·30분보다 나았다(미확정).")
    p.add_argument("--signal", default="kine",
                   choices=["kine", "rev", "sess", "imp", "skew", "ac1", "rmz",
                            "dir", "impconf", "impanti"],
                   help="kine = 위약 승률 속도(밴드 있음) · "
                        "rev = 1시간 되돌림(밴드 없음, 횡단면 순위만)")
    p.add_argument("--entry-hour", type=int, default=-1,
                   help="이 UTC 시각 정각에만 새로 연다(-1 이면 항상). "
                        "하루 한 번 여는 갈래용")
    p.add_argument("--live", action="store_true",
                   help="**실거래**. 진입·청산이 실제 주문으로 나간다. "
                        "--account 가 반드시 함께 있어야 한다")
    p.add_argument("--account", type=int, default=0,
                   help="exchange_accounts.id. --live 에만 쓴다")
    p.add_argument("--leverage", type=int, default=1,
                   help="거래소 레버리지. 기본 1 — 올리면 -5%% 손절이 "
                        "자본의 -5%% 가 아니게 된다(문서 §4.2)")
    p.add_argument("--dry-run", action="store_true",
                   help="--live 배선을 타되 주문은 내지 않는다")
    p.add_argument("--tag", default="", help="경로 꼬리표")
    p.add_argument("--dir", default="",
                   help="상태·원장 디렉터리. 비우면 runs/kinematics_paper/s{슬롯}")
    p.add_argument("--stop-cooldown-min", type=int, default=0,
                   help="손절당한 종목을 이 분 동안 다시 잡지 않는다. 0 이면 끔. "
                        "영구 금지가 아니라 시간 제한이다. 권고값은 보유 기간과 "
                        "같은 120")
    p.add_argument("--margin-buffer", type=float, default=0.95,
                   help="실거래 다리당 명목 = 지갑 x 이 값 / 슬롯. 1.0 이면 "
                        "지갑을 딱 나눠 마지막 자리가 -2019 로 거절된다. "
                        "0.95 근거: 바이낸스 증거금은 **표시가** 기준이라 "
                        "명목보다 최대 0.6% 크고(실측 69.41/69.03), 진입 "
                        "테이커 수수료가 지갑에서 먼저 빠진다.")
    p.add_argument("--emit-pool", action="store_true",
                   help="사이클마다 후보 풀을 <dir>/<날짜>/cycles.jsonl 에 "
                        "남긴다. 그림자가 '실거래가 열 수 있었던 것'을 "
                        "재구성하는 자료원이다. 기본 꺼짐 — 다른 갈래의 "
                        "동작을 바꾸지 않는다")
    a = p.parse_args()
    # ⚠ 인자를 전역에 **반영**한다. 안 하면 --stop-pct 를 받고도 코드가
    #   기본값을 쓴다 — 교훈#88(클래스만 고치고 경로를 안 봐서 재진입
    #   차단이 한 번도 동작 안 했다)과 같은 형태다.
    global STOP_PCT, STOP_COOLDOWN_MIN
    global DIR_MIN, DIR_THR
    DIR_MIN = int(a.dir_min)
    DIR_THR = float(a.dir_thr)
    STOP_PCT = float(a.stop_pct)
    STOP_COOLDOWN_MIN = int(a.stop_cooldown_min)
    # ⚠ 풀을 자르는 순서는 **선별 순서와 같아야** 한다. `--pick noise` 는
    #   잡음 순위로 고르므로 z_vel 상위 25개를 남기면 실제로 뽑혔을 종목이
    #   잘려 나간다 — 그림자가 조용히 틀린다.
    if a.emit_pool and a.pick != "zvel":
        raise SystemExit(f"--emit-pool 은 --pick zvel 에서만 옳다 (지금 {a.pick})")
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    tag = (f"s{a.slots}" + ("both" if a.both else "short" if a.short else "")
           + (f"_d{a.delay_min}" if a.delay_min else "")
           + (f"_{a.tag}" if a.tag else ""))
    d = Path(a.dir) if a.dir else OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    state_p, ledger = d / "state.json", d / "trades.csv"
    st = load_state(state_p)
    side = "롱숏동시" if a.both else ("숏" if a.short else "롱")
    log.info("손절 상한 **%.2f%%** (0 이면 끔) — 인자 도달 확인", STOP_PCT)
    if a.signal in ("dir", "impconf", "impanti"):
        log.info("방향 되돌아보기 **%d분** · 문턱 **%.2f%%** — 인자 도달 확인",
                 DIR_MIN, DIR_THR)
    log.info("손절 후 재진입 금지 **%d분** (0 이면 끔) — 인자 도달 확인",
             STOP_COOLDOWN_MIN)
    if st.cooldown:
        log.info("복원된 냉각 %d종목: %s", len(st.cooldown),
                 ", ".join(f"{k}→{v[:16]}" for k, v in
                           sorted(st.cooldown.items())[:5]))
    log.info("운동학 페이퍼 — %d종목 · %s · 슬롯 %d(%s) · 보유 %d분 · 경로 %s",
             len(syms), side, a.slots,
             f"롱{a.slots//2}+숏{a.slots//2}" if a.both else side, a.hold_min, d)
    if a.delay_min:
        log.info("**진입 지연 %d분** — 신호 시각에 예약하고 그때 가격으로 산다",
                 a.delay_min)
    if a.pick != "zvel" or a.signal != "kine" or a.entry_hour >= 0 \
            or a.hold_min != HOLD:
        log.info("변형 — 신호 %s · 선별 %s · 보유 %d분 · 진입시각 %s",
                 a.signal, a.pick, a.hold_min,
                 f"UTC {a.entry_hour}시" if a.entry_hour >= 0 else "항상")
    log.info("상태 — 자본 %.4f · 보유 %d · 대기 %d · 누적거래 %d",
             st.equity, len(st.positions), len(st.pending), st.n_trades)

    # ── 실거래 배선 ─────────────────────────────────────────
    broker = None
    if a.live:
        if a.account <= 0:
            raise SystemExit("--live 에는 --account 가 필요하다")
        if a.delay_min:
            # 대기열 승격 경로는 실거래로 배선하지 않았다. 반쯤 배선된 채
            # 돌면 신호는 예약되는데 주문이 안 나가 **조용히 다른 전략**이 된다.
            raise SystemExit("--live 는 --delay-min 0 만 지원한다 "
                             "(대기열 승격 경로 미배선)")
        # ⚠ 맨이름 import 는 PM2 본실행(`PYTHONPATH=.`)에서 죽는다.
        try:
            from scripts.binance.kine_live_broker import KineLiveBroker
        except ImportError:                           # 직접 실행·대화형용
            from kine_live_broker import KineLiveBroker
        broker = KineLiveBroker(account_id=a.account, leverage=a.leverage,
                                dry_run=a.dry_run)
        # ⚠ 알림은 **없어져도 조용하다**(교훈#102). RSI·신상저격수가 쓰는
        #   **같은 발송기**를 그대로 쓴다 — 두 벌 만들면 한쪽만 고쳐지는
        #   날이 온다. 계좌에 봇 토큰이 없으면 조용히 건너뛰므로,
        #   기동 때 배선 여부를 로그로 남긴다.
        try:
            from scripts.binance.lifecycle_live_signal_driver import (
                _telegram_notify)
            broker.notify = lambda t, _a=int(a.account): _telegram_notify(_a, t)
            log.info("텔레그램 알림 — 계좌 %s 로 발송", a.account)
        except Exception as exc:                              # noqa: BLE001
            log.error("텔레그램 배선 실패 — 알림 없이 계속한다: %s", exc)
        broker.connect()
        # ⚠ 재시작 대조 — 거래소가 진실이다. 우리 장부에 없는 포지션은
        #   손대지 않고 **드러내기만** 한다(수동 개입일 수 있다).
        onx = broker.reconcile({p["symbol"] for p in st.positions})
        if onx is None:
            # ⚠ 못 읽었다 = 없다가 아니다. 장부를 **그대로 둔다**.
            #   2026-09-08 `-1003` IP 차단 때 장부가 통째로 비워졌다.
            log.critical("기동 대조 실패 — 장부를 손대지 않는다 (보유 %d건 유지). "
                         "거래소를 직접 확인하라", len(st.positions))
        else:
            kept = []
            for p in st.positions:
                if p["symbol"] in onx:
                    kept.append(p)
                else:
                    log.warning("장부엔 %s 가 있는데 거래소엔 없다 — 장부에서 뺀다",
                                p["symbol"])
            st.positions = kept
        w = broker.wallet_balance()
        log.warning("*** 실거래 모드 *** 계좌 %s · 레버리지 %dx · 슬롯 %d "
                    "· 지갑 %s USDT · 다리당 명목 %s · 증거금 완충 %.2f%s",
                    a.account, a.leverage, a.slots,
                    f"{w:.4f}" if w else "조회실패",
                    f"${w * a.margin_buffer / max(1, a.slots):.2f}" if w else "?",
                    a.margin_buffer,
                    " · DRY-RUN" if a.dry_run else "")

    while not _stop:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        now -= timedelta(minutes=now.minute % STEP)
        t0 = time.time()
        try:
            fr = funding_rates() if a.short or True else {}
            r = cycle(syms, st, ledger, now, a.slots, a.short, fr,
                      a.both, a.delay_min, a.hold_min, a.pick, a.signal,
                      a.entry_hour, broker, emit_pool=a.emit_pool,
                      margin_buffer=a.margin_buffer)
            save_state(state_p, st)
            if a.emit_pool:
                _emit_pool(d, now, r)
            log.info("%s · 후보 %d · 예약 %d · 승격 %d · 대기 %d · 청산 %d "
                     "· 보유 %d/%d · 자본 %.4f(%+.2f%%) · 누적 %d · %.0f초",
                     now.strftime("%m-%d %H:%M"), r["cands"], r["opened"],
                     r.get("promoted", 0), r.get("pending", 0), r["closed"],
                     r["held"], a.slots, st.equity,
                     (st.equity - 1) * 100, st.n_trades, time.time() - t0)
        except Exception as e:                                  # noqa: BLE001
            log.exception("사이클 실패: %s", e)
        if a.once:
            break
        # 다음 5분 격자까지 대기
        nxt = now + timedelta(minutes=STEP)
        while not _stop and datetime.now(timezone.utc) < nxt:
            time.sleep(2)
    save_state(state_p, st)
    log.info("종료 — 자본 %.4f · 보유 %d · 누적거래 %d",
             st.equity, len(st.positions), st.n_trades)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
