"""후행 지표로 **앞을 맞힐 수 있나** — 횡단면 순위 검정.

## 왜 이 설계인가 (2026-08-27)

"지금 강한 상승"은 후행이라 쉽다. 어려운 건 "앞으로 오른다"다. 이 트랙에서
후행 국면으로 앞을 맞히는 시도가 여러 번 닫혔다 — 비겹침 과거→선도 48h
상관이 **r −0.05** 였다.

그래서 시계열이 아니라 **횡단면**으로 짠다.

    같은 시각 안에서 종목을 신호로 줄 세우고, 상위군 − 하위군 선도수익률.

이러면 그 시간대의 시장 표류가 **통째로 상쇄된다**. 시장이 3% 올랐든 내렸든
상·하위 양쪽에 똑같이 실리므로 차이에는 안 남는다. 시계열로 재면 표류를
예측력으로 읽게 된다 — 이번 세션에서 네 번 그랬다.

## 🚨 시간대 안 겹침 — 이것부터 막아야 한다 (2026-08-28 실측)

시간대 하나에 앵커가 12개다(H:00, H:05, … H:55). 그런데

    H:55 의 **후행** 1시간 = [H-1:55, H:55]
    H:00 의 **선도** 1시간 = [H:00,   H+1:00]

**둘이 55분 겹친다.** 시간 단위로 접으면 그 겹침이 신호와 표적에 같이 들어가
없는 예측력을 만든다. 실측:

    lag 0h(겹침)   +0.331%p  t **+95.8**
    lag 1h(겹침 X) +0.005%p  t   +1.7      ← **66배 축소**

t 95 는 금융 신호에서 나올 수 없는 크기다. 그런데 **장치 4종이 전부 통과했다** —
IS/OOS 둘 다 강했고, 13/13 개월 양수였고, '비겹침' 장치는 시간대 **사이**
겹침만 없앴지 시간대 **안** 겹침은 그대로 뒀다. 결함이 판 구성 단계에 있으면
그 뒤 장치는 전부 같은 허상을 검증한다.

그래서 `--lag-hours` **기본값이 1** 이다. 0 으로 내리려면 왜 겹치지 않는지
먼저 답할 수 있어야 한다.

## 위약 — 같은 시각 안에서 섞는다

⚠ 신호를 **시각 안에서만** 섞는다. 전체를 섞으면 시간대 구성이 깨져
  위약이 약해지고 뭐든 통과한다.

⚠ 격자를 뒤지므로 귀무는 **최대통계량**이다(교훈#95). 섞은 자료로 **같은
  격자를 전부 다시** 훑어 그 최고를 기준선으로 쓴다. 칸별 위약은 이미
  선택된 칸이라 통과한다.

⚠ 표본은 **시간 단위 26개**다. 종목 359개를 곱해도 독립인 시점은 26개뿐이다.
  그래서 t 는 **시간대 단위**로 낸다(종목 단위로 내면 부풀려진다).

사용:
  python3 -m scripts.research.tick_forward_signal --reps 500
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "runs" / "research_track" / "regime" / "tick_regime.csv"
OUT = ROOT / "runs" / "research_track" / "regime"
log = logging.getLogger("fwd_signal")

HORIZONS = (60, 180, 360)


@dataclass(frozen=True)
class Cfg:
    q: float = 0.2          # 상·하위 몇 분위를 볼 것인가
    lag_hours: int = 1      # 🚨 신호를 몇 시간 미뤄 쓸 것인가. 0 은 겹친다
    min_symbols: int = 100  # 이보다 적은 시간대는 버린다
    reps: int = 500
    seed: int = 20260827


def signals(d: pd.DataFrame) -> dict[str, pd.Series]:
    """후보 신호 — **전부 후행이다**. 선도 컬럼은 하나도 안 쓴다."""
    rv = d.rv_60.replace(0, np.nan)
    return {
        "모멘텀6h": d.tr_360,
        "모멘텀1h": d.tr_60,
        "모멘텀6h_변동성조정": d.tr_360 / rv,
        "모멘텀1h_변동성조정": d.tr_60 / rv,
        "가속": d.tr_60 - d.tr_180 / 3.0,
        "단기반전": -d.tr_60,
        "장기반전": -d.tr_360,
        "고저폭_변동성비": d.rng_60 / rv,
        "변동성": d.rv_60,
        "일관성": (np.sign(d.tr_60) + np.sign(d.tr_180) + np.sign(d.tr_360)),
    }


def _spreads(D: pd.DataFrame, sig: str, tgt: str, cfg: Cfg) -> pd.Series:
    """시간대별 상위군 − 하위군 (%p) — **벡터화**.

    ⚠ 시간대를 파이썬으로 돌면 1년치(8,736시간)에 위약 500회가 감당이 안 된다.
      분위수는 groupby 한 번, 평균은 마스크 두 번으로 끝난다.
    """
    d = D[["hour", sig, tgt]].dropna()
    if d.empty:
        return pd.Series(dtype=float)
    cnt = d.groupby("hour")[tgt].size()
    ok = cnt[cnt >= cfg.min_symbols].index
    if len(ok) == 0:
        return pd.Series(dtype=float)
    d = d[d.hour.isin(ok)]
    q = d.groupby("hour")[sig].quantile([cfg.q, 1 - cfg.q]).unstack()
    lo = d.hour.map(q[cfg.q]); hi = d.hour.map(q[1 - cfg.q])
    # 상·하위가 안 갈리는 시간대(신호가 상수)는 버린다
    valid = hi > lo
    d, lo, hi = d[valid], lo[valid], hi[valid]
    if d.empty:
        return pd.Series(dtype=float)
    top = d[d[sig] >= hi].groupby("hour")[tgt].mean()
    bot = d[d[sig] <= lo].groupby("hour")[tgt].mean()
    return (top - bot).dropna()


def _hac_t(x: np.ndarray, lag: int) -> float:
    """겹치는 표본의 평균에 대한 Newey-West t.

    ⚠ 6시간 지평은 인접 시간대끼리 6시간이 겹친다. 그냥 t 를 내면 부풀려진다 —
      이 트랙에서 비겹침 t 2.01 이 중첩+HAC 로 **−0.62** 가 된 적이 있다
      (교훈#92). 지평에서 유도한 lag 를 쓴다.
    """
    n = len(x)
    if n < 3:
        return 0.0
    m = x.mean()
    e = x - m
    g0 = float((e * e).sum() / n)
    v = g0
    for k in range(1, min(lag, n - 1) + 1):
        gk = float((e[k:] * e[:-k]).sum() / n)
        v += 2.0 * (1.0 - k / (lag + 1.0)) * gk
    if v <= 0:
        return 0.0
    return float(m / np.sqrt(v / n))


def _lag(D: pd.DataFrame, names: list[str], cfg: Cfg) -> pd.DataFrame:
    """신호를 `lag_hours` 만큼 미뤄 표적과 붙인다 — 시간대 안 겹침 차단.

    ⚠ lag 0 이면 H:55 의 후행 창과 H:00 의 선도 창이 55분 겹친다. 그 겹침만으로
      t 가 1.7 → 95.8 이 된다(2026-08-28 실측).
    """
    if cfg.lag_hours <= 0:
        return D
    S = D[["symbol", "hour"] + names].copy()
    S["hour"] = S.hour + pd.Timedelta(hours=cfg.lag_hours)
    T = D[["symbol", "hour"] + [c for c in D.columns if c.startswith("fwd_")]]
    return S.merge(T, on=["symbol", "hour"], how="inner")


def evaluate(D: pd.DataFrame, names: list[str], cfg: Cfg) -> pd.DataFrame:
    D = _lag(D, names, cfg)
    rows = []
    for h in HORIZONS:
        tgt = f"fwd_{h}_med"
        for nm in names:
            ser = _spreads(D, nm, tgt, cfg)
            if len(ser) < 5:
                continue
            a = ser.sort_index().to_numpy(dtype=float)
            # ⚠ t 는 **시간대 단위**. 독립인 시점이 그만큼뿐이다.
            t = a.mean() / (a.std(ddof=1) / np.sqrt(len(a))) if a.std(ddof=1) > 0 else 0.0
            # 겹침 보정 — 지평이 h분이면 인접 h/60 시간대가 겹친다
            t_hac = _hac_t(a, max(int(round(h / 60)), 1))
            rows.append({"horizon": h, "signal": nm, "n_hours": len(a),
                         "spread": a.mean(), "median": float(np.median(a)),
                         "t": float(t), "t_hac": t_hac,
                         "win": 100.0 * (a > 0).mean()})
    return pd.DataFrame(rows)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--regime", default="",
                   help="국면 기질 CSV 경로. 비우면 틱 판본")
    p.add_argument("--lag-hours", type=int, default=None,
                   help="🚨 신호를 몇 시간 미룰까. 기본 1. 0 은 시간대 안에서 "
                        "후행·선도 창이 겹쳐 없는 예측력을 만든다")
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--q", type=float, default=None)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    over = {k: v for k, v in (("reps", a.reps), ("q", a.q),
                              ("lag_hours", a.lag_hours)) if v is not None}
    cfg = Cfg(**over)
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))
    for k, v in over.items():
        assert getattr(cfg, k) == v, f"{k} 가 설정에 도달하지 않았다"

    reg = Path(a.regime) if a.regime else REG
    if not reg.exists():
        raise SystemExit(f"국면 기질이 없다: {reg}")
    D = pd.read_csv(reg)
    D["hour"] = pd.to_datetime(D.hour, utc=True)
    sig = signals(D)
    for nm, v in sig.items():
        D[nm] = v
    names = list(sig)
    if cfg.lag_hours <= 0:
        log.warning("🚨 lag_hours=0 — 시간대 안에서 후행·선도 창이 겹친다. "
                    "실측에서 t 1.7 이 95.8 로 부풀었다. 왜 안 겹치는지 "
                    "답할 수 있을 때만 써라")
    log.info("신호 지연 %d시간", cfg.lag_hours)
    log.info("자료 %s행 · 종목 %d · 시간대 %d · 신호 %d × 지평 %d = %d칸",
             f"{len(D):,}", D.symbol.nunique(), D.hour.nunique(),
             len(names), len(HORIZONS), len(names) * len(HORIZONS))

    t0 = time.time()
    R = evaluate(D, names, cfg)
    if R.empty:
        raise SystemExit("한 칸도 못 냈다 — 여문 선도가 있는 시간대를 확인하라")
    # 판정은 **HAC 기준**으로 한다 — 보정 전 t 로 고르면 겹침이 큰 칸이 이긴다
    R["abs_t"] = R.t_hac.abs()
    obs_max = float(R.abs_t.max())

    # ── 최대통계량 귀무: **시각 안에서** 신호를 섞고 같은 격자를 다시 전부
    rng = np.random.default_rng(cfg.seed)
    null = np.empty(cfg.reps)
    S = (D[["hour", "symbol"] + names + [f"fwd_{h}_med" for h in HORIZONS]]
         .sort_values("hour").reset_index(drop=True))
    # ⚠ 시간대를 하나씩 돌며 .loc 로 섞으면 3.1M 행에서 **한 회에 230초**가
    #   걸린다(2026-08-28 실측: 6.4시간에 100회를 못 넘겼다). 시각 순으로
    #   정렬해 두고 (시각, 난수) 로 lexsort 하면 **한 번에** 시각 안 섞기가 된다.
    hour_code = pd.factorize(S.hour, sort=True)[0]
    sig_mat = S[names].to_numpy()
    Z = S.copy()
    for r in range(cfg.reps):
        order = np.lexsort((rng.random(len(S)), hour_code))
        Z[names] = sig_mat[order]
        RR = evaluate(Z, names, cfg)
        null[r] = float(RR.t_hac.abs().max()) if len(RR) else 0.0
        if (r + 1) % 100 == 0:
            log.info("위약 %d/%d · %.1f분", r + 1, cfg.reps, (time.time()-t0)/60)
    p_max = float((null >= obs_max).mean())

    # ── 장치 ①: IS / OOS 분할. 시간순 70/30 — 섞으면 미래가 과거로 샌다
    hrs = np.sort(D.hour.unique())
    cut = hrs[int(len(hrs) * 0.7)]
    R_is = evaluate(D[D.hour < cut], names, cfg).rename(
        columns={"spread": "spread_is", "t_hac": "t_is"})
    R_oos = evaluate(D[D.hour >= cut], names, cfg).rename(
        columns={"spread": "spread_oos", "t_hac": "t_oos"})
    R = R.merge(R_is[["horizon", "signal", "spread_is", "t_is"]],
                on=["horizon", "signal"], how="left")
    R = R.merge(R_oos[["horizon", "signal", "spread_oos", "t_oos"]],
                on=["horizon", "signal"], how="left")

    # ── 장치 ②: 월별 안정성. 한 달이 다 벌었으면 규칙이 아니다
    D2 = D.assign(ym=D.hour.dt.to_period("M").astype(str))
    月 = {}
    for ym, g in D2.groupby("ym"):
        if g.hour.nunique() < 24:
            continue
        rr = evaluate(g, names, cfg)
        if rr.empty or "horizon" not in rr.columns:
            continue
        for _, x in rr.iterrows():
            月.setdefault((x.horizon, x.signal), []).append(x.spread)
    R["n_months"] = R.apply(lambda r: len(月.get((r.horizon, r.signal), [])), axis=1)
    R["months_pos"] = R.apply(
        lambda r: (100.0 * np.mean([v > 0 for v in 月[(r.horizon, r.signal)]])
                   if 月.get((r.horizon, r.signal)) else np.nan), axis=1)
    R["month_worst"] = R.apply(
        lambda r: (min(月[(r.horizon, r.signal)])
                   if 月.get((r.horizon, r.signal)) else np.nan), axis=1)

    # ── 장치 ③: 비겹침 표본. HAC 대신 아예 안 겹치게 뽑아 t 를 다시 낸다
    for i, r in R.iterrows():
        step = max(int(round(r.horizon / 60)), 1)
        sub = D[D.hour.isin(hrs[::step])]
        rr = evaluate(sub, names, cfg)
        # ⚠ 솎아낸 표본에서 한 칸도 안 나오면 rr 은 **컬럼이 없는** 빈 표다.
        #   `rr.horizon` 이 AttributeError 로 터진다 — 2026-08-28 새벽에
        #   3시간짜리 실행이 마지막 단계에서 이걸로 죽었다. 비어 있는지 먼저 본다.
        if rr.empty or "horizon" not in rr.columns:
            R.loc[i, "t_nonoverlap"] = np.nan
            R.loc[i, "n_nonoverlap"] = 0
            continue
        m = rr[(rr.horizon == r.horizon) & (rr.signal == r.signal)]
        R.loc[i, "t_nonoverlap"] = float(m.t.iloc[0]) if len(m) else np.nan
        R.loc[i, "n_nonoverlap"] = int(m.n_hours.iloc[0]) if len(m) else 0

    # ── 장치 ④: 시간대(세션) 통제.
    # ⚠ 실측 결과 이 장치는 **구조상 무효**다. 횡단면 스프레드는 같은 시각 안의
    #   상위−하위라, 그 시각 전체에 상수를 더하거나 빼도 값이 안 변한다. 즉
    #   설계 자체가 이미 모든 시각 수준 효과(표류·세션·변동성 국면)를 제거한다.
    #   남겨 두는 것은 "이미 통제됨"을 눈으로 확인하기 위해서다.
    D3 = D.assign(hod=D.hour.dt.hour)
    for i, r in R.iterrows():
        tgt = f"fwd_{int(r.horizon)}_med"
        # 각 UTC 시각의 평균을 빼서 세션 성분을 제거한 뒤 다시 잰다
        Z = D3.copy()
        Z[r.signal] = Z[r.signal] - Z.groupby("hod")[r.signal].transform("mean")
        Z[tgt] = Z[tgt] - Z.groupby("hod")[tgt].transform("mean")
        rr = evaluate(Z, [r.signal], cfg)
        if rr.empty or "horizon" not in rr.columns:
            R.loc[i, "t_hod_adj"] = np.nan
            continue
        m = rr[rr.horizon == r.horizon]
        R.loc[i, "t_hod_adj"] = float(m.t_hac.iloc[0]) if len(m) else np.nan

    R = R.sort_values("abs_t", ascending=False)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_forward_signal.csv"
    R.to_csv(path, index=False)
    # ⚠ 위약 분포를 **파일로** 남긴다. 화면에만 찍으면 출력이 유실될 때
    #   17분짜리 실행을 통째로 다시 돌려야 한다(2026-08-27 실제로 겪음).
    (path.with_suffix(".null.json")).write_text(json.dumps({
        "obs_max_abs_t_hac": obs_max, "p_max": p_max, "reps": cfg.reps,
        "null_median": float(np.median(null)),
        "null_p95": float(np.quantile(null, 0.95)),
        "null_max": float(null.max()),
        "null": [round(float(x), 4) for x in null],
        "cfg": asdict(cfg)}, ensure_ascii=False, indent=1))

    print(f"\n■ 관측 최대 |t| {obs_max:.2f}  ·  위약 최대 중앙 "
          f"{np.median(null):.2f} · 95분위 {np.quantile(null,0.95):.2f} "
          f"· 최대 {null.max():.2f}")
    print(f"■ **최대통계량 p = {p_max:.3f}**  (위약 {cfg.reps}회)")
    print(f"\n■ 칸별 (시간대 단위 t · 상하위 {cfg.q:.0%})")
    print(R.head(14)[["horizon", "signal", "n_hours", "spread", "median",
                      "t", "t_hac", "win"]].to_string(index=False,
          float_format=lambda x: f"{x:.3f}"))
    print("\n■ 장치 4종 — 하나만 통과한 것은 통과가 아니다(교훈#96)")
    cols = ["horizon", "signal", "spread", "t_hac", "spread_is", "t_is",
            "spread_oos", "t_oos", "n_months", "months_pos", "month_worst",
            "t_nonoverlap", "n_nonoverlap", "t_hod_adj"]
    print(R.head(10)[cols].to_string(index=False,
          float_format=lambda x: f"{x:.3f}"))
    print("\n  읽는 법 — 관측 최대통계량 p 를 통과해도 ①OOS 부호가 유지되고 "
          "②월별 대부분 양수이고\n  ③비겹침에서도 살아 있고 ④세션 제거 후에도 "
          "남아야 한다. 하나라도 무너지면 후보다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
