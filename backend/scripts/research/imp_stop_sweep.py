"""충격숏3(imp3s) 손절 문턱 격자 — **로컬 틱만** 쓴다 (2026-09-09).

## 왜

코드 주석은 "14개월 8구성 실측에서 5% 가 최적"이라고 적혀 있지만 그 검정은
패널(봉) 기질이었다. 여기서는 **실제로 난 거래 92건의 틱 경로**를 다시 걸어
문턱을 바꿔 본다.

## 기질

`runs/ticks/<종목>/<UTC날짜>.parquet` (ts_ms, price). REST 를 쓰지 않는다 —
2026-09-09 에 klines 를 몰아 던져 IP 가 차단됐고 실거래 드라이버까지 멈췄다.
로컬에 있는 것을 두고 밖에서 받지 마라.

## 한계 (정직하게)

한 거래를 일찍 끊으면 그 자리가 비어 **다른 거래가 들어온다.** 이 격자는
그걸 모형화하지 않는다 — "이 진입들을 그대로 두고 문턱만 바꾸면" 이다.
따라서 낮은 문턱의 성적은 **실제보다 나쁘게** 잡힌다(회전 이득 누락).

사용:
    python3 -m scripts.research.imp_stop_sweep --smoke
    python3 -m scripts.research.imp_stop_sweep
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("stopsweep")
KST = "Asia/Seoul"


@dataclass
class Cfg:
    ledger: str = "runs/kinematics_paper/s3short_imp/trades.csv"
    ticks: str = "runs/ticks"
    fee_rt: float = 0.072                    # 왕복(%)
    slots: int = 3
    stops: tuple = (0.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0)
    only_after_stop_intro: bool = False       # True 면 손절 도입 後만


def load_path(sym: str, a: pd.Timestamp, b: pd.Timestamp, ticks: Path):
    """진입~청산 구간의 (시각, 가격) 경로. 없으면 None."""
    days = pd.date_range(a.tz_convert("UTC").normalize() - pd.Timedelta(days=1),
                         b.tz_convert("UTC").normalize(), freq="D")
    out = []
    for d in days:
        f = ticks / sym / f"{d:%Y-%m-%d}.parquet"
        if not f.exists():
            continue
        try:
            x = pd.read_parquet(f, columns=["ts_ms", "price"])
        except Exception:
            continue
        out.append(x)
    if not out:
        return None
    x = pd.concat(out, ignore_index=True)
    t = pd.to_datetime(x.ts_ms, unit="ms", utc=True)
    m = (t >= a) & (t <= b)
    if m.sum() < 50:
        return None
    return x.loc[m, "price"].to_numpy(float)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="예비비행 — 5건")
    ap.add_argument("--after-stop", action="store_true",
                    help="손절 도입(2026-09-03 06:10) 이후 거래만")
    a = ap.parse_args()
    c = Cfg(only_after_stop_intro=a.after_stop)
    log.info("설정 — 문턱 %s · 통행료 %.3f%% · 슬롯 %d · 도입後만 %s",
             c.stops, c.fee_rt, c.slots, c.only_after_stop_intro)

    d = pd.read_csv(ROOT / c.ledger)
    d["e"] = pd.to_datetime(d.entry_ts, utc=True, errors="coerce")
    d["x"] = pd.to_datetime(d.exit_ts, utc=True, errors="coerce")
    if c.only_after_stop_intro:
        d = d[d.stopped.notna()]
    if a.smoke:
        d = d.head(5)
    log.info("거래 %d건", len(d))

    ticks = ROOT / c.ticks
    recs, miss = [], 0
    for i, (_, r) in enumerate(d.iterrows(), 1):
        p = load_path(r.symbol, r.e, r.x, ticks)
        if p is None:
            miss += 1
            continue
        E = float(r.entry_px)
        short = bool(r["short"])
        # 숏이면 위로, 롱이면 아래로가 역행
        adverse = (p.max() / E - 1) if short else (1 - p.min() / E)
        last = float(p[-1])
        base = (100 * (E - last) / E) if short else (100 * (last - E) / E)
        recs.append({"sym": r.symbol, "e": r.e, "short": short,
                     "역행%": 100 * adverse, "무손절net%": base - c.fee_rt,
                     "원장net%": r.net_pct, "path": p, "E": E})
        if i % 20 == 0:
            log.info("  %d/%d · 경로 없음 %d", i, len(d), miss)
    log.info("경로 확보 %d건 · 없음 %d건", len(recs), miss)
    if not recs:
        raise SystemExit("틱 경로를 하나도 못 읽었다")

    print(f"\n■ 손절 문턱 격자 — 거래 {len(recs)}건 (틱 경로 재현)")
    print(f"{'문턱%':>6} {'발동률':>7} {'합%':>9} {'자본%':>8} {'평균%':>8} "
          f"{'중앙%':>8} {'승률':>6} {'최악%':>8} {'상5제외%':>9}")
    rows = []
    for s in c.stops:
        nets = []
        hit = 0
        for r in recs:
            if s > 0 and r["역행%"] >= s:
                nets.append(-s - c.fee_rt)
                hit += 1
            else:
                nets.append(r["무손절net%"])
        n = np.asarray(nets)
        q = np.quantile(n, 0.95)
        ex = n[n < q]
        rows.append((s, 100 * hit / len(n), n.sum(), n.sum() / c.slots,
                     n.mean(), float(np.median(n)), 100 * (n > 0).mean(),
                     n.min(), ex.mean()))
        print(f"{s:>6.1f} {rows[-1][1]:>6.1f}% {n.sum():>+9.2f} "
              f"{n.sum()/c.slots:>+8.2f} {n.mean():>+8.3f} {np.median(n):>+8.3f} "
              f"{100*(n>0).mean():>5.1f}% {n.min():>+8.2f} {ex.mean():>+9.3f}")
    best = max(rows, key=lambda z: z[2])
    print(f"\n  총손익 최대 문턱 = **{best[0]:.1f}%** (합 {best[2]:+.2f}%)")
    print("  ⚠ 일찍 끊으면 자리가 비어 다른 거래가 들어온다 — 이 격자는 그 이득을"
          " 세지 않으므로 **낮은 문턱이 실제보다 불리하게** 잡힌다.")


if __name__ == "__main__":
    main()
