"""그룹 C 가설 1 — **마틴게일 파생의 생존 조건 검정**.

마틴게일은 엣지를 만들지 않는다. 분포를 바꿀 뿐이다.
    고정 크기 : 자주 조금 잃고 가끔 조금 번다        → 기댓값 = 엣지 x 횟수
    마틴게일  : 거의 항상 조금 벌고 드물게 전부 잃는다 → 기댓값 = **같다**
승률만 99% 로 올라간다. 백테스트가 아름답고 실거래가 파국인 이유다.

그래서 이 스캔은 "마틴게일이 되는가" 를 묻지 않는다. **네 조건 중 어디서
죽는지**를 잰다.

  ① 되돌림이 **구조적**인가 (통계 경향이 아니라 제약인가)
  ② 최대 역행폭(MAE) 분포의 **꼬리가 유한**한가
  ③ 자본이 그 꼬리를 견디는가 (필요 자본 배수)
  ④ **각 계단의 기대수익 > 그 계단의 마찰** 인가

①②③ 은 마틴게일 고유 조건이고 ④ 는 모든 전략의 조건이다. 2026-08-11 하루에
열두 가설이 전부 ④ 에서 죽었다.

왜 이 대상인가
  USDT/USDC 무기한 괴리는 ①②③ 을 만족하고 **④ 하나만** 못 넘은 계열이다.
      되돌림 t +153 ~ +425 (16칸 전부 양수, z·보유 양방향 단조)
      잔차 sd 2.6bp — 상한 있음
      닫은 이유: 왕복 마찰 24bp > 최고 gross 8.76bp
  마틴게일이 정확히 ④ 를 건드린다 — 이탈이 클수록 크게 걸면 자본이 엣지가 가장
  큰 지점에 집중된다. 그것으로 24bp 를 넘는지가 이 검정의 질문이다.

세 사다리를 **같은 데이터**로 비교한다
  · 고정      : 1,1,1,1        (대조군)
  · 산술 가중 : 1,2,3,4        (마틴게일 파생)
  · 기하 배증 : 1,2,4,8        (순수 마틴게일)
  대조군을 반드시 같이 돌린다. 마틴게일이 좋아 보이면 그게 사다리 덕인지
  그냥 그 구간이 좋았던 건지 갈라야 한다.

무엇을 조심하는가
  · **파산 계상** — 자본 한도를 넘으면 그 시점에 전량 손절하고 손실을 확정한다.
    한도 없이 무한히 물타면 백테스트가 항상 이긴다. 그게 마틴게일의 거짓말이다.
  · 각 계단마다 **마찰을 따로** 물린다. 계단을 늘리면 마찰도 늘어난다.
  · 겹침 금지 — 한 사이클이 끝나야 다음 진입.
  · MAE(최대 역행폭)를 **사이클마다 기록**해 꼬리를 직접 본다.
  · 승률이 아니라 **기댓값과 꼬리**로 판정한다.

사용:
  python3 scripts/research/martingale_ladder_scan.py --days 60
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
log = logging.getLogger("martingale_ladder")

DET = 240                # 느린 성분 제거 창 (분)
RUNGS_Z = (1.0, 2.0, 3.0, 4.0)      # 계단이 서는 z
LADDERS = {"고정 1,1,1,1": (1, 1, 1, 1),
           "산술 1,2,3,4": (1, 2, 3, 4),
           "기하 1,2,4,8": (1, 2, 4, 8)}
CAP_MULT = (4, 10, 25)   # 자본 한도 = 1계단 명목의 몇 배까지 버티나
MAX_HOLD = 720           # 사이클 최대 보유 (분)
FRIC_TAKER = 24.0        # USDT/USDC 양다리 왕복 (2026-08-11 실측)
FRIC_MAKER = 12.0        # 네 다리 전부 지정가일 때
# 단일 종목 모드 — 한 다리만 밟으므로 마찰이 훨씬 싸다
FRIC_SINGLE = 10.0       # 바이낸스 테이커 왕복


def load_single(agg: str, days: int, min_dvol: float, det: int, limit: int) -> dict:
    """단일 종목 평균회귀 계열 — 가격이 자기 이동중앙값에서 얼마나 벗어났나(bp).

    USDT/USDC 괴리는 이탈 폭이 2.6bp 라 마틴게일에게 불공정한 시험대다
    (한 사이클 최대 수익이 마찰의 1/10). 여기서는 **이탈이 마찰보다 훨씬 큰**
    계열로 다시 잰다 — 종목 가격이 자기 평균에서 수백 bp 벗어나는 일은 흔하다.
    즉 조건 ④(계단 기대수익 > 계단 마찰)를 만족할 수 있는 자리다.
    남는 질문은 ②③ — **역행폭 꼬리가 유한한가, 자본이 견디는가.**
    """
    out = {}
    for f in sorted(glob.glob(os.path.join(agg, "*_agg1m.joblib")))[:limit]:
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        try:
            d = joblib.load(f)
        except Exception:
            continue
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d = d.loc[d.index >= d.index.max() - pd.Timedelta(days=days)]
        if len(d) < 20000:
            continue
        if d["quote_volume"].resample("1D").sum().median() < min_dvol:
            continue
        px = d["px_open"].astype(float)
        base = px.rolling(det, min_periods=det // 4).median()
        r = (px / base - 1.0) * 1e4                      # 평균 대비 이탈 (bp)
        z = r / r.rolling(det, min_periods=det // 4).std()
        out[sym] = pd.DataFrame({"r": r, "z": z, "p": px}).dropna()
    return out


def load_pairs(cache: str, agg: str, days: int) -> dict:
    out = {}
    for cf in sorted(glob.glob(os.path.join(cache, "*_1m.joblib"))):
        uc = os.path.basename(cf).replace("_1m.joblib", "")
        ut = uc[:-4] + "USDT"
        af = os.path.join(agg, f"{ut}_agg1m.joblib")
        if not os.path.exists(af):
            continue
        dc = joblib.load(cf)
        dt = joblib.load(af)
        dt = dt[~dt.index.duplicated(keep="last")].sort_index()
        idx = dc.index.intersection(dt.index)
        if len(idx) < 20000:
            continue
        b = (dc.loc[idx, "px_open"].astype(float) /
             dt.loc[idx, "px_open"].astype(float) - 1.0) * 1e4
        r = b - b.rolling(DET, min_periods=DET // 4).median()
        z = r / r.rolling(DET, min_periods=DET // 4).std()
        out[uc] = pd.DataFrame({"r": r, "z": z, "p": r}).dropna()
    return out


def run_cycles(df: pd.DataFrame, weights, cap_units: float, fric: float):
    """사다리 한 벌을 굴린다. 반환: (사이클별 손익 bp·단위가중, MAE 리스트, 파산수)

    **손익은 `r`(신호)이 아니라 `p`(실제 거래 대상)로 계산한다.**
    단일 종목에서 잔차가 0 으로 돌아오는 것은 가격이 내려와서일 수도, **이동
    중앙값이 따라 올라가서**일 수도 있다. 후자는 손익이 아니다. 잔차로 손익을
    재면 중앙값이 쫓아온 것까지 이익으로 계상돼 백테스트가 화려해진다
    (2026-08-11 초판에서 +587bp / 승률 98.3% 로 나왔다 — 전부 이 허상이었다).
    USDT/USDC 모드는 잔차 자체가 거래 대상(양다리)이라 p = r 로 둔다.
    """
    z = df["z"].values
    r = df["r"].values
    pv = df["p"].values
    n = len(z)
    pnls, maes, ruins = [], [], 0
    i = 0
    while i < n - 1:
        # 진입: |z| 가 첫 계단을 넘은 시점
        if not np.isfinite(z[i]) or abs(z[i]) < RUNGS_Z[0]:
            i += 1
            continue
        side = -np.sign(z[i])              # 되돌림 베팅
        entries = [(pv[i], weights[0])]    # (진입 **가격**, 단위수)
        p0 = pv[i]
        units = weights[0]
        rung = 1
        mae = 0.0
        j = i + 1
        closed = False
        while j < n and (j - i) <= MAX_HOLD:
            cur = r[j]
            curp = pv[j]
            # 미실현 (bp x 단위) — 가격 변화를 bp 로 환산
            unreal = sum(w * side * (curp / e - 1.0) * 1e4 for e, w in entries)
            mae = min(mae, unreal)
            # 파산 판정: 미실현 손실이 자본 한도를 넘으면 전량 손절
            if unreal <= -cap_units:
                pnls.append(unreal - fric * units)
                maes.append(mae)
                ruins += 1
                closed = True
                break
            # 청산: 잔차가 0 을 통과
            if side * (cur - 0.0) >= 0:
                pnls.append(unreal - fric * units)
                maes.append(mae)
                closed = True
                break
            # 다음 계단
            if rung < len(weights) and abs(z[j]) >= RUNGS_Z[rung] and np.sign(z[j]) == -side:
                entries.append((curp, weights[rung]))
                units += weights[rung]
                rung += 1
            j += 1
        if not closed:                     # 시간 초과 — 시장가 청산
            curp = pv[min(j, n - 1)]
            unreal = sum(w * side * (curp / e - 1.0) * 1e4 for e, w in entries)
            pnls.append(unreal - fric * units)
            maes.append(min(mae, unreal))
        i = j + 1                          # 겹침 금지
    return pnls, maes, ruins


def main() -> int:
    p = argparse.ArgumentParser(description="마틴게일 파생 생존 조건 검정")
    p.add_argument("--cache", default=str(ROOT / "runs" / "usdc_1m"))
    p.add_argument("--agg", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--maker", action="store_true", help="네 다리 지정가 가정")
    p.add_argument("--single", action="store_true",
                   help="단일 종목 평균회귀 계열 (이탈 폭이 큰 자리)")
    p.add_argument("--det", type=int, default=DET)
    p.add_argument("--min-dvol-usd", type=float, default=20_000_000)
    p.add_argument("--limit", type=int, default=250)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "martingale_ladder_scan.json"))
    args = p.parse_args()

    if args.single:
        fric = FRIC_SINGLE
        pairs = load_single(args.agg, args.days, args.min_dvol_usd, args.det, args.limit)
        mode = f"단일종목 평균회귀 (기준 {args.det}분 이동중앙값)"
    else:
        fric = FRIC_MAKER if args.maker else FRIC_TAKER
        pairs = load_pairs(args.cache, args.agg, args.days)
        mode = "USDT-USDC 괴리"
    log.info("대상 %d개 / 계단당 마찰 %.0fbp / %s", len(pairs), fric, mode)
    if len(pairs) < 10:
        log.error("코인 부족")
        return 1

    res = []
    for lab, w in LADDERS.items():
        for cap in CAP_MULT:
            # 자본 한도 (bp x 단위). 계열의 이탈 규모에 맞춰 정한다.
            scale = float(np.median([abs(v["r"]).median() for v in pairs.values()]))
            cap_units = cap * max(scale, 1.0) * sum(w)
            allp, allm, ruin, ncyc = [], [], 0, 0
            for sym, df in pairs.items():
                pn, ma, ru = run_cycles(df, w, cap_units, fric)
                allp.extend(pn)
                allm.extend(ma)
                ruin += ru
                ncyc += len(pn)
            if ncyc < 300:
                continue
            a = np.array(allp)
            m = np.array(allm)
            se = a.std(ddof=1) / np.sqrt(len(a))
            res.append({"ladder": lab, "cap_mult": cap, "n_cycles": ncyc,
                        "mean_bp": float(a.mean()), "se_bp": float(se),
                        "t": float(a.mean() / se) if se else np.nan,
                        "win": float((a > 0).mean() * 100),
                        "worst": float(a.min()),
                        "mae_p50": float(np.percentile(m, 50)),
                        "mae_p99": float(np.percentile(m, 1)),
                        "ruin_pct": float(100 * ruin / ncyc)})

    df = pd.DataFrame(res)
    print("\n" + "=" * 108)
    print(f"그룹 C 가설 1 — 마틴게일 파생 생존 검정  ({len(pairs)}개 / {mode})")
    print("=" * 108)
    print(f"  계단 z = {RUNGS_Z} / 계단당 마찰 {fric:.0f}bp / 최대 보유 {MAX_HOLD}분")
    print("  ** 대조군(고정 1,1,1,1)과 반드시 비교할 것. 사다리 덕인지 구간 덕인지 갈라야 한다. **")
    print("-" * 108)
    print(f"{'사다리':<16}{'자본배수':>9}{'사이클':>9}{'평균bp':>10}{'오차':>8}{'t':>8}"
          f"{'승률%':>8}{'최악':>10}{'MAE p99':>10}{'파산%':>8}")
    print("-" * 108)
    for _, r in df.sort_values(["ladder", "cap_mult"]).iterrows():
        print(f"{r.ladder:<16}{r.cap_mult:>9.0f}{r.n_cycles:>9,.0f}{r.mean_bp:>+10.2f}"
              f"{r.se_bp:>8.2f}{r.t:>+8.2f}{r.win:>8.1f}{r.worst:>+10.1f}"
              f"{r.mae_p99:>+10.1f}{r.ruin_pct:>8.2f}")
    print("-" * 108)
    npass = int(((df.mean_bp > 0) & (df.t >= 3.0)).sum())
    print(f"  기댓값>0 & t>=3.0 : {npass}/{len(df)}")
    if len(df):
        b = df.sort_values("mean_bp", ascending=False).iloc[0]
        c = df[df.ladder == "고정 1,1,1,1"].sort_values("mean_bp", ascending=False)
        print(f"  최고: {b.ladder} / 자본 {b.cap_mult:.0f}배 → {b.mean_bp:+.2f} ± {b.se_bp:.2f}bp "
              f"(승률 {b.win:.1f}%, 파산 {b.ruin_pct:.2f}%)")
        if len(c):
            c0 = c.iloc[0]
            print(f"  대조군 최고: {c0.ladder} / 자본 {c0.cap_mult:.0f}배 → {c0.mean_bp:+.2f}bp")
            print(f"  **사다리가 대조군을 이겼나: "
                  f"{'예' if b.mean_bp > c0.mean_bp and b.ladder != c0.ladder else '아니오'}**")
    print("=" * 108 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_pairs": len(pairs), "friction_bp": fric,
                   "rungs_z": list(RUNGS_Z), "results": res}, fh,
                  indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
