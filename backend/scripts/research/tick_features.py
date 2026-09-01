"""틱 → 5분 특징봉. 한 번 만들고 계속 읽는다.

## 왜 (2026-08-31)

운동학 z_vel 밴드를 닫으면서(총엣지 +0.040~0.084% 대 통행료 0.072%) 값어치가
**밴드가 아니라 틱 미시구조**에 있다는 쪽으로 옮겼다. 실측 근거:

    잡음6 첫 사이클  롱 다리 초과 +0.071%p (유니버스 중앙과 같음 = 0)
                     숏 다리 초과 +5.226%p (358종목 중 최하위 2개)

틱을 매번 다시 읽으면 격자 한 번에 수십 분이 든다. 특징을 미리 접어 둔다.

## 담는 것 (5분 봉 · 종목별)

    cl    마지막 체결가
    ntr   체결 수
    qsum  체결 수량 합
    flip  가격 방향이 **뒤집힌** 횟수 (0 은 직전 방향 유지로 처리)
    dtm   체결 간격 평균(ms)      dts  체결 간격 표준편차(ms)
    tkb   테이커 매수 비율 = 1 - mean(is_buyer_maker)
    tkq   테이커 매수 수량 비율

⚠ 가짜 체결 — 바이낸스 @trade 가 price 0 · qty 0 을 섞어 보낸다(0.110%,
  유동성 클수록 많음). 최저가·로그수익률을 조용히 파괴한다. **여기서 거른다**.
⚠ flip 은 부호가 0 인 체결(같은 가격)을 직전 부호로 채운 뒤 센다. 안 그러면
  같은 가격 연속 체결이 전부 '뒤집힘 아님'으로 세어져 유동성 대리변수가 된다.

사용:
  python3 -m scripts.research.tick_features            # 없는 것만
  python3 -m scripts.research.tick_features --refresh
"""
from __future__ import annotations

import argparse
import logging
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "tickbars5m"
BAR_MS = 5 * 60 * 1000
log = logging.getLogger("tickfeat")


def one(sym: str) -> tuple[str, int]:
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))
    if not fs:
        return sym, 0
    try:
        t = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    except Exception:                                           # noqa: BLE001
        return sym, 0
    # ⚠ 가짜 체결 제거 — price 0 · qty 0 (2026-08-27 규명)
    t = t[(t.price > 0) & (t.qty > 0)].sort_values("ts_ms")
    if len(t) < 2_000:
        return sym, 0
    pr = t.price.to_numpy(float)
    sg = np.sign(np.diff(pr, prepend=pr[0]))
    prv = pd.Series(np.where(sg == 0, np.nan, sg)).ffill().to_numpy()
    prev_ = np.roll(prv, 1)
    t["_fl"] = ((sg != 0) & (prev_ != 0) & (sg != prev_)).astype(np.int32)
    t["_dt"] = np.diff(t.ts_ms.to_numpy(), prepend=int(t.ts_ms.iloc[0])).astype(float)
    t["_tb"] = (~t.is_buyer_maker).astype(np.float32)     # 테이커 매수 = 1
    t["_nv"] = t.price*t.qty          # 체결별 거래대금
    t["_bin"] = (t.ts_ms // BAR_MS) * BAR_MS
    g = t.groupby("_bin")
    b = pd.DataFrame({
        # ⚠ OHLC 를 넣는다 — RSI·볼린저·ADX·스토캐스틱이 고가·저가를 쓴다.
        #   2026-09-01 까지 종가만 있어 지표를 못 만들었다.
        "op": g.price.first(), "hi": g.price.max(), "lo": g.price.min(),
        "cl": g.price.last(), "ntr": g.price.size(),
        "qsum": g.qty.sum(), "flip": g._fl.sum(),
        "dtm": g._dt.mean(), "dts": g._dt.std(),
        "tkb": g._tb.mean(),
        "tkq": g.apply(lambda x: float((x.qty*x._tb).sum()/max(x.qty.sum(), 1e-9)),
                       include_groups=False),
        # ⚠ qty 의 **분포** — 합계(qsum)만으로는 고래 한 건과 잔거래 천 건이
        #   구분이 안 된다. H1(고래 각인)에 필요하다(2026-09-01).
        "qmax": g._nv.max(),          # 단일 체결 최대 거래대금
        "q90": g._nv.quantile(0.9),
        "qmed": g._nv.median(),
        "qmax_buy": g.apply(                       # 최대 체결이 테이커 매수였나
            lambda x: float(x._tb.iloc[int(np.argmax(x._nv.to_numpy()))])
            if len(x) else np.nan, include_groups=False),
    }).reset_index().rename(columns={"_bin": "ts_ms"})
    OUT.mkdir(parents=True, exist_ok=True)
    b.to_parquet(OUT / f"{sym}.parquet", index=False)
    return sym, len(b)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--smoke", type=int, default=0)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    syms = [d.name for d in sorted(TICKS.iterdir()) if d.is_dir()]
    if not a.refresh:
        syms = [s for s in syms if not (OUT / f"{s}.parquet").exists()]
    if a.smoke:
        syms = syms[:a.smoke]
    if not syms:
        log.info("만들 것이 없다 — %d개 이미 있음", len(list(OUT.glob("*.parquet"))))
        return 0
    log.info("특징봉 — %d종목 · 워커 %d", len(syms), a.workers)
    t0, done, empty = time.time(), 0, 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (s, n) in enumerate(ex.map(one, syms), 1):
            done += n
            empty += (n == 0)
            if i % 40 == 0 or i == len(syms):
                el = time.time()-t0
                log.info("[%d/%d] 봉 %s · 빈 %d · %.1f분 · 남은 %.1f분",
                         i, len(syms), f"{done:,}", empty, el/60,
                         (len(syms)-i)*el/i/60)
    log.info("완료 — %d종목 · 봉 %s · 빈 %d · %.1f분",
             len(syms), f"{done:,}", empty, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
