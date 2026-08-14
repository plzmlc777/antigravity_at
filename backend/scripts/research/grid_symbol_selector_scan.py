"""그룹 C 가설 4 — **그리드 동적 종목 선택**.

착상 (대표님 지적, 2026-08-11)
  "한 종목에서 계속 마틴게일을 할 필요는 없다. 수많은 종목 중 그 시점에 가장
  마틴게일에 적당한 종목을 동적으로 골라서 하면 되지 않나."

  옳다. **그리드에는 신호가 없다.** 손익은 가격 경로가 전부 결정한다. 그러면
  신호가 있어야 할 자리는 매매 규칙이 아니라 **종목 선택**이다.

그리드에 맞는 종목의 정의
  많이 흔들리되 어디로도 가지 않는 종목. 표준 지표가 효율비다.
      ER = |구간 순이동| / Σ|봉별 이동|
      ER → 1 : 순수 추세 (그리드 사망)
      ER → 0 : 순수 진동 (그리드 천국)
  진폭도 필요하다 — 안 움직이면 계단을 못 넘는다. 그래서 두 축을 같이 본다:
      점수 = 진폭(실현변동성) x (1 - ER)

결정적 질문 — 지속되는가
  지난 창에서 진동한 종목이 **다음 창에도** 진동하지 않으면 선택기는 무용지물이다.
  따라서 먼저 **비겹침 창**으로 지속성을 잰다.
  (2026-08-10 교훈: 겹치는 창만으로 상관 +0.470 이 조작됐고 비겹침에서 +0.001
   이었다. 여기서는 그 실수를 반복하지 않는다.)

검정 설계
  · 창을 비겹치게 자른다. 창 t 의 점수로 종목을 고르고 창 t+1 에서 성과를 잰다.
  · **대조군 둘을 반드시 같이 돌린다.**
        무작위 K종목        — 선택기가 정말 일하는지
        하위 K종목(역선택)  — 점수가 방향을 갖는지 (하위가 더 나빠야 한다)
  · 계좌는 **하나**로 본다. 종목별로 새 자본을 주면 현실보다 후해진다
    (가설 3 에서 저지른 오류). 슬리브가 파산하면 그 자본은 사라진다.
  · 파산률과 최종 자산을 같이 낸다. 평균 수익만 보면 안 된다.

사용:
  python3 scripts/research/grid_symbol_selector_scan.py --days 60 --win-days 7
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
log = logging.getLogger("grid_selector")

FEE = 2.0
GRID_BP = 120.0
MAX_RUNGS = 8
LADDER = [2 ** i for i in range(MAX_RUNGS)]     # 기하 (가설 3 최고 조합)
LADDER_FLAT = [1] * MAX_RUNGS
CAP_MULT = 100                                   # 자본 한도 = 간격 x 배수


def run_grid(px: np.ndarray, g_bp: float, weights, cap_units: float):
    """가설 3 과 동일 엔진. 반환 (손익 bp·단위, 파산여부)"""
    g = g_bp / 1e4
    lots = [(px[0], weights[0])]
    total = -FEE * weights[0]
    last_entry = px[0]
    for p in px[1:]:
        keep = []
        for e, w in lots:
            if p >= e * (1 + g):
                total += w * ((p / e - 1.0) * 1e4) - FEE * w
            else:
                keep.append((e, w))
        lots = keep
        unreal = sum(w * (p / e - 1.0) * 1e4 for e, w in lots)
        if unreal <= -cap_units:
            total += unreal - FEE * sum(w for _, w in lots)
            return total, True
        if lots:
            lo = min(e for e, _ in lots)
            if p <= lo * (1 - g) and len(lots) < len(weights):
                w = weights[len(lots)]
                lots.append((p, w))
                total -= FEE * w
        elif p <= last_entry * (1 - g) or p >= last_entry * (1 + g):
            lots = [(p, weights[0])]
            total -= FEE * weights[0]
            last_entry = p
    if lots:
        p = px[-1]
        total += sum(w * ((p / e - 1.0) * 1e4) - FEE * w for e, w in lots)
    return total, False


def score(px: np.ndarray) -> float:
    """진폭 x (1 - 효율비). 클수록 그리드에 적합."""
    if len(px) < 100:
        return np.nan
    r = np.diff(np.log(px))
    path = np.abs(r).sum()
    net = abs(np.log(px[-1] / px[0]))
    if path <= 0:
        return np.nan
    er = net / path
    amp = float(np.std(r) * np.sqrt(len(r)) * 1e4)   # 구간 실현변동 (bp)
    return amp * (1.0 - er)


def main() -> int:
    p = argparse.ArgumentParser(description="그리드 동적 종목 선택")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--win-days", type=int, default=7)
    p.add_argument("--topk", type=int, default=10)
    p.add_argument("--min-dvol-usd", type=float, default=20_000_000)
    p.add_argument("--limit", type=int, default=300)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "grid_symbol_selector.json"))
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
    log.info("대상 %d종목", len(prices))
    if len(prices) < 30:
        log.error("종목 부족")
        return 1

    # ── 비겹침 창으로 자른다 ────────────────────────────────────────
    t0 = max(s.index.min() for s in prices.values())
    t1 = min(s.index.max() for s in prices.values())
    W = pd.Timedelta(days=args.win_days)
    edges = []
    c = t0
    while c + W <= t1:
        edges.append((c, c + W))
        c += W
    log.info("비겹침 창 %d개 (%d일씩) %s ~ %s", len(edges), args.win_days, t0, t1)
    if len(edges) < 4:
        log.error("창 부족")
        return 1

    S = {}    # 창별 종목 점수
    R = {}    # 창별 종목 그리드 성과 (기하 / 고정)
    for wi, (a, b) in enumerate(edges):
        S[wi], R[wi] = {}, {}
        for sym, s in prices.items():
            seg = s.loc[a:b].values
            if len(seg) < 5000:
                continue
            S[wi][sym] = score(seg)
            g_pnl, g_ru = run_grid(seg, GRID_BP, LADDER, CAP_MULT * GRID_BP)
            f_pnl, f_ru = run_grid(seg, GRID_BP, LADDER_FLAT, CAP_MULT * GRID_BP)
            R[wi][sym] = {"geo": (g_pnl, g_ru), "flat": (f_pnl, f_ru)}

    # ── ① 점수 지속성 (비겹침) ──────────────────────────────────────
    per = []
    for wi in range(len(edges) - 1):
        a = pd.Series(S[wi]).dropna()
        b = pd.Series(S[wi + 1]).dropna()
        common = a.index.intersection(b.index)
        if len(common) < 20:
            continue
        per.append({"win": wi, "n": len(common),
                    "rho": float(a[common].rank().corr(b[common].rank()))})
    print("\n" + "=" * 96)
    print(f"그룹 C 가설 4 — 그리드 동적 종목 선택  ({len(prices)}종목 / "
          f"비겹침 {args.win_days}일 창 {len(edges)}개)")
    print("=" * 96)
    print("① 점수 지속성 — 이번 창에서 진동한 종목이 **다음 창에도** 진동하는가")
    print(f"   {'창':>4}{'종목':>7}{'순위상관 ρ':>12}")
    for r in per:
        print(f"   {r['win']:>4}{r['n']:>7}{r['rho']:>+12.3f}")
    rho_m = float(np.mean([r["rho"] for r in per])) if per else np.nan
    print(f"   **평균 ρ = {rho_m:+.3f}**   (0 이면 선택기 무용, 겹침 없음)")
    print("-" * 96)

    # ── ② 선택 vs 무작위 vs 역선택 ─────────────────────────────────
    rng = np.random.default_rng(20260811)
    out = []
    for mode in ("geo", "flat"):
        rows = {"상위 선택": [], "무작위": [], "하위(역선택)": []}
        ruins = {k: 0 for k in rows}
        cnt = {k: 0 for k in rows}
        for wi in range(len(edges) - 1):
            sc = pd.Series(S[wi]).dropna()
            nxt = R[wi + 1]
            cand = [x for x in sc.index if x in nxt]
            if len(cand) < args.topk * 3:
                continue
            sc = sc[cand].sort_values(ascending=False)
            picks = {"상위 선택": list(sc.index[:args.topk]),
                     "하위(역선택)": list(sc.index[-args.topk:]),
                     "무작위": list(rng.choice(cand, size=args.topk, replace=False))}
            for k, syms in picks.items():
                for sm in syms:
                    pnl, ru = nxt[sm][mode]
                    rows[k].append(pnl)
                    ruins[k] += int(ru)
                    cnt[k] += 1
        for k, v in rows.items():
            if len(v) < 30:
                continue
            a = np.array(v)
            se = a.std(ddof=1) / np.sqrt(len(a))
            out.append({"ladder": mode, "group": k, "n": len(a),
                        "mean_bp": float(a.mean()), "se_bp": float(se),
                        "t": float(a.mean() / se) if se else np.nan,
                        "pos_pct": float(100 * (a > 0).mean()),
                        "ruin_pct": float(100 * ruins[k] / max(cnt[k], 1)),
                        "worst": float(a.min())})

    D = pd.DataFrame(out)
    print("② 선택기가 일하는가 — 다음 창 성과 (창 t 점수로 골라 창 t+1 에서 운용)")
    print(f"   {'사다리':<6}{'집단':<16}{'표본':>7}{'평균bp':>11}{'오차':>9}{'t':>8}"
          f"{'양수%':>8}{'파산%':>8}{'최악':>10}")
    print("   " + "-" * 90)
    for _, r in D.iterrows():
        print(f"   {r.ladder:<6}{r.group:<16}{r.n:>7,.0f}{r.mean_bp:>+11.1f}{r.se_bp:>9.1f}"
              f"{r.t:>+8.2f}{r.pos_pct:>8.1f}{r.ruin_pct:>8.1f}{r.worst:>+10.0f}")
    print("-" * 96)
    for mode in ("geo", "flat"):
        sub = D[D.ladder == mode]
        if len(sub) < 3:
            continue
        top = sub[sub.group == "상위 선택"].iloc[0]
        rnd = sub[sub.group == "무작위"].iloc[0]
        bot = sub[sub.group == "하위(역선택)"].iloc[0]
        gap = top.mean_bp - rnd.mean_bp
        gse = float(np.hypot(top.se_bp, rnd.se_bp))
        print(f"  [{mode}] 상위 - 무작위 = {gap:+.1f}bp (t {gap/gse:+.2f})   "
              f"상위 {top.mean_bp:+.0f} / 무작위 {rnd.mean_bp:+.0f} / 하위 {bot.mean_bp:+.0f}")
        print(f"        방향 일치(상위>무작위>하위): "
              f"{'예' if top.mean_bp > rnd.mean_bp > bot.mean_bp else '아니오'}")
    print("=" * 96 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": len(prices), "n_windows": len(edges),
                   "persistence": per, "rho_mean": rho_m, "results": out},
                  fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
