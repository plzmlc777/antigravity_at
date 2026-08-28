"""봉 기반 국면 기질 — 틱과 **같은 스키마**로, 대신 몇 년치.

## 왜 (2026-08-27)

틱으로 만든 국면 기질(`tick_regime.csv`)로 후행→선도 신호를 검정했더니 최대
통계량 위약을 통과했다(p 0.008). 그런데 **표본이 시간대 26개, 그것도 같은
하루**다. 위약 통과는 "이 하루 안에서 우연이 아니다"까지만 말한다.

표본을 늘리는 길은 위약을 더 돌리는 게 아니라 **다른 날을 보는 것**이다.
`ohlcv_1m` 은 4년치가 있다. 틱 대신 1분봉으로 같은 것을 만든다.

⚠ 틱 대신 1분봉을 써도 되나 — 된다. 후행(구간수익률·실현변동성·고저폭)과
  선도(끝점·MFE·MAE)는 전부 분 단위 고저로 충분하다. 틱이 필요한 건 분 안의
  **체결 순서**인데 이 기질에는 그런 항목이 없다.

⚠ 출력 컬럼을 틱 판본과 **똑같이** 맞춘다. 그래야 `tick_forward_signal.py`
  가 `--regime` 만 바꿔 그대로 돈다. 스키마가 갈라지면 두 벌을 유지하게 된다.

⚠ 종목마다 자료 구간이 다르다(BTC·ETH 는 최근 365일 중 140일뿐). 커버리지를
  세어서 남긴다 — 유니버스 평균을 조용히 기울이는 함정이다.

⚠ 종목마다 **부분 저장**한다. 끝에 한 번에 쓰다 몇 시간을 잃을 수 있다.
  이미 있는 종목은 건너뛰므로 중단해도 이어서 돌릴 수 있다.

사용:
  python3 -m scripts.research.build_bar_regime --smoke 3
  python3 -m scripts.research.build_bar_regime --days 365
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.rsi_tp_sl_harness import load_1m_resampled  # noqa: E402

OUT = ROOT / "runs" / "research_track" / "regime"
log = logging.getLogger("bar_regime")

HORIZONS = (60, 180, 360)      # 분 — 틱 판본과 동일
TRAILING = (60, 180, 360)


@dataclass(frozen=True)
class Cfg:
    days: int = 365
    step_min: int = 5
    min_anchors: int = 6
    min_bars: int = 5_000      # 이보다 짧은 종목은 안 낸다


def one(sym: str, cfg: Cfg, a: str, b: str) -> pd.DataFrame | None:
    bars = load_1m_resampled(sym, "1m", cfg.min_bars, a, b)
    if bars is None or len(bars) < max(TRAILING) + max(HORIZONS) + 60:
        return None
    # ⚠ 결측 분은 앞 값으로 채운다. 안 채우면 "60봉 전"이 60분 전이 아니다.
    idx = pd.date_range(bars.index.min(), bars.index.max(), freq="1min")
    bars = bars.reindex(idx).ffill()
    hi, lo, cl = (bars.high.astype(float), bars.low.astype(float),
                  bars.close.astype(float))
    d = pd.DataFrame(index=bars.index)
    # ── 후행
    for w in TRAILING:
        d[f"tr_{w}"] = (cl / cl.shift(w) - 1.0) * 100.0
    lr = np.log(cl.clip(lower=1e-12)).diff()
    d["rv_60"] = lr.rolling(60).std() * np.sqrt(60) * 100.0
    d["rng_60"] = (hi.rolling(60).max() - lo.rolling(60).min()) / cl * 100.0
    # ── 선도. rolling(h).max().shift(-h) 는 [i+1, i+h] 구간의 최대다.
    for h in HORIZONS:
        top = hi.rolling(h).max().shift(-h)
        bot = lo.rolling(h).min().shift(-h)
        d[f"fwd_{h}"] = (cl.shift(-h) / cl - 1.0) * 100.0
        d[f"mfe_{h}"] = (top / cl - 1.0) * 100.0
        d[f"mae_{h}"] = (1.0 - bot / cl) * 100.0

    d = d.iloc[max(TRAILING)::cfg.step_min]          # 앵커만
    d = d[d[[f"tr_{w}" for w in TRAILING]].notna().all(axis=1)]
    if len(d) < cfg.min_anchors:
        return None
    d["hour"] = d.index.floor("1h")
    agg = {"n_anchors": ("rv_60", "size")}
    for w in TRAILING:
        agg[f"tr_{w}"] = (f"tr_{w}", "median")
    agg["rv_60"] = ("rv_60", "median")
    agg["rng_60"] = ("rng_60", "median")
    for h in HORIZONS:
        agg[f"n_{h}"] = (f"fwd_{h}", "count")
        agg[f"fwd_{h}_med"] = (f"fwd_{h}", "median")
        agg[f"fwd_{h}_mean"] = (f"fwd_{h}", "mean")
        agg[f"up_{h}"] = (f"fwd_{h}", lambda s: 100.0 * (s > 0).mean())
        agg[f"mfe_{h}_med"] = (f"mfe_{h}", "median")
        agg[f"mfe_{h}_p75"] = (f"mfe_{h}", lambda s: s.quantile(0.75))
        agg[f"mae_{h}_med"] = (f"mae_{h}", "median")
        agg[f"mae_{h}_p75"] = (f"mae_{h}", lambda s: s.quantile(0.75))
    G = d.groupby("hour").agg(**agg).reset_index()
    G = G[G.n_anchors >= cfg.min_anchors]
    G.insert(0, "symbol", sym)
    return G if len(G) else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--symbols", default="")
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--step-min", type=int, default=None)
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--sleep", type=float, default=0.3,
                   help="종목 사이 쉼 — 실거래가 같은 DB 를 쓴다")
    p.add_argument("--out", default="")
    p.add_argument("--fresh", action="store_true", help="이어 하지 않고 새로")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    over = {k: v for k, v in (("days", a.days), ("step_min", a.step_min))
            if v is not None}
    cfg = Cfg(**over)
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))
    for k, v in over.items():
        assert getattr(cfg, k) == v, f"{k} 가 설정에 도달하지 않았다"

    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            if a.symbols else
            [s.strip().upper() for s in
             (ROOT / a.universe).read_text().split() if s.strip()])
    if a.smoke:
        syms = syms[:a.smoke]
    end = pd.Timestamp.now(tz="UTC").tz_localize(None).floor("h")
    start = end - pd.Timedelta(days=cfg.days)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / f"bar_regime_1h_{cfg.days}d.csv"

    done: set[str] = set()
    if a.fresh and path.exists():
        path.unlink()
    elif path.exists():
        try:
            done = set(pd.read_csv(path, usecols=["symbol"]).symbol.unique())
            log.info("이어서 — 이미 %d종목 있음", len(done))
        except Exception:                                       # noqa: BLE001
            done = set()

    todo = [s for s in syms if s not in done]
    log.info("봉 국면 기질 — %d종목(남은 %d) · %s ~ %s",
             len(syms), len(todo), start.date(), end.date())

    t0, n_ok, n_rows = time.time(), 0, 0
    for i, s in enumerate(todo, 1):
        try:
            r = one(s, cfg, str(start), str(end))
        except Exception as e:                                  # noqa: BLE001
            log.warning("%s 실패: %s", s, str(e)[:100]); r = None
        if r is not None:
            # ⚠ 종목마다 곧바로 덧붙인다 — 끝에 한 번에 쓰다 몇 시간을 잃지 않는다
            r.to_csv(path, mode="a", header=not path.exists(), index=False)
            n_ok += 1; n_rows += len(r)
        if i % 10 == 0 or i == len(todo):
            el = time.time() - t0
            log.info("[%d/%d] 성공 %d · 행 %s · %.1f분 · 남은 %.1f분",
                     i, len(todo), n_ok, f"{n_rows:,}", el / 60,
                     (len(todo) - i) * el / i / 60)
        time.sleep(a.sleep)

    D = pd.read_csv(path)
    D["hour"] = pd.to_datetime(D.hour)
    cov = D.groupby("symbol").hour.nunique().sort_values()
    log.info("완료 — %s행 · 종목 %d · 시간대 %d · %.1f분", f"{len(D):,}",
             D.symbol.nunique(), D.hour.nunique(), (time.time() - t0) / 60)
    print(f"\n■ 커버리지 — 종목당 시간대 중앙 {cov.median():.0f} · "
          f"최대 {cov.max()} · 최소 {cov.min()}")
    print("  가장 얇은 5: " + ", ".join(f"{s}({n})" for s, n in cov.head(5).items()))
    per = D.groupby("hour").symbol.nunique()
    print(f"■ 시간대당 종목 수 — 중앙 {per.median():.0f} · "
          f"100종목 이상인 시간대 {int((per >= 100).sum()):,} / {len(per):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
