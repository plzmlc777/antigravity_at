"""지표 신호 **중복도** — 엣지를 재기 전에 중복부터 잰다.

무엇을 묻는가
    "RSI 말고 다른 지표"라고 할 때, 그 지표가 정말 **다른 거래**를 만드는가.
    단기 지표는 계열이 셋뿐이다 — 오실레이터(A) · 변동성밴드(B) ·
    거래량앵커(C). 한 계열 안에서는 이름만 다르고 거의 같은 봉에서 발화한다.
    격자를 돌리기 전에 이걸 알면 며칠을 아낀다.

    (문서 「마찰이 먼저다」의 단계 2와 같은 정신 — 비싼 걸 돌리기 전에
     싼 걸로 먼저 자른다.)

앵커 관측단위
    **(종목, 신호 발화 봉)**. 손익이 아니다 — 커널을 부르지 않는다.
    같은 급락을 1~2봉 차이로 잡는 건 실무적으로 **같은 거래**이므로
    정확 일치와 함께 `±tol봉 허용 매칭`도 낸다.

내장 눈금 두 개 (이게 없으면 0.4가 큰 건지 작은 건지 모른다)
    ① `bb20_2` vs `z20_2`   — 수학적으로 **동일한 지표**다.
       (c ≤ ma − 2·sd) ⟺ ((c−ma)/sd ≤ −2). 여기 나온 값이 이 척도의 **1.0**.
    ② `stoch14_12` vs `willr14_88` — 평활(3봉)만 다른 **사실상 같은 지표**.
       "이름만 다른 지표"가 이 척도에서 몇으로 나오는지 알려준다.
    이 둘보다 낮아야 비로소 "다른 지표"다.

⚠ 미래참조 없음
    모든 지표는 t 시점 종가까지만 쓴다(rolling/ewm, center 없음).
    발화는 `~inside & inside.shift(1)` — t−1 과 t 만 본다.

⚠ 워밍업을 **공통으로** 자른다
    지표마다 워밍업이 다르다(RSI 14 · VWAP 96). 안 맞추면 워밍업 짧은 지표가
    앞구간에서 혼자 발화해 "다른 지표"로 보인다. 지표 탓이 아니라 구간 탓이다.

⚠ RSI 는 **정본 소스의 함수**를 그대로 쓴다
    `app.composer_framework.sources.rsi_threshold_source.wilder_rsi`.
    새로 짜면 실거래와 다른 물건을 비교하게 된다.

사용:
  python3 -m scripts.research.signal_overlap --selftest
  python3 -m scripts.research.signal_overlap --limit 5 --workers 3
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("overlap")

OUT_DIR = ROOT / "runs" / "research_track" / "signal_overlap"


# ══════════════════════════════════════════════════════════════════════
#  ① 설정은 여기 한 곳에만
# ══════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Ind:
    """지표 하나. `inside` = 극단 구간 안. 발화는 여기서 나오는 게 아니라
    `cross_back()` 이 균일하게 만든다 — 지표마다 다른 발화 규칙을 쓰면
    비교가 성립하지 않는다."""
    key: str
    family: str          # A_osc | B_band | C_flow
    label: str
    kind: str            # 계산기 이름
    params: tuple


@dataclass(frozen=True)
class OverlapConfig:
    tf: str = "5m"
    side: str = "long"           # long = 과매도 극단 / short = 과매수 극단
    start: str = "2025-08-17"
    end: str = "2026-08-17"
    tol_bars: int = 3            # ±3봉 = 5분봉 기준 15분
    warmup_bars: int = 300       # 공통 워밍업 (최장 지표 96*2 보다 넉넉히)
    min_bars: int = 2000         # 이보다 짧은 종목은 제외
    min_signals: int = 200       # 검정력 사전검사 — 이하면 비율이 불안정
    universe_file: str = "configs/rsi_paper_universe.txt"

    def key(self) -> str:
        return f"{self.side}_{self.tf}_{self.start}_{self.end}_tol{self.tol_bars}"


# 롱(과매도) 기준 문턱. 숏이면 `mirror()` 가 뒤집는다.
INDICATORS: tuple[Ind, ...] = (
    # ── A 계열: 오실레이터 ────────────────────────────────────────────
    Ind("rsi14_12",   "A_osc",  "RSI(14) ≤ 12",              "rsi",   (14, 12.0)),
    Ind("rsi21_12",   "A_osc",  "RSI(21) ≤ 12  ※눈금",        "rsi",   (21, 12.0)),
    Ind("stoch14_12", "A_osc",  "Stoch %K(14,3) ≤ 12",       "stoch", (14, 3, 12.0)),
    Ind("willr14_88", "A_osc",  "Williams %R(14) ≤ −88",     "willr", (14, -88.0)),
    Ind("cci20_200",  "A_osc",  "CCI(20) ≤ −200",            "cci",   (20, -200.0)),
    Ind("mfi14_12",   "A_osc",  "MFI(14,Wilder) ≤ 12",       "mfi",   (14, 12.0)),
    # ── B 계열: 변동성 밴드 ───────────────────────────────────────────
    Ind("bb20_2",     "B_band", "볼린저 하단 이탈(20,2σ)",     "bb",    (20, 2.0)),
    Ind("z20_2",      "B_band", "z-score(20) ≤ −2",          "z",     (20, 2.0)),
    Ind("kelt20_2",   "B_band", "켈트너 하단(EMA20−2ATR14)",   "kelt",  (20, 14, 2.0)),
    # ── C 계열: 거래량·가격 앵커 ──────────────────────────────────────
    Ind("vwap96_2",   "C_flow", "rolling VWAP(96) −2σ 이탈",  "vwap",  (96, 2.0)),
    Ind("volcap",     "C_flow", "거래량z≥3 & 5봉수익≤−3%",     "volcap", (96, 3.0, -0.03)),
)


# ══════════════════════════════════════════════════════════════════════
#  ② 지표 — 전부 `inside`(극단 구간 안) 불리언만 낸다
# ══════════════════════════════════════════════════════════════════════
def _score(ind: Ind, b: pd.DataFrame) -> pd.Series:
    """지표의 **연속 점수**. 규약: 값이 작을수록 롱 극단(과매도)이다.

    왜 불리언이 아니라 점수인가 (2026-08-22 예비비행에서 드러남)
        관례 문턱을 그대로 쓰면 발화량이 300배까지 벌어진다
        (RSI≤12 는 59건, Williams %R≤−88 은 18,531건). 그러면 자카드가
        낮게 나오는 게 **문턱 탓인지 지표 탓인지** 못 가른다.
        점수로 두면 나중에 **같은 빈도**로 맞춰 자를 수 있다.
    """
    c, h, lo, v = b["close"], b["high"], b["low"], b["volume"]
    k = ind.kind

    P = ind.params                    # 문턱은 FIXED_THR 이 갖는다 — 여기선 기간만
    if k == "rsi":
        from app.composer_framework.sources.rsi_threshold_source import wilder_rsi
        n = P[0]
        return wilder_rsi(c, int(n))

    # ⚠ 범위는 **직전 N봉**으로 잰다(현재 봉 제외). 현재 봉을 범위에 넣는
    #   교과서 정의는 신저가에서 값이 **정확히 0** 으로 뭉쳐, 문턱을 아무리
    #   조여도 신호가 안 줄어든다(예비비행 실측: 목표 76건에 6,490건).
    #   등급이 안 매겨지면 희소 신호를 만들 수 없고, 그러면 비교도 못 한다.
    #   한 봉 차이이고 미래참조는 오히려 더 없다.
    elif k == "stoch":
        n, sm = int(P[0]), int(P[1])
        hh = h.rolling(n).max().shift(1)
        ll = lo.rolling(n).min().shift(1)
        raw = 100.0 * (c - ll) / (hh - ll).replace(0.0, np.nan)
        return raw.rolling(sm).mean()

    elif k == "willr":
        n = int(P[0])
        hh = h.rolling(n).max().shift(1)
        ll = lo.rolling(n).min().shift(1)
        return -100.0 * (hh - c) / (hh - ll).replace(0.0, np.nan)

    elif k == "cci":
        n = int(P[0])
        tp = (h + lo + c) / 3.0
        ma = tp.rolling(n).mean()
        md = (tp - ma).abs().rolling(n).mean()
        return (tp - ma) / (0.015 * md.replace(0.0, np.nan))

    elif k == "mfi":
        n = int(P[0])
        tp = (h + lo + c) / 3.0
        mf = tp * v
        # ⚠ 단순합(rolling.sum) 판은 하락 구간에서 up 이 **정확히 0** 이 돼
        #   값이 0 에 뭉친다(예비비행 실측: 경계 동점 51%). 등급이 안 매겨지면
        #   희소 신호를 못 만든다. RSI 가 이 문제를 피하는 방식 그대로
        #   **Wilder 지수평활**을 쓴다 — 지수 기억이라 0 으로 붙지 않는다.
        a = 1.0 / n
        up = mf.where(tp.diff() > 0, 0.0).ewm(alpha=a, adjust=False,
                                              min_periods=n).mean()
        dn = mf.where(tp.diff() < 0, 0.0).ewm(alpha=a, adjust=False,
                                              min_periods=n).mean()
        mfi = 100.0 - 100.0 / (1.0 + up / dn.replace(0.0, np.nan))
        return mfi.where(dn != 0.0, 100.0)

    elif k in ("bb", "z"):
        n = int(P[0])
        ma = c.rolling(n).mean()
        sd = c.rolling(n).std(ddof=0)
        return (c - ma) / sd.replace(0.0, np.nan)

    elif k == "kelt":
        n, an = int(P[0]), int(P[1])
        ema = c.ewm(span=n, adjust=False).mean()
        tr = pd.concat([h - lo, (h - c.shift()).abs(),
                        (lo - c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1.0 / an, adjust=False, min_periods=an).mean()
        return (c - ema) / atr.replace(0.0, np.nan)

    elif k == "vwap":
        n = int(P[0])
        tp = (h + lo + c) / 3.0
        pv = (tp * v).rolling(n).sum()
        vv = v.rolling(n).sum()
        vwap = pv / vv.replace(0.0, np.nan)
        d = (c - vwap) / vwap
        return (d - d.rolling(n).mean()) / d.rolling(n).std(ddof=0).replace(0.0, np.nan)

    elif k == "volcap":
        n, vz = int(P[0]), float(P[1])
        vzs = (v - v.rolling(n).mean()) / v.rolling(n).std(ddof=0).replace(0.0, np.nan)
        # 거래량이 안 터진 봉은 **후보에서 뺀다**(+inf). 그래야 빈도를 맞출 때
        # '거래량 터진 봉 중 가장 많이 빠진 것' 이 뽑힌다.
        return c.pct_change(5).where(vzs >= vz, np.inf)

    raise ValueError(f"모르는 지표 종류: {k}")


# 관례 문턱 — `_score` 규약(작을수록 롱 극단)에 맞춘 값. 롱 기준.
FIXED_THR = {"rsi": 12.0, "stoch": 12.0, "willr": -88.0, "cci": -200.0,
             "mfi": 12.0, "bb": -2.0, "z": -2.0, "kelt": -2.0,
             "vwap": -2.0, "volcap": -0.03}


def _inside(ind: Ind, b: pd.DataFrame, side: str,
            q: float | None = None, warmup: int = 0) -> pd.Series:
    """극단 구간 안. `side` 는 **여기서만** 갈린다.

    q 가 None 이면 관례 문턱(FIXED_THR), 주면 **분위수**로 자른다
    (= 빈도 맞춤 모드).
    """
    sc = _score(ind, b)
    lng = side == "long"
    if q is None:
        thr = FIXED_THR[ind.kind]
        # 숏은 점수 규약을 뒤집는다. rsi/stoch/mfi 는 0~100 대칭,
        # willr 는 −100~0, 나머지는 0 중심이다.
        if lng:
            return (sc <= thr).fillna(False).astype(bool)
        if ind.kind in ("rsi", "stoch", "mfi"):
            return (sc >= 100.0 - thr).fillna(False).astype(bool)
        if ind.kind == "willr":
            return (sc >= -100.0 - thr).fillna(False).astype(bool)
        return (sc >= -thr).fillna(False).astype(bool)
    v = sc.to_numpy(dtype=float)
    fin = np.isfinite(v)
    # ⚠ 절단선은 **워밍업 이후 구간**에서만 잰다. 워밍업의 NaN·초기값이
    #   섞이면 종목마다 다른 편향이 들어간다.
    ev = v[warmup:][np.isfinite(v[warmup:])]
    if ev.size < 100:
        return pd.Series(False, index=sc.index)
    cut = float(np.quantile(ev, q if lng else 1.0 - q))
    out = (v <= cut) if lng else (v >= cut)
    return pd.Series(out & fin, index=sc.index)


def cross_back(inside: pd.Series) -> pd.Series:
    """구간 **밖으로 되돌아 나오는 봉**. 모든 지표에 똑같이 적용한다."""
    return (~inside) & inside.shift(1).fillna(False)


# ══════════════════════════════════════════════════════════════════════
#  ③ 종목 하나 → 지표별 발화 봉 인덱스
# ══════════════════════════════════════════════════════════════════════
ANCHOR = "rsi14_12"          # 실거래 중인 신호. 빈도 맞춤의 기준.

def _fire_idx(ins: pd.Series, W: int) -> np.ndarray:
    cb = cross_back(ins).to_numpy(copy=True)
    cb[:W] = False
    return np.flatnonzero(cb).astype(np.int64)


def _episodes(mask: np.ndarray, W: int) -> np.ndarray:
    """구간을 **빠져나오는 봉**의 위치."""
    out = (~mask) & np.concatenate(([False], mask[:-1]))
    out[:W] = False
    return np.flatnonzero(out).astype(np.int64)


def _match_count(ind: Ind, b: pd.DataFrame, side: str, W: int, target: int,
                 seed: int = 20260822) -> tuple[np.ndarray, int, bool]:
    """**사건 수**를 기준에 맞춘다 — 체류시간도 분위수도 아니다.

    ⚠ 왜 체류시간이 아닌가 (자기검사가 잡음)
      극단 구간에 머문 **시간**을 같게 맞춰도 발화 **횟수**는 27배까지
      벌어졌다. 매끄러운 지표(RSI)는 한 번 들어가면 오래 있어 사건이 적고,
      튀는 지표는 들락거려 사건이 많다. 비교 단위가 '거래'이므로 사건 수다.

    ⚠ 왜 분위수가 아닌가 (예비비행이 잡음)
      Williams %R 은 N봉 최저가에서 **정확히 −100** 이라 동점이 대량으로
      뭉친다. `값 <= 분위수` 로 자르면 그 뭉치를 통째로 집어 목표 76건에
      6,490건이 나왔다. 그래서 **상위 K개 봉**을 직접 고른다.
      동점은 고정 씨앗 무작위로 가른다 — 그 지표 자신의 척도로는 똑같이
      극단인 봉들이라, 시간순으로 가르면 앞구간에 쏠린다.

    K(구간 안 봉 수)를 늘려가며 사건 수가 목표에 가장 가까운 K를 고른다.
    사건 수는 K에 단조가 아니다(에피소드가 합쳐지면 준다) — 격자 훑기.
    """
    sc = _score(ind, b)
    v = sc.to_numpy(dtype=float)
    n = v.size
    fin = np.isfinite(v)
    pool = np.flatnonzero(fin)
    pool = pool[pool >= W]
    if pool.size < 50 or target <= 0:
        return np.zeros(0, dtype=np.int64), 0, True, 1.0
    x = v[pool] if side == "long" else -v[pool]
    rng = np.random.default_rng(seed + (hash(ind.key) & 0xFFFF))
    order = np.lexsort((rng.random(pool.size), x))      # 1차 점수 · 2차 동점처리
    ranked = pool[order]
    hi = int(min(pool.size, max(target * 60, 4000)))
    grid = np.unique(np.round(np.geomspace(max(target, 2), hi, 44)).astype(int))
    best, best_k, best_d = np.zeros(0, dtype=np.int64), 0, None
    for K in grid:
        mask = np.zeros(n, dtype=bool)
        mask[ranked[:K]] = True
        idx = _episodes(mask, W)
        d = abs(int(idx.size) - target)
        if best_d is None or d < best_d:
            best, best_k, best_d = idx, int(K), d
        if d == 0:
            break
    capped = best_d > max(1, int(0.25 * target))
    # **동점 진단** — 뽑힌 K개 중 경계값과 같은 값이 몇 %인가.
    # 높으면 그 지표는 이 희소도에서 **등급을 못 매긴다**(뽑기가 무작위가 된다).
    # 그러면 겹침이 낮게 나와도 "다른 지표"가 아니라 "잡음"이다.
    tie = 0.0
    if best_k:
        sel = v[ranked[:best_k]]
        bnd = sel[-1]
        tie = float(np.mean(sel == bnd))
    return best, best_k, capped, tie


def signals_for_symbol(cfg: OverlapConfig, sym: str, bars: pd.DataFrame
                       ) -> dict[str, dict[str, np.ndarray]] | None:
    """두 모드로 발화 봉을 낸다. 공통 워밍업을 자른 **뒤** 위치 인덱스.

    fixed   — 관례 문턱 그대로. "지표를 그냥 갈아끼우면" 무슨 일이 나는가.
    matched — **RSI 와 같은 발화 빈도**로 문턱을 자른다. 발화량 차이를
              지우고 "고르는 자리가 다른가"만 묻는다.

    ⚠ matched 는 **측정 장치**다. 분위수를 구간 전체에서 잡으므로
      미래참조가 있다 — 거래 규칙으로 쓰면 안 된다. 여기서는 손익을
      내지 않고 발화 시점만 비교하므로 문제가 되지 않는다.
    """
    if bars is None or len(bars) < cfg.min_bars:
        return None
    b = bars.astype(float)
    W = cfg.warmup_bars
    anchor = next(i for i in INDICATORS if i.key == ANCHOR)
    ins_a = _inside(anchor, b, cfg.side).to_numpy()
    q = float(ins_a[W:].mean()) if len(ins_a) > W else 0.0

    out: dict = {"fixed": {}, "matched": {}, "_q": q, "_cap": [],
                 "_qmatch": {}, "_tie": {}}
    for ind in INDICATORS:
        out["fixed"][ind.key] = _fire_idx(_inside(ind, b, cfg.side), W)
    target = int(out["fixed"][ANCHOR].size)
    for ind in INDICATORS:
        if ind.key == ANCHOR:
            out["matched"][ind.key] = out["fixed"][ANCHOR]
            out["_qmatch"][ind.key] = float("nan")
            out["_tie"][ind.key] = 0.0
            continue
        idx, km, capped, tie = _match_count(ind, b, cfg.side, W, target)
        out["matched"][ind.key] = idx
        out["_qmatch"][ind.key] = km
        out["_tie"][ind.key] = tie
        if capped:
            out["_cap"].append(ind.key)
    return out


def pair_counts(cfg: OverlapConfig,
                fire: dict[str, np.ndarray]) -> dict:
    """이 종목에서의 개수만 낸다 — 시각을 부모로 보내지 않는다(메모리)."""
    keys = [i.key for i in INDICATORS]
    n = {k: int(len(fire[k])) for k in keys}
    ex, cv = {}, {}
    for a, bkey in combinations(keys, 2):
        A, B = fire[a], fire[bkey]
        ex[f"{a}|{bkey}"] = int(np.intersect1d(A, B, assume_unique=True).size)
        cv[f"{a}>{bkey}"] = _cov(A, B, cfg.tol_bars)
        cv[f"{bkey}>{a}"] = _cov(B, A, cfg.tol_bars)
    return {"n": n, "exact": ex, "cov": cv}


def _cov(A: np.ndarray, B: np.ndarray, tol: int) -> int:
    """A 의 발화 중 **±tol봉 안에 B 발화가 있는** 개수."""
    if A.size == 0 or B.size == 0:
        return 0
    j = np.searchsorted(B, A)
    ok = np.zeros(A.size, dtype=bool)
    for off in (0, -1):                      # 바로 뒤 / 바로 앞 이웃만 보면 된다
        idx = np.clip(j + off, 0, B.size - 1)
        ok |= np.abs(B[idx] - A) <= tol
    return int(ok.sum())


# ══════════════════════════════════════════════════════════════════════
#  ④ 자기검사 — 파라미터 도달 · 감응 · 눈금
# ══════════════════════════════════════════════════════════════════════
def selftest() -> None:
    # ⚠ 순수 랜덤워크로는 RSI≤12·거래량z≥3 이 **한 번도** 안 난다. 그러면
    #   "발화 0" 이 코드 결함인지 표본 탓인지 못 가린다. 그래서 **급락 사건을
    #   심은** 합성표본을 쓴다 — 실제 이 지표들이 잡으려는 게 그 사건이다.
    rng = np.random.default_rng(11)
    n = 6000
    ret = rng.normal(0, 0.004, n)
    vol = rng.lognormal(10, 0.5, n)
    for c0 in rng.choice(np.arange(400, n - 60), size=40, replace=False):
        L = int(rng.integers(6, 16))
        ret[c0:c0 + L] -= rng.uniform(0.010, 0.030, L)   # 연속 급락
        vol[c0:c0 + L] *= rng.uniform(8, 30)             # 거래량 폭증
        ret[c0 + L:c0 + L + 6] += rng.uniform(0.005, 0.020, 6)   # 되돌림
    px = 100 * np.exp(np.cumsum(ret))
    ix = pd.date_range("2025-01-01", periods=n, freq="5min")
    b = pd.DataFrame({"open": px, "high": px * (1 + rng.random(n) * 0.003),
                      "low": px * (1 - rng.random(n) * 0.003), "close": px,
                      "volume": vol}, index=ix)
    cfg = OverlapConfig()

    # ⓐ 전부 발화하는가 — 0이면 그 지표는 표에서 무의미하다
    res = signals_for_symbol(cfg, "T", b)
    if res is None:
        raise SystemExit("합성 표본이 min_bars 미만이다")
    q = res["_q"]
    fire = res["fixed"]
    dead = [k for k, v in fire.items() if len(v) == 0]
    if dead:
        raise SystemExit(f"**발화 0인 지표** — 문턱이 합성표본에 안 맞는다: {dead}")
    log.info("✔ 발화 확인 — %s", " ".join(f"{k}:{len(v)}" for k, v in fire.items()))

    # ⓑ 문턱 감응 — 조이면 줄어야 한다. 안 줄면 파라미터가 도달 안 한 것이다
    for base, tighter in ((Ind("t", "A", "", "rsi", (14,)),
                           Ind("t", "A", "", "rsi", (14,))),
                          (Ind("t", "B", "", "bb", (20, 2.0)),
                           Ind("t", "B", "", "bb", (20, 2.0))),
                          (Ind("t", "C", "", "vwap", (96, 2.0)),
                           Ind("t", "C", "", "vwap", (96, 2.0)))):
        n0 = _match_count(base, b, "long", 300, 40)[0].size
        n1 = _match_count(tighter, b, "long", 300, 12)[0].size
        if not (n1 < n0):
            raise SystemExit(f"**목표가 신호를 안 바꾼다** — {base.kind}: {n0}→{n1}")
        log.info("✔ 목표 감응 — %-6s 목표40→%d건 · 목표12→%d건", base.kind, n0, n1)

    # ⓒ 방향 — 숏은 롱과 같은 봉에서 켜지면 안 된다
    fl = cross_back(_inside(INDICATORS[0], b, "long"))
    fs = cross_back(_inside(INDICATORS[0], b, "short"))
    if int((fl & fs).sum()):
        raise SystemExit("롱·숏이 같은 봉에서 발화했다")
    log.info("✔ 방향 확인 — 롱 %d봉 / 숏 %d봉 · 겹침 0",
             int(fl.sum()), int(fs.sum()))

    # ⓓ **눈금 ①** — bb 와 z 는 수학적으로 같은 지표다. 1.000 이 아니면
    #    척도 자체가 틀린 것이다.
    A, B = fire["bb20_2"], fire["z20_2"]
    if not np.array_equal(A, B):
        raise SystemExit(f"**눈금이 깨졌다** — bb20_2({A.size}) ≠ z20_2({B.size}). "
                         "동일 정의인데 다르면 계산기가 틀렸다")
    log.info("✔ 눈금① 확인 — bb20_2 ≡ z20_2 (%d봉 완전일치)", A.size)

    # ⓔ 미래참조 — 뒤를 잘라도 앞쪽 발화가 안 변해야 한다
    half = b.iloc[: n // 2]
    f2 = signals_for_symbol(OverlapConfig(min_bars=100), "T", half)["fixed"]
    for k in fire:
        a = fire[k][fire[k] < n // 2 - 60]
        c_ = f2[k][f2[k] < n // 2 - 60]
        if not np.array_equal(a, c_):
            raise SystemExit(f"**미래참조** — {k}: 뒤를 자르니 앞 발화가 변했다 "
                             f"({a.size} vs {c_.size})")
    log.info("✔ 미래참조 없음 — 10개 지표 전부 뒤 절단에 불변")

    # ⓕ 허용매칭 계산기
    if _cov(np.array([10, 50]), np.array([12, 999]), 3) != 1:
        raise SystemExit("_cov 가 ±tol 을 틀렸다")
    if _cov(np.array([10]), np.array([14]), 3) != 0:
        raise SystemExit("_cov 가 tol 밖을 셌다")
    if _cov(np.array([10]), np.array([7]), 3) != 1:
        raise SystemExit("_cov 가 **앞쪽** 이웃을 못 본다")
    log.info("✔ 허용매칭 확인 — ±%d봉, 앞뒤 양쪽", cfg.tol_bars)

    # ⓖ 워밍업 공통 절단
    f3 = signals_for_symbol(OverlapConfig(warmup_bars=1500), "T", b)["fixed"]
    if any(v.size and v.min() < 1500 for v in f3.values()):
        raise SystemExit("워밍업 공통 절단이 도달하지 않았다")
    log.info("✔ 워밍업 공통 절단 확인")

    # ⓗ **빈도 맞춤이 실제로 빈도를 맞추는가** — 이게 이번 판의 핵심 장치다.
    #    맞춘 뒤에도 발화 수가 몇 배씩 벌어지면 비교가 여전히 오염된다.
    mt = res["matched"]
    cnt = {k: len(v) for k, v in mt.items()}
    tgt = cnt[ANCHOR]
    off = {k: abs(n_ - tgt) / max(tgt, 1) for k, n_ in cnt.items()}
    bad_m = [k for k, d in off.items() if d > 0.25 and k not in res["_cap"]]
    if bad_m:
        raise SystemExit(f"**빈도 맞춤 실패** — 기준 {tgt}건인데 {bad_m} "
                         f"= { {k: cnt[k] for k in bad_m} } (capped 아님)")
    if len(res["_cap"]) > 2:
        raise SystemExit(f"맞춤 불가 지표가 너무 많다 — {res['_cap']} {cnt}")
    log.info("✔ 빈도 맞춤 확인 — 기준 %d건 · 발화수 %s · 도달불가 %s",
             tgt, cnt, res["_cap"] or "없음")
    tied = [k for k, t in res["_tie"].items() if t > 0.5]
    if tied:
        raise SystemExit(f"**동점 지배 지표** {tied} — 이 희소도에서 등급을 못 "
                         f"매긴다. 겹침이 낮게 나와도 잡음이지 '다른 지표'가 아니다")
    log.info("✔ 동점 확인 — 경계 동점 최대 %.0f%%",
             100 * max(res["_tie"].values()))
    if not np.array_equal(mt["bb20_2"], mt["z20_2"]):
        raise SystemExit("빈도 맞춤에서 눈금① 이 깨졌다")
    log.info("✔ 눈금① 확인(맞춤) — bb20_2 ≡ z20_2 (%d봉)", len(mt["bb20_2"]))
    log.info("✔ 자기검사 통과")


# ══════════════════════════════════════════════════════════════════════
#  ⑤ 실행 — 로더는 RSI 하네스와 **같은 것**을 쓴다
# ══════════════════════════════════════════════════════════════════════
def run_symbol(cfg: OverlapConfig, sym: str) -> dict:
    from scripts.research.rsi_tp_sl_harness import load_1m_resampled
    # 워밍업분을 **창 앞에서** 확보한다. 창 안에서 워밍업하면 앞구간이 죽는다.
    pre = pd.Timestamp(cfg.start) - pd.Timedelta(minutes=5 * (cfg.warmup_bars + 50))
    bars = load_1m_resampled(sym, cfg.tf, cfg.min_bars,
                             pre.strftime("%Y-%m-%d"), cfg.end)
    if bars is None:
        return {"symbol": sym, "error": "1m 데이터 부족"}
    res = signals_for_symbol(cfg, sym, bars)
    if res is None:
        return {"symbol": sym, "error": f"봉 {len(bars)} < {cfg.min_bars}"}
    q = res.pop("_q")
    capped = res.pop("_cap")
    qmatch = res.pop("_qmatch")
    ties = res.pop("_tie")
    # 창 검사 — 요청 구간 밖(워밍업 확보용 앞구간) 발화는 버린다
    ts = bars.index
    lo = pd.Timestamp(cfg.start)
    if ts.tz is not None:
        lo = lo.tz_localize(ts.tz)
    out_of_win = 0
    r: dict = {"symbol": sym, "bars": int(len(bars)), "anchor_rate": q,
               "capped": capped, "qmatch": qmatch, "ties": ties,
               "first": str(ts[0]), "last": str(ts[-1])}
    for mode in ("fixed", "matched"):
        fire = res[mode]
        for k, v in fire.items():
            keep = v[ts[v] >= lo]
            out_of_win += int(v.size - keep.size)
            fire[k] = keep
        r[mode] = pair_counts(cfg, fire)
    r["dropped_pre_window"] = out_of_win
    return r


def main() -> int:
    p = argparse.ArgumentParser(description="지표 신호 중복도")
    p.add_argument("--tf", default="5m")
    p.add_argument("--side", default="long", choices=["long", "short"])
    p.add_argument("--start", default="2025-08-17")
    p.add_argument("--end", default="2026-08-17")
    p.add_argument("--tol-bars", type=int, default=3)
    p.add_argument("--min-bars", type=int, default=2000)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--symbols", default="")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--preflight", type=int, default=3)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--tag", default="")
    a = p.parse_args()

    selftest()
    if a.selftest:
        return 0

    cfg = OverlapConfig(tf=a.tf, side=a.side, start=a.start, end=a.end,
                        tol_bars=a.tol_bars, min_bars=a.min_bars)
    log.info("설정 전문: %s", json.dumps(asdict(cfg), ensure_ascii=False))

    syms = [x.strip().upper() for x in a.symbols.split(",") if x.strip()]
    if not syms:
        syms = sorted({x.strip().upper() for x in
                       (ROOT / cfg.universe_file).read_text().split() if x.strip()})
    if a.limit:
        syms = syms[:a.limit]
    log.info("종목 %d · 워커 %d · 지표 %d · 쌍 %d",
             len(syms), a.workers, len(INDICATORS),
             len(INDICATORS) * (len(INDICATORS) - 1) // 2)

    rows: list = []
    t0 = datetime.now()

    def _run(ss: list) -> None:
        if a.workers <= 1:
            for i, s_ in enumerate(ss, 1):
                rows.append(run_symbol(cfg, s_))
                if i % 5 == 0:
                    _save(rows, cfg, a, partial=True)
                    log.info("[%d/%d] %.0f초", i, len(ss),
                             (datetime.now() - t0).total_seconds())
            return
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            fut = {ex.submit(run_symbol, cfg, s_): s_ for s_ in ss}
            for i, f in enumerate(as_completed(fut), 1):
                rows.append(f.result())
                if i % 5 == 0:
                    _save(rows, cfg, a, partial=True)
                    log.info("[%d/%d] %.0f초 · 누적 신호 %s", i, len(ss),
                             (datetime.now() - t0).total_seconds(),
                             f"{sum(sum(r.get('n', {}).values()) for r in rows):,}")

    # 예비비행 — 본실행과 **같은 경로·같은 워커 수**
    if a.preflight > 0 and len(syms) > a.preflight:
        log.info("예비비행 — %d종목", a.preflight)
        _run(syms[:a.preflight])
        # ⚠ 관문이 보는 키를 산출물 키와 **같이** 유지해야 한다. 반환형을
        #   두 모드로 바꾸면서 여기만 옛 키('n')를 봐 정상 실행이 '실패'로
        #   찍혔다 — 그리고 rows 전문을 로그에 토했다. 교훈 #88 그대로다.
        ok = [r for r in rows if "matched" in r]
        if not ok:
            log.error("예비비행 실패 — %s",
                      [r.get("error", r.get("symbol")) for r in rows])
            return 1
        tg = {k: sum(r["matched"]["n"][k] for r in ok) for k in
              (i.key for i in INDICATORS)}
        lo_, hi_ = min(tg.values()), max(tg.values())
        if lo_ and hi_ / lo_ > 1.5:
            log.error("예비비행 실패 — 빈도 맞춤이 어긋났다 %s", tg)
            return 1
        log.info("예비비행 통과 — %d종목 · %.0f초 · 맞춤 발화 %d~%d건",
                 len(ok), (datetime.now() - t0).total_seconds(), lo_, hi_)
        syms = syms[a.preflight:]

    _run(syms)
    _save(rows, cfg, a, partial=False)
    report(rows, cfg)
    return 0


def _save(rows, cfg, a, partial: bool) -> None:
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        nm = ("partial_" if partial else "") + f"overlap_{a.tag or cfg.key()}.json"
        (OUT_DIR / nm).write_text(json.dumps(
            {"config": asdict(cfg), "rows": rows}, ensure_ascii=False))
    except Exception as e:
        log.warning("저장 실패: %s", e)


# ══════════════════════════════════════════════════════════════════════
#  ⑥ 판독
# ══════════════════════════════════════════════════════════════════════
def report(rows: list, cfg: OverlapConfig) -> None:
    ok = [r for r in rows if "fixed" in r]
    bad = [r for r in rows if "fixed" not in r]
    keys = [i.key for i in INDICATORS]
    lab = {i.key: i for i in INDICATORS}

    print("\n" + "=" * 80)
    print(f"지표 신호 중복도 — {cfg.side} · {cfg.tf} · {cfg.start}~{cfg.end}")
    print(f"종목 {len(ok)} 성공 / {len(bad)} 실패 · 허용 ±{cfg.tol_bars}봉 · "
          f"기준 {ANCHOR}")
    if ok:
        ar = np.array([r["anchor_rate"] for r in ok])
        print(f"기준 발화율(구간 안 봉 비율) 중앙 {np.median(ar)*100:.3f}% · "
              f"최소 {ar.min()*100:.3f}% · 최대 {ar.max()*100:.3f}%")
    print("=" * 80)

    for mode, title in (("matched", "빈도 맞춤 — RSI 와 **같은 발화율**로 문턱을 자름"),
                        ("fixed", "관례 문턱 — 교과서 값 그대로")):
        _report_mode(ok, cfg, keys, lab, mode, title)

    if bad:
        print(f"\n[!] 실패 {len(bad)}종목: "
              f"{', '.join(sorted({r.get('error','?')[:40] for r in bad}))}")
    print()


def _report_mode(ok, cfg, keys, lab, mode: str, title: str) -> None:
    N = {k: sum(r[mode]["n"][k] for r in ok) for k in keys}
    SYM = {k: sum(1 for r in ok if r[mode]["n"][k] > 0) for k in keys}
    EX, CV = {}, {}
    for a_, b_ in combinations(keys, 2):
        EX[(a_, b_)] = sum(r[mode]["exact"][f"{a_}|{b_}"] for r in ok)
        CV[(a_, b_)] = sum(r[mode]["cov"][f"{a_}>{b_}"] for r in ok)
        CV[(b_, a_)] = sum(r[mode]["cov"][f"{b_}>{a_}"] for r in ok)

    print("\n" + "─" * 80)
    print(f"■ {mode.upper()} — {title}")
    print("─" * 80)

    print("\n[1] 지표별 발화량")
    hdr = f"{'지표':<12} {'계열':<7} {'신호수':>9} {'종목':>5} {'종목당중앙':>10}"
    print(hdr + ("   동점%" if mode == "matched" else "") + "  설명")
    for k in keys:
        med = np.median([r[mode]["n"][k] for r in ok]) if ok else 0
        flag = "  ⚠검정력부족" if N[k] < cfg.min_signals else ""
        tie = ""
        if mode == "matched":
            tv = np.median([r["ties"].get(k, 0.0) for r in ok]) if ok else 0.0
            tie = f"{100*tv:>7.0f}%" + ("⚠" if tv > 0.5 else " ")
        print(f"{k:<12} {lab[k].family:<7} {N[k]:>9,} {SYM[k]:>5} "
              f"{med:>10.0f}{tie}  {lab[k].label}{flag}")
    if mode == "matched":
        bad_t = [k for k in keys
                 if np.median([r["ties"].get(k, 0.0) for r in ok] or [0]) > 0.5]
        if bad_t:
            print(f"    ⚠ **동점 지배** {bad_t} — 이 희소도에서 등급을 못 매긴다. "
                  f"뽑기가 무작위라 겹침이 낮아도 '다른 지표'가 아니라 잡음이다.")

    print(f"\n[2] 자카드 — ±{cfg.tol_bars}봉 허용 (같은 사건으로 본다)")
    _matrix(keys, lambda x, y: _jacc_tol(CV, N, x, y))

    # ⚠ 라벨을 값에 맞춘다. 셀 = CV[(행,열)]/N[행] = **행이 발화했을 때
    #   열도 ±tol 안에 발화한 비율**. 예비비행 판에서 이 라벨이 뒤집혀 있었다.
    print(f"\n[3] 조건부 커버리지 — '**행** 지표가 발화했을 때 "
          f"**열** 지표도 ±{cfg.tol_bars}봉 안에 발화한 비율'")
    _matrix(keys, lambda x, y: 1.0 if x == y else
            ((CV[(y, x)] / N[y]) if N[y] else float("nan")), symmetric=False)

    print(f"\n[4] {ANCHOR} 기준 — 새 지표가 가져오는 **RSI 밖의 신호**")
    print(f"{'지표':<12} {'신호수':>9} {'RSI중복':>9} {'신규':>9} {'신규비율':>9}")
    for k in keys:
        if k == ANCHOR:
            continue
        dup = CV[(k, ANCHOR)]
        print(f"{k:<12} {N[k]:>9,} {dup:>9,} {N[k]-dup:>9,} "
              f"{(1 - dup / N[k]) * 100 if N[k] else 0:>8.1f}%")

    print(f"\n[5] 눈금 — 이 값보다 **낮아야** '다른 지표'다")
    for a_, b_, why in (("bb20_2", "z20_2", "수학적 동일 → 이 척도의 1.0"),
                        ("rsi14_12", "rsi21_12", "같은 지표 · 기간만 14→21"),
                        ("stoch14_12", "willr14_88", "같은 지표 · 평활만 다름")):
        print(f"    {a_:<11} ↔ {b_:<11} {_jacc_tol(CV, N, a_, b_):.3f}   ← {why}")

    print(f"\n[6] 계열 안 vs 계열 밖 (±{cfg.tol_bars}봉 자카드 중앙값)")
    fam = {}
    for a_, b_ in combinations(keys, 2):
        if {a_, b_} in ({"bb20_2", "z20_2"}, {"rsi14_12", "rsi21_12"},
                        {"stoch14_12", "willr14_88"}):
            continue                      # 눈금 쌍은 표본이 아니다
        same = lab[a_].family == lab[b_].family
        fam.setdefault(("계열 안" if same else "계열 밖"), []).append(
            _jacc_tol(CV, N, a_, b_))
    for k2 in ("계열 안", "계열 밖"):
        v = [x for x in fam.get(k2, []) if x == x]
        if v:
            print(f"    {k2}  중앙 {np.median(v):.3f}  "
                  f"(최소 {min(v):.3f} ~ 최대 {max(v):.3f}, {len(v)}쌍)")


def _jacc(EX, N, x, y):
    if x == y:
        return 1.0
    a, b = (x, y) if (x, y) in EX else (y, x)
    u = N[x] + N[y] - EX[(a, b)]
    return EX[(a, b)] / u if u else float("nan")


def _jacc_tol(CV, N, x, y):
    """양쪽 매칭 개수의 합 / 양쪽 신호 수의 합. 비대칭을 한 값으로 접는다."""
    if x == y:
        return 1.0
    tot = N[x] + N[y]
    return (CV[(x, y)] + CV[(y, x)]) / tot if tot else float("nan")


def _matrix(keys, f, symmetric: bool = True) -> None:
    w = 11
    print(" " * 12 + "".join(f"{k[:9]:>{w}}" for k in keys))
    for y in keys:
        cells = []
        for x in keys:
            if symmetric and keys.index(x) < keys.index(y):
                cells.append(" " * w)
            else:
                v = 1.0 if x == y else f(x, y)
                cells.append(f"{v:>{w}.3f}" if v == v else f"{'—':>{w}}")
        print(f"{y[:11]:<12}" + "".join(cells))


if __name__ == "__main__":
    raise SystemExit(main())
