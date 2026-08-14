"""신상저격수 — **표본 밖(OOS) 재검정**.

배경 (2026-08-12)
  대표님이 실거래 재개 가능 여부를 물으셨다. 실계좌 3개월 원장(20거래, +$202.25)은
  거래당 **t +1.02** 로 0 과 구분되지 않고, **상위 2건이 총손익의 96.4%**,
  3건을 빼면 -$72.45 로 적자다. 그리고 오늘 페이퍼에서 **재진입 버그**를 찾았다
  (소스가 -1.0 을 영원히 내보내 익절 뒤 즉시 재진입 → REUSDT 실계좌 8회 진입).
  즉 실적은 의도한 패러다임의 것이 아니다.

  그런데 **백테스트는 원래 옳았다.** `listing_volume_cliff_poc.py` 등 기존
  R-1/R-2 는 순수 Day-1 종가 숏 → Day-30 종가(또는 SL) 로 한 번만 거래한다.
  구현이 백테스트에서 벗어난 것이다.

  따라서 같은 백테스트를 다시 돌리는 것은 의미가 없다 — 원래 값(중앙 +21.6%)이
  재현될 뿐이다. **물어야 할 것은 다르다:**

      R-4 판정(2026-05-13) **이후에 상장된 종목**에서도 성립하는가.

  R-4 코호트는 그 시점까지의 상장분이다. 이후 3개월은 전부 표본 밖이다.
  알파 감쇠를 재는 유일한 정직한 방법이다.

설계
  · 거래는 **상장 Day-1 종가 숏 → Day-30 종가 청산, SL +50%**. 재진입 없음.
  · 코호트를 **R-4 이전 / 이후**로 갈라 같은 규칙으로 돌린다.
  · 이후 코호트는 표본이 작으므로(월 4~6건) **판정이 아니라 방향 확인**이다.
  · 마찰: 테이커 왕복 10bp + 실측 스프레드는 이 규모(30일 보유)에선 무시 가능하나
    명시적으로 뺀다.
  · 집중도(상위 k건 제외)를 같이 낸다 — 실계좌에서 이게 결정적이었다.

사용:
  python3 scripts/research/lifecycle_oos_recheck.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lifecycle_oos")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
R4_DATE = date(2026, 5, 13)          # R-4 PASS 판정일 — 이 이후 상장이 표본 밖
HOLD_DAYS = 30
SL_PCT = 0.50                        # 숏 손절 +50%
FRIC_BP = 10.0                       # 테이커 왕복


def daily_bars(conn, sym: str, start: date, end: date) -> pd.DataFrame:
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' AND timestamp >= :a AND timestamp < :b "
        "ORDER BY timestamp"), {"s": sym, "a": start, "b": end})
    rows = r.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.set_index("ts").astype(float)
    return pd.DataFrame({"open": df["open"].resample("1D").first(),
                         "high": df["high"].resample("1D").max(),
                         "low": df["low"].resample("1D").min(),
                         "close": df["close"].resample("1D").last(),
                         "volume": df["volume"].resample("1D").sum()}).dropna()


def one_trade(daily: pd.DataFrame) -> tuple:
    """Day-1 종가 숏 → Day-30 종가, 중간에 +50% 닿으면 손절. 재진입 없음."""
    if len(daily) < 3:
        return None
    entry = float(daily["close"].iloc[0])
    if entry <= 0:
        return None
    stop = entry * (1 + SL_PCT)
    end = min(HOLD_DAYS, len(daily) - 1)
    for k in range(1, end + 1):
        if float(daily["high"].iloc[k]) >= stop:
            return (-SL_PCT * 100 - FRIC_BP / 100, k, "sl")
    exit_px = float(daily["close"].iloc[end])
    # 숏 수익률 = (진입-청산)/진입 — 커널 close() 규약. 예전엔 entry/exit-1 이라
    # 상한이 없어 이익 거래가 부풀려졌다(251 코호트 평균 43.41%→5.15%). 2026-08-14
    ret = (entry - exit_px) / entry * 100 - FRIC_BP / 100     # 숏
    return (ret, end, "time")


def stats(a: np.ndarray) -> dict:
    if not len(a):
        return {}
    se = a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else np.nan
    return {"n": len(a), "mean": float(a.mean()), "median": float(np.median(a)),
            "win": float(100 * (a > 0).mean()), "se": float(se),
            "t": float(a.mean() / se) if se and se > 0 else np.nan,
            "best": float(a.max()), "worst": float(a.min())}


def main() -> int:
    p = argparse.ArgumentParser(description="신상저격수 OOS 재검정")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "lifecycle_oos_recheck.json"))
    args = p.parse_args()

    if not LISTINGS.exists():
        log.error("상장일 파일 없음: %s", LISTINGS)
        return 1
    listings = json.load(open(LISTINGS))
    log.info("상장 기록 %d종목", len(listings))

    from app.db.session import engine
    recs = []
    with engine.connect() as conn:
        for i, (sym, meta) in enumerate(sorted(listings.items()), 1):
            od = meta.get("onboard_date")
            if not od:
                continue
            ld = datetime.strptime(od, "%Y-%m-%d").date()
            d = daily_bars(conn, sym, ld, ld + pd.Timedelta(days=HOLD_DAYS + 5))
            if len(d) < HOLD_DAYS + 1:
                continue
            t = one_trade(d)
            if t is None:
                continue
            recs.append({"symbol": sym, "listing": str(ld), "ret": t[0],
                         "held": t[1], "reason": t[2],
                         "oos": ld > R4_DATE})
            if i % 100 == 0:
                log.info("%d/%d (사용 %d)", i, len(listings), len(recs))

    if len(recs) < 30:
        log.error("코호트 부족: %d", len(recs))
        return 1
    D = pd.DataFrame(recs)
    ins = D[~D.oos].ret.values
    oos = D[D.oos].ret.values

    print("\n" + "=" * 96)
    print(f"신상저격수 OOS 재검정 — 순수 Day-1 숏 → Day-30 (재진입 없음, SL +50%)")
    print("=" * 96)
    print(f"  코호트 {len(D)}건  /  R-4 판정일 {R4_DATE} 기준 분할")
    print(f"  기간 {D.listing.min()} ~ {D.listing.max()}")
    print("-" * 96)
    print(f"{'구간':<22}{'건수':>6}{'평균%':>10}{'중앙%':>10}{'승률%':>8}{'오차':>8}{'t':>8}"
          f"{'최고%':>9}{'최악%':>9}")
    print("-" * 96)
    for lab, a in (("표본 안 (R-4 이전)", ins), ("**표본 밖 (이후)**", oos),
                   ("전체", D.ret.values)):
        s = stats(a)
        if not s:
            continue
        print(f"{lab:<22}{s['n']:>6}{s['mean']:>+10.2f}{s['median']:>+10.2f}{s['win']:>8.1f}"
              f"{s['se']:>8.2f}{s['t']:>+8.2f}{s['best']:>+9.1f}{s['worst']:>+9.1f}")
    print("-" * 96)
    print("  ** 집중도 — 상위 k건 제외 **")
    for lab, a in (("표본 안", ins), ("표본 밖", oos)):
        if len(a) < 5:
            continue
        s = np.sort(a)[::-1]
        line = "   ".join(f"상위{k} 제외 평균 {s[k:].mean():+6.2f}%" for k in (1, 3, 5))
        print(f"    {lab:<8} 전체 평균 {a.mean():+6.2f}%   {line}")
    print("-" * 96)
    print("  ** 청산 사유 **")
    for lab, sub in (("표본 안", D[~D.oos]), ("표본 밖", D[D.oos])):
        if not len(sub):
            continue
        vc = sub.reason.value_counts().to_dict()
        print(f"    {lab:<8} {vc}   (SL 비율 {100*vc.get('sl',0)/len(sub):.1f}%)")
    if len(oos) >= 5:
        print("-" * 96)
        print("  ** 표본 밖 개별 거래 **")
        for _, x in D[D.oos].sort_values("listing").iterrows():
            print(f"    {x.listing}  {x.symbol:<14}{x.ret:>+8.2f}%  {x.reason:<6}보유 {x.held}일")
    print("=" * 96 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"r4_date": str(R4_DATE), "n": len(D),
                   "in_sample": stats(ins), "out_of_sample": stats(oos),
                   "trades": recs}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
