"""1h 신상저격수 타당성 연구 — **만들기 전에 무엇이 달라지는지 먼저 잰다**.

왜 이 측정이 먼저인가
    일봉 최적화 격자에서 손절을 조일수록 수익이 **단조로 올라갔다**
    (손절 50% → 2%: IS 2.63% → 7.64%, t 0.96 → 7.28). 그런데 그 구간을
    믿을 수 없어 `SL_FLOOR = 0.20` 으로 막아 뒀다. 이유:

        일봉에서는 손절이 **바 안에서** 언제 닿았는지 알 수 없다.
        백테스트는 손절가에 정확히 체결됐다고 기록하지만, 그 바가 시가부터
        이미 손절선을 넘겨 열렸다면 그 가격에 못 나온다.
        실측: 진입 바 일중 상승폭 p50 **10.5%** · p75 **25.4%**

    **1h 로 내리면 그 구간이 측정 가능해지는가?** 이게 1h 판본의 유일한
    본질적 이유다. "해상도가 높으니 좋다"가 아니라 **"막혀 있던 축이 열리는가"**
    를 먼저 확인해야 한다. 안 열리면 만들 이유가 없다.

무엇을 재나
    손절 수준마다, 손절이 발동한 바의 **시가가 이미 손절선을 넘었는가**.
    넘었으면 백테스트가 기록한 체결가는 허구이고 실제 손실은 더 크다.
        일봉 해상도 vs 1h 해상도에서 그 비율과 초과폭(슬리피지)을 비교한다.

⚠ 이 스크립트는 전략을 만들지 않는다. **만들 가치가 있는지만 잰다.**

사용:
  python3 -m scripts.research.lifecycle_resolution_study --since 2025-08-01
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("res_study")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "lifecycle_resolution_study.json"

SL_GRID = [0.02, 0.05, 0.10, 0.20, 0.30, 0.50]
HOLD_DAYS = 30


def load_1m(conn, sym: str, start, end) -> pd.DataFrame:
    from sqlalchemy import text
    rows = conn.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol = :s AND time_frame = '1m' "
        "AND timestamp >= :a AND timestamp < :b ORDER BY timestamp"),
        {"s": sym, "a": start, "b": end}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.set_index("ts").sort_index()


def resample(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    return pd.DataFrame({
        "open": m1["open"].resample(rule).first(),
        "high": m1["high"].resample(rule).max(),
        "low": m1["low"].resample(rule).min(),
        "close": m1["close"].resample(rule).last(),
    }).dropna()


def entry_bar_skip(bars: pd.DataFrame, entry_idx: int, entry_px: float,
                   sl: float) -> bool:
    """**진입 바 안에서** 이미 손절선을 넘었는가.

    ⚠ 이것이 일봉 판정의 진짜 결함이다. 커널은 미래참조를 피하려고 진입 바에서
      손절·익절을 보지 않는다(그 자체는 옳다). 그런데 그 바의 상승폭이 손절보다
      크면 **그 손절은 존재하지 않은 것과 같다** — 백테스트는 그 손실을 기록하지
      않고 다음 바로 넘어간다.

    ⚠ 앞선 판본에서 나는 '청산 바 시가가 손절선을 넘었나'(갭)를 쟀는데,
      크립토는 24시간 거래라 갭이 없어서 전부 0.0% 가 나왔다. 의미 없는 양이었다.
    """
    if entry_idx >= len(bars):
        return False
    return float(bars.iloc[entry_idx]["high"]) >= entry_px * (1 + sl)


def main() -> int:
    p = argparse.ArgumentParser(description="1h 판본 타당성 연구")
    p.add_argument("--since", default="2025-08-01")
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine

    listings = json.loads(LISTINGS.read_text())
    cohort = sorted(((s, m["onboard_date"]) for s, m in listings.items()
                     if isinstance(m, dict) and m.get("onboard_date")
                     and m["onboard_date"] >= a.since), key=lambda x: x[1])
    log.info("코호트 후보 %d종목", len(cohort))

    recs = []
    with engine.connect() as conn:
        for sym, d in cohort:
            if len(recs) >= a.limit:
                break
            ld = datetime.strptime(d, "%Y-%m-%d")
            m1 = load_1m(conn, sym, ld, ld + timedelta(days=HOLD_DAYS + 2))
            if len(m1) < 1400:                    # Day-1 이 거의 완전해야 한다
                continue
            d1 = resample(m1, "1D")
            h1 = resample(m1, "1h")
            if len(d1) < 5 or len(h1) < 48:
                continue
            # 진입 = Day-1 종가. 1h 격자에서는 그 시각의 봉.
            entry_px = float(d1.iloc[0]["close"])
            # ⚠ 1h 진입 봉 — Day-1 **마지막** 1h 봉이다. searchsorted 로
            #   23:59 를 찾으면 다음 날 00:00 을 가리켜 한 시간이 밀린다
            #   (앞선 판본의 21.4% 는 그 오프바이원이었다).
            day1_end = d1.index[0] + timedelta(days=1)
            hpos = int(h1.index.searchsorted(day1_end, side="left")) - 1
            if hpos < 0 or hpos >= len(h1) - 24:
                continue
            rec = {"symbol": sym, "listing": d, "entry_px": entry_px,
                   "day1_range_pct": float((d1.iloc[0]["high"] - d1.iloc[0]["open"])
                                           / d1.iloc[0]["open"] * 100)}
            # 진입 바 = 일봉이면 Day-1, 1h 면 Day-1 의 마지막 시간봉
            rec["h_entry_range_pct"] = float(
                (h1.iloc[hpos]["high"] - h1.iloc[hpos]["open"])
                / h1.iloc[hpos]["open"] * 100)
            for sl in SL_GRID:
                rec[f"d_{sl}"] = entry_bar_skip(d1, 0, float(d1.iloc[0]["open"]), sl)
                rec[f"h_{sl}"] = entry_bar_skip(
                    h1, hpos, float(h1.iloc[hpos]["open"]), sl)
            recs.append(rec)
            if len(recs) % 10 == 0:
                log.info("  %d종목 처리", len(recs))

    if not recs:
        raise SystemExit("표본이 없다 — 1분봉 적재를 확인하라")
    log.info("표본 %d상장", len(recs))

    print("=" * 96)
    print(f"해상도 연구 — 상장 {len(recs)}건 · {recs[0]['listing']} ~ "
          f"{recs[-1]['listing']} · 진입 = Day-1 종가 숏")
    print("⚠ 커널과 같이 **진입 바는 손절 판정에서 제외**한다(미래참조 방지)")
    print("=" * 96)
    r0 = np.array([r["day1_range_pct"] for r in recs])
    print(f"\n  Day-1 일중 상승폭 — p50 {np.percentile(r0,50):.1f}% · "
          f"p75 {np.percentile(r0,75):.1f}% · p90 {np.percentile(r0,90):.1f}%")

    rh = np.array([r["h_entry_range_pct"] for r in recs])
    print(f"  1h 진입 봉 상승폭  — p50 {np.percentile(rh,50):.1f}% · "
          f"p75 {np.percentile(rh,75):.1f}% · p90 {np.percentile(rh,90):.1f}%")

    print(f"\n【핵심】 진입 바 안에서 이미 손절선을 넘긴 비율 = **그 손절은 없는 것**")
    print(f"  {'손절':>6}{'일봉 무력화':>13}{'1h 무력화':>12}{'개선':>10}")
    print("  " + "-" * 46)
    res = {}
    for sl in SL_GRID:
        dpct = 100 * float(np.mean([r[f"d_{sl}"] for r in recs]))
        hpct = 100 * float(np.mean([r[f"h_{sl}"] for r in recs]))
        res[f"sl_{sl}"] = {"daily_dead_pct": dpct, "h1_dead_pct": hpct}
        mark = "  ← 축이 열린다" if (dpct >= 30 and hpct < 15) else ""
        print(f"  {sl:>6.0%}{dpct:>12.1f}%{hpct:>11.1f}%"
              f"{dpct-hpct:>+9.1f}%p{mark}")

    print("\n  " + "-" * 46)
    print("  읽는 법 — 일봉에서 무력화율이 높은데 1h 에서 낮아지는 손절 구간이")
    print("            **1h 판본으로만 측정 가능한 영역**이다. 그 구간이 없으면")
    print("            1h 로 내릴 이유도 없다.")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n": len(recs),
         "day1_range_pct": {"p50": float(np.percentile(r0, 50)),
                            "p75": float(np.percentile(r0, 75)),
                            "p90": float(np.percentile(r0, 90))},
         "results": res}, ensure_ascii=False, indent=2, default=str))
    print("=" * 96)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
