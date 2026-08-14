"""그룹 C 가설 5 — **사이클 단위 종목 회전 그리드**.

착상 (대표님 지적, 2026-08-11)
  "7일간 한 종목을 유지할 필요도 없다. 극단적으로 한 거래만 하고 바로 다시
  최적화된 종목을 찾아 변경하고, 이걸 반복하는 방향으로 갈 수 있지 않나."

  이 발상은 **파산 메커니즘을 정면으로 친다.** 그리드가 죽는 경로는 하나다 —
  계단이 쌓인 채 가격이 계속 가는 것. 한 사이클이 끝나면 바로 갈아타면
  계단이 쌓일 시간 자체가 없다.

  가설 4 실측이 그 필요성을 보여줬다:
      기하 사다리 x 고진폭 선택 → **파산률 97.1%**
      고정 사다리 x 저진폭 선택 → 파산률 2.9%
  파산률이 성과를 지배한다. 회전은 그 축을 직접 건드린다.

먼저 확인할 것 — 짧은 창에서도 점수가 지속되는가
  7일 비겹침 창에서 순위상관 ρ +0.886 이었다. 회전을 빠르게 하려면 **짧은
  창에서도** 지속돼야 한다. 1h/4h/12h/24h 를 전부 비겹침으로 잰다.
  (2026-08-10 교훈: 겹치는 창은 상관을 조작한다. 여기서도 비겹침만 쓴다.)

설계
  · 계좌는 **항상 한 종목만** 보유한다. 종목별 새 자본을 주지 않는다.
  · 이탈 조건 셋 — 사이클 완료(전량 익절) / 계단 상한 도달 / 시간 초과
  · 이탈 즉시 그 시점 점수로 **다시 고른다** (직전 창 정보만 사용, lookahead 없음)
  · 대조군: **무작위 회전** — 회전 자체가 좋은 건지 선택이 좋은 건지 가른다
  · 대조군: **회전 없음** — 한 종목 붙박이

  점수는 가설 4 에서 **부호가 뒤집힌 것**이 확인됐다(고진폭이 나빴다). 그래서
  여기서는 저진폭·저추세 쪽을 상위로 두고, 반대 방향도 같이 돌려 확인한다.

사용:
  python3 scripts/research/grid_rotation_scan.py --days 60
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
log = logging.getLogger("grid_rotation")

FEE = 2.0
GRID_BP = 120.0
CAP_UNITS = 100 * GRID_BP        # 자본 한도 (bp x 단위)
LOOKBACK_MIN = 1440              # 점수 산출 창 (분)
MAX_HOLD_MIN = 720               # 사이클 시간 상한


def score(px: np.ndarray) -> float:
    """진폭 x (1 - 효율비). 가설 4 에서 **높을수록 나빴다** — 부호 해석 주의."""
    if len(px) < 60:
        return np.nan
    r = np.diff(np.log(px))
    path = np.abs(r).sum()
    if path <= 0:
        return np.nan
    er = abs(np.log(px[-1] / px[0])) / path
    amp = float(np.std(r) * np.sqrt(len(r)) * 1e4)
    return amp * (1.0 - er)


def cycle(px: np.ndarray, start: int, max_rungs: int, weights):
    """한 사이클. 반환 (손익 bp·단위, 끝난 인덱스, 사유)"""
    g = GRID_BP / 1e4
    lots = [(px[start], weights[0])]
    total = -FEE * weights[0]
    i = start + 1
    n = len(px)
    while i < n and (i - start) <= MAX_HOLD_MIN:
        p = px[i]
        keep = []
        for e, w in lots:
            if p >= e * (1 + g):
                total += w * ((p / e - 1.0) * 1e4) - FEE * w
            else:
                keep.append((e, w))
        lots = keep
        if not lots:
            return total, i, "완료"                 # 전량 익절 → 회전
        unreal = sum(w * (p / e - 1.0) * 1e4 for e, w in lots)
        if unreal <= -CAP_UNITS:
            total += unreal - FEE * sum(w for _, w in lots)
            return total, i, "파산"
        lo = min(e for e, _ in lots)
        if p <= lo * (1 - g):
            if len(lots) >= max_rungs:              # 계단 상한 → 잘라내고 회전
                total += unreal - FEE * sum(w for _, w in lots)
                return total, i, "계단상한"
            w = weights[min(len(lots), len(weights) - 1)]
            lots.append((p, w))
            total -= FEE * w
        i += 1
    p = px[min(i, n - 1)]
    total += sum(w * ((p / e - 1.0) * 1e4) - FEE * w for e, w in lots)
    return total, min(i, n - 1), "시간초과"


def main() -> int:
    p = argparse.ArgumentParser(description="사이클 단위 종목 회전 그리드")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=20_000_000)
    p.add_argument("--limit", type=int, default=300)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "grid_rotation_scan.json"))
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
    if len(prices) < 20:
        return 1

    # 공통 시간축
    idx = None
    for s in prices.values():
        idx = s.index if idx is None else idx.intersection(s.index)
    M = pd.DataFrame({k: v.reindex(idx) for k, v in prices.items()}).ffill().dropna(axis=1)
    syms = list(M.columns)
    A = M.values                       # (시간, 종목)
    log.info("공통 격자 %d분 x %d종목", len(M), len(syms))

    # ── ① 짧은 창 지속성 (비겹침) ──────────────────────────────────
    print("\n" + "=" * 96)
    print(f"그룹 C 가설 5 — 사이클 회전 그리드  ({len(syms)}종목 / {len(M):,}분)")
    print("=" * 96)
    print("① 점수 지속성 — 창 길이별 (전부 비겹침)")
    print(f"   {'창':>8}{'창 개수':>9}{'평균 ρ':>10}")
    pers = {}
    for wmin in (60, 240, 720, 1440, 10080):
        rs = []
        k = 0
        while (k + 2) * wmin <= len(A):
            a = np.array([score(A[k * wmin:(k + 1) * wmin, j]) for j in range(len(syms))])
            b = np.array([score(A[(k + 1) * wmin:(k + 2) * wmin, j]) for j in range(len(syms))])
            ok = np.isfinite(a) & np.isfinite(b)
            if ok.sum() >= 15:
                rs.append(float(pd.Series(a[ok]).rank().corr(pd.Series(b[ok]).rank())))
            k += 2
        if rs:
            pers[wmin] = float(np.mean(rs))
            lab = f"{wmin//60}시간" if wmin < 1440 else f"{wmin//1440}일"
            print(f"   {lab:>8}{len(rs):>9}{np.mean(rs):>+10.3f}")
    print("-" * 96)

    # ── ② 회전 시뮬레이션 ──────────────────────────────────────────
    rng = np.random.default_rng(20260811)
    res = []
    for max_rungs in (1, 2, 3, 4):
        for lab_lad, weights in (("고정", [1] * 8), ("기하", [2 ** i for i in range(8)])):
            for mode in ("저진폭 선택", "고진폭 선택", "무작위", "회전없음"):
                total, cyc, ruin, reasons = 0.0, 0, 0, {}
                i = LOOKBACK_MIN
                fixed = rng.integers(0, len(syms)) if mode == "회전없음" else None
                while i < len(A) - 10:
                    sc = np.array([score(A[i - LOOKBACK_MIN:i, j]) for j in range(len(syms))])
                    ok = np.flatnonzero(np.isfinite(sc))
                    if len(ok) < 5:
                        i += 60
                        continue
                    if mode == "저진폭 선택":
                        j = ok[np.argmin(sc[ok])]
                    elif mode == "고진폭 선택":
                        j = ok[np.argmax(sc[ok])]
                    elif mode == "무작위":
                        j = int(rng.choice(ok))
                    else:
                        j = fixed
                    pnl, end, why = cycle(A[:, j], i, max_rungs, weights)
                    total += pnl
                    cyc += 1
                    ruin += int(why == "파산")
                    reasons[why] = reasons.get(why, 0) + 1
                    i = end + 1
                if cyc < 20:
                    continue
                res.append({"max_rungs": max_rungs, "ladder": lab_lad, "mode": mode,
                            "cycles": cyc, "total_bp": total,
                            "per_cycle": total / cyc, "ruin_pct": 100 * ruin / cyc,
                            "reasons": reasons})

    D = pd.DataFrame(res)
    print("② 회전 시뮬레이션 — 계좌 하나, 항상 한 종목")
    print(f"   {'계단상한':>8}{'사다리':<6}{'선택':<12}{'사이클':>8}{'총손익bp':>12}"
          f"{'사이클당':>10}{'파산%':>8}")
    print("   " + "-" * 84)
    for _, r in D.sort_values(["max_rungs", "ladder", "mode"]).iterrows():
        print(f"   {r.max_rungs:>8.0f}{r.ladder:<6}{r['mode']:<12}{r.cycles:>8,.0f}"
              f"{r.total_bp:>+12,.0f}{r.per_cycle:>+10.1f}{r.ruin_pct:>8.2f}")
    print("-" * 96)
    b = D.sort_values("total_bp", ascending=False).iloc[0]
    print(f"  최고: 계단상한 {b.max_rungs:.0f} / {b.ladder} / {b['mode']} → "
          f"{b.total_bp:+,.0f}bp ({b.cycles:,.0f}사이클, 파산 {b.ruin_pct:.2f}%)")
    for mr in sorted(D.max_rungs.unique()):
        s = D[(D.max_rungs == mr) & (D.ladder == b.ladder)]
        try:
            sel = s[s["mode"] == b["mode"]].iloc[0]
            rnd = s[s["mode"] == "무작위"].iloc[0]
            print(f"  계단상한 {mr}: {b['mode']} {sel.total_bp:+,.0f} vs 무작위 "
                  f"{rnd.total_bp:+,.0f}  → 선택 우위 "
                  f"{'예' if sel.total_bp > rnd.total_bp else '아니오'}")
        except IndexError:
            pass
    print("=" * 96 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": len(syms), "persistence": pers, "results": res},
                  fh, indent=2, ensure_ascii=False, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
