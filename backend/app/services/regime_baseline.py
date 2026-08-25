"""국면 기질 — 전략과 무관한 시장 눈금. 한 번 만들고 계속 읽는다.

## 무엇인가

(종목, 날짜) 마다 "그때 시장이 뭘 줬나"를 담은 표다. 익절·손절·보유를 쓰지
않아 **어떤 전략에도 붙는다**. 만드는 쪽은 `scripts/research/build_regime_baseline.py`.

    symbol, date, n_bars, ret_day, vol_day,
    fwd_6h, fwd_24h, fwd_48h,     선도수익률(%) — 그날 봉들의 평균
    up_6h,  up_24h,  up_48h       그중 양수인 봉의 비율(%)

## 두 종류를 반드시 가른다

    후행(backward)  ret_day · vol_day · trailing_*  → **지금 알 수 있다**
    선도(forward)   fwd_* · up_*                    → **그 시간이 지나야 안다**

선도값을 실시간 판단에 쓰면 미래참조다. 그래서 `state()` 는 후행만 돌려주고,
선도를 원하면 `diagnose()` 로 **사후 진단임을 명시**해서 부른다.

## 왜 만들었나 (2026-08-25)

"어떤 장에서 되고 안 되는가"를 네 번 물어 네 번 닫혔다. 다섯 번째로 위약
(rotate)을 눈금 삼았더니 해석이 명확했는데 — 단위·종목·마찰이 전략과 짝지어
지기 때문이다 — 두 가지가 막았다.

  ① rotate 는 신호를 시간축에서 민 것이라 **위약도 신호 근처에만** 생긴다.
     실측: 2025-10월 실측 367거래인데 위약 12건. 가장 중요한 달을 못 쟀다.
  ② 저장된 위약 24만 건은 설정이 제각각이다(5m/15m/30m · 익절 5~8% ·
     손절 0.3~1.5%). 같은 순간이라도 규칙이 다르면 값이 다르다.

그래서 **격자 진입**으로 다시 만들었다. 신호를 안 본다.

⚠ 이 기질은 **진단**을 위한 것이다. 실측으로 확인된 바:
    과거(비겹침) → 선도 48h  r -0.05  — 예측되지 않는다
  겹친 창으로 재면 r +0.40 이 나오는데 그건 자기상관이다. 이 트랙에서 같은
  실수로 r +0.470 이 비겹침에서 +0.001 이 된 적이 있다.
"""
from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = ROOT / "runs" / "research_track" / "regime"

FORWARD_COLS = ("fwd_6h", "fwd_24h", "fwd_48h", "up_6h", "up_24h", "up_48h")
BACKWARD_COLS = ("ret_day", "vol_day", "n_bars")
# 선도 컬럼이 온전해지려면 그만큼 지나야 한다
HORIZON_HOURS = {"6h": 6, "24h": 24, "48h": 48}


class RegimeBaselineMissing(RuntimeError):
    """기질 파일이 없다 — 조용한 빈 표를 돌려주지 않는다."""


def path_for(tf: str = "30m") -> Path:
    return BASE_DIR / f"regime_baseline_{tf}.csv"


@lru_cache(maxsize=4)
def load(tf: str = "30m") -> pd.DataFrame:
    """기질 표. 프로세스당 한 번만 읽는다(43MB)."""
    p = path_for(tf)
    if not p.exists():
        raise RegimeBaselineMissing(
            f"국면 기질이 없다: {p}\n"
            f"  만들기: python3 -m scripts.research.build_regime_baseline --tf {tf}")
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def coverage(tf: str = "30m") -> dict:
    """무엇이 얼마나 들어 있나 — 쓰기 전에 확인하라.

    ⚠ 과거로 갈수록 종목이 준다(2022년 85 · 2025년 377). 구간을 넘나드는
      비교는 **종목 수를 명시**해야 한다.
    """
    d = load(tf)
    y = d.assign(y=d.date.dt.year).groupby("y").agg(
        symbols=("symbol", "nunique"), rows=("symbol", "size"))
    return {"rows": len(d), "symbols": int(d.symbol.nunique()),
            "start": d.date.min().date(), "end": d.date.max().date(),
            "by_year": y.to_dict("index")}


# ── ① 후행 — 실시간에 쓸 수 있다 ────────────────────────────
def state(symbol: str, asof: datetime | _date | str | None = None,
          tf: str = "30m", lookbacks=(1, 2, 3, 7)) -> dict:
    """`asof` 시점에 **관측 가능한** 시장 상태.

    선도값은 절대 넣지 않는다 — 실시간 경로가 이 함수를 부르기 때문이다.
    후행 창은 `asof` **전날까지**로 끝난다(당일을 넣으면 진입 직전 움직임이
    섞여 겹침이 된다).

    돌려주는 것
        ret_prev      전일 수익률(%)
        vol_prev      전일 변동성(%, 연율)
        trailing_{k}d 전일까지 k일 누적 수익률(%)
        n_days        쓸 수 있었던 과거 일수
    """
    d = load(tf)
    d = d[d.symbol == symbol]
    if asof is None:
        asof = d.date.max() + timedelta(days=1) if len(d) else datetime.utcnow()
    asof = pd.Timestamp(asof).normalize()
    past = d[d.date < asof]                      # ⚠ 당일 제외
    if past.empty:
        return {"symbol": symbol, "asof": asof.date(), "n_days": 0}
    r = past.ret_day.to_numpy(dtype=float)
    out = {"symbol": symbol, "asof": asof.date(), "n_days": int(len(past)),
           "ret_prev": float(r[-1]),
           "vol_prev": float(past.vol_day.iloc[-1])}
    for k in lookbacks:
        if len(r) >= k:
            out[f"trailing_{k}d"] = float(100 * (np.prod(1 + r[-k:] / 100) - 1))
    return out


def market_state(asof: datetime | _date | str | None = None, tf: str = "30m",
                 min_symbols: int = 50, lookbacks=(1, 2, 3, 7)) -> dict:
    """유니버스 전체의 후행 상태(중앙값). 종목이 모자라면 소리내어 막는다.

    ⚠ 실측(2026-08-25): 시장 후행 국면은 이 전략의 익절률을 **가르지 못했다**
      (상위 5일 제외 표본에서 위약 p 0.100). 종목 단위 하락 폭은 갈랐다
      (p 0.001). 시장 국면을 게이트로 쓰기 전에 그 전략에서 다시 재라.
    """
    d = load(tf)
    asof = (pd.Timestamp(asof).normalize() if asof is not None
            else d.date.max() + timedelta(days=1))
    past = d[d.date < asof]
    if past.empty:
        return {"asof": asof.date(), "n_symbols": 0}
    last = past.date.max()
    day = past[past.date == last]
    if len(day) < min_symbols:
        raise ValueError(f"{last.date()} 종목 {len(day)}개 < 최소 {min_symbols} — "
                         f"중앙값이 못 믿을 만하다")
    piv = (past.pivot_table(index="date", columns="symbol", values="ret_day")
           .sort_index())
    med = piv.median(axis=1).to_numpy(dtype=float)
    out = {"asof": asof.date(), "n_symbols": int(len(day)),
           "ret_prev": float(med[-1]),
           "vol_prev": float(day.vol_day.median())}
    for k in lookbacks:
        if len(med) >= k:
            out[f"trailing_{k}d"] = float(100 * (np.prod(1 + med[-k:] / 100) - 1))
    return out


# ── ② 선도 — 사후 진단 전용 ─────────────────────────────────
def diagnose(trades: pd.DataFrame, *, symbol_col: str = "symbol",
             ts_col: str = "entry_ts", tf: str = "30m",
             horizon: str = "48h") -> pd.DataFrame:
    """원장에 **선도** 눈금을 붙인다 — 사후 진단 전용.

    ⚠ 함수 이름이 `diagnose` 인 것은 의도다. 여기서 나오는 `fwd_*` 는 미래를
      보므로 거래 규칙에 쓰면 안 된다. 실시간 판단은 `state()` 를 써라.

    붙는 것
        mkt_fwd   그 (종목, 날짜) 의 선도수익률(%)
        excess    거래 수익률 − mkt_fwd  = 신호의 순수 기여

    ⚠ 최근 `horizon` 만큼은 선도가 아직 안 여물었다. 그 구간은 NaN 으로 둔다.
    """
    if horizon not in HORIZON_HOURS:
        raise ValueError(f"horizon 은 {list(HORIZON_HOURS)} — {horizon!r}")
    b = load(tf)
    cutoff = b.date.max() - timedelta(hours=HORIZON_HOURS[horizon])
    col = f"fwd_{horizon}"
    keep = ["symbol", "date", col, f"up_{horizon}", "ret_day", "vol_day"]
    b = b[keep].rename(columns={col: "mkt_fwd", f"up_{horizon}": "mkt_up"})
    b.loc[b.date > cutoff, ["mkt_fwd", "mkt_up"]] = np.nan   # 아직 안 여물었다

    t = trades.copy()
    t["_date"] = pd.to_datetime(t[ts_col]).dt.normalize()
    out = t.merge(b, left_on=[symbol_col, "_date"], right_on=["symbol", "date"],
                  how="left", suffixes=("", "_base")).drop(columns=["_date"])
    if "ret_pct" in out.columns:
        out["excess"] = out["ret_pct"] - out["mkt_fwd"]
    miss = float(out["mkt_fwd"].isna().mean())
    if miss > 0.05:
        log.warning("국면 눈금 결손 %.1f%% — 유니버스·구간이 기질과 어긋나는지 "
                    "확인하라(연도별 종목 수가 다르다)", 100 * miss)
    return out


def buckets(values, edges=(-5.0, -1.0, 1.0, 5.0),
            labels=("강한하락", "하락", "횡보", "상승", "강한상승")):
    """수익률(%)을 국면 이름으로. 경계는 필요에 맞게 바꿔 쓴다."""
    return pd.cut(values, [-np.inf, *edges, np.inf], labels=list(labels))
