"""틱 국면 기질 — 격자 진입 위약을 **시간 단위**로 접어 둔다.

## 왜 (2026-08-27)

30분봉 국면 기질(`regime_baseline_30m.csv`, 4년·377종목)은 **하루 한 값**이고
끝점 수익률만 담는다. 가는 길이 없다. 그런데 익절·손절을 얼마로 잡을지는
표류가 아니라 **진폭**이 정한다 — 실측에서 표류는 −0.68~+2.24% 로 흔들리는데
진폭(유리+불리)은 2.40~3.74% 로 안정적이었다.

틱은 두 가지를 더 준다.
    ① 시간 해상도  하루 한 값 → 매 시간(원하면 매 분)
    ② 경로         유리폭(MFE)·불리폭(MAE) — 끝점만이 아니라 가는 길

같은 것을 재는지 확인했다 — 08-26 겹치는 구간 357종목에서 30분봉 기질과
**스피어만 ρ +0.703 · 피어슨 r +0.832**. 순서는 맞고, 수준 차이는 틱이 그날
12:12 UTC 부터라 절반만 덮기 때문이다.

## 무엇을 담나

    후행(지금 알 수 있다)   tr_1h · tr_3h · tr_6h(직전 수익률) · rv_1h(실현변동성)
                            · rng_1h(고저폭)
    선도(지나야 안다)       h∈{30,60,180,360}분 마다
                            fwd_med/mean · up_frac · mfe_med/p75 · mae_med/p75

⚠ **선도를 실시간 판단에 쓰면 미래참조다.** 그래서 조회 API(`app/services/
  tick_regime.py`)가 `state()`(후행만)와 `forward()`(사후 진단)로 갈라 놓았다.

⚠ 격자 진입이다 — **신호를 안 본다**. 그래서 어떤 전략에도 붙는다. 전략의
  거래를 같은 (종목·시각·지평) 의 이 값과 대면 그 전략의 **초과분**이 나온다.
  이번 세션에서 지지·저항 세 축이 닫히고 띠 경계만 살아남은 것도 이 대조군이
  "롱만 벌었다(표류)"와 "양쪽 다 벌었다(규칙)"를 갈랐기 때문이다.

⚠ 여물지 않은 앵커는 **버린다**. 자료 끝에서 지평만큼은 선도가 없다. 잘라
  쓰면 최근 시간대가 조용히 유리해진다.

사용:
  python3 -m scripts.research.build_tick_regime --smoke 10
  python3 -m scripts.research.build_tick_regime --merge
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
log = logging.getLogger("tick_regime")

HORIZONS = (30, 60, 180, 360)          # 분
TRAILING = (60, 180, 360)              # 후행 창(분)


@dataclass(frozen=True)
class Cfg:
    step_min: int = 5          # 앵커 간격
    min_anchors: int = 6       # 이보다 적은 시간대는 안 낸다
    min_ticks: int = 2_000
    hours_back: int = 0        # 0 = 있는 만큼 전부


def _bars(t: pd.DataFrame) -> pd.DataFrame:
    g = t.groupby(t.ts_ms // 60_000)
    b = pd.DataFrame({"hi": g.price.max(), "lo": g.price.min(),
                      "cl": g.price.last()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    # ⚠ 체결이 없는 분은 봉이 없다. 앞 값으로 채워야 지평이 시간과 맞는다.
    full = pd.date_range(b.index.min(), b.index.max(), freq="1min", tz="UTC")
    return b.reindex(full).ffill()


def one(sym: str, cfg: Cfg) -> pd.DataFrame | None:
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))
    if not fs:
        return None
    t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                   for f in fs], ignore_index=True)
    t = t[(t.price > 0) & (t.qty > 0)]          # 가짜 체결(바이낸스 원본)
    if cfg.hours_back:
        t = t[t.ts_ms >= (time.time() - cfg.hours_back * 3600) * 1000]
    if len(t) < cfg.min_ticks:
        return None
    b = _bars(t.sort_values("ts_ms"))
    hi, lo, cl = (b.hi.to_numpy(float), b.lo.to_numpy(float),
                  b.cl.to_numpy(float))
    n = len(cl)
    if n < max(HORIZONS) + max(TRAILING) + 60:
        return None

    lr = np.diff(np.log(np.maximum(cl, 1e-12)), prepend=np.log(max(cl[0], 1e-12)))
    rows = []
    start = max(TRAILING)
    # ⚠ **끝까지** 돈다. 선도 지평이 안 들어가는 최근 앵커도 후행은 멀쩡하다.
    #   예전엔 n-max(HORIZONS) 에서 멈춰 후행까지 같이 버렸고, 그 결과
    #   실시간 함수 state() 가 **7시간 묵은 값**을 돌려줬다(2026-08-27 적발).
    #   선도는 자리마다 NaN 으로 두고, 읽는 쪽이 여물었는지 보고 쓴다.
    for i in range(start, n, cfg.step_min):
        e = cl[i]
        if e <= 0:
            continue
        r = {"symbol": sym, "ts": b.index[i]}
        # ── 후행 — 지금 알 수 있다
        for w in TRAILING:
            r[f"tr_{w}"] = 100.0 * (e / cl[i - w] - 1.0) if cl[i - w] > 0 else np.nan
        r["rv_60"] = float(np.std(lr[i - 60:i]) * np.sqrt(60) * 100.0)
        r["rng_60"] = 100.0 * (hi[i - 60:i].max() - lo[i - 60:i].min()) / e
        # ── 선도 — 지나야 안다
        for h in HORIZONS:
            j = i + h
            if j >= n:                  # 아직 안 여물었다 — 잘라 쓰지 않는다
                r[f"fwd_{h}"] = r[f"mfe_{h}"] = r[f"mae_{h}"] = np.nan
                continue
            up = 100.0 * (hi[i + 1:j + 1].max() - e) / e
            dn = 100.0 * (e - lo[i + 1:j + 1].min()) / e
            r[f"fwd_{h}"] = 100.0 * (cl[j] - e) / e
            r[f"mfe_{h}"] = up          # 롱 기준 유리폭 = 숏 기준 불리폭
            r[f"mae_{h}"] = dn
        rows.append(r)
    if len(rows) < cfg.min_anchors:
        return None
    A = pd.DataFrame(rows)
    A["hour"] = A.ts.dt.floor("1h")
    agg = {"n_anchors": ("symbol", "size")}
    for w in TRAILING:
        agg[f"tr_{w}"] = (f"tr_{w}", "median")
    agg["rv_60"] = ("rv_60", "median")
    agg["rng_60"] = ("rng_60", "median")
    for h in HORIZONS:
        agg[f"n_{h}"] = (f"fwd_{h}", "count")     # 여문 앵커 수(0 이면 미성숙)
        agg[f"fwd_{h}_med"] = (f"fwd_{h}", "median")
        agg[f"fwd_{h}_mean"] = (f"fwd_{h}", "mean")
        agg[f"up_{h}"] = (f"fwd_{h}", lambda s: 100.0 * (s > 0).mean())
        agg[f"mfe_{h}_med"] = (f"mfe_{h}", "median")
        agg[f"mfe_{h}_p75"] = (f"mfe_{h}", lambda s: s.quantile(0.75))
        agg[f"mae_{h}_med"] = (f"mae_{h}", "median")
        agg[f"mae_{h}_p75"] = (f"mae_{h}", lambda s: s.quantile(0.75))
    G = A.groupby("hour").agg(**agg).reset_index()
    G = G[G.n_anchors >= cfg.min_anchors]
    G.insert(0, "symbol", sym)
    return G if len(G) else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--symbols", default="")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--step-min", type=int, default=None)
    p.add_argument("--hours-back", type=int, default=None)
    p.add_argument("--merge", action="store_true",
                   help="기존 표에 이어 붙인다. (symbol,hour) 중복은 **새 값 우선** "
                        "— 선도가 여물면서 바뀌기 때문이다")
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    over = {k: v for k, v in
            (("step_min", a.step_min), ("hours_back", a.hours_back))
            if v is not None}
    cfg = Cfg(**over)
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))
    for k, v in over.items():                    # 파라미터 도달 증명
        assert getattr(cfg, k) == v, f"{k} 가 설정에 도달하지 않았다"

    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            if a.symbols else
            [s.strip().upper() for s in
             (ROOT / a.universe).read_text().split() if s.strip()])
    if a.smoke:
        syms = syms[:a.smoke]
    log.info("틱 국면 기질 — %d종목 · 지평 %s분 · 앵커 %d분 간격",
             len(syms), HORIZONS, cfg.step_min)

    t0, parts, empty = time.time(), [], 0
    for i, s in enumerate(syms, 1):
        try:
            r = one(s, cfg)
        except Exception as e:                                  # noqa: BLE001
            log.warning("%s 실패: %s", s, str(e)[:100]); r = None
        if r is None:
            empty += 1
        else:
            parts.append(r)
        if i % 50 == 0 or i == len(syms):
            el = time.time() - t0
            log.info("[%d/%d] 행 %s · 없음 %d · %.1f분 · 남은 %.1f분", i, len(syms),
                     f"{sum(len(x) for x in parts):,}", empty, el / 60,
                     (len(syms) - i) * el / i / 60)
    if not parts:
        raise SystemExit(
            "한 종목도 못 만들었다 — 틱이 최소 "
            f"{(max(HORIZONS)+max(TRAILING)+60)/60:.0f}시간은 있어야 한다")
    R = pd.concat(parts, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_regime.csv"
    if a.merge and path.exists():
        old = pd.read_csv(path); old["hour"] = pd.to_datetime(old.hour, utc=True)
        R["hour"] = pd.to_datetime(R.hour, utc=True)
        before = len(old)
        R = (pd.concat([old, R], ignore_index=True)
               .drop_duplicates(subset=["symbol", "hour"], keep="last")
               .sort_values(["symbol", "hour"]))
        log.info("병합 — 기존 %s행 → %s행", f"{before:,}", f"{len(R):,}")
    R.to_csv(path, index=False)
    log.info("저장 %s — %s행 · 종목 %d · 시간 %d · %.1f분", path, f"{len(R):,}",
             R.symbol.nunique(), R.hour.nunique(), (time.time() - t0) / 60)

    R["hour"] = pd.to_datetime(R.hour, utc=True)
    ripe = R.groupby("hour")[f"n_{max(HORIZONS)}"].sum()
    log.info("선도 %d분이 여문 시간대 %d / %d", max(HORIZONS),
             int((ripe > 0).sum()), len(ripe))
    m = R.groupby("hour").agg(종목=("symbol", "nunique"),
                              표류=("fwd_360_med", "median"),
                              유리=("mfe_360_med", "median"),
                              불리=("mae_360_med", "median"),
                              변동성=("rv_60", "median"))
    m["진폭"] = m.유리 + m.불리
    print("\n■ 시간별 국면 (앞으로 6시간 · 마지막 12시간)")
    print(m.tail(12).round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
