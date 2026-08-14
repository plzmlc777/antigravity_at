"""그룹 C 가설 2 — **분기선물 basis 마틴게일**.

왜 이 계열인가
  가설 1 에서 두 계열이 각각 반대쪽에서 죽었다.
      USDT/USDC 괴리    : ①②③ 만족, **④ 실패** (이탈 2.6bp < 마찰 24bp)
      단일종목 평균회귀 : **①②③ 실패**, ④ 통과 (가격은 평균으로 돌아올 의무 없음)
  둘 다 갖춘 계열을 찾아야 한다.

  분기선물이 그 후보다.
      ① **만기에 수렴이 수학적 의무** — 인도가격이 지수로 정산된다. 통계적
         경향이 아니라 계약 조건이다. 조건 ①의 가장 강한 형태.
      ② 만기까지 보유하면 종착점이 0 으로 고정 — 종착 위험이 유한하다.
      ④ 만기가 수개월이라 basis 가 수백 bp 로 벌어질 수 있다. 마찰 20bp
         (2다리 x 테이커 5bp x 왕복) 를 넘을 여지가 있다.

무엇을 신호로 쓰나
  **원시 basis 는 평균회귀 계열이 아니다** — 만기가 다가오면 자연히 0 으로
  줄어든다(캐리). 그걸 되돌림으로 착각하면 안 된다.
  따라서 **연율화 basis** 로 정규화한다:
      ann = (선물/무기한 - 1) x 1e4 x 365 / 잔존일수
  이 값이 평균회귀 대상이다.

손익
  거래 대상이 **스프레드 자체**(선물 롱 + 무기한 숏)이므로 손익 = basis 변화.
  가설 1 단일종목 모드에서 저지른 오류(잔차로 손익 계산)가 여기서는 발생하지
  않는다 — 여기서는 잔차가 곧 거래 대상이다.

무엇을 조심하는가
  · **만기 보유를 최종 청산으로 둔다.** 수렴이 보장되는 유일한 지점이다.
  · 계단마다 마찰을 따로 물린다. 2다리이므로 계단당 20bp.
  · 자본 한도를 넘으면 그 자리에서 손절 확정(파산 계상). 무한 물타기 금지.
  · **대조군(고정 크기) 필수.** 사다리 덕인지 계열 덕인지 갈라야 한다.
  · 만료 계약만 쓴다 — 진행 중 계약은 결과가 아직 없다(생존 편향 방지).

사용:
  python3 scripts/research/quarterly_basis_martingale.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("q_basis_mart")

FAPI = "https://fapi.binance.com"
FRIC_RUNG_BP = 20.0      # 2다리 x 테이커 5bp x 왕복
RUNGS_Z = (1.0, 2.0, 3.0, 4.0)
LADDERS = {"고정 1,1,1,1": (1, 1, 1, 1),
           "산술 1,2,3,4": (1, 2, 3, 4),
           "기하 1,2,4,8": (1, 2, 4, 8)}
CAP_BP = (200, 500, 1500)   # 자본 한도 (bp x 단위)
ZWIN = 24 * 14              # z 창 (시간) = 2주


def klines(sym: str, start_ms: int, interval: str = "1h") -> pd.Series:
    rows, cur = [], start_ms
    end = int(time.time() * 1000)
    while cur < end:
        try:
            r = requests.get(f"{FAPI}/fapi/v1/klines",
                             params={"symbol": sym, "interval": interval,
                                     "startTime": cur, "limit": 1500}, timeout=30)
            if r.status_code != 200:
                break
            d = r.json()
        except Exception:
            break
        if not isinstance(d, list) or not d:
            break
        rows.extend(d)
        nxt = int(d[-1][0]) + 1
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.06)
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows).iloc[:, :5]
    df.columns = ["ot", "o", "h", "l", "c"]
    df["ts"] = pd.to_datetime(df["ot"].astype("int64"), unit="ms")
    s = df.set_index("ts")["c"].astype(float).sort_index()
    return s[~s.index.duplicated(keep="last")]


def quarter_symbols(base: str, back_years: int = 3) -> list:
    """분기 만기(3·6·9·12월 마지막 금요일 근처) 후보를 만들어 존재 여부를 확인."""
    out = []
    today = dt.date.today()
    for y in range(today.year - back_years, today.year + 1):
        for m in (3, 6, 9, 12):
            # 그 달 마지막 금요일
            d = dt.date(y, m, 28)
            while d.month == m:
                d += dt.timedelta(days=1)
            d -= dt.timedelta(days=1)
            while d.weekday() != 4:
                d -= dt.timedelta(days=1)
            if d >= today:
                continue                      # 진행 중 계약 제외 (생존 편향)
            out.append((f"{base}_{d.strftime('%y%m%d')}", d))
    return out


def run_cycles(bs: pd.Series, z: pd.Series, weights, cap_bp: float, expiry: pd.Timestamp):
    """basis 계열에 사다리를 굴린다. 손익 단위 = bp x 단위수."""
    zi, bi = z.values, bs.values
    ts = bs.index
    n = len(bi)
    pnls, maes, ruins, expiries = [], [], 0, 0
    i = 0
    while i < n - 1:
        if not np.isfinite(zi[i]) or abs(zi[i]) < RUNGS_Z[0]:
            i += 1
            continue
        side = -np.sign(zi[i])
        entries = [(bi[i], weights[0])]
        units = weights[0]
        rung, mae = 1, 0.0
        j, closed = i + 1, False
        while j < n:
            cur = bi[j]
            unreal = sum(w * side * (cur - e) for e, w in entries)
            mae = min(mae, unreal)
            if unreal <= -cap_bp:
                pnls.append(unreal - FRIC_RUNG_BP * units)
                maes.append(mae); ruins += 1; closed = True; break
            if side * cur >= 0:                       # basis 가 0 통과
                pnls.append(unreal - FRIC_RUNG_BP * units)
                maes.append(mae); closed = True; break
            if ts[j] >= expiry:                       # **만기 = 보장된 수렴**
                unreal = sum(w * side * (0.0 - e) for e, w in entries)
                pnls.append(unreal - FRIC_RUNG_BP * units)
                maes.append(mae); expiries += 1; closed = True; break
            if rung < len(weights) and abs(zi[j]) >= RUNGS_Z[rung] and np.sign(zi[j]) == -side:
                entries.append((cur, weights[rung])); units += weights[rung]; rung += 1
            j += 1
        if not closed:
            unreal = sum(w * side * (0.0 - e) for e, w in entries)
            pnls.append(unreal - FRIC_RUNG_BP * units)
            maes.append(mae); expiries += 1
        i = j + 1
    return pnls, maes, ruins, expiries


def main() -> int:
    p = argparse.ArgumentParser(description="분기선물 basis 마틴게일")
    p.add_argument("--bases", default="BTCUSDT,ETHUSDT")
    p.add_argument("--back-years", type=int, default=3)
    p.add_argument("--cache", default=str(ROOT / "runs" / "qbasis"))
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "quarterly_basis_martingale.json"))
    args = p.parse_args()
    os.makedirs(args.cache, exist_ok=True)

    series = {}
    for base in args.bases.split(","):
        perp = None
        for qsym, exp in quarter_symbols(base, args.back_years):
            cf = os.path.join(args.cache, f"{qsym}.joblib")
            if os.path.exists(cf):
                df = joblib.load(cf)
            else:
                start = int((dt.datetime.combine(exp, dt.time()) -
                             dt.timedelta(days=200)).timestamp() * 1000)
                q = klines(qsym, start)
                if q.empty or len(q) < 300:
                    log.info("  %s 없음/부족", qsym)
                    continue
                if perp is None or perp.index.min() > q.index.min():
                    perp = klines(base, int(q.index.min().timestamp() * 1000))
                pp = perp.reindex(q.index).ffill()
                df = pd.DataFrame({"q": q, "p": pp}).dropna()
                joblib.dump(df, cf)
            if len(df) < 300:
                continue
            exp_ts = pd.Timestamp(dt.datetime.combine(exp, dt.time(8, 0)))
            dte = (exp_ts - df.index).total_seconds() / 86400.0
            df = df[dte > 1.0]
            dte = dte[dte > 1.0]
            bs = (df["q"] / df["p"] - 1.0) * 1e4                 # 원시 basis (bp)
            ann = bs * 365.0 / dte                                # 연율화 → 평균회귀 대상
            z = (ann - ann.rolling(ZWIN, min_periods=ZWIN // 4).mean()) \
                / ann.rolling(ZWIN, min_periods=ZWIN // 4).std()
            ok = z.notna()
            if ok.sum() < 200:
                continue
            series[qsym] = (bs[ok], z[ok], exp_ts, float(bs.abs().median()),
                            float(ann.abs().median()))
            log.info("%s: %d시간 / basis 중앙 %.1fbp / 연율 중앙 %.0fbp",
                     qsym, int(ok.sum()), series[qsym][3], series[qsym][4])

    if len(series) < 4:
        log.error("계약 부족: %d", len(series))
        return 1

    res = []
    for lab, w in LADDERS.items():
        for cap in CAP_BP:
            allp, allm, ruin, expc, ncyc = [], [], 0, 0, 0
            for qsym, (bs, z, exp_ts, _, _) in series.items():
                pn, ma, ru, ex = run_cycles(bs, z, w, cap, exp_ts)
                allp.extend(pn); allm.extend(ma); ruin += ru; expc += ex; ncyc += len(pn)
            if ncyc < 100:
                continue
            a, m = np.array(allp), np.array(allm)
            se = a.std(ddof=1) / np.sqrt(len(a))
            res.append({"ladder": lab, "cap_bp": cap, "n_cycles": ncyc,
                        "mean_bp": float(a.mean()), "se_bp": float(se),
                        "t": float(a.mean() / se) if se else np.nan,
                        "win": float((a > 0).mean() * 100), "worst": float(a.min()),
                        "mae_p99": float(np.percentile(m, 1)),
                        "ruin_pct": float(100 * ruin / ncyc),
                        "expiry_pct": float(100 * expc / ncyc)})

    df = pd.DataFrame(res)
    print("\n" + "=" * 110)
    print(f"그룹 C 가설 2 — 분기선물 basis 마틴게일  ({len(series)}계약 / 만료분만)")
    print("=" * 110)
    print(f"  신호 = 연율화 basis 의 z (창 {ZWIN}시간) / 계단당 마찰 {FRIC_RUNG_BP:.0f}bp")
    print("  청산 = basis 0 통과 **또는 만기(수렴 보장)**")
    print("-" * 110)
    print(f"{'사다리':<16}{'자본bp':>8}{'사이클':>8}{'평균bp':>10}{'오차':>8}{'t':>8}"
          f"{'승률%':>8}{'최악':>10}{'MAEp99':>10}{'파산%':>8}{'만기청산%':>10}")
    print("-" * 110)
    for _, r in df.sort_values(["ladder", "cap_bp"]).iterrows():
        print(f"{r.ladder:<16}{r.cap_bp:>8.0f}{r.n_cycles:>8,.0f}{r.mean_bp:>+10.2f}"
              f"{r.se_bp:>8.2f}{r.t:>+8.2f}{r.win:>8.1f}{r.worst:>+10.1f}"
              f"{r.mae_p99:>+10.1f}{r.ruin_pct:>8.2f}{r.expiry_pct:>10.1f}")
    print("-" * 110)
    npass = int(((df.mean_bp > 0) & (df.t >= 3.0)).sum())
    print(f"  기댓값>0 & t>=3.0 : {npass}/{len(df)}")
    if len(df):
        b = df.sort_values("mean_bp", ascending=False).iloc[0]
        c = df[df.ladder == "고정 1,1,1,1"].sort_values("mean_bp", ascending=False).iloc[0]
        print(f"  최고: {b.ladder} / 자본 {b.cap_bp:.0f}bp → {b.mean_bp:+.2f} ± {b.se_bp:.2f}bp")
        print(f"  대조군 최고: {c.mean_bp:+.2f}bp")
        print(f"  **사다리가 대조군을 이겼나: "
              f"{'예' if b.mean_bp > c.mean_bp and b.ladder != c.ladder else '아니오'}**")
    print("=" * 110 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_contracts": len(series), "friction_rung_bp": FRIC_RUNG_BP,
                   "results": res}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
