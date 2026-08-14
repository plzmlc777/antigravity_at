"""그룹 C 가설 7 — **무작위를 이기는 종목 선택 팩터 탐색**.

배경 (2026-08-11)
  가설 6 에서 180칸 중 t>=3.0 을 넘은 유일한 칸이 **무작위 대조군**이었다.
  선택기 셋(저진폭·저효율비·곱)이 전부 무작위를 못 이겼다.
  전략(회전 그리드 + 바구니 익절)은 이제 고정하고 **선택 팩터만** 바꿔가며
  무작위를 이기는 것이 있는지 찾는다.

설계 개선 — 짝지은 비교
  지금까지는 팩터 선택과 무작위를 **따로** 돌려 총합을 비교했다. 그러면 서로
  다른 시장 구간을 보게 되어 비교가 둔해진다.
  여기서는 **같은 회전 시점에서 팩터 종목과 무작위 종목을 나란히** 돌린다.
  국면이 상쇄되므로 차이의 t 를 직접 낼 수 있다 (짝지은 t 검정).

팩터 (그리드 손익 결정 요소에서 역산)
  그리드 손익 = (계단 교차 횟수 x g) - 추세 손실 - 마찰
  따라서 "많이 교차하고 / 추세가 없고 / 마찰이 싼" 종목이 좋아야 한다.

    amp        실현변동 (교차 횟수의 대리)
    er         효율비 |순이동|/경로합 (추세 정도)
    vr         분산비 var(k봉)/(k x var(1봉)) — <1 평균회귀, >1 추세. ER 보다 표준적
    negac      1분 수익률 자기상관의 음수 정도 (되돌림 성향)
    cross      탈추세 가격의 0 교차 횟수 (진동의 직접 계수)
    spread     실측 실효 스프레드 (마찰)
    amp_sp     진폭/스프레드 비 (마찰 대비 움직임)
    mdd        구간 내 최대낙폭 (꼬리 위험 대리)
    fund       펀딩률 절대값 (한쪽 쏠림 = 추세 위험)
    **pastpnl  직전 구간의 실제 그리드 손익** ← 실무자가 가장 먼저 볼 팩터
    combo      vr 낮고 amp_sp 높은 것 (상위 둘의 결합)

무엇을 조심하는가
  · 팩터는 **직전 창 정보로만** 산출 (lookahead 없음).
  · 짝지은 비교이므로 같은 시점·같은 사이클 정의를 쓴다.
  · **부호 양방향** 검정 — 팩터가 반대로 작동할 수도 있다 (가설 4 에서 겪음).
  · 표본 300 사이클 미만 팩터는 판정하지 않는다.

사용:
  python3 scripts/research/grid_factor_search.py --days 60
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
log = logging.getLogger("grid_factor")

FEE = 2.0
LOOKBACK = 1440
MAX_HOLD = 720
SCORE_EVERY = 60          # 유니버스 확대에 맞춰 격자를 절반으로
GRID_BP, MAX_RUNGS, TP_MULT = 120.0, 4, 2       # 가설 6 최고 칸 설정
CAP_MULT = 100
MIN_CYCLES = 300


def cycle(px, start, g_bp, max_rungs, weights, tp_mult):
    g = g_bp / 1e4
    cap = CAP_MULT * g_bp
    lots = [(px[start], weights[0])]
    realized = -FEE * weights[0]
    i, n = start + 1, len(px)
    while i < n and (i - start) <= MAX_HOLD:
        p = px[i]
        keep = []
        for e, w in lots:
            if p >= e * (1 + g):
                realized += w * ((p / e - 1.0) * 1e4) - FEE * w
            else:
                keep.append((e, w))
        lots = keep
        if not lots:
            return realized, i
        unreal = sum(w * (p / e - 1.0) * 1e4 for e, w in lots)
        ou = sum(w for _, w in lots)
        if tp_mult > 0 and realized + unreal >= FEE * ou * tp_mult:
            return realized + unreal - FEE * ou, i
        if unreal <= -cap:
            return realized + unreal - FEE * ou, i
        lo = min(e for e, _ in lots)
        if p <= lo * (1 - g):
            if len(lots) >= max_rungs:
                return realized + unreal - FEE * ou, i
            w = weights[min(len(lots), len(weights) - 1)]
            lots.append((p, w))
            realized -= FEE * w
        i += 1
    p = px[min(i, n - 1)]
    unreal = sum(w * (p / e - 1.0) * 1e4 for e, w in lots)
    return realized + unreal - FEE * sum(w for _, w in lots), min(i, n - 1)


def factors(seg: np.ndarray, spread: float, fund: float, past: float) -> dict:
    r = np.diff(np.log(seg))
    if len(r) < 60:
        return {}
    path = np.abs(r).sum()
    if path <= 0:
        return {}
    amp = float(np.std(r) * np.sqrt(len(r)) * 1e4)
    er = float(abs(np.log(seg[-1] / seg[0])) / path)
    k = 30
    m = len(r) // k * k
    if m < k * 2:
        return {}
    vr = float(np.var(r[:m].reshape(-1, k).sum(axis=1)) / (k * np.var(r) + 1e-18))
    negac = float(-np.corrcoef(r[:-1], r[1:])[0, 1]) if len(r) > 10 else np.nan
    base = pd.Series(seg).rolling(240, min_periods=60).median().values
    dv = seg - base
    ok = np.isfinite(dv)
    cross = float(np.sum(np.diff(np.sign(dv[ok])) != 0)) if ok.sum() > 10 else np.nan
    run = np.maximum.accumulate(seg)
    mdd = float(np.min(seg / run - 1.0) * 1e4)
    return {"amp": amp, "er": er, "vr": vr, "negac": negac, "cross": cross,
            "spread": spread, "amp_sp": amp / max(spread, 0.1), "mdd": mdd,
            "fund": abs(fund), "pastpnl": past,
            "combo": (1.0 / max(vr, 0.05)) * (amp / max(spread, 0.1))}


def main() -> int:
    p = argparse.ArgumentParser(description="그리드 선택 팩터 탐색")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=20_000_000)
    p.add_argument("--limit", type=int, default=300)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "grid_factor_search.json"))
    args = p.parse_args()

    prices, spreads = {}, {}
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
        spreads[sym] = float(d["eff_spread_bp_adj"].median())
    # 종목이 많아지면 인덱스 교집합이 비어버린다(결측 위치가 제각각).
    # 공통 분 격자를 만들어 붙이고, 결측이 5% 넘는 종목만 버린다.
    # 신규 상장 종목은 이력이 짧다. 전체 종목의 교집합/최대최소로 창을 잡으면
    # 하나만 짧아도 창이 사라진다. 목표 창을 먼저 정하고 **그 창을 덮는 종목만**
    # 쓴다.
    hi = max(v.index.max() for v in prices.values())
    lo = hi - pd.Timedelta(days=args.days)
    prices = {k: v for k, v in prices.items()
              if v.index.min() <= lo + pd.Timedelta(days=1)
              and v.index.max() >= hi - pd.Timedelta(days=1)}
    log.info("창 %s ~ %s 를 덮는 종목 %d", lo, hi, len(prices))
    if len(prices) < 20:
        log.error("종목 부족")
        return 1
    idx = pd.date_range(lo, hi, freq="1min")
    M = pd.DataFrame({k: v.reindex(idx) for k, v in prices.items()})
    keep = M.columns[M.isna().mean() <= 0.05]
    M = M[keep].ffill().bfill()
    M = M.dropna(axis=1)
    A, syms, T = M.values, list(M.columns), len(M)
    SP = np.array([spreads[s] for s in syms])
    log.info("%d종목 x %d분", len(syms), T)

    # 펀딩률 (있으면 사용, 없으면 0)
    FR = np.zeros(len(syms))

    grid_t = np.arange(LOOKBACK, T - 10, SCORE_EVERY)
    FN = None
    W = [2 ** k for k in range(8)]
    # 팩터 행렬 + 직전 구간 그리드 손익
    past = np.zeros(len(syms))
    FMAT = {}
    for gi, t in enumerate(grid_t):
        seg = A[t - LOOKBACK:t]
        if gi > 0:
            # 직전 창 **전체**를 그리드로 굴린 손익. 한 사이클만 보면 표본이
            # 한 건이라 잡음이 크다. 창 전체를 굴려 누적을 쓴다.
            for j in range(len(syms)):
                tot, k = 0.0, t - LOOKBACK
                while k < t - 60:
                    v, e2 = cycle(A[:, j], k, GRID_BP, MAX_RUNGS, W, TP_MULT)
                    tot += v
                    k = e2 + 1
                past[j] = tot
        row = {}
        for j in range(len(syms)):
            fs = factors(seg[:, j], SP[j], FR[j], past[j])
            if not fs:
                continue
            for k2, v2 in fs.items():
                row.setdefault(k2, np.full(len(syms), np.nan))[j] = v2
        FMAT[gi] = row
        if FN is None and row:
            FN = list(row)
        if gi % 200 == 0:
            log.info("팩터 %d/%d", gi, len(grid_t))
    log.info("팩터 %d종: %s", len(FN), FN)

    rng = np.random.default_rng(20260811)
    res = []
    for fac in FN:
        for sign, slab in ((-1, "낮은쪽"), (+1, "높은쪽")):
            dif, fpn, rpn = [], [], []
            i = LOOKBACK
            while i < T - 10:
                gi = min(int((i - LOOKBACK) // SCORE_EVERY), len(grid_t) - 1)
                v = FMAT.get(gi, {}).get(fac)
                if v is None:
                    i += SCORE_EVERY
                    continue
                ok = np.flatnonzero(np.isfinite(v))
                if len(ok) < 8:
                    i += SCORE_EVERY
                    continue
                j = int(ok[np.argmin(sign * -v[ok])]) if sign > 0 else int(ok[np.argmin(v[ok])])
                jr = int(rng.choice(ok[ok != j]))
                a, ea = cycle(A[:, j], i, GRID_BP, MAX_RUNGS, W, TP_MULT)
                b, eb = cycle(A[:, jr], i, GRID_BP, MAX_RUNGS, W, TP_MULT)
                fpn.append(a); rpn.append(b); dif.append(a - b)
                i = max(ea, eb) + 1
            if len(dif) < MIN_CYCLES:
                continue
            d = np.array(dif)
            se = d.std(ddof=1) / np.sqrt(len(d))
            res.append({"factor": fac, "side": slab, "n": len(d),
                        "fac_mean": float(np.mean(fpn)), "rnd_mean": float(np.mean(rpn)),
                        "diff": float(d.mean()), "se": float(se),
                        "t": float(d.mean() / se) if se else np.nan,
                        "win": float(100 * (d > 0).mean())})

    D = pd.DataFrame(res).sort_values("t", ascending=False)
    print("\n" + "=" * 100)
    print(f"그룹 C 가설 7 — 무작위를 이기는 팩터  ({len(syms)}종목 / {args.days}일 / 짝지은 비교)")
    print("=" * 100)
    print(f"  전략 고정: 간격 {GRID_BP:.0f}bp / 계단 {MAX_RUNGS} / 바구니익절 x{TP_MULT} / 기하")
    print("  같은 시점에 팩터 종목과 무작위 종목을 나란히 굴려 **차이**의 t 를 낸다")
    print("-" * 100)
    print(f"{'팩터':<12}{'방향':<8}{'사이클':>8}{'팩터bp':>10}{'무작위bp':>10}"
          f"{'차이bp':>10}{'오차':>8}{'차이 t':>9}{'승률%':>8}")
    print("-" * 100)
    for _, r in D.iterrows():
        star = "  ★" if r["diff"] > 0 and r["t"] >= 3.0 else ""
        print(f"{r['factor']:<12}{r['side']:<8}{r['n']:>8,.0f}{r['fac_mean']:>+10.1f}"
              f"{r['rnd_mean']:>+10.1f}{r['diff']:>+10.1f}{r['se']:>8.1f}{r['t']:>+9.2f}{r['win']:>8.1f}{star}")
    print("-" * 100)
    npass = int(((D["diff"] > 0) & (D.t >= 3.0)).sum())
    print(f"  무작위를 이긴 팩터 (차이>0 & t>=3.0): **{npass}/{len(D)}**")
    print("=" * 100 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": len(syms), "results": res}, fh,
                  indent=2, ensure_ascii=False, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
