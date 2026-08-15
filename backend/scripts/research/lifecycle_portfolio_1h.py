"""신상저격수 포트폴리오 판정을 **1시간봉 해상도**로 다시 잰다 (1h 판본 3단계).

왜 다시 재나
    2단계에서 **거래당** 기준으로 일봉 격자의 "손절 조일수록 좋다"가
    인공물임이 드러났다(1h 에서 역전: 손절 50% 5.39% > 20% 3.44%).

    그런데 오늘 실제 파라미터 변경의 근거는 **포트폴리오** 판정이었고,
    그건 자본 제약·포착률을 재는 다른 측정이라 거래당 결과만으로 안 뒤집힌다.
    (오늘 배운 것: 거래당 ≠ 포트폴리오. `run_binance_paper_cycle.sh` 주석에
     d7 이 거래당 최악인데 포트폴리오에서 3.4배인 사례가 있다.)

    **그래서 같은 자본 모델을 1h 해상도로 다시 돌린다.** 손절·익절 판정만
    시간 단위가 되고 자본 회전 규칙은 그대로다.

⚠ 일봉판과 진입을 같은 시각으로 맞춘다
    일봉판: 진입가 = Day-1 **종가** = 상장+24h
    1h판  : 진입가 = 상장+24h **봉의 시가** = 같은 순간

    ⚠ 판정 시작 봉이 다르다 — 일봉판은 진입 바 **다음** 봉부터 본다(진입 전
      구간이 그 바에 섞여 있으므로 옳다). 1h 판은 진입이 그 봉의 시가이므로
      **그 봉부터** 본다. 둘 다 "진입 이후만" 이라는 같은 규칙이다.

⚠ vol_cliff 는 일 단위 그대로다
    조기청산은 "Day 7 / Day 14 의 거래량 비율"이라 1h 로 내려도 정의가
    바뀌지 않는다. 1h 거래량을 일별로 합쳐 쓴다.

사용:
  python3 -m scripts.research.lifecycle_portfolio_1h --cap 0.20 --splits 3
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pf_1h")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "lifecycle_portfolio_1h.json"

INITIAL_CAPITAL = 593.44
FEE_ROUND_TRIP = 0.0008
MIN_NOTIONAL = 5.0
MARGIN_FRACTION = 0.97
VOL_CLIFF_THR = 0.40
HOLD_DAYS = 30

CONFIGS = [
    ("종전 실거래  SL50/익절없음/d7", 0.50, None, 7),
    ("신규 커밋    SL20/익절50/d7", 0.20, 0.50, 7),
    ("신규+base    SL20/익절50/없음", 0.20, 0.50, None),
    ("base 종전    SL50/익절없음/없음", 0.50, None, None),
    ("신규+d14     SL20/익절50/d14", 0.20, 0.50, 14),
]


def load_cohort(conn, since: str, entry_h: int = 24) -> list[dict]:
    from sqlalchemy import text
    listings = json.loads(LISTINGS.read_text())
    today = date.today()
    h = pd.DataFrame(conn.execute(text(
        "SELECT symbol, ts, open, high, low, close, volume FROM ohlcv_hourly "
        "ORDER BY symbol, ts")).fetchall(),
        columns=["symbol", "ts", "open", "high", "low", "close", "volume"])
    h["ts"] = pd.to_datetime(h["ts"])
    for c in ("open", "high", "low", "close", "volume"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
    out = []
    for sym, g in h.groupby("symbol"):
        meta = listings.get(sym)
        if not isinstance(meta, dict) or not meta.get("onboard_date"):
            continue
        d = meta["onboard_date"]
        if d < since:
            continue
        ld = datetime.strptime(d, "%Y-%m-%d").date()
        if (today - ld).days < HOLD_DAYS:      # 아직 30일이 안 지난 상장 제외
            continue
        bars = g.set_index("ts").sort_index()
        entry_ts = pd.Timestamp(ld) + pd.Timedelta(hours=entry_h)
        seg = bars.loc[(bars.index >= entry_ts)
                       & (bars.index <= entry_ts + pd.Timedelta(days=HOLD_DAYS))]
        if len(seg) < 24 * 5:
            continue
        # 진입 봉이 정확히 상장+entry_h 여야 한다
        if abs((seg.index[0] - entry_ts).total_seconds()) > 3600:
            continue
        # vol_cliff 용 일별 거래량 — 1h 를 일로 합친다 (정의는 그대로)
        dv = bars.loc[bars.index >= pd.Timestamp(ld)]["volume"].resample("1D").sum()
        out.append({"symbol": sym, "listing": ld, "bars": seg, "daily_vol": dv})
    return out


def resolve(item: dict, sl: float, tp: float | None,
            check_day: int | None) -> dict:
    """1시간봉으로 청산 시점·가격. 진입 = 첫 봉 **시가**(= 상장+24h)."""
    bars = item["bars"]
    entry = float(bars.iloc[0]["open"])
    sl_px = entry * (1.0 + sl)
    tp_px = entry * (1.0 - tp) if tp is not None else None

    ee_ts = None
    if check_day is not None:
        dv = item["daily_vol"].values
        if len(dv) > check_day and dv[0] > 0:
            seg = dv[1:7] if check_day == 7 else dv[7:14]
            if len(seg) and float(np.mean(seg)) / float(dv[0]) >= VOL_CLIFF_THR:
                ee_ts = pd.Timestamp(item["listing"]) + pd.Timedelta(days=check_day)

    exit_i, exit_px, reason = len(bars) - 1, float(bars.iloc[-1]["close"]), "time"
    for i in range(len(bars)):
        hi, lo = float(bars.iloc[i]["high"]), float(bars.iloc[i]["low"])
        if hi >= sl_px:
            exit_i, exit_px, reason = i, sl_px, "sl"
            break
        if tp_px is not None and lo <= tp_px:
            exit_i, exit_px, reason = i, tp_px, "tp"
            break
        if ee_ts is not None and bars.index[i] >= ee_ts:
            exit_i, exit_px, reason = i, float(bars.iloc[i]["close"]), "early"
            break
    return {"entry_date": bars.index[0].date(),
            "exit_date": bars.index[exit_i].date(),
            "entry_price": entry, "exit_price": exit_px,
            "ret": (entry - exit_px) / entry - FEE_ROUND_TRIP,
            "reason": reason,
            "path": bars.iloc[:exit_i + 1]["close"].resample("1D").last()}


def simulate(cohort: list[dict], cap: float, sl: float, tp: float | None,
             check_day: int | None) -> dict:
    trades = []
    for c in cohort:
        t = resolve(c, sl, tp, check_day)
        t["symbol"] = c["symbol"]
        trades.append(t)
    trades.sort(key=lambda t: t["entry_date"])
    by_entry: dict = {}
    for t in trades:
        by_entry.setdefault(t["entry_date"], []).append(t)

    days = pd.date_range(min(t["entry_date"] for t in trades),
                         max(t["exit_date"] for t in trades), freq="D")
    wallet, open_pos = INITIAL_CAPITAL, []
    taken, starved, curve, reasons = [], [], [], {}
    for d in days:
        dd = d.date()
        still = []
        for p in open_pos:
            if p["exit_date"] <= dd:
                wallet += p["margin"] * p["ret"]
                reasons[p["reason"]] = reasons.get(p["reason"], 0) + 1
                continue
            still.append(p)
        open_pos = still
        locked = sum(p["margin"] for p in open_pos)
        for t in by_entry.get(dd, []):
            avail = max(wallet - locked, 0.0)
            margin = min(cap * wallet, avail * MARGIN_FRACTION)
            if margin < MIN_NOTIONAL:
                starved.append(t["symbol"])
                continue
            open_pos.append({**t, "margin": margin})
            locked += margin
            taken.append({"symbol": t["symbol"], "margin": margin,
                          "pnl": margin * t["ret"], "ret": t["ret"]})
        unreal = 0.0
        for p in open_pos:
            try:
                px = float(p["path"].loc[:d].iloc[-1])
            except Exception:
                px = p["entry_price"]
            unreal += p["margin"] * ((p["entry_price"] - px) / p["entry_price"])
        curve.append(wallet + unreal)

    eq = np.array(curve)
    peak = np.maximum.accumulate(eq)
    pnls = [t["pnl"] for t in taken]
    return {"n_listings": len(trades), "taken": len(taken),
            "starved": len(starved),
            "capture_pct": 100.0 * len(taken) / max(len(trades), 1),
            "final_equity": float(eq[-1]) if len(eq) else INITIAL_CAPITAL,
            "total_pnl": float(sum(pnls)),
            "mdd_pct": float(((eq - peak) / peak).min() * 100) if len(eq) else 0.0,
            "worst_trade": float(min(pnls)) if pnls else 0.0,
            "win_pct": 100.0 * float(np.mean([p > 0 for p in pnls])) if pnls else 0.0,
            "exit_reasons": reasons}


def main() -> int:
    p = argparse.ArgumentParser(description="1시간봉 포트폴리오 판정")
    p.add_argument("--cap", type=float, default=0.20)
    p.add_argument("--since", default="2025-01-01")
    # ⚠ 해상도 효과를 분리하려면 **같은 상장 집합**이어야 한다.
    #   코호트가 다르면(1h 195건 vs 일봉 124건) 기회 수 차이가
    #   해상도 차이로 오독된다.
    # ⚠ 실측(DOSUSDT): 실거래 진입가 0.3118 은 상장+48h(0.3281, +5.2%)에
    #   가깝고 +24h(0.3800, +21.9%)와는 멀다. **실거래는 하루 늦게 들어간다**
    #   (`ohlcv_daily` 가 상장일 부분봉을 빼서 첫 완전봉이 다음날이 된다).
    #   해상도 효과만 분리하려면 일봉판과 **같은 48h** 로 맞춰야 한다.
    p.add_argument("--entry-offset-h", type=int, default=48)
    p.add_argument("--only", default="", help="쉼표 구분 종목 제한")
    p.add_argument("--splits", type=int, default=3)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine
    with engine.connect() as conn:
        cohort = load_cohort(conn, a.since, a.entry_offset_h)
    if a.only:
        keep = {x.strip().upper() for x in a.only.split(",") if x.strip()}
        cohort = [c for c in cohort if c["symbol"] in keep]
    if not cohort:
        raise SystemExit("코호트가 비었다")
    log.info("코호트 %d상장 · %s ~ %s", len(cohort),
             min(c["listing"] for c in cohort), max(c["listing"] for c in cohort))

    print("=" * 104)
    print(f"신상저격수 포트폴리오 — **1시간봉 해상도** · 상장 {len(cohort)}건 · "
          f"상한 {a.cap:.0%} · 시드 ${INITIAL_CAPITAL:.2f} · 1x · 진입 상장+{a.entry_offset_h}h")
    print("⚠ 자본 회전 규칙은 일봉판과 동일. **손절·익절 판정만 시간 단위**다")
    print("=" * 104)
    print(f"  {'설정':<30}{'잡음':>6}{'놓침':>6}{'포착%':>8}{'최종자본$':>11}"
          f"{'총손익$':>10}{'MDD%':>8}{'최악$':>9}{'승률%':>7}")
    print("  " + "-" * 100)

    res = {}
    for name, sl, tp, cd in CONFIGS:
        r = simulate(cohort, a.cap, sl, tp, cd)
        res[name] = {"sl": sl, "tp": tp, "check_day": cd, **r}
        print(f"  {name:<30}{r['taken']:>6}{r['starved']:>6}"
              f"{r['capture_pct']:>8.1f}{r['final_equity']:>11.2f}"
              f"{r['total_pnl']:>10.2f}{r['mdd_pct']:>8.1f}"
              f"{r['worst_trade']:>9.2f}{r['win_pct']:>7.1f}")

    if a.splits > 1:
        co = sorted(cohort, key=lambda c: c["listing"])
        chunks = [co[j * len(co) // a.splits:(j + 1) * len(co) // a.splits]
                  for j in range(a.splits)]
        print(f"\n  분할 안정성 — 상장일 기준 {a.splits}등분 · 최종자본$ (순위)")
        print(f"  {'설정':<30}" + "".join(f"{'분할'+str(j+1):>16}"
                                          for j in range(a.splits)))
        print("  " + "-" * (30 + 16 * a.splits))
        per = {n: [simulate(ch, a.cap, sl, tp, cd)["final_equity"]
                   for ch in chunks if len(ch) >= 10]
               for n, sl, tp, cd in CONFIGS}
        ranks = []
        for j in range(len(next(iter(per.values())))):
            order = sorted(per, key=lambda n: -per[n][j])
            ranks.append({n: order.index(n) + 1 for n in per})
        for name in per:
            print(f"  {name:<30}" + "".join(
                f"{per[name][j]:>11.0f}({ranks[j][name]})"
                for j in range(len(per[name]))))
        top = [min(r, key=r.get) for r in ranks]
        print(f"\n  각 분할 1위: {top}")
        print(f"  → 순위 {'**유지된다**' if len(set(top)) == 1 else '**뒤집힌다**'}")
        res["_split"] = {"per_split": per, "top": top,
                         "stable": len(set(top)) == 1}

    print("\n  청산 사유:")
    for name, *_ in CONFIGS:
        print(f"    {name:<30} {res[name]['exit_reasons']}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"params": vars(a), "results": res},
                                      ensure_ascii=False, indent=2, default=str))
    print("=" * 104)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
