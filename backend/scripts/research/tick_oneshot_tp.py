"""손절 없이 **한 번만** 진입하면 어떻게 되나 — 도달률과 그 대가.

## 착상 (대표님, 2026-08-27)

GPSUSDT 는 22시간 동안 진폭 1.77% 스윙을 44회 왕복했다. 그렇다면 **방향이
틀려도 기다리면 돌아온다**. 매번 거래하는 게 아니라 딱 한 번만 걸어두면
익절에 닿을 것이다.

구조적으로 맞는 지적이다. 횡보장에서 손절이 없으면 익절은 결국 온다.
그래서 재야 할 것은 도달률이 아니라 **안 닿는 소수의 깊이**다.

## 그래서 무엇을 재나

    도달률      정해진 보유 안에 익절에 닿은 비율 (손절 없음)
    도달시간    닿기까지 걸린 분
    최대 불리폭 닿기 전까지 견뎌야 했던 미실현 손실 (MAE)
    미도달 손익 못 닿고 만기 청산했을 때의 손익

⚠ 방향을 **양쪽 다** 돌린다. 한쪽만 재면 그날의 표류를 규칙 효과로 읽는다
  (교훈#91). 롱·숏 합이 0 이 아니면 그건 국면이지 규칙이 아니다.

⚠ 창이 잘리면 늦은 앵커가 불리해진다. 그래서 **보유 시간이 온전히 남은
  앵커만** 쓴다. 잘라 쓰면 도달률이 조용히 부풀려진다.

⚠ 표본은 **하루**다. 이 하루가 횡보였다면 답도 횡보의 답이다. GPSUSDT 는
  첫 1시간에 −16% 를 냈다 — 그 구간에 손절 없이 롱이면 −16% 를 안고 있었다.

사용:
  python3 -m scripts.research.tick_oneshot_tp --smoke 10
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
OUT = ROOT / "runs" / "research_track" / "tick_sr"
log = logging.getLogger("oneshot")

TPS = (0.5, 1.0, 1.5, 2.0, 2.4, 3.0, 5.0)      # %
HOLDS = (60, 180, 360, 720)                     # 분


@dataclass(frozen=True)
class Cfg:
    hours: int = 24
    step_min: int = 5        # 앵커 간격
    min_ticks: int = 2_000


def one(sym: str, cfg: Cfg, cut_ms: int) -> list[dict]:
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))[-2:] if d.is_dir() else []
    if not fs:
        return []
    t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                   for f in fs], ignore_index=True)
    t = t[(t.ts_ms >= cut_ms) & (t.price > 0) & (t.qty > 0)]
    if len(t) < cfg.min_ticks:
        return []
    t = t.sort_values("ts_ms")
    g = t.groupby(t.ts_ms // 60_000)
    hi = g.price.max().to_numpy(float)
    lo = g.price.min().to_numpy(float)
    cl = g.price.last().to_numpy(float)
    n = len(cl)
    if n < max(HOLDS) + 10:
        return []

    rows = []
    for hold in HOLDS:
        # ⚠ 보유가 온전히 남은 앵커만 — 잘라 쓰면 도달률이 부풀려진다
        anchors = range(0, n - hold, cfg.step_min)
        for i in anchors:
            e = cl[i]
            if e <= 0:
                continue
            j = i + hold
            up = 100.0 * (hi[i + 1:j + 1] - e) / e     # 롱의 유리 / 숏의 불리
            dn = 100.0 * (e - lo[i + 1:j + 1]) / e     # 롱의 불리 / 숏의 유리
            cup, cdn = np.maximum.accumulate(up), np.maximum.accumulate(dn)
            end_ret = 100.0 * (cl[j] - e) / e
            for long in (True, False):
                fav, adv = (cup, cdn) if long else (cdn, cup)
                r = {"symbol": sym, "hold": hold, "i": i,
                     "dir": "롱" if long else "숏",
                     "end_ret": end_ret if long else -end_ret,
                     "mae_full": float(adv[-1])}
                for x in TPS:
                    k = int(np.argmax(fav >= x)) if (fav >= x).any() else -1
                    r[f"hit_{x}"] = k >= 0
                    r[f"t_{x}"] = float(k + 1) if k >= 0 else np.nan
                    # 닿기 전까지 견뎌야 했던 손실. 못 닿으면 만기까지
                    r[f"mae_{x}"] = float(adv[k] if k >= 0 else adv[-1])
                rows.append(r)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--step-min", type=int, default=None)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"step_min": a.step_min} if a.step_min else {}))
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    cut_ms = int((time.time() - cfg.hours * 3600) * 1000)
    log.info("한 방 익절 — %d종목 · 익절 %s · 보유 %s분", len(syms), TPS, HOLDS)

    t0, parts = time.time(), []
    for i, s in enumerate(syms, 1):
        try:
            r = one(s, cfg, cut_ms)
        except Exception as e:                                  # noqa: BLE001
            log.warning("%s 실패: %s", s, str(e)[:100]); r = []
        if r:
            parts.append(pd.DataFrame(r))
        if i % 50 == 0 or i == len(syms):
            el = time.time() - t0
            log.info("[%d/%d] %s건 · %.1f분 · 남은 %.1f분", i, len(syms),
                     f"{sum(len(x) for x in parts):,}", el / 60,
                     (len(syms) - i) * el / i / 60)
    R = pd.concat(parts, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_oneshot_tp.csv"
    R.to_csv(path, index=False)
    log.info("저장 %s — %s행 · %.1f분", path, f"{len(R):,}", (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
