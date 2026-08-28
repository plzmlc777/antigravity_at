"""짧은 지평 횡단면 검정 — 시간 단위로 접지 않는다.

## 왜 다시 짜나 (2026-08-28, 대표님 지적)

앞선 검정은 앵커를 **시간 단위로 접었다**. 그러니 한 시간 안 12개 앵커에서
H:55 의 후행 창과 H:00 의 선도 창이 55분 겹쳤고, 그 겹침만으로 t 가 1.7 →
95.8 이 됐다.

접지 않으면 그 문제가 **구조적으로** 사라진다.

    앵커 i 에서   후행 = [i-60, i]      선도 = [i, i+h]
                  경계를 공유할 뿐 겹치지 않는다

그리고 지평을 1·5·10·30·60분으로 내리면 시행 횟수가 크게 는다. 37시간에
5분 간격이면 **444회**다(시간 단위로 접었을 때는 37회였다).

## 무엇을 재나

각 앵커 시각에서 종목을 신호로 줄 세우고 상위 20% − 하위 20% 의 선도수익률.
같은 시각 안 비교라 그 순간의 시장 표류·세션·변동성 국면이 **전부 상쇄**된다.

⚠ 지평이 앵커 간격보다 길면 이웃 앵커끼리 겹친다. 그래서 두 가지를 같이 낸다.
    t_hac        중첩 보정(Newey-West, lag = 지평/간격)
    t_nonoverlap 아예 안 겹치게 앵커를 솎아 다시 계산

⚠ 위약은 **같은 시각 안에서** 신호를 섞고 같은 격자를 전부 다시 훑은 최댓값
  (교훈#95). 칸별 위약은 이미 선택된 칸이라 통과한다.

⚠ 마찰: 왕복 수수료는 지정가 0.036% · 시장가 0.09%. 스프레드가 이보다 작으면
  통계가 아무리 좋아도 거래가 안 된다.

사용:
  python3 -m scripts.research.tick_short_signal --smoke 20
  python3 -m scripts.research.tick_short_signal --reps 300
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
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "research_track" / "regime"
log = logging.getLogger("short_sig")

HORIZONS = (1, 5, 10, 30, 60)      # 분 — 대표님 지정 범위
TRAILING = (5, 15, 60, 180)        # 후행 창(분)


@dataclass(frozen=True)
class Cfg:
    step_min: int = 5           # 앵커 간격
    q: float = 0.2
    min_symbols: int = 100
    min_ticks: int = 2_000
    fee_pct: float = 0.036      # 지정가 왕복
    reps: int = 300
    seed: int = 20260828


def panel(syms: list[str], cfg: Cfg) -> pd.DataFrame:
    """(시각, 종목) 판. 시간 단위로 **접지 않는다**."""
    parts = []
    for s in syms:
        d = TICKS / s
        fs = sorted(d.glob("*.parquet"))
        if not fs:
            continue
        t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                       for f in fs], ignore_index=True)
        t = t[(t.price > 0) & (t.qty > 0)]
        if len(t) < cfg.min_ticks:
            continue
        g = t.sort_values("ts_ms").groupby(t.ts_ms // 60_000)
        cl = g.price.last()
        cl.index = pd.to_datetime(cl.index * 60_000, unit="ms", utc=True)
        # ⚠ 체결 없는 분은 앞 값으로 — 안 채우면 "60봉 전"이 60분 전이 아니다
        cl = cl.reindex(pd.date_range(cl.index.min(), cl.index.max(),
                                      freq="1min", tz="UTC")).ffill()
        if len(cl) < max(TRAILING) + max(HORIZONS) + 30:
            continue
        f = pd.DataFrame(index=cl.index)
        for w in TRAILING:
            f[f"tr_{w}"] = (cl / cl.shift(w) - 1.0) * 100.0
        lr = np.log(cl.clip(lower=1e-12)).diff()
        f["rv"] = lr.rolling(60).std() * np.sqrt(60) * 100.0
        for h in HORIZONS:
            f[f"y_{h}"] = (cl.shift(-h) / cl - 1.0) * 100.0
        f = f.iloc[max(TRAILING)::cfg.step_min]
        f = f.dropna(subset=[f"tr_{w}" for w in TRAILING] + ["rv"])
        if f.empty:
            continue
        f["symbol"] = s
        parts.append(f.reset_index(names="ts"))
    if not parts:
        raise SystemExit("판을 못 만들었다 — 틱 구간을 확인하라")
    return pd.concat(parts, ignore_index=True)


def signals(d: pd.DataFrame) -> dict[str, pd.Series]:
    """후보 — 전부 **후행**이다."""
    rv = d.rv.replace(0, np.nan)
    return {
        "모멘텀5m": d.tr_5,
        "모멘텀15m": d.tr_15,
        "모멘텀1h": d.tr_60,
        "모멘텀3h": d.tr_180,
        "모멘텀5m_변동성조정": d.tr_5 / rv,
        "모멘텀1h_변동성조정": d.tr_60 / rv,
        "가속": d.tr_5 - d.tr_15 / 3.0,
        "단기반전": -d.tr_5,
        "장기반전": -d.tr_180,
        "변동성": d.rv,
    }


def _spread(D: pd.DataFrame, sig: str, tgt: str, cfg: Cfg) -> pd.Series:
    d = D[["ts", sig, tgt]].dropna()
    if d.empty:
        return pd.Series(dtype=float)
    cnt = d.groupby("ts")[tgt].size()
    d = d[d.ts.isin(cnt[cnt >= cfg.min_symbols].index)]
    if d.empty:
        return pd.Series(dtype=float)
    q = d.groupby("ts")[sig].quantile([cfg.q, 1 - cfg.q]).unstack()
    lo, hi = d.ts.map(q[cfg.q]), d.ts.map(q[1 - cfg.q])
    ok = hi > lo
    d, lo, hi = d[ok], lo[ok], hi[ok]
    if d.empty:
        return pd.Series(dtype=float)
    top = d[d[sig] >= hi].groupby("ts")[tgt].mean()
    bot = d[d[sig] <= lo].groupby("ts")[tgt].mean()
    return (top - bot).dropna()


def _hac_t(x: np.ndarray, lag: int) -> float:
    n = len(x)
    if n < 3:
        return 0.0
    e = x - x.mean()
    g0 = float((e * e).sum() / n)
    v = g0
    for k in range(1, min(lag, n - 1) + 1):
        v += 2.0 * (1.0 - k / (lag + 1.0)) * float((e[k:] * e[:-k]).sum() / n)
    return float(x.mean() / np.sqrt(v / n)) if v > 0 else 0.0


def evaluate(D: pd.DataFrame, names: list[str], cfg: Cfg,
             full: bool = False) -> pd.DataFrame:
    rows = []
    for h in HORIZONS:
        # 지평이 간격보다 길면 이웃 앵커가 겹친다
        lag = max(int(np.ceil(h / cfg.step_min)) - 1, 0)
        for nm in names:
            ser = _spread(D, nm, f"y_{h}", cfg)
            if len(ser) < 10:
                continue
            a = ser.sort_index().to_numpy(float)
            t = (a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))
                 if a.std(ddof=1) > 0 else 0.0)
            r = {"horizon": h, "signal": nm, "n": len(a), "spread": a.mean(),
                 "t": float(t), "t_hac": _hac_t(a, lag) if lag else float(t),
                 "win": 100.0 * (a > 0).mean()}
            if full:
                step = lag + 1
                b = a[::step]
                r["t_nonoverlap"] = (b.mean() / (b.std(ddof=1) / np.sqrt(len(b)))
                                     if len(b) > 3 and b.std(ddof=1) > 0 else np.nan)
                r["n_nonoverlap"] = len(b)
                r["net"] = a.mean() - cfg.fee_pct
            rows.append(r)
    return pd.DataFrame(rows)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--step-min", type=int, default=None)
    p.add_argument("--split", default="2026-08-27 12:00",
                   help="IS/OOS 경계(UTC). 이 뒤는 어제 검정 시점에 없던 자료")
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    over = {k: v for k, v in (("reps", a.reps), ("step_min", a.step_min))
            if v is not None}
    cfg = Cfg(**over)
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))
    for k, v in over.items():
        assert getattr(cfg, k) == v, f"{k} 가 설정에 도달하지 않았다"

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    t0 = time.time()
    D = panel(syms, cfg)
    for nm, v in signals(D).items():
        D[nm] = v
    names = list(signals(D))
    log.info("판 %s행 · 종목 %d · 앵커시각 %s · %.1f분", f"{len(D):,}",
             D.symbol.nunique(), f"{D.ts.nunique():,}", (time.time()-t0)/60)
    log.info("지평 %s분 · 앵커 간격 %d분 · 격자 %d칸",
             HORIZONS, cfg.step_min, len(HORIZONS) * len(names))

    R = evaluate(D, names, cfg, full=True)
    if R.empty:
        raise SystemExit("한 칸도 못 냈다")
    obs = float(R.t_hac.abs().max())

    # ── 최대통계량 위약: 같은 **시각** 안에서 섞고 같은 격자 재탐색
    rng = np.random.default_rng(cfg.seed)
    S = D[["ts", "symbol"] + names +
          [f"y_{h}" for h in HORIZONS]].sort_values("ts").reset_index(drop=True)
    code = pd.factorize(S.ts, sort=True)[0]
    mat = S[names].to_numpy()
    Z = S.copy()
    null = np.empty(cfg.reps)
    for r in range(cfg.reps):
        Z[names] = mat[np.lexsort((rng.random(len(S)), code))]
        rr = evaluate(Z, names, cfg)
        null[r] = float(rr.t_hac.abs().max()) if len(rr) else 0.0
        if (r + 1) % 50 == 0:
            log.info("위약 %d/%d · %.1f분", r + 1, cfg.reps, (time.time()-t0)/60)
    p_max = float((null >= obs).mean())

    # ── IS / OOS. OOS 는 어제 검정 시점에 **존재하지 않던** 자료다
    cut = pd.Timestamp(a.split, tz="UTC")
    R_is = evaluate(D[D.ts <= cut], names, cfg).rename(
        columns={"spread": "spread_is", "t_hac": "t_is", "n": "n_is"})
    R_oos = evaluate(D[D.ts > cut], names, cfg).rename(
        columns={"spread": "spread_oos", "t_hac": "t_oos", "n": "n_oos"})
    R = (R.merge(R_is[["horizon", "signal", "spread_is", "t_is", "n_is"]],
                 on=["horizon", "signal"], how="left")
          .merge(R_oos[["horizon", "signal", "spread_oos", "t_oos", "n_oos"]],
                 on=["horizon", "signal"], how="left"))
    R["abs_t"] = R.t_hac.abs()
    R = R.sort_values("abs_t", ascending=False)

    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_short_signal.csv"
    R.to_csv(path, index=False)
    path.with_suffix(".null.json").write_text(json.dumps(
        {"obs": obs, "p_max": p_max, "reps": cfg.reps,
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, 0.95)),
         "null_max": float(null.max()),
         "null": [round(float(x), 4) for x in null],
         "cfg": asdict(cfg)}, ensure_ascii=False, indent=1))

    print(f"\n■ 관측 최대 |t_hac| {obs:.2f} · 위약 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,0.95):.2f} · 최대 {null.max():.2f}")
    print(f"■ **최대통계량 p = {p_max:.3f}** (위약 {cfg.reps}회)")
    print(f"\n■ 상위 14칸 (마찰 {cfg.fee_pct}% 왕복)")
    cols = ["horizon", "signal", "n", "spread", "net", "t_hac",
            "t_nonoverlap", "n_nonoverlap", "win", "spread_is", "t_is",
            "spread_oos", "t_oos"]
    print(R.head(14)[cols].to_string(index=False,
          float_format=lambda x: f"{x:.3f}"))
    print(f"\n  저장 {path} · 총 {(time.time()-t0)/60:.1f}분")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
