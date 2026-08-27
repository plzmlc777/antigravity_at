"""틱 국면 기질 — 전략과 무관한 **시간 단위** 시장 눈금.

## 무엇인가

(종목, 시각) 마다 "그때 시장이 뭘 줬나"를 담은 표다. 격자 진입이라 신호를
안 본다 — 그래서 어떤 전략에도 붙는다. 만드는 쪽은
`scripts/research/build_tick_regime.py`.

    후행(backward)  tr_60 · tr_180 · tr_360 · rv_60 · rng_60   → **지금 알 수 있다**
    선도(forward)   fwd_* · up_* · mfe_* · mae_*               → **그 시간이 지나야 안다**

선도값을 실시간 판단에 쓰면 미래참조다. 그래서 `state()` 는 후행만 돌려주고,
선도는 `forward()`/`diagnose()` 로 **사후임을 명시**해서 부른다.
[[regime_baseline]] 과 같은 규약이다.

## 30분봉 기질과의 관계 — 대체재가 아니다

    regime_baseline_30m   4년 · 하루 한 값 · 끝점만        → **자**  (오늘이 이상한가)
    tick_regime           수일 · 시간 단위 · 경로 포함      → **돋보기** (지금 뭘 주나)

같은 것을 재는지 확인했다(2026-08-27, 08-26 겹치는 구간 357종목):
**스피어만 ρ +0.703 · 피어슨 r +0.832**. 수준 차이는 틱이 그날 절반만 덮어서다.

## 왜 경로가 중요한가 (실측)

표류는 시간대마다 −0.68 ~ +2.24% 로 크게 흔들리는데 **진폭(유리+불리)은
2.40 ~ 3.74% 로 안정적**이다. 익절·손절을 얼마로 잡을지는 표류가 아니라
진폭이 정한다 — 30분봉 기질에는 이 축이 없다.

## 가장 쓸모 있는 용법 — `control()`

전역 표류 하나를 빼는 것보다, **종목·방향·지평까지 맞춘** 무작위 앵커 값을
대조군으로 쓰는 게 훨씬 강하다. 2026-08-27 세션에서 지지·저항 세 축이 닫히고
띠 경계만 살아남은 것도 이 대조군이 "롱만 벌었다(표류)" 와 "양쪽 다 벌었다
(규칙)" 를 갈랐기 때문이다.

## 🚫 이 대조군을 **익절·손절 있는 원장**에 쓰지 마라

여기 담긴 값은 **지평까지 그냥 들고 있었을 때**의 결과다. 익절·손절이 있는
전략과 대면 상방이 잘린 쪽만 손해를 본다. 실측(2026-08-27, 같은 원장):

    하네스 대조군(무작위 시각 + **같은 익절·손절**)   롱 초과 **+0.393%p**
    이 기질 대조군(무작위 시각 + 무제한 360분 보유)   롱 초과 **−0.590%p**

같은 전략인데 부호가 뒤집힌다. 대조군은 **진입 시각만이 아니라 청산 규칙까지**
맞춰야 한다. 익절·손절이 있으면 그 규칙을 무작위 시각에 그대로 적용한 대조군을
직접 만들어라(참조: `scripts/research/tick_band_edge.py` 의 `arm="무작위"`).

`excess()` 는 **고정 지평 보유** 전략에만 쓴다.

⚠ 보관은 예산제다(50GB ≈ 182일). 오래된 날은 지워지므로 `coverage()` 로
  구간부터 확인하고 써라. 없는 구간을 조용히 빈 값으로 받으면 안 된다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "runs" / "research_track" / "regime" / "tick_regime.csv"

HORIZONS = (30, 60, 180, 360)
TRAILING = (60, 180, 360)
BACKWARD_COLS = tuple(f"tr_{w}" for w in TRAILING) + ("rv_60", "rng_60")
FORWARD_PREFIX = ("fwd_", "up_", "mfe_", "mae_")


class TickRegimeMissing(RuntimeError):
    """기질 파일이 없다 — 조용한 빈 표를 돌려주지 않는다."""


@lru_cache(maxsize=2)
def load() -> pd.DataFrame:
    if not PATH.exists():
        raise TickRegimeMissing(
            f"틱 국면 기질이 없다: {PATH}\n"
            f"  만들기: python3 -m scripts.research.build_tick_regime")
    d = pd.read_csv(PATH)
    d["hour"] = pd.to_datetime(d["hour"], utc=True)
    return d.sort_values(["symbol", "hour"]).reset_index(drop=True)


def reload() -> pd.DataFrame:
    """갱신 후 다시 읽는다 — 상주 프로세스는 캐시를 비워야 새 값을 본다."""
    load.cache_clear()
    return load()


def coverage() -> dict:
    """무엇이 얼마나 들어 있나 — **쓰기 전에 확인하라**.

    ⚠ 틱은 예산제로 오래된 날부터 지워진다. 구간을 넘나드는 비교는 종목 수와
      시간 수를 명시해야 한다.
    """
    d = load()
    per = d.groupby("symbol").hour.agg(["min", "max", "size"])
    out = {"rows": len(d), "symbols": int(d.symbol.nunique()),
           "start": d.hour.min(), "end": d.hour.max(),
           "hours": int(d.hour.nunique()),
           "hours_per_symbol_median": float(per["size"].median()),
           "thinnest": per["size"].nsmallest(3).to_dict()}
    # ⚠ 후행은 끝까지 있지만 선도는 지평만큼 뒤처진다. 둘을 따로 알려준다.
    for h in HORIZONS:
        col = f"n_{h}"
        if col in d.columns:
            ripe = d[d[col] > 0]
            out[f"forward_{h}m_end"] = ripe.hour.max() if len(ripe) else None
    return out


def _ts(x) -> pd.Timestamp:
    """tz 유무를 가리지 않고 UTC 로 맞춘다.

    ⚠ `pd.Timestamp(aware, tz=...)` 는 예외를 던진다. 호출부가 aware 를 줄지
      naive 를 줄지 모르므로 한 곳에서 흡수한다.
    """
    ts = pd.Timestamp(x)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _ripe_cutoff(horizon: int) -> pd.Timestamp:
    """이 시각 이후는 선도가 아직 안 여물었다."""
    return load().hour.max() - timedelta(minutes=horizon)


# ── ① 후행 — 실시간에 쓸 수 있다 ────────────────────────────
def state(symbol: str, asof: datetime | str | None = None) -> dict:
    """`asof` 시점에 **관측 가능한** 시장 상태. 선도값은 절대 넣지 않는다.

    돌려주는 것
        tr_60/180/360  직전 1·3·6시간 수익률(%)
        rv_60          직전 1시간 실현변동성(%)
        rng_60         직전 1시간 고저폭(%)
        age_min        쓴 값이 몇 분 전 것인가
    """
    d = load()
    d = d[d.symbol == symbol]
    if d.empty:
        return {"symbol": symbol, "n_hours": 0}
    asof = _ts(asof) if asof is not None else _ts(datetime.now(timezone.utc))
    # ⚠ asof **이하**만 본다. 같은 시간대 값은 그 시간이 끝나야 온전하지만
    #   후행 지표라 미래참조는 아니다 — 다만 age_min 으로 신선도를 드러낸다.
    past = d[d.hour <= asof]
    if past.empty:
        return {"symbol": symbol, "n_hours": 0, "asof": asof}
    r = past.iloc[-1]
    out = {"symbol": symbol, "asof": asof, "n_hours": int(len(past)),
           "hour": r.hour, "n_anchors": int(r.n_anchors),
           "age_min": float((asof - r.hour).total_seconds() / 60)}
    for c in BACKWARD_COLS:
        out[c] = float(r[c]) if c in r and pd.notna(r[c]) else np.nan
    return out


def market_state(asof: datetime | str | None = None,
                 min_symbols: int = 50) -> dict:
    """유니버스 전체의 후행 상태(중앙값). 종목이 모자라면 **소리내어 막는다**."""
    d = load()
    asof = _ts(asof) if asof is not None else _ts(datetime.now(timezone.utc))
    past = d[d.hour <= asof]
    if past.empty:
        return {"asof": asof, "n_symbols": 0}
    last = past.hour.max()
    cur = past[past.hour == last]
    if len(cur) < min_symbols:
        raise ValueError(f"{last} 종목 {len(cur)}개 < 최소 {min_symbols} — "
                         f"중앙값이 못 믿을 만하다")
    out = {"asof": asof, "hour": last, "n_symbols": int(len(cur)),
           "age_min": float((asof - last).total_seconds() / 60)}
    for c in BACKWARD_COLS:
        out[c] = float(cur[c].median())
    return out


# ── ② 선도 — 사후 진단·대조군 전용 ──────────────────────────
def forward(symbol: str, at: datetime | str, horizon: int = 360) -> dict:
    """그 시각 시장이 앞으로 무엇을 줬나 — **사후 전용**.

    ⚠ 실시간 경로에서 부르면 미래참조다. 규칙에 쓰지 마라.
    """
    if horizon not in HORIZONS:
        raise ValueError(f"horizon 은 {list(HORIZONS)} — {horizon!r}")
    d = load()
    at = _ts(at).floor("1h")
    r = d[(d.symbol == symbol) & (d.hour == at)]
    if r.empty:
        return {"symbol": symbol, "hour": at, "ripe": False, "reason": "행 없음"}
    r = r.iloc[0]
    # 성숙 판정은 **그 행이 실제로 몇 개를 셌는지**로 한다. 시각 비교만 쓰면
    # 자료 구멍(체결 없음·재연결 공백)을 성숙으로 오독한다.
    n_ripe = int(r.get(f"n_{horizon}", 0) or 0)
    if n_ripe == 0 or pd.isna(r[f"fwd_{horizon}_med"]):
        return {"symbol": symbol, "hour": at, "ripe": False,
                "reason": f"{horizon}분이 아직 안 지났다(여문 앵커 {n_ripe}개)"}
    return {"symbol": symbol, "hour": at, "ripe": True, "horizon": horizon,
            "n_anchors": int(r.n_anchors), "n_ripe": n_ripe,
            "fwd_med": float(r[f"fwd_{horizon}_med"]),
            "fwd_mean": float(r[f"fwd_{horizon}_mean"]),
            "up_frac": float(r[f"up_{horizon}"]),
            "mfe_med": float(r[f"mfe_{horizon}_med"]),
            "mfe_p75": float(r[f"mfe_{horizon}_p75"]),
            "mae_med": float(r[f"mae_{horizon}_med"]),
            "mae_p75": float(r[f"mae_{horizon}_p75"]),
            "amplitude": float(r[f"mfe_{horizon}_med"] + r[f"mae_{horizon}_med"])}


def control(symbol: str, at: datetime | str, horizon: int = 360,
            direction: str = "long") -> dict:
    """**대조군** — 같은 종목·시각·지평에 아무 때나 들어갔으면 뭘 받았나.

    전략의 거래를 이 값과 대면 그 전략의 **초과분**이 나온다. 전역 표류 하나를
    빼는 것보다 훨씬 강하다 — 종목·방향·지평이 전부 맞춰져 있기 때문이다.

    ⚠ 숏은 롱의 정확한 거울이다(부호 반전 + 유리/불리 교환). 롱만 재고
      "벌었다" 하면 그날 표류를 규칙 효과로 읽는다(교훈#91).
    """
    if direction not in ("long", "short"):
        raise ValueError("direction 은 'long' 또는 'short'")
    f = forward(symbol, at, horizon)
    if not f.get("ripe"):
        return f
    if direction == "short":
        f = {**f, "fwd_med": -f["fwd_med"], "fwd_mean": -f["fwd_mean"],
             "up_frac": 100.0 - f["up_frac"],
             "mfe_med": f["mae_med"], "mfe_p75": f["mae_p75"],
             "mae_med": f["mfe_med"], "mae_p75": f["mfe_p75"]}
    f["direction"] = direction
    return f


def excess(trades: pd.DataFrame, *, symbol_col: str = "symbol",
           ts_col: str = "entry_ts", ret_col: str = "ret_pct",
           dir_col: str | None = None, horizon: int = 360,
           i_know_no_tp_sl: bool = False) -> pd.DataFrame:
    """원장에 대조군을 붙이고 **초과분**을 낸다 — 사후 진단 전용.

    🚫 **고정 지평 보유 전략에만 쓴다.** 익절·손절이 있으면 상방이 잘린 쪽만
       손해를 봐서 부호까지 뒤집힌다(실측 +0.393 → −0.590%p). 그런 전략은
       같은 익절·손절을 무작위 시각에 적용한 대조군을 직접 만들어라.

    ⚠ 시각은 **자료에서** 가져와라. 봉 번호로 지어내면 창 시작이 달라 10시간씩
      어긋난 채 "100% 매칭"으로 보고된다 — 실제로 그렇게 틀린 적이 있다.

    붙는 것
        ctl_fwd   그 (종목, 시각) 에 아무 때나 들어갔을 때의 수익률(중앙)
        ctl_mfe / ctl_mae / ctl_amp
        excess    거래 수익률 − ctl_fwd

    ⚠ 여물지 않은 구간은 NaN 으로 둔다. 결손이 5% 를 넘으면 경고한다 —
      조용히 줄어든 표본으로 결론 내지 마라.
    """
    # 익절·손절 흔적이 보이면 소리내어 막는다 — 조용히 틀린 답을 주지 않는다
    hints = [c for c in trades.columns
             if str(c).lower() in ("tp", "sl", "tpf", "slf", "tp_pct", "sl_pct",
                                   "why", "exit_reason")]
    if hints and not i_know_no_tp_sl:
        raise ValueError(
            f"원장에 익절·손절 흔적이 있다({hints}). 이 대조군은 고정 지평 "
            f"보유 기준이라 상방이 잘린 전략과 대면 부호까지 뒤집힌다"
            f"(실측 +0.393 → -0.590%p). 같은 익절·손절을 무작위 시각에 적용한 "
            f"대조군을 직접 만들어라. 정말 고정 지평이면 "
            f"i_know_no_tp_sl=True 로 넘겨라.")
    d = load()
    cut = _ripe_cutoff(horizon)
    keep = ["symbol", "hour", f"fwd_{horizon}_med", f"mfe_{horizon}_med",
            f"mae_{horizon}_med"]
    b = d[keep].rename(columns={f"fwd_{horizon}_med": "ctl_fwd",
                                f"mfe_{horizon}_med": "ctl_mfe",
                                f"mae_{horizon}_med": "ctl_mae"})
    b.loc[b.hour > cut, ["ctl_fwd", "ctl_mfe", "ctl_mae"]] = np.nan
    b["ctl_amp"] = b.ctl_mfe + b.ctl_mae

    t = trades.copy()
    t["_hour"] = pd.to_datetime(t[ts_col], utc=True).dt.floor("1h")
    out = t.merge(b, left_on=[symbol_col, "_hour"], right_on=["symbol", "hour"],
                  how="left", suffixes=("", "_ctl")).drop(columns=["_hour"])
    if dir_col is not None:
        # 숏은 대조군 부호를 뒤집는다
        short = out[dir_col].astype(str).str.lower().isin(("short", "숏", "sell"))
        out.loc[short, "ctl_fwd"] = -out.loc[short, "ctl_fwd"]
        out.loc[short, ["ctl_mfe", "ctl_mae"]] = \
            out.loc[short, ["ctl_mae", "ctl_mfe"]].to_numpy()
    if ret_col in out.columns:
        out["excess"] = out[ret_col] - out["ctl_fwd"]
    miss = float(out["ctl_fwd"].isna().mean())
    if miss > 0.05:
        log.warning("틱 대조군 결손 %.1f%% — 구간이 기질 밖이거나 아직 안 여물었다. "
                    "coverage() 로 보관 구간을 확인하라", 100 * miss)
    return out


def label(drift: float, edges=(-2.0, -0.5, 0.5, 2.0),
          names=("강한하락", "하락", "횡보", "상승", "강한상승")) -> str:
    """표류(%)를 국면 이름으로. 경계는 필요에 맞게 바꿔 쓴다."""
    for e, nm in zip(edges, names):
        if drift <= e:
            return nm
    return names[-1]
