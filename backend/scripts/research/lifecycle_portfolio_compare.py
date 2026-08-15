"""신상저격수 파라미터를 **포트폴리오 기준**으로 비교한다.

⚠ 왜 거래당 지표로는 안 되나 — 이미 겪은 사례가 있다
    `run_binance_paper_cycle.sh` 주석(실측):
        거래 **단위** 백테스트(251건)에서 d7 은 base 대비 **-14.08%p (t -3.05)**
        로 최악이었다. 그런데 포트폴리오에서는 총손익 **3.4배**, 포착률
        **+13.8%p**, MDD **-50.4 → -41.4%** 로 뒤집힌다.
        조기청산이 자본을 빨리 풀어 **다음 상장을 잡게 해주기** 때문이다.

    계좌는 $720 이고 종목당 상한 20% 다. 자본이 묶이면 그 뒤 상장을 통째로
    놓친다. 거래당 평균은 **놓친 거래를 세지 않으므로** 그걸 못 본다.

    2026-08-15 에 나는 이 오류를 그대로 반복했다 — 거래당 격자만 보고
    "base 가 낫다"고 했다. 이 스크립트는 그 판정을 포트폴리오로 다시 재기
    위한 것이다.

원본 `notional_cap_portfolio_sim.py` 의 자본 회전 모델을 그대로 쓰되
(진입 = min(cap×지갑, 가용×0.97) · 가용<$5 면 포기 · 청산 먼저 후 진입),
**익절·조기청산·손절폭을 파라미터로** 연다.

⚠ 이 시뮬은 상장당 **한 번만** 진입한다. 따라서 `entry_window_days`(재진입 창)
   3→1 변경은 **여기서 측정되지 않는다.** 그 축은 별도 판단이 필요하다.

조기청산 공식은 소스 원본과 같다:
    d7  vol_cliff = mean(vol[Day2..Day7]) / vol[Day1]   >= 0.40 → 청산
    d14 vol_cliff = mean(vol[Day8..Day14]) / vol[Day1]  >= 0.40 → 청산

사용:
  python3 -m scripts.research.lifecycle_portfolio_compare --cap 0.20
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pf_compare")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "lifecycle_portfolio_compare.json"

INITIAL_CAPITAL = 593.44      # 실계좌 최초 입금액 (원본과 동일)
FEE_ROUND_TRIP = 0.0008
MIN_NOTIONAL = 5.0
MARGIN_FRACTION = 0.97
VOL_CLIFF_THR = 0.40

# 비교 대상 — 이름, 손절, 익절(None=없음), 조기청산 check_day(None=없음)
CONFIGS = [
    ("종전 실거래  SL50/익절없음/d7", 0.50, None, 7),
    ("신규 커밋    SL20/익절50/d7", 0.20, 0.50, 7),
    ("신규+base    SL20/익절50/없음", 0.20, 0.50, None),
    ("base 종전    SL50/익절없음/없음", 0.50, None, None),
    ("신규+d14     SL20/익절50/d14", 0.20, 0.50, 14),
]


def load_cohort(conn) -> list[dict]:
    """상장 30~365일 지난 종목. 일봉은 `ohlcv_daily` 에서 (거래량 포함)."""
    from sqlalchemy import text
    listings = json.loads(LISTINGS.read_text())
    today = date.today()
    px = pd.DataFrame(conn.execute(text(
        "SELECT symbol, date, open, high, low, close, volume FROM ohlcv_daily "
        "WHERE is_partial = false ORDER BY symbol, date")).fetchall(),
        columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    px["date"] = pd.to_datetime(px["date"])
    for c in ("open", "high", "low", "close", "volume"):
        px[c] = pd.to_numeric(px[c], errors="coerce")

    out = []
    for sym, g in px.groupby("symbol"):
        meta = listings.get(sym)
        if not isinstance(meta, dict) or not meta.get("onboard_date"):
            continue
        ld = datetime.strptime(meta["onboard_date"], "%Y-%m-%d").date()
        if not (30 <= (today - ld).days <= 365):
            continue
        d = g.set_index("date").sort_index()
        if len(d) < 30:
            continue
        pos = d.index.get_indexer([pd.Timestamp(ld)], method="nearest")[0]
        # 상장일 봉을 못 맞추거나 뒤가 30일 안 되면 못 쓴다
        if abs((d.index[pos].date() - ld).days) > 2 or pos >= len(d) - 30:
            continue
        out.append({"symbol": sym, "listing": ld, "entry_pos": int(pos),
                    "daily": d})
    return out


def resolve(daily: pd.DataFrame, pos: int, sl: float, tp: float | None,
            check_day: int | None, hold: int = 30) -> dict:
    """한 상장의 청산 시점·가격. 자본과 무관하다.

    숏이므로 손절은 **위**(고가), 익절은 **아래**(저가)에서 걸린다.
    같은 봉에서 둘 다 닿으면 **손절 우선**(보수적).
    """
    entry = float(daily.iloc[pos]["close"])
    sl_px = entry * (1.0 + sl)
    tp_px = entry * (1.0 - tp) if tp is not None else None
    last = min(pos + hold, len(daily) - 1)

    # 조기청산 판정일 — 소스와 같은 날짜 규약(Day 1 = iloc[pos])
    ee_idx = None
    if check_day is not None:
        vols = daily["volume"].values
        d1 = float(vols[pos]) if pos < len(vols) else 0.0
        if d1 > 0:
            if check_day == 7:
                seg = vols[pos + 1:pos + 7]        # Day2..Day7
            else:
                seg = vols[pos + 7:pos + 14]       # Day8..Day14
            if len(seg) > 0 and float(np.mean(seg)) / d1 >= VOL_CLIFF_THR:
                cand = pos + check_day - 1
                if cand <= last:
                    ee_idx = cand

    exit_idx, exit_px, reason = last, float(daily.iloc[last]["close"]), "time"
    for i in range(pos + 1, last + 1):
        hi, lo = float(daily.iloc[i]["high"]), float(daily.iloc[i]["low"])
        if hi >= sl_px:
            exit_idx, exit_px, reason = i, sl_px, "sl"
            break
        if tp_px is not None and lo <= tp_px:
            exit_idx, exit_px, reason = i, tp_px, "tp"
            break
        if ee_idx is not None and i >= ee_idx:
            exit_idx, exit_px, reason = i, float(daily.iloc[i]["close"]), "early"
            break

    return {"entry_date": daily.index[pos].date(),
            "exit_date": daily.index[exit_idx].date(),
            "entry_price": entry, "exit_price": exit_px,
            "ret": (entry - exit_px) / entry - FEE_ROUND_TRIP,
            "reason": reason,
            "path": daily.iloc[pos:exit_idx + 1]}


def simulate(cohort: list[dict], cap: float, sl: float, tp: float | None,
             check_day: int | None) -> dict:
    trades = []
    for c in cohort:
        t = resolve(c["daily"], c["entry_pos"], sl, tp, check_day)
        t["symbol"] = c["symbol"]
        trades.append(t)
    trades.sort(key=lambda t: t["entry_date"])
    by_entry: dict = {}
    for t in trades:
        by_entry.setdefault(t["entry_date"], []).append(t)

    days = pd.date_range(min(t["entry_date"] for t in trades),
                         max(t["exit_date"] for t in trades), freq="D")
    wallet, open_pos = INITIAL_CAPITAL, []
    taken, starved, curve = [], [], []
    reasons: dict = {}
    for d in days:
        dd = d.date()
        still = []
        for p in open_pos:                       # 1) 청산 먼저 — 증거금 반환
            if p["exit_date"] <= dd:
                wallet += p["margin"] * p["ret"]
                reasons[p["reason"]] = reasons.get(p["reason"], 0) + 1
                continue
            still.append(p)
        open_pos = still

        locked = sum(p["margin"] for p in open_pos)
        for t in by_entry.get(dd, []):           # 2) 진입
            avail = max(wallet - locked, 0.0)
            margin = min(cap * wallet, avail * MARGIN_FRACTION)
            if margin < MIN_NOTIONAL:
                starved.append(t["symbol"])      # 자본이 없어 못 잡은 상장
                continue
            open_pos.append({**t, "margin": margin})
            locked += margin
            taken.append({"symbol": t["symbol"], "margin": margin,
                          "pnl": margin * t["ret"], "ret": t["ret"]})

        unreal = 0.0                             # 3) 일별 마킹
        for p in open_pos:
            try:
                px = float(p["path"].loc[:d].iloc[-1]["close"])
            except Exception:
                px = p["entry_price"]
            unreal += p["margin"] * ((p["entry_price"] - px) / p["entry_price"])
        curve.append(wallet + unreal)

    eq = np.array(curve)
    peak = np.maximum.accumulate(eq)
    mdd = float(((eq - peak) / peak).min() * 100) if len(eq) else 0.0
    pnls = [t["pnl"] for t in taken]
    return {"n_listings": len(trades), "taken": len(taken),
            "starved": len(starved),
            "capture_pct": 100.0 * len(taken) / max(len(trades), 1),
            "final_equity": float(eq[-1]) if len(eq) else INITIAL_CAPITAL,
            "total_pnl": float(sum(pnls)),
            "mdd_pct": mdd,
            "worst_trade": float(min(pnls)) if pnls else 0.0,
            "best_trade": float(max(pnls)) if pnls else 0.0,
            "win_pct": 100.0 * float(np.mean([p > 0 for p in pnls])) if pnls else 0.0,
            "exit_reasons": reasons}


def main() -> int:
    p = argparse.ArgumentParser(description="신상저격수 포트폴리오 비교")
    p.add_argument("--cap", type=float, default=0.20, help="종목당 상한(실거래 0.20)")
    # ⚠ 단일 경로 · 중첩이 심하다. 원본 도구 주석이 경고한 그대로다 —
    #   "수익 기준 최적이 분할마다 100%/30%/25% 로 뒤집힌다".
    #   그래서 **분할마다 순위가 유지되는지**를 함께 낸다.
    p.add_argument("--only", default="", help="쉼표 구분 종목 제한")
    p.add_argument("--grid", action="store_true", help="손절×익절 격자")
    p.add_argument("--grid-sl", default="0.08,0.10,0.15,0.20,0.30,0.50")
    p.add_argument("--grid-tp", default="none,0.30,0.50")
    p.add_argument("--dump-symbols", default="", help="코호트 종목을 파일로")
    p.add_argument("--splits", type=int, default=2, help="상장일 기준 균등 분할 수")
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()


    # ⚠ 격자 모드 — 같은 코호트·같은 진입 시각에서 손절×익절을 훑는다.
    #   "최고순익" 비교는 **포트폴리오**로 해야 한다(거래당 ≠ 포트폴리오).
    if a.grid:
        sls = [float(x) for x in a.grid_sl.split(",")]
        tps = [None if x.strip().lower() == "none" else float(x)
               for x in a.grid_tp.split(",")]
        CONFIGS.clear()
        for sl in sls:
            for tp in tps:
                lab = f"SL{sl:.0%}/{'없음' if tp is None else f'TP{tp:.0%}'}/d7"
                CONFIGS.append((lab, sl, tp, 7))

    from app.db.session import engine
    with engine.connect() as conn:
        cohort = load_cohort(conn)
    if a.only:
        keep = {x.strip().upper() for x in a.only.split(",") if x.strip()}
        cohort = [c for c in cohort if c["symbol"] in keep]
    if a.dump_symbols:
        Path(a.dump_symbols).write_text(
            ",".join(sorted(c["symbol"] for c in cohort)))
        print(f"코호트 {len(cohort)}종목 → {a.dump_symbols}")
        return 0
    if not cohort:
        raise SystemExit("코호트가 비었다 — listing_dates.json / ohlcv_daily 확인")
    log.info("코호트 %d상장 · %s ~ %s", len(cohort),
             min(c["listing"] for c in cohort), max(c["listing"] for c in cohort))

    print("=" * 104)
    print(f"신상저격수 포트폴리오 비교 — 상장 {len(cohort)}건 · 종목당 상한 "
          f"{a.cap:.0%} · 시드 ${INITIAL_CAPITAL:.2f} · 1x")
    print("⚠ 거래당 지표가 아니라 **자본 제약을 넣은 포트폴리오**다. "
          "놓친 상장(starved)이 성과에 반영된다")
    print("⚠ 상장당 1회 진입 모델이라 **진입창(재진입) 변경은 여기서 안 잡힌다**")
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

    # ── 분할 안정성 ──────────────────────────────────────────────────
    if a.splits > 1:
        co = sorted(cohort, key=lambda c: c["listing"])
        chunks = [co[i::1][j * len(co) // a.splits:(j + 1) * len(co) // a.splits]
                  for j in range(a.splits) for i in (0,)][:a.splits]
        print(f"\n  분할 안정성 — 상장일 기준 {a.splits}등분 · 최종자본$ (순위)")
        head = "".join(f"{'분할'+str(j+1):>16}" for j in range(a.splits))
        print(f"  {'설정':<30}{head}")
        print("  " + "-" * (30 + 16 * a.splits))
        per = {}
        for name, sl, tp, cd in CONFIGS:
            per[name] = [simulate(ch, a.cap, sl, tp, cd)["final_equity"]
                         for ch in chunks if len(ch) >= 10]
        ranks = []
        for j in range(len(next(iter(per.values())))):
            order = sorted(per, key=lambda n: -per[n][j])
            ranks.append({n: order.index(n) + 1 for n in per})
        for name in per:
            cells = "".join(f"{per[name][j]:>11.0f}({ranks[j][name]})"
                            for j in range(len(per[name])))
            print(f"  {name:<30}{cells}")
        top = [min(r, key=r.get) for r in ranks]
        stable = len(set(top)) == 1
        print(f"\n  각 분할 1위: {top}")
        print(f"  → 순위 {'**유지된다** — 수익으로 골라도 된다' if stable else '**뒤집힌다** — 수익 순위를 못 믿는다'}")
        res["_split_stability"] = {"per_split": per, "top": top, "stable": stable}

    print("\n  청산 사유:")
    for name in [n for n, *_ in CONFIGS]:   # `_split_stability` 항목 제외
        print(f"    {name:<30} {res[name]['exit_reasons']}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"params": vars(a), "results": res},
                                      ensure_ascii=False, indent=2, default=str))
    print("=" * 104)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
