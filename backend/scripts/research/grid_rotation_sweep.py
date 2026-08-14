"""그룹 C 가설 6 — **바구니 익절 + 저진폭 선택 회전 그리드** (고원 탐색).

배경
  가설 5 에서 32칸 중 **한 칸만** 양수였다:
      저진폭 선택 + 계단상한 3 + 기하 → 118사이클 x +13.1bp = +1,550bp
  32칸 중 1칸 양수는 우연으로도 나온다. 그래서 이 스캔은 **그 칸을 더 좋게
  만드는** 것이 아니라 **그 칸이 진짜인지** 를 본다.

      진짜 효과는 **고원**을 만들고, 잡음은 **뾰족한 봉우리**를 만든다.

  주변 파라미터가 같이 양수면 신호이고, 그 칸만 튀면 잡음이다.

두 가지 설계 변경 (대표님 지적, 2026-08-11)
  ① **바구니 익절** — 지금은 각 계단이 개별로 +g 에 닿아야 닫힌다. 대신 **바구니
     전체 손익이 마찰의 M 배를 넘으면 통째로 닫고 회전**한다. 그러면 이미 마찰
     이상을 벌었을 때만 마찰을 낸다. 가설 5 손실의 3분의 2가 순수 마찰이었다.
  ② **점수 분해** — 지금까지 `진폭 x (1-효율비)` 를 묶어 썼다. 둘 중 무엇이
     일하는지 갈라야 한다. 진폭만 / 효율비만 / 곱 을 각각 돌린다.

무엇을 조심하는가
  · **사이클별 손익을 기록해 t 를 낸다.** 총합만 보면 판정 못 한다 (가설 5 오류).
  · 대조군(무작위·고진폭)을 모든 칸에서 같이 돌린다.
  · 고원 판정: 최고 칸 **주변 8칸의 부호 일치율**을 같이 낸다.
  · 점수는 직전 창 정보로만 산출 (lookahead 없음).

사용:
  python3 scripts/research/grid_rotation_sweep.py --days 60
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
log = logging.getLogger("grid_sweep")

FEE = 2.0
LOOKBACK = 1440
MAX_HOLD = 720
CAP_UNITS_MULT = 100
SCORE_EVERY = 30          # 점수 재계산 간격(분) — 사전 계산용


def amp_er(px: np.ndarray):
    r = np.diff(np.log(px))
    path = np.abs(r).sum()
    if path <= 0 or len(r) < 30:
        return np.nan, np.nan
    er = abs(np.log(px[-1] / px[0])) / path
    amp = float(np.std(r) * np.sqrt(len(r)) * 1e4)
    return amp, er


def cycle(px, start, g_bp, max_rungs, weights, tp_mult):
    """한 사이클.

    tp_mult > 0 이면 **바구니 익절** — 실현+미실현 합이 (마찰 x 단위 x tp_mult)
    를 넘으면 통째로 닫는다. 0 이면 계단별 개별 익절만 쓴다.
    """
    g = g_bp / 1e4
    cap = CAP_UNITS_MULT * g_bp
    lots = [(px[start], weights[0])]
    realized = -FEE * weights[0]
    units = weights[0]
    i, n = start + 1, len(px)
    while i < n and (i - start) <= MAX_HOLD:
        p = px[i]
        keep = []
        for e, w in lots:
            if p >= e * (1 + g):
                realized += w * ((p / e - 1.0) * 1e4) - FEE * w
                units -= w
            else:
                keep.append((e, w))
        lots = keep
        if not lots:
            return realized, i, "완료"
        unreal = sum(w * (p / e - 1.0) * 1e4 for e, w in lots)
        # 바구니 익절 — 마찰 이상을 이미 벌었을 때만 마찰을 낸다
        if tp_mult > 0:
            open_u = sum(w for _, w in lots)
            if realized + unreal >= FEE * open_u * tp_mult:
                return realized + unreal - FEE * open_u, i, "바구니익절"
        if unreal <= -cap:
            return realized + unreal - FEE * sum(w for _, w in lots), i, "파산"
        lo = min(e for e, _ in lots)
        if p <= lo * (1 - g):
            if len(lots) >= max_rungs:
                return realized + unreal - FEE * sum(w for _, w in lots), i, "계단상한"
            w = weights[min(len(lots), len(weights) - 1)]
            lots.append((p, w))
            units += w
            realized -= FEE * w
        i += 1
    p = px[min(i, n - 1)]
    unreal = sum(w * (p / e - 1.0) * 1e4 for e, w in lots)
    return realized + unreal - FEE * sum(w for _, w in lots), min(i, n - 1), "시간초과"


def main() -> int:
    p = argparse.ArgumentParser(description="회전 그리드 고원 탐색")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=20_000_000)
    p.add_argument("--limit", type=int, default=300)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "grid_rotation_sweep.json"))
    args = p.parse_args()

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
        prices[sym] = d["px_open"].astype(float)
    idx = None
    for s in prices.values():
        idx = s.index if idx is None else idx.intersection(s.index)
    M = pd.DataFrame({k: v.reindex(idx) for k, v in prices.items()}).ffill().dropna(axis=1)
    A = M.values
    syms = list(M.columns)
    T = len(M)
    log.info("%d종목 x %d분", len(syms), T)

    # ── 점수 사전 계산 (30분 격자) ─────────────────────────────────
    grid_t = np.arange(LOOKBACK, T - 10, SCORE_EVERY)
    AMP = np.full((len(grid_t), len(syms)), np.nan)
    ER = np.full((len(grid_t), len(syms)), np.nan)
    for gi, t in enumerate(grid_t):
        seg = A[t - LOOKBACK:t]
        for j in range(len(syms)):
            a, e = amp_er(seg[:, j])
            AMP[gi, j], ER[gi, j] = a, e
    log.info("점수 격자 %d개 완료", len(grid_t))

    SCORES = {"저진폭": lambda gi: AMP[gi],
              "저효율비": lambda gi: ER[gi],
              "저(진폭x비추세)": lambda gi: AMP[gi] * (1 - ER[gi]),
              "고진폭(대조)": lambda gi: -AMP[gi]}

    def pick(gi, mode, rng):
        if mode == "무작위(대조)":
            ok = np.flatnonzero(np.isfinite(AMP[gi]))
            return int(rng.choice(ok)) if len(ok) else None
        v = SCORES[mode](gi)
        ok = np.flatnonzero(np.isfinite(v))
        return int(ok[np.argmin(v[ok])]) if len(ok) else None

    rng = np.random.default_rng(20260811)
    res = []
    modes = list(SCORES) + ["무작위(대조)"]
    for g_bp in (60, 120, 250):
        for max_rungs in (2, 3, 4):
            for tp_mult in (0, 1, 2, 4):
                for mode in modes:
                    pn = []
                    reasons = {}
                    i = LOOKBACK
                    W = [2 ** k for k in range(8)]
                    while i < T - 10:
                        gi = min(int((i - LOOKBACK) // SCORE_EVERY), len(grid_t) - 1)
                        j = pick(gi, mode, rng)
                        if j is None:
                            i += SCORE_EVERY
                            continue
                        v, end, why = cycle(A[:, j], i, g_bp, max_rungs, W, tp_mult)
                        pn.append(v)
                        reasons[why] = reasons.get(why, 0) + 1
                        i = end + 1
                    if len(pn) < 60:
                        continue
                    a = np.array(pn)
                    se = a.std(ddof=1) / np.sqrt(len(a))
                    res.append({"grid_bp": g_bp, "max_rungs": max_rungs,
                                "tp_mult": tp_mult, "mode": mode, "n": len(a),
                                "total": float(a.sum()), "mean": float(a.mean()),
                                "se": float(se),
                                "t": float(a.mean() / se) if se else np.nan,
                                "win": float(100 * (a > 0).mean()),
                                "ruin_pct": float(100 * reasons.get("파산", 0) / len(a)),
                                "reasons": reasons})

    D = pd.DataFrame(res)
    print("\n" + "=" * 104)
    print(f"그룹 C 가설 6 — 바구니 익절 x 저진폭 선택 ({len(syms)}종목 / {args.days}일)")
    print("=" * 104)
    print("  tp_mult = 바구니 손익이 마찰의 몇 배를 넘으면 통째로 닫는가 (0 = 계단별 개별 익절)")
    print("-" * 104)
    top = D.sort_values("t", ascending=False).head(14)
    print(f"{'간격':>5}{'계단':>5}{'익절x':>6}{'선택':<16}{'사이클':>8}{'평균bp':>10}"
          f"{'오차':>8}{'t':>8}{'승률%':>8}{'파산%':>7}{'총계':>11}")
    print("-" * 104)
    for _, r in top.iterrows():
        print(f"{r.grid_bp:>5.0f}{r.max_rungs:>5.0f}{r.tp_mult:>6.0f}{r['mode']:<16}"
              f"{r.n:>8,.0f}{r['mean']:>+10.1f}{r.se:>8.1f}{r.t:>+8.2f}{r.win:>8.1f}"
              f"{r.ruin_pct:>7.1f}{r.total:>+11,.0f}")
    print("-" * 104)
    npass = int(((D["mean"] > 0) & (D.t >= 3.0)).sum())
    print(f"  평균>0 & t>=3.0 : {npass}/{len(D)}   (양수 칸 {int((D['mean']>0).sum())}/{len(D)})")

    # ── 고원 판정 — 최고 칸 주변의 부호 일치 ────────────────────────
    b = D.sort_values("t", ascending=False).iloc[0]
    nb = D[(D["mode"] == b["mode"]) &
           (D.grid_bp.isin([x for x in (60, 120, 250)])) &
           (abs(D.max_rungs - b.max_rungs) <= 1)]
    print("-" * 104)
    print(f"  최고 칸: 간격{b.grid_bp:.0f} / 계단{b.max_rungs:.0f} / 익절x{b.tp_mult:.0f} / "
          f"{b['mode']} → {b['mean']:+.1f}bp (t {b.t:+.2f})")
    print(f"  **고원 판정** — 같은 선택기·인접 계단 {len(nb)}칸 중 양수 "
          f"{int((nb['mean']>0).sum())}칸 ({100*(nb['mean']>0).mean():.0f}%)")
    for _, r in nb.sort_values(["grid_bp", "max_rungs", "tp_mult"]).iterrows():
        print(f"     간격{r.grid_bp:>4.0f} 계단{r.max_rungs:.0f} 익절x{r.tp_mult:.0f} → "
              f"{r['mean']:>+8.1f}bp (t {r.t:>+5.2f}, n {r.n:>5,.0f})")
    print("=" * 104 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": len(syms), "results": res}, fh,
                  indent=2, ensure_ascii=False, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
