"""신상저격수 — **레버리지 × 종목당 상한** 포트폴리오 시뮬레이션.

질문 (대표님, 2026-08-12)
  "자본을 늘리지 말고 레버리지를 조정해서 빈도수를 늘리는 효과를 볼 수 있을까?"

구조 확인
  현행 상한 `REAL_MAX_SYMBOL_FRACTION = 0.20` 은 **증거금** 기준이고 레버리지는 1배다.
      증거금 20% × 1배 = 명목 20%  →  동시 5포지션
  **레버리지만 올리면 포지션이 커질 뿐 개수는 그대로다.** 개수를 늘리려면
  증거금 상한을 낮추고 레버리지로 명목을 유지해야 한다.
      증거금 10% × 2배 = 명목 20%  →  10포지션
      증거금  5% × 4배 = 명목 20%  →  20포지션

  즉 이 질문은 "명목을 유지한 채 분산을 늘리면 좋아지는가" 다.

무엇이 위험한가
  SL 은 숏 기준 **+50% 역행**이다. 레버리지 L 이면 증거금 대비 손실이 50%×L 이다.
      L=1  →  증거금의  50% 손실 (여유 있음)
      L=2  →  증거금의 100% 손실 (정확히 전액)
      L=4  →  증거금의 200% 손실 (**증거금을 넘어 공용 풀에서 끌어씀**)
  교차 마진이라 개별 청산이 아니라 **계좌 전체**가 흔들린다. 거래의 37%가 SL 이고
  국면에 따라 몰린다(2024년 SL 50%). 그래서 분산 이득과 꼬리 손실을 같이 재야 한다.

모델
  · 상장 캘린더대로 자본을 굴린다 (기존 notional_cap_portfolio_sim 과 동일 구조).
  · 진입 증거금 = min(cap × 지갑, 가용 × 0.97), 명목 = 증거금 × L.
  · 손익 = 명목 × 수익률. 수수료는 명목 기준 왕복 0.08%.
  · **계좌 파산 판정**: 에쿼티(지갑+미실현) ≤ 0 이면 그 시점에 전량 청산하고 종료.
  · 포착률(잡은 상장 / 전체 상장)을 같이 낸다 — 빈도 효과의 직접 측정치.

사용:
  python3 scripts/research/lifecycle_leverage_sim.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "research"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lev_sim")

INITIAL = 724.04          # 현재 실계좌 잔고
FEE_RT = 0.0008
MIN_MARGIN = 5.0
MARGIN_FRAC = 0.97
CAPS = [0.20, 0.10, 0.05, 0.03]
LEVS = [1, 2, 3, 5]


def run(trades, cap_frac: float, lev: int) -> dict:
    trades = sorted(trades, key=lambda t: t["entry_date"])
    days = pd.date_range(min(t["entry_date"] for t in trades),
                         max(t["exit_date"] for t in trades), freq="D")
    wallet = INITIAL
    open_pos, taken, starved, eq_curve = [], [], [], []
    max_conc, blown_at = 0, None
    by_entry = {}
    for t in trades:
        by_entry.setdefault(t["entry_date"], []).append(t)

    for d in days:
        dd = d.date()
        still = []
        for p in open_pos:
            if p["exit_date"] <= dd:
                wallet += p["notional"] * p["ret"] - p["notional"] * FEE_RT
                continue
            still.append(p)
        open_pos = still

        locked = sum(p["margin"] for p in open_pos)
        for t in by_entry.get(dd, []):
            avail = max(wallet - locked, 0.0)
            margin = min(cap_frac * wallet, avail * MARGIN_FRAC)
            if margin < MIN_MARGIN:
                starved.append(t["symbol"])
                continue
            p = {**t, "margin": margin, "notional": margin * lev}
            open_pos.append(p)
            locked += margin
            taken.append({"symbol": t["symbol"], "margin": margin,
                          "pnl": margin * lev * t["ret"] - margin * lev * FEE_RT})
        max_conc = max(max_conc, len(open_pos))

        unreal = 0.0
        for p in open_pos:
            try:
                px = float(p["path"].loc[:d].iloc[-1]["close"])
            except Exception:
                px = p["entry_price"]
            unreal += p["notional"] * ((p["entry_price"] - px) / p["entry_price"])
        eq = wallet + unreal
        eq_curve.append((dd, eq))
        if eq <= 0 and blown_at is None:      # 계좌 파산
            blown_at = str(dd)
            wallet = 0.0
            open_pos = []
            break

    if blown_at is None:
        for p in open_pos:
            wallet += p["notional"] * p["ret"] - p["notional"] * FEE_RT

    e = np.array([v for _, v in eq_curve], dtype=float)
    peak = np.maximum.accumulate(e) if len(e) else np.array([1.0])
    mdd = float(((e - peak) / np.maximum(peak, 1e-9)).min() * 100) if len(e) else 0.0
    pnls = [t["pnl"] for t in taken]
    n_all = len(taken) + len(starved)
    return {"cap": cap_frac, "lev": lev,
            "final": round(wallet, 2),
            "ret_pct": round((wallet / INITIAL - 1) * 100, 2),
            "mdd_pct": round(mdd, 2),
            "n_taken": len(taken), "n_starved": len(starved),
            "capture_pct": round(100 * len(taken) / max(n_all, 1), 1),
            "max_conc": max_conc,
            "worst": round(min(pnls), 2) if pnls else 0.0,
            "blown_at": blown_at}


def main() -> int:
    p = argparse.ArgumentParser(description="레버리지 x 상한 시뮬")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "lifecycle_phase" / "leverage_sim__metrics.json"))
    args = p.parse_args()

    from notional_cap_portfolio_sim import build_cohort, resolve_trade
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        cohort = build_cohort(db)
    finally:
        db.close()
    trades = []
    for c in cohort:
        t = resolve_trade(c["daily"], c["entry_pos"])
        t["symbol"] = c["symbol"]
        trades.append(t)
    log.info("코호트 %d건", len(trades))

    res = [run(trades, c, l) for c in CAPS for l in LEVS]
    print("\n" + "=" * 104)
    print(f"레버리지 x 종목당 상한 — 상장 {len(trades)}건 / 초기자본 ${INITIAL:.0f}")
    print("=" * 104)
    print("  명목 = 증거금상한 x 레버리지. 같은 명목이면 위험은 같고 분산만 달라진다.")
    print(f"  {'증거금':>7}{'배':>4}{'명목':>7}{'최종$':>10}{'수익%':>10}{'MDD%':>9}"
          f"{'잡은수':>7}{'놓친수':>7}{'포착%':>7}{'동시':>6}{'최악$':>9}  파산")
    print("-" * 104)
    for r in res:
        nom = r["cap"] * r["lev"]
        blown = r["blown_at"] or ""
        print(f"  {r['cap']*100:>6.0f}%{r['lev']:>4}{nom*100:>6.0f}%{r['final']:>10,.0f}"
              f"{r['ret_pct']:>+10.1f}{r['mdd_pct']:>9.1f}{r['n_taken']:>7}"
              f"{r['n_starved']:>7}{r['capture_pct']:>7.1f}{r['max_conc']:>6}"
              f"{r['worst']:>9,.0f}  {blown}")
    print("-" * 104)
    same = [r for r in res if abs(r["cap"] * r["lev"] - 0.20) < 1e-9]
    if same:
        print("  ** 명목 20% 고정 — 분산만 늘렸을 때 **")
        for r in sorted(same, key=lambda z: z["lev"]):
            print(f"     증거금 {r['cap']*100:>3.0f}% x {r['lev']}배 → 동시 {r['max_conc']:>2}포지션 / "
                  f"포착 {r['capture_pct']:>5.1f}% / 수익 {r['ret_pct']:>+9.1f}% / "
                  f"MDD {r['mdd_pct']:>7.1f}% {'/ **파산 ' + r['blown_at'] + '**' if r['blown_at'] else ''}")
    print("=" * 104 + "\n")
    json.dump({"initial": INITIAL, "results": res}, open(args.out, "w"),
              ensure_ascii=False, indent=2, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
