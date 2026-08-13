"""신상저격수 — **사이징 옵션 그림자 포트폴리오** (페이퍼).

왜 (대표님 지시, 2026-08-12)
  "페이퍼 모드에 3%×1배와 3%×3배 옵션 전략을 추가해줘."

  레버리지 시뮬(131건 캘린더)에서 현행 20%×1배 대비 두 대안이 나왔다:

      설정          포착률   MDD      최악 단일
      20% x 1 (현행)  61.8%  -37.8%   -$97
      3%  x 1        100.0%  -19.1%   -$13
      3%  x 3        100.0%  -47.7%   -$47

  수익률은 비교 기준으로 쓰지 않는다 — 기존 `notional_cap_portfolio_sim.py` 가
  이미 확인했다: **수익 기준 최적 상한은 시간 분할마다 뒤집힌다**(단일 경로,
  심한 중첩). 모든 분할에서 단조인 축은 **포착률 / MDD / 최악 단일거래** 셋뿐이다.

왜 그림자 포트폴리오인가
  현재 페이퍼 트랙은 **종목당 고정 $200** 이라 상한·레버리지 개념이 없다
  (`lifecycle_live_signal_driver.py` — "paper: fixed notional from link").
  옵션을 붙이려면 계좌를 새로 만들고 주문 경로를 늘려야 하는데, 질문은 순수하게
  **사이징**이다. 신호는 이미 System-2 세션이 만들고 있다.

  그래서 같은 신호에 사이징만 다르게 적용하는 장부를 따로 굴린다. 새 계좌도,
  새 주문 경로도, 추가 위험도 없다. 그리고 **과거분까지 소급 계산**되므로
  기다리지 않고 바로 비교가 시작된다.

모델
  · 진입 증거금 = min(cap × 지갑, 가용 × 0.97), 명목 = 증거금 × 레버리지
  · 손익 = 명목 × 수익률 − 명목 × 왕복수수료(0.08%)
  · 증거금 < $5 면 진입 포기(starved) — 실계좌 MIN_REAL_NOTIONAL 과 동일
  · 에쿼티 ≤ 0 이면 파산 처리하고 그 시점에 정지
  · **멱등**: 매 실행마다 전 거래를 다시 굴린다. 중복 계상이 없다.

사용:
  python3 scripts/binance/lifecycle_sizing_shadow.py            # 계산 + 저장
  python3 scripts/binance/lifecycle_sizing_shadow.py --report   # 표만 출력
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("sizing_shadow")

OUT = ROOT / "runs" / "lifecycle_sizing_shadow"
INITIAL = 724.04          # 실계좌 잔고와 맞춘 출발점
FEE_RT = 0.0008
MIN_MARGIN = 5.0
MARGIN_FRAC = 0.97

# (이름, 증거금 상한, 레버리지)
VARIANTS = [
    ("현행 20%x1", 0.20, 1),
    ("대안A 3%x1", 0.03, 1),
    ("대안B 3%x3", 0.03, 3),
]


def load_trades() -> list:
    """System-2 lifecycle **base** 세션의 실제 거래를 사건 목록으로."""
    out = []
    for d in sorted(glob.glob(str(ROOT / "runs" / "paper_sessions" / "*"))):
        f = os.path.join(d, "session.json")
        if not os.path.exists(f):
            continue
        j = json.load(open(f))
        n = j.get("name", "")
        if "lifecycle" not in n:
            continue
        if any(v in n for v in ("h21", "earlyexit", "bearskip")):
            continue                      # base 변형만 — 백테스트 규칙과 같은 것
        tf = os.path.join(d, "trades.jsonl")
        if not os.path.exists(tf):
            continue
        for t in (json.loads(x) for x in open(tf)):
            if t.get("invalid"):        # 무효 표시된 기록 제외
                continue
            out.append({"symbol": j["symbol"],
                        "entry": pd.Timestamp(t["entry_ts"]).date(),
                        "exit": pd.Timestamp(t["exit_ts"]).date(),
                        "ret": float(t["return_pct"]),
                        "reason": t.get("exit_reason", "")})
    out.sort(key=lambda x: x["entry"])
    return out


def run(trades: list, cap: float, lev: int) -> dict:
    if not trades:
        return {}
    days = pd.date_range(min(t["entry"] for t in trades),
                         max(t["exit"] for t in trades), freq="D")
    wallet = INITIAL
    open_pos, taken, starved, curve = [], [], [], []
    max_conc, blown = 0, None
    by_entry: dict = {}
    for t in trades:
        by_entry.setdefault(t["entry"], []).append(t)

    for d in days:
        dd = d.date()
        keep = []
        for p in open_pos:
            if p["exit"] <= dd:
                wallet += p["notional"] * p["ret"] - p["notional"] * FEE_RT
                continue
            keep.append(p)
        open_pos = keep

        locked = sum(p["margin"] for p in open_pos)
        for t in by_entry.get(dd, []):
            avail = max(wallet - locked, 0.0)
            m = min(cap * wallet, avail * MARGIN_FRAC)
            if m < MIN_MARGIN:
                starved.append(t["symbol"])
                continue
            open_pos.append({**t, "margin": m, "notional": m * lev})
            locked += m
            taken.append({"symbol": t["symbol"], "date": str(dd),
                          "margin": round(m, 2),
                          "pnl": round(m * lev * (t["ret"] - FEE_RT), 2)})
        max_conc = max(max_conc, len(open_pos))
        # 보수적 마킹 — 미청산 포지션은 최종 수익률로 선형 근사
        unreal = sum(p["notional"] * p["ret"] for p in open_pos)
        eq = wallet + unreal
        curve.append((str(dd), round(eq, 2)))
        if eq <= 0 and blown is None:
            blown = str(dd)
            wallet, open_pos = 0.0, []
            break
    if blown is None:
        for p in open_pos:
            wallet += p["notional"] * p["ret"] - p["notional"] * FEE_RT

    e = np.array([v for _, v in curve], dtype=float)
    peak = np.maximum.accumulate(e) if len(e) else np.array([1.0])
    mdd = float(((e - peak) / np.maximum(peak, 1e-9)).min() * 100) if len(e) else 0.0
    pn = [t["pnl"] for t in taken]
    n_all = len(taken) + len(starved)
    return {"final": round(wallet, 2), "ret_pct": round((wallet / INITIAL - 1) * 100, 2),
            "mdd_pct": round(mdd, 2), "n_taken": len(taken), "n_starved": len(starved),
            "capture_pct": round(100 * len(taken) / max(n_all, 1), 1),
            "max_conc": max_conc, "worst": round(min(pn), 2) if pn else 0.0,
            "best": round(max(pn), 2) if pn else 0.0, "blown_at": blown,
            "avg_margin": round(float(np.mean([t["margin"] for t in taken])), 2) if taken else 0.0,
            "curve": curve[::7], "taken": taken[-20:]}


def main() -> int:
    p = argparse.ArgumentParser(description="사이징 옵션 그림자 포트폴리오")
    p.add_argument("--report", action="store_true", help="계산 후 표만 출력")
    args = p.parse_args()

    trades = load_trades()
    log.info("lifecycle base 거래 %d건 / 종목 %d",
             len(trades), len({t["symbol"] for t in trades}))
    if not trades:
        log.error("거래 없음")
        return 1

    res = {}
    for name, cap, lev in VARIANTS:
        r = run(trades, cap, lev)
        r.update({"cap": cap, "lev": lev})
        res[name] = r

    print("\n" + "=" * 100)
    print(f"신상저격수 사이징 옵션 — 그림자 포트폴리오 (초기 ${INITIAL:.0f} / "
          f"거래 {len(trades)}건)")
    print("=" * 100)
    print("  ** 수익률로 고르지 말 것 — 시간 분할마다 뒤집힌다.")
    print("     단조 축은 포착률 / MDD / 최악 단일거래 셋뿐이다. **")
    print("-" * 100)
    print(f"  {'설정':<14}{'포착%':>8}{'MDD%':>9}{'최악$':>9}{'동시':>6}"
          f"{'평균증거금$':>12}{'잡음':>6}{'놓침':>6}{'최종$':>10}{'수익%':>9}")
    print("-" * 100)
    for name, r in res.items():
        if not r:
            continue
        print(f"  {name:<14}{r['capture_pct']:>8.1f}{r['mdd_pct']:>9.1f}{r['worst']:>9.0f}"
              f"{r['max_conc']:>6}{r['avg_margin']:>12.1f}{r['n_taken']:>6}"
              f"{r['n_starved']:>6}{r['final']:>10,.0f}{r['ret_pct']:>+9.1f}"
              + (f"  **파산 {r['blown_at']}**" if r["blown_at"] else ""))
    print("=" * 100 + "\n")

    os.makedirs(OUT, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    with open(OUT / f"{stamp}.json", "w") as fh:
        json.dump({"generated": datetime.now().isoformat(timespec="seconds"),
                   "initial": INITIAL, "n_trades": len(trades), "variants": res},
                  fh, ensure_ascii=False, indent=2)
    with open(OUT / "latest.json", "w") as fh:
        json.dump({"generated": datetime.now().isoformat(timespec="seconds"),
                   "initial": INITIAL, "n_trades": len(trades), "variants": res},
                  fh, ensure_ascii=False, indent=2)
    log.info("저장: %s", OUT / "latest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
