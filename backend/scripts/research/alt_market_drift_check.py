"""대조군이 번 이유 — **정말 하락장인가**를 직접 잰다.

배경
    `lifecycle_random_control` 에서 기성 종목 랜덤 숏이 30일에 평균 +10% 를
    벌었다. "숏이 벌었다"는 곧 "값이 내렸다"이지만, 그게 **시장 전체 하락장**
    인지 **알트만의 상대 약세**인지는 다른 질문이다. 추측하지 말고 재라.

재는 것
    ① 무조건 보유 대조 — 같은 앵커에서 기성 종목을 **그냥 사서** 30일 들고
      있으면 얼마인가. 숏 수익의 거울이다. 손절·익절 없이 순수 드리프트만.
    ② BTC 는 같은 구간에 어땠나 — BTC 가 올랐는데 알트만 내렸으면
      "하락장"이 아니라 **알트 상대 약세**다.
    ③ 시간에 걸쳐 고르게 내렸나, 몇 달에 몰렸나 — 몰려 있으면 "장세"가
      아니라 특정 사건이다.
    ④ **비겹침** 창으로도 같은가 — 교훈 #92. 앵커가 겹치면 t 가 부풀고,
      한 번의 폭락이 수십 번 세어진다.

⚠ 유동성 게이트가 **하락 쪽을 깎는다**
    풀 선정의 `ADV >= $3M` 은 `close * volume` 평균이다. 크게 무너진 종목은
    close 가 낮아 게이트에서 탈락한다. 즉 이 측정은 하락을 **과소평가**한다 —
    나오는 숫자는 보수적인 하한으로 읽어라.

사용:
  python3 -m scripts.research.alt_market_drift_check
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("drift")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "alt_market_drift_check.json"

CONTROL_LISTED_BEFORE = "2024-07-01"
CONTROL_MIN_ADV = 3e6
CONTROL_MIN_DAYS = 500
HOLD_DAYS = 30
BENCH = ["BTCUSDT", "ETHUSDT"]


def fwd_ret(bars: pd.DataFrame, anchor: pd.Timestamp, hold: int) -> float | None:
    """앵커 다음 봉 **시가**에 사서 hold 봉 뒤 **종가**에 판다.

    대조군 백테스트의 체결 규약과 같다(신호지연 1봉 → 다음 바 시가). 다르게
    잡으면 숏 수익률의 거울이 아니게 된다.
    """
    idx = bars.index.searchsorted(anchor, side="left")
    if idx + 1 + hold >= len(bars):
        return None
    e = float(bars["open"].iloc[idx + 1])
    x = float(bars["close"].iloc[idx + 1 + hold])
    if not (e > 0):
        return None
    return (x / e - 1.0) * 100


def main() -> int:
    p = argparse.ArgumentParser(description="알트 시장 드리프트 점검")
    p.add_argument("--since", default="2025-01-01")
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine
    listings = json.loads(LISTINGS.read_text())
    pool_cand = sorted(k for k, m in listings.items()
                       if isinstance(m, dict) and m.get("onboard_date")
                       and m["onboard_date"] <= CONTROL_LISTED_BEFORE)
    with engine.connect() as conn:
        liq = {r[0]: (r[1], float(r[2] or 0)) for r in conn.execute(text(
            "SELECT symbol, count(*), avg(close*volume) FROM ohlcv_daily "
            "WHERE date >= :d GROUP BY symbol"), {"d": a.since}).fetchall()}
        pool = [s for s in pool_cand
                if liq.get(s, (0, 0))[0] >= CONTROL_MIN_DAYS
                and liq.get(s, (0, 0))[1] >= CONTROL_MIN_ADV]
        syms = sorted(set(pool) | set(BENCH))
        r = conn.execute(text(
            "SELECT symbol, date, open, high, low, close, volume FROM ohlcv_daily "
            "WHERE symbol = ANY(:s) AND date >= :d ORDER BY symbol, date"),
            {"s": syms, "d": a.since}).fetchall()
    df = pd.DataFrame(r, columns=["symbol", "ts", "open", "high", "low",
                                  "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    bars = {s: g.set_index("ts")[["open", "high", "low", "close", "volume"]]
            for s, g in df.groupby("symbol")}
    log.info("대조 풀 %d종목 · 벤치 %s", len(pool), BENCH)

    anchors = sorted({pd.Timestamp(datetime.strptime(m["onboard_date"], "%Y-%m-%d"))
                      for m in listings.values()
                      if isinstance(m, dict) and m.get("onboard_date")
                      and m["onboard_date"] >= a.since})
    log.info("앵커(상장일) %d개 · %s ~ %s", len(anchors),
             anchors[0].date(), anchors[-1].date())

    print("=" * 96)
    print(f"  **대조군이 번 이유** — 기성 알트를 그냥 들고 있으면 얼마였나 "
          f"(보유 {HOLD_DAYS}일 · 풀 {len(pool)}종목)")
    print("=" * 96)

    # ── ① 무조건 보유 (앵커 전부 · 겹침) ─────────────────────────────
    rows = []
    for an in anchors:
        for s in pool:
            v = fwd_ret(bars.get(s, pd.DataFrame()), an, HOLD_DAYS)
            if v is not None:
                rows.append({"anchor": an, "symbol": s, "ret": v})
    d = pd.DataFrame(rows)
    if d.empty:
        raise SystemExit("표본 없음")
    lo = d["ret"].values
    print(f"\n  ① 무조건 매수 · 30일 보유  n={len(lo):,}")
    print(f"     평균 {lo.mean():+.2f}% · 중앙 {np.median(lo):+.2f}% · "
          f"상승 비율 {100*(lo>0).mean():.1f}%")
    print(f"     → 거울인 **무조건 숏**은 평균 {-lo.mean():+.2f}% · "
          f"중앙 {-np.median(lo):+.2f}%")
    print("     ⚠ 겹치는 앵커라 t 는 못 쓴다(교훈 #92) — 아래 ④ 비겹침으로 판정")

    # ── ② 벤치마크 ────────────────────────────────────────────────────
    print(f"\n  ② 같은 앵커에서 벤치마크는")
    bench_stat = {}
    for b in BENCH:
        v = [fwd_ret(bars.get(b, pd.DataFrame()), an, HOLD_DAYS) for an in anchors]
        v = np.array([x for x in v if x is not None])
        if len(v):
            bench_stat[b] = {"n": int(len(v)), "mean": float(v.mean()),
                             "med": float(np.median(v))}
            print(f"     {b:10} 평균 {v.mean():+.2f}% · 중앙 {np.median(v):+.2f}%"
                  f"  (n={len(v)})")
    # 구간 전체 단순 보유
    print(f"\n     구간 전체({a.since} ~ ) 단순 보유 수익률")
    span = {}
    for b in BENCH:
        g = bars.get(b)
        if g is not None and len(g) > 1:
            v = float(g["close"].iloc[-1] / g["open"].iloc[0] - 1) * 100
            span[b] = v
            print(f"     {b:10} {v:+.1f}%")
    # 풀 동일가중 지수 — 일별 횡단면 평균 수익률의 누적
    idx_rows = []
    for s in pool:
        g = bars.get(s)
        if g is None or len(g) < 2:
            continue
        rr = g["close"].pct_change()
        idx_rows.append(rr.rename(s))
    ew = pd.concat(idx_rows, axis=1).mean(axis=1, skipna=True)
    ew_cum = float((1 + ew.fillna(0)).prod() - 1) * 100
    span["POOL_EW"] = ew_cum
    print(f"     {'풀 동일가중':10} {ew_cum:+.1f}%   ← 기성 알트 시장 지수")

    # ── ③ 월별 ────────────────────────────────────────────────────────
    print(f"\n  ③ 월별 — 고르게 내렸나, 몇 달에 몰렸나 (앵커 월 기준 중앙값)")
    d["m"] = d["anchor"].dt.to_period("M").astype(str)
    mon = d.groupby("m")["ret"].agg(["median", "mean", "count"])
    for m, row in mon.iterrows():
        bar = "▼" * min(20, int(abs(row["median"]) / 2)) if row["median"] < 0 \
            else "▲" * min(20, int(row["median"] / 2))
        print(f"     {m}  중앙 {row['median']:+7.2f}%  평균 {row['mean']:+7.2f}%"
              f"  n={int(row['count']):>5}  {bar}")
    n_dn = int((mon["median"] < 0).sum())
    print(f"     → 중앙값이 마이너스인 달: **{n_dn}/{len(mon)}**")

    # ── ④ 비겹침 (교훈 #92) ───────────────────────────────────────────
    print(f"\n  ④ **비겹침** 창 — 앵커를 {HOLD_DAYS}일 간격으로만 (겹침 제거)")
    keep, last = [], None
    for an in anchors:
        if last is None or (an - last).days >= HOLD_DAYS:
            keep.append(an)
            last = an
    per = []
    for an in keep:
        v = [fwd_ret(bars.get(s, pd.DataFrame()), an, HOLD_DAYS) for s in pool]
        v = [x for x in v if x is not None]
        if len(v) >= 10:
            per.append({"anchor": str(an.date()), "n": len(v),
                        "mean": float(np.mean(v)), "med": float(np.median(v))})
    if len(per) >= 2:
        mm = np.array([x["mean"] for x in per])
        se = mm.std(ddof=1) / np.sqrt(len(mm))
        t = mm.mean() / se if se else float("nan")
        print(f"     비겹침 기간 {len(mm)}개 · 기간평균 {mm.mean():+.2f}% · "
              f"중앙 {np.median(mm):+.2f}% · **t {t:+.2f}**")
        print(f"     마이너스 기간 {int((mm<0).sum())}/{len(mm)}")
        for x in per:
            print(f"       {x['anchor']}  평균 {x['mean']:+7.2f}%  "
                  f"중앙 {x['med']:+7.2f}%  n={x['n']}")
    print("\n" + "=" * 96)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"pool": pool, "n_pairs": int(len(d)),
         "hold_mean": float(lo.mean()), "hold_med": float(np.median(lo)),
         "bench_fwd": bench_stat, "span_return": span,
         "monthly": mon.reset_index().to_dict("records"),
         "nonoverlap": per}, ensure_ascii=False, indent=2, default=str))
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
