"""그룹 C 가설 3 — **그리드 마틴게일** (바이낸스 단일 종목).

왜 이 형태인가
  가설 1 의 단일종목 검정은 마틴게일의 실제 형태가 아니었다. z-score 로 진입해
  "잔차가 0 을 통과하면" 청산했는데, 그 잔차의 기준선(이동중앙값)이 가격을
  쫓아가므로 허상이 생긴다.

  실제 마틴게일 파생은 **고정된 가격 간격**으로 물타고, **각 물량마다 그
  진입가 대비 일정 폭 위**에서 익절한다. 이동평균을 참조하지 않는다.
  그게 그리드이고, 커뮤니티에서 "마틴게일 파생" 이라 하면 사실상 이걸 말한다.
  거래소도 기본 봇으로 제공한다. **바이낸스 안에서, 한 종목으로 된다.**

구조
  · 진입: 직전 체결가에서 g bp 떨어질 때마다 한 계단 매수
  · 익절: 각 계단은 **자기 진입가 + g bp** 에서 개별 청산
  · 계단 크기: 고정 1,1,1,1… / 산술 1,2,3,4… / 기하 1,2,4,8… (마틴게일 정도)
  · 자본 한도를 넘으면 그 자리에서 전량 손절 (파산 계상)

무엇을 묻는가
  그리드에는 **신호가 없다.** 손익은 가격 경로가 전부 결정한다. 따라서 질문은
  하나로 압축된다:
      **진동에서 걷는 수확이 추세에서 잃는 것과 마찰을 넘는가.**

무엇을 조심하는가
  · **파산을 반드시 계상한다.** 한도 없이 물타면 백테스트가 항상 이긴다.
    그게 마틴게일의 거짓말이다.
  · 마찰은 체결마다 물린다. 그리드는 지정가이므로 **메이커 2bp**를 기본으로
    쓰되, 익절 지정가가 안 채워져 시장가로 나가는 경우를 위해 taker 옵션도 둔다.
  · **고정 크기 대조군 필수.** 사다리가 이기면 그게 사다리 덕인지 그냥 그
    구간이 좋았던 건지 갈라야 한다.
  · 종목별로 따로 돌리고 **양수 종목 비율**을 본다. 한두 종목이 전부면 전략이
    아니라 사건이다 (2026-08-11 가설 2 에서 겪음).
  · 상위 거래 절삭 검정을 같이 낸다 (교훈 #81).

사용:
  python3 scripts/research/grid_martingale_scan.py --days 60
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("grid_mart")

GRIDS_BP = (30, 60, 120, 250)       # 계단 간격
MAX_RUNGS = 8
LADDERS = {"고정": [1] * MAX_RUNGS,
           "산술": list(range(1, MAX_RUNGS + 1)),
           "기하": [2 ** i for i in range(MAX_RUNGS)]}
CAP_MULT = (5, 20, 100)             # 자본 한도 = 1계단 명목의 몇 배
FEE_MAKER, FEE_TAKER = 2.0, 5.0


def run_grid(px: np.ndarray, g_bp: float, weights, cap_units: float,
             fee_in: float, fee_out: float):
    """그리드 한 벌. 반환 (총손익 bp·단위, 체결수, 최대미실현손실, 파산여부)"""
    g = g_bp / 1e4
    lots = []            # [(진입가, 단위수)]
    total, fills, worst, ruin = 0.0, 0, 0.0, False
    units = 0.0
    last_entry = px[0]
    lots.append((px[0], weights[0]))
    units = weights[0]
    total -= fee_in * weights[0]
    fills += 1
    for p in px[1:]:
        # 익절 — 각 계단 개별
        keep = []
        for e, w in lots:
            if p >= e * (1 + g):
                total += w * ((p / e - 1.0) * 1e4) - fee_out * w
                units -= w
                fills += 1
            else:
                keep.append((e, w))
        lots = keep
        # 미실현
        unreal = sum(w * (p / e - 1.0) * 1e4 for e, w in lots)
        worst = min(worst, unreal)
        if unreal <= -cap_units:
            total += unreal - fee_out * units
            fills += len(lots)
            lots, units, ruin = [], 0.0, True
            break
        # 추가 진입 — 직전 진입가에서 g 만큼 더 떨어졌을 때
        if lots:
            lowest = min(e for e, _ in lots)
            if p <= lowest * (1 - g) and len(lots) < len(weights):
                w = weights[len(lots)]
                lots.append((p, w))
                units += w
                total -= fee_in * w
                fills += 1
        elif p <= last_entry * (1 - g) or p >= last_entry * (1 + g):
            lots.append((p, weights[0]))
            units = weights[0]
            total -= fee_in * weights[0]
            fills += 1
            last_entry = p
    if lots:                                   # 기간 종료 — 시장가 청산
        p = px[-1]
        total += sum(w * ((p / e - 1.0) * 1e4) - fee_out * w for e, w in lots)
    return total, fills, worst, ruin


def main() -> int:
    p = argparse.ArgumentParser(description="그리드 마틴게일")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=20_000_000)
    p.add_argument("--limit", type=int, default=300)
    p.add_argument("--taker-exit", action="store_true", help="익절도 시장가로 가정")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "grid_martingale_scan.json"))
    args = p.parse_args()

    fee_in = FEE_MAKER
    fee_out = FEE_TAKER if args.taker_exit else FEE_MAKER

    prices = {}
    for f in sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))[:args.limit]:
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        try:
            d = joblib.load(f)
        except Exception:
            continue
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d = d.loc[d.index >= d.index.max() - pd.Timedelta(days=args.days)]
        if len(d) < 20000:
            continue
        if d["quote_volume"].resample("1D").sum().median() < args.min_dvol_usd:
            continue
        prices[sym] = d["px_open"].astype(float).values
    log.info("대상 %d종목 / 진입 %.0fbp + 청산 %.0fbp", len(prices), fee_in, fee_out)
    if len(prices) < 20:
        log.error("종목 부족")
        return 1

    res, detail = [], []
    for g in GRIDS_BP:
        for lab, w in LADDERS.items():
            for cap in CAP_MULT:
                cap_units = cap * g              # 자본 한도 (bp x 단위)
                tots, ruins, fl = [], 0, []
                for sym, px in prices.items():
                    t, n, worst, ru = run_grid(px, g, w, cap_units, fee_in, fee_out)
                    tots.append(t)
                    fl.append(n)
                    ruins += int(ru)
                    detail.append({"grid": g, "ladder": lab, "cap": cap,
                                   "sym": sym, "pnl": t})
                a = np.array(tots)
                se = a.std(ddof=1) / np.sqrt(len(a))
                res.append({"grid_bp": g, "ladder": lab, "cap_mult": cap,
                            "n_sym": len(a), "mean_bp": float(a.mean()),
                            "se_bp": float(se),
                            "t": float(a.mean() / se) if se else np.nan,
                            "pos_pct": float(100 * (a > 0).mean()),
                            "worst": float(a.min()), "best": float(a.max()),
                            "ruin_pct": float(100 * ruins / len(a)),
                            "fills": float(np.mean(fl))})

    df = pd.DataFrame(res)
    D = pd.DataFrame(detail)
    print("\n" + "=" * 108)
    print(f"그룹 C 가설 3 — 그리드 마틴게일  ({len(prices)}종목 / 최근 {args.days}일 / "
          f"종목당 총손익 bp)")
    print("=" * 108)
    print(f"  진입 지정가 {fee_in:.0f}bp / 청산 {fee_out:.0f}bp / 최대 {MAX_RUNGS}계단")
    print("  ** 그리드에는 신호가 없다. 질문은 하나 — 진동 수확이 추세 손실 + 마찰을 넘는가 **")
    print("-" * 108)
    print(f"{'간격bp':>7}{'사다리':<8}{'자본배수':>9}{'평균bp':>11}{'오차':>9}{'t':>8}"
          f"{'양수종목%':>10}{'최악':>11}{'최고':>11}{'파산%':>8}{'체결':>8}")
    print("-" * 108)
    for _, r in df.sort_values(["grid_bp", "ladder", "cap_mult"]).iterrows():
        print(f"{r.grid_bp:>7.0f}{r.ladder:<8}{r.cap_mult:>9.0f}{r.mean_bp:>+11.1f}"
              f"{r.se_bp:>9.1f}{r.t:>+8.2f}{r.pos_pct:>10.1f}{r.worst:>+11.0f}"
              f"{r.best:>+11.0f}{r.ruin_pct:>8.1f}{r.fills:>8.0f}")
    print("-" * 108)
    npass = int(((df.mean_bp > 0) & (df.t >= 3.0)).sum())
    print(f"  평균>0 & t>=3.0 : {npass}/{len(df)}")
    b = df.sort_values("mean_bp", ascending=False).iloc[0]
    c = df[df.ladder == "고정"].sort_values("mean_bp", ascending=False).iloc[0]
    print(f"  최고: 간격 {b.grid_bp:.0f}bp / {b.ladder} / 자본 {b.cap_mult:.0f}배 → "
          f"{b.mean_bp:+.1f}bp (t {b.t:+.2f}, 양수종목 {b.pos_pct:.1f}%, 파산 {b.ruin_pct:.1f}%)")
    print(f"  대조군(고정) 최고: 간격 {c.grid_bp:.0f}bp / 자본 {c.cap_mult:.0f}배 → {c.mean_bp:+.1f}bp")
    print(f"  **사다리가 대조군을 이겼나: "
          f"{'예' if b.mean_bp > c.mean_bp and b.ladder != '고정' else '아니오'}**")
    # 최고 조합 상위 절삭
    key = D[(D.grid == b.grid_bp) & (D.ladder == b.ladder) & (D.cap == b.cap_mult)]
    print("-" * 108)
    print("  최고 조합의 상위 종목 절삭 (교훈 #81)")
    for k in (1, 3, 5):
        t = key.drop(key.nlargest(k, "pnl").index)
        se = t.pnl.std(ddof=1) / np.sqrt(len(t))
        print(f"     상위 {k}종목 제외 → 평균 {t.pnl.mean():+9.1f}bp  t {t.pnl.mean()/se:+6.2f}")
    print("=" * 108 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": len(prices), "fee_in": fee_in, "fee_out": fee_out,
                   "results": res}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
