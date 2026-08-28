"""급등·급락 뒤 되돌림 — **절대 문턱** 사건 연구.

## 앞선 검정과 무엇이 다른가 (2026-08-28, 대표님 지적)

`tick_short_signal.py` 는 **횡단면 순위**를 쟀다. 매 순간 359종목을 줄 세워
상위 20% − 하위 20%. 그래서 "많이 올랐다"가 상대적이고, 시장이 조용하면
상위 20%도 +0.1% 다. 평균 되돌림이 1.7bp 로 나왔고 수수료 3.6bp 에 먹혔다.

여기서는 **절대 문턱**을 건다.

    W분 동안 −thr% 이상 떨어졌다  →  롱(반등 기대)
    W분 동안 +thr% 이상 올랐다    →  숏(되돌림 기대)

사건이 드물어지는 대신 폭이 커진다. **빈도 × 엣지**로 판정한다(대표님 지시:
승률·거래당 엣지만 보면 결론이 뒤집힌다).

## 반드시 같이 봐야 하는 것

  ① 반대 방향     급락에 **숏**. 반등이 아니라 추세면 이쪽이 번다(교훈#91)
  ② 무작위 시각   같은 종목·같은 방향·같은 지평, 앵커만 아무 데나.
                  없으면 그 구간의 표류를 사건 효과로 읽는다
  ③ 시장 대비     그 순간 전 종목 중앙값을 뺀 초과 움직임으로도 조건을 건다.
                  시장이 같이 빠진 −3% 와 혼자 빠진 −3% 는 다르다
  ④ 마찰          지정가 왕복 0.036%. 스프레드가 이보다 작으면 통계가 아무리
                  좋아도 거래가 안 된다

⚠ 사건은 **시간과 종목에 뭉친다**. 한 번 급락하면 몇 분간 계속 조건을 만족하고,
  시장이 흔들리면 여러 종목이 동시에 걸린다. 그래서 재무장 규칙을 두고,
  t 는 **시각 클러스터** 기준으로도 낸다.

⚠ 표본은 아직 하루 반이다. 결론이 아니라 지형이다.

사용:
  python3 -m scripts.research.tick_shock_rebound --smoke 40
"""
from __future__ import annotations

import argparse
import itertools
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
log = logging.getLogger("shock")

WINS = (1, 5, 15, 30)              # 충격을 재는 창(분)
THRS = (1.0, 2.0, 3.0, 5.0)        # 문턱(%)
HORIZONS = (5, 15, 30, 60, 120)    # 선도(분)


@dataclass(frozen=True)
class Cfg:
    cooldown: int = 30       # 사건 뒤 이만큼은 같은 종목 재발화 금지(분)
    n_control: int = 40      # 종목당 무작위 앵커
    min_ticks: int = 2_000
    fee_pct: float = 0.036   # 지정가 왕복
    seed: int = 20260828


def bars(sym: str, cfg: Cfg) -> pd.DataFrame | None:
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))
    if not fs:
        return None
    t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                   for f in fs], ignore_index=True)
    t = t[(t.price > 0) & (t.qty > 0)]
    if len(t) < cfg.min_ticks:
        return None
    g = t.sort_values("ts_ms").groupby(t.ts_ms // 60_000)
    b = pd.DataFrame({"hi": g.price.max(), "lo": g.price.min(),
                      "cl": g.price.last()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    full = pd.date_range(b.index.min(), b.index.max(), freq="1min", tz="UTC")
    b = b.reindex(full).ffill()
    return b if len(b) >= max(WINS) + max(HORIZONS) + 30 else None


def _fwd(hi, lo, cl, i, entry, long) -> dict:
    out = {}
    n = len(cl)
    for h in HORIZONS:
        j = i + h
        if j >= n:
            out[f"ret_{h}"] = out[f"mfe_{h}"] = out[f"mae_{h}"] = np.nan
            continue
        top, bot = hi[i + 1:j + 1].max(), lo[i + 1:j + 1].min()
        r = 100.0 * (cl[j] - entry) / entry
        out[f"ret_{h}"] = r if long else -r
        out[f"mfe_{h}"] = (100.0 * (top - entry) / entry if long
                           else 100.0 * (entry - bot) / entry)
        out[f"mae_{h}"] = (100.0 * (entry - bot) / entry if long
                           else 100.0 * (top - entry) / entry)
    return out


def one(sym: str, B: pd.DataFrame, MKT: pd.Series, cfg: Cfg,
        rng) -> list[dict]:
    hi, lo, cl = (B.hi.to_numpy(float), B.lo.to_numpy(float),
                  B.cl.to_numpy(float))
    ts = B.index
    n = len(cl)
    mkt = MKT.reindex(ts).to_numpy(float)          # 그 순간 시장 중앙(%)
    rows: list[dict] = []
    for W in WINS:
        past = np.full(n, np.nan)
        past[W:] = (cl[W:] / cl[:-W] - 1.0) * 100.0
        # 시장 대비 초과 — 시장이 같이 빠진 것과 혼자 빠진 것을 가른다
        mw = np.full(n, np.nan)
        mw[W:] = mkt[W:] - mkt[:-W]
        excess = past - mw
        for thr, rel in itertools.product(THRS, (False, True)):
            v = excess if rel else past
            last = -10 ** 9
            for i in range(max(WINS), n - min(HORIZONS)):
                if not np.isfinite(v[i]) or i - last < cfg.cooldown:
                    continue
                if v[i] <= -thr:
                    ev, long = "급락", True
                elif v[i] >= thr:
                    ev, long = "급등", False
                else:
                    continue
                base = {"symbol": sym, "W": W, "thr": thr,
                        "rel": rel, "event": ev, "i": i, "ts": ts[i],
                        "move": float(v[i])}
                for arm, dirn in (("실측", long), ("반대", not long)):
                    r = dict(base, arm=arm,
                             dir="롱" if dirn else "숏")
                    r.update(_fwd(hi, lo, cl, i, cl[i], dirn))
                    rows.append(r)
                last = i
    # 무작위 대조 — 같은 종목, 롱·숏 양쪽
    k = min(cfg.n_control, max(n - max(WINS) - max(HORIZONS), 1))
    for j in rng.choice(np.arange(max(WINS), n - max(HORIZONS)), size=k,
                        replace=False):
        j = int(j)
        for dirn in (True, False):
            r = {"symbol": sym, "W": 0, "thr": 0.0, "rel": False,
                 "event": "무작위", "i": j, "ts": ts[j], "move": np.nan,
                 "arm": "무작위", "dir": "롱" if dirn else "숏"}
            r.update(_fwd(hi, lo, cl, j, cl[j], dirn))
            rows.append(r)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--cooldown", type=int, default=None)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    over = {k: v for k, v in (("cooldown", a.cooldown),) if v is not None}
    cfg = Cfg(**over)
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))
    for k, v in over.items():
        assert getattr(cfg, k) == v, f"{k} 가 설정에 도달하지 않았다"

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    log.info("급등·급락 되돌림 — %d종목 · 창 %s분 · 문턱 %s%% · 선도 %s분",
             len(syms), WINS, THRS, HORIZONS)

    t0 = time.time()
    B: dict[str, pd.DataFrame] = {}
    for s in syms:
        b = bars(s, cfg)
        if b is not None:
            B[s] = b
    log.info("봉 %d종목 · %.1f분", len(B), (time.time() - t0) / 60)
    if len(B) < 20:
        raise SystemExit(f"종목이 {len(B)}개뿐이다 — 틱 구간을 확인하라")

    # 시장 지수 — 전 종목 정규화 종가의 중앙값(%)
    idx = pd.concat({s: np.log(b.cl.clip(lower=1e-12)) for s, b in B.items()},
                    axis=1)
    MKT = (idx.subtract(idx.iloc[0]).median(axis=1)) * 100.0

    rng = np.random.default_rng(cfg.seed)
    rows = []
    for i, (s, b) in enumerate(B.items(), 1):
        rows += one(s, b, MKT, cfg, rng)
        if i % 50 == 0 or i == len(B):
            el = time.time() - t0
            log.info("[%d/%d] 사건 %s · %.1f분 · 남은 %.1f분", i, len(B),
                     f"{len(rows):,}", el / 60, (len(B) - i) * el / i / 60)
    R = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_shock_rebound.csv"
    R.to_csv(path, index=False)
    log.info("저장 %s — %s행 · %.1f분", path, f"{len(R):,}", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
