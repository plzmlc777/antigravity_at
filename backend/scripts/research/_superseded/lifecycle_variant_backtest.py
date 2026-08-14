"""신상저격수 — **신호 변형 5종 백테스트** (같은 코호트·같은 마찰).

배경 (2026-08-12)
  페이퍼에 도는 lifecycle 세션은 15개 상장 사건 × **5가지 신호 변형** = 72세션이다.
  그런데 내가 돌린 백테스트는 `base` 하나뿐이었고, 나머지 넷은 페이퍼 기록만
  있는데 그건 재진입 버그로 오염돼 있다. 여기서 다섯을 같은 잣대로 잰다.

변형 정의 (소스 구현에서 그대로 가져옴)
  base          Day-1 종가 숏 → Day-30 종가, SL +50%
  h21           Day-1 종가 숏 → **Day-21** 종가, SL +50%
  earlyexit_d7  Day-1 숏. Day-7 에 vol_cliff = mean(vol[1:7]) / vol[0] 계산.
                vc >= 0.40 이면 **Day-7 종가에 조기청산**, 아니면 Day-30 까지.
  earlyexit_d14 같은 방식, Day-14 에 vol_cliff = mean(vol[7:14]) / vol[0].
                (R-2 정렬 정의 — 위치 7..13 = Day 8..14)
  bearskip      상장 직전 BTC 30일 수익률 <= -5% 면 **진입 자체를 건너뜀**.

  vol_cliff 임계 0.40 은 스포너 기본값(`--early-exit-vc-threshold 0.40`).
  bear 임계 -0.05 는 `--bear-skip-threshold`.

무엇을 조심하는가
  · 다섯 변형에 **완전히 같은 코호트**를 쓴다. 진입 시점도 같다.
  · bearskip 은 건너뛴 사건을 **0% 수익**이 아니라 **거래 없음**으로 센다.
    (현금 보유는 수익이 아니다. 별도로 '건너뛴 건수'를 낸다.)
  · 마찰 테이커 왕복 10bp.
  · 짝지은 비교 — 같은 상장 사건에서 base 대비 차이의 t 를 낸다.

사용:
  python3 scripts/research/lifecycle_variant_backtest.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lc_variant")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
SL_PCT = 0.50
FRIC_BP = 10.0
VC_THR = 0.40
BEAR_THR = -0.05
SPLIT = date(2026, 5, 13)


def daily(conn, sym: str, a: date, b: date) -> pd.DataFrame:
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT timestamp, high, close, volume FROM ohlcv WHERE symbol=:s "
        "AND time_frame='1m' AND timestamp >= :a AND timestamp < :b ORDER BY timestamp"),
        {"s": sym, "a": a, "b": b}).fetchall()
    if not r:
        return pd.DataFrame()
    df = pd.DataFrame(r, columns=["ts", "high", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    d = df.set_index("ts").astype(float)
    return pd.DataFrame({"high": d["high"].resample("1D").max(),
                         "close": d["close"].resample("1D").last(),
                         "volume": d["volume"].resample("1D").sum()}).dropna()


def trade(dl: pd.DataFrame, hold: int, early_day: int | None):
    """Day-1 종가 숏. SL / 조기청산 / 시간청산 중 먼저 닿는 것."""
    if len(dl) < 3:
        return None
    e = float(dl["close"].iloc[0])
    if e <= 0:
        return None
    stop = e * (1 + SL_PCT)
    exit_pos = min(hold, len(dl) - 1)
    if early_day is not None and len(dl) >= early_day:
        v = dl["volume"].values
        v0 = float(v[0])
        win = v[7:14] if early_day == 14 else v[1:7]
        if v0 > 0 and len(win) >= 1 and float(win.mean()) / v0 >= VC_THR:
            exit_pos = min(early_day - 1, exit_pos)   # Day-N 종가
    for k in range(1, exit_pos + 1):
        if float(dl["high"].iloc[k]) >= stop:
            return (-SL_PCT * 100 - FRIC_BP / 100, k, "sl")
    # 숏 수익률 = (진입-청산)/진입 (커널 규약). 규약 통일 2026-08-14
    x = float(dl["close"].iloc[exit_pos])
    ret = (e - x) / e * 100 - FRIC_BP / 100
    reason = "early" if (early_day is not None and exit_pos == early_day - 1
                         and exit_pos < hold) else "time"
    return (ret, exit_pos, reason)


def btc_pre_ret(conn, ld: date) -> float | None:
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT timestamp, close FROM ohlcv WHERE symbol='BTCUSDT' AND time_frame='1m' "
        "AND timestamp >= :a AND timestamp < :b ORDER BY timestamp"),
        {"a": ld - timedelta(days=32), "b": ld}).fetchall()
    if not r:
        return None
    s = pd.Series({pd.Timestamp(t): float(c) for t, c in r}).sort_index()
    d = s.resample("1D").last().dropna()
    if len(d) < 20:
        return None
    return float(d.iloc[-1] / d.iloc[0] - 1.0)


def st(a: np.ndarray) -> dict:
    if len(a) < 2:
        return {"n": len(a)}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"n": len(a), "mean": float(a.mean()), "med": float(np.median(a)),
            "win": float(100 * (a > 0).mean()), "t": float(a.mean() / se)}


def main() -> int:
    p = argparse.ArgumentParser(description="신호 변형 5종 백테스트")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "lifecycle_variant_backtest.json"))
    args = p.parse_args()

    listings = json.load(open(LISTINGS))
    from app.db.session import engine
    VAR = [("base", 30, None), ("h21", 21, None),
           ("earlyexit_d7", 30, 7), ("earlyexit_d14", 30, 14)]
    rows, btc_cache = [], {}
    with engine.connect() as conn:
        for i, (sym, meta) in enumerate(sorted(listings.items()), 1):
            od = meta.get("onboard_date")
            if not od:
                continue
            ld = datetime.strptime(od, "%Y-%m-%d").date()
            dl = daily(conn, sym, ld, ld + timedelta(days=35))
            if len(dl) < 31:
                continue
            rec = {"symbol": sym, "listing": str(ld), "oos": ld > SPLIT}
            ok = True
            for name, hold, ed in VAR:
                t = trade(dl, hold, ed)
                if t is None:
                    ok = False
                    break
                rec[name] = t[0]
                rec[name + "_reason"] = t[2]
            if not ok:
                continue
            key = ld.strftime("%Y-%m")
            if key not in btc_cache:
                btc_cache[key] = btc_pre_ret(conn, ld)
            pre = btc_cache[key]
            rec["btc_pre"] = pre
            rec["bearskip"] = None if (pre is not None and pre <= BEAR_THR) else rec["base"]
            rows.append(rec)
            if i % 100 == 0:
                log.info("%d/%d (사용 %d)", i, len(listings), len(rows))

    D = pd.DataFrame(rows)
    if len(D) < 30:
        log.error("코호트 부족 %d", len(D))
        return 1
    names = ["base", "h21", "earlyexit_d7", "earlyexit_d14", "bearskip"]

    print("\n" + "=" * 104)
    print(f"신상저격수 신호 변형 5종 — 같은 코호트 {len(D)}건 / "
          f"{D.listing.min()} ~ {D.listing.max()}")
    print("=" * 104)
    print(f"  {'변형':<15}{'거래':>6}{'평균%':>10}{'중앙%':>10}{'승률%':>8}{'t':>8}"
          f"{'SL%':>7}{'조기%':>7}{'건너뜀':>7}")
    print("-" * 104)
    res = {}
    for n in names:
        v = D[n].dropna().values
        s = st(v)
        res[n] = s
        skipped = int(D[n].isna().sum())
        rs = D.get(n + "_reason")
        slp = 100 * (rs == "sl").mean() if rs is not None else (
            100 * (D["base_reason"] == "sl").mean() if n == "bearskip" else 0)
        erp = 100 * (rs == "early").mean() if rs is not None else 0
        print(f"  {n:<15}{s['n']:>6}{s['mean']:>+10.2f}{s['med']:>+10.2f}"
              f"{s['win']:>8.1f}{s['t']:>+8.2f}{slp:>7.1f}{erp:>7.1f}{skipped:>7}")
    print("-" * 104)
    print("  ** base 대비 짝지은 차이 (같은 상장 사건 안에서) **")
    b = D["base"]
    for n in names[1:]:
        d = (D[n] - b).dropna()
        if len(d) < 5:
            continue
        se = d.std(ddof=1) / np.sqrt(len(d))
        print(f"     {n:<15} {d.mean():>+8.2f}%p  (오차 {se:>5.2f}, t {d.mean()/se:>+6.2f}, "
              f"n={len(d)}, 개선 {100*(d>0).mean():>4.0f}%)")
    print("-" * 104)
    print("  ** 표본 밖 (R-4 2026-05-13 이후) **")
    O = D[D.oos]
    print(f"  {'변형':<15}{'거래':>6}{'평균%':>10}{'중앙%':>10}{'승률%':>8}{'t':>8}")
    for n in names:
        v = O[n].dropna().values
        s = st(v)
        if s.get("n", 0) < 2:
            continue
        print(f"  {n:<15}{s['n']:>6}{s.get('mean',0):>+10.2f}{s.get('med',0):>+10.2f}"
              f"{s.get('win',0):>8.1f}{s.get('t',0):>+8.2f}")
    print("=" * 104 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"n": len(D), "variants": res, "rows": rows}, open(args.out, "w"),
              ensure_ascii=False, indent=2, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
