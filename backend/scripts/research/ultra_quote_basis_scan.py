"""초단타 새 관점 — **같은 코인의 두 계약 사이 괴리** (USDT 무기한 vs USDC 무기한).

배경 (2026-08-11)
  가설 1~8 은 전부 같은 구조였다. **한 종목의 자기 호가창 안에서 어디에 설까.**
    가설1 터치 / 2 흐름기울임 / 3 큐이탈 / 4 결합 / 5 물러섬 / 6 호가불균형
    가설7 물러섬+불균형 / 8 국면조건부
  전부 음수였고 벽은 늘 같았다 — **역선택 3.80bp > 반스프레드 3.42bp**.
  상대가 나보다 안다. 어디에 서든 그 사실이 안 바뀐다.

  방향 예측 쪽도 닫혔다 (자기 주문흐름 -1.3~+5.3bp, BTC 대비 잔차 +1.0~+3.1bp,
  횡단면 되돌림 48칸 전부 음수) — 전부 gross 1~5bp 대 마찰 11~13bp.

  강제청산 라벨(`!forceOrder@arr`)로 "상대가 확실히 모르는 순간"을 잡으려 했으나
  스트림이 무응답(대조군 @trade 1,169건 / forceOrder 0건, 세 형태 전부),
  REST 는 allForceOrders/liquidationSnapshot 404 폐지. **데이터 부재로 종결.**

무엇이 다른가
  지금까지는 **한 가격이 어디로 갈까**를 맞히려 했다. 여기서는 맞히지 않는다.
  같은 코인의 두 계약 가격은 **떨어질 수 없다** — 벌어지면 차익거래가 닫는다.
  즉 방향이 아니라 **구조적 제약**을 거래한다. 이게 결정적 차이다.

  역선택 논리도 달라진다. BTCUSDC 가 BTCUSDT 에서 벌어졌을 때 내 반대편에 선
  쪽은 "BTC 가 오를 걸 아는 사람" 이 아니라 **한쪽 장부만 움직인 사람**이다.

무엇을 조심하는가
  · **USDC 자체 가치가 1 이 아니다.** USDT/USDC 환율이 움직이면 두 계약 가격이
    갈리는 게 정상이다. 이걸 괴리로 착각하면 안 된다 → 괴리의 **느린 성분을
    빼고**(이동중앙값) 빠른 잔차만 본다.
  · **겹치는 창 금지** (2026-08-10 교훈: 겹침만으로 r +0.470 이 조작됐다).
    보유 구간이 안 겹치게 step >= H 로 표본을 뜬다.
  · 마찰은 **두 다리 왕복** — 스프레드 2개 + 테이커 4회. 낙관 금지.
  · USDC 계약은 거래대금이 얇다. 유동성 관문 필수 (Lesson #78).
  · 표본 1,000건 미만 칸은 판정하지 않는다.

사용:
  python3 scripts/research/ultra_quote_basis_scan.py --days 60
"""
from __future__ import annotations

import argparse
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
log = logging.getLogger("ultra_quote_basis_scan")

FAPI = "https://fapi.binance.com"
TAKER_FEE_BP = 4.0            # 다리당 편도
DETREND_MIN = 240             # 느린 성분(USDT/USDC 환율) 제거 창 (분)
ENTRY_Z = (1.5, 2.0, 2.5, 3.0)
HOLDS_MIN = (5, 15, 30, 60)
MIN_CELL = 1000


def usdc_perp_pairs() -> list:
    r = requests.get(f"{FAPI}/fapi/v1/exchangeInfo", timeout=30).json()
    per = [s for s in r["symbols"]
           if s["contractType"] == "PERPETUAL" and s["status"] == "TRADING"]
    usdt = {s["symbol"] for s in per if s["quoteAsset"] == "USDT"}
    out = []
    for s in per:
        if s["quoteAsset"] != "USDC":
            continue
        t = s["symbol"][:-4] + "USDT"
        if t in usdt:
            out.append((s["symbol"], t))
    return out


def fetch_klines(sym: str, days: int) -> pd.DataFrame:
    """1분봉 REST 수집. USDC 계약은 아카이브에 없어 직접 받는다."""
    end = int(time.time() * 1000)
    start = end - days * 86400_000
    rows, cur = [], start
    while cur < end:
        try:
            r = requests.get(f"{FAPI}/fapi/v1/klines",
                             params={"symbol": sym, "interval": "1m",
                                     "startTime": cur, "limit": 1500},
                             timeout=30)
            if r.status_code != 200:
                time.sleep(1.0)
                continue
            d = r.json()
        except Exception:
            time.sleep(1.0)
            continue
        if not d:
            break
        rows.extend(d)
        nxt = int(d[-1][0]) + 60_000
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.09)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ot", "o", "h", "l", "c", "v", "ct",
                                     "qv", "n", "tbv", "tbq", "ig"])
    df["ts"] = pd.to_datetime(df["ot"].astype("int64"), unit="ms")
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return pd.DataFrame({"px_open": df["o"].astype(float),
                         "quote_volume": df["qv"].astype(float)})


def main() -> int:
    p = argparse.ArgumentParser(description="USDT/USDC 무기한 괴리 되돌림")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=1_000_000,
                   help="USDC 계약 최소 일 거래대금")
    p.add_argument("--cache", default=str(ROOT / "runs" / "usdc_1m"))
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "ultra_quote_basis_scan.json"))
    args = p.parse_args()

    os.makedirs(args.cache, exist_ok=True)
    pairs = usdc_perp_pairs()
    log.info("양쪽 계약 있는 코인 %d개", len(pairs))

    data = {}
    for i, (uc, ut) in enumerate(pairs, 1):
        cf = os.path.join(args.cache, f"{uc}_1m.joblib")
        if os.path.exists(cf):
            dc = joblib.load(cf)
        else:
            dc = fetch_klines(uc, args.days)
            if len(dc):
                joblib.dump(dc, cf)
        if not len(dc):
            continue
        dv = dc["quote_volume"].resample("1D").sum().median()
        if not np.isfinite(dv) or dv < args.min_dvol_usd:
            log.info("  %s 유동성 미달 $%.1fM — 제외", uc, dv / 1e6)
            continue
        af = ROOT / "runs" / "aggtrade_1m" / f"{ut}_agg1m.joblib"
        if not af.exists():
            log.info("  %s 아카이브 없음 — 제외", ut)
            continue
        dt = joblib.load(af)
        dt = dt[~dt.index.duplicated(keep="last")].sort_index()
        idx = dc.index.intersection(dt.index)
        if len(idx) < 20000:
            continue
        data[uc] = {
            "pc": dc.loc[idx, "px_open"].astype(float),
            "pt": dt.loc[idx, "px_open"].astype(float),
            "sp_t": float(dt.loc[idx, "eff_spread_bp_adj"].median()),
            "dvol_c": float(dv),
        }
        log.info("%d/%d %-14s 겹침 %d분 / USDC $%.1fM/일",
                 i, len(pairs), uc, len(idx), dv / 1e6)

    if len(data) < 8:
        log.error("사용 가능 코인 부족: %d", len(data))
        return 1

    # ── 괴리의 크기부터 본다. 마찰보다 작으면 나머지는 볼 필요가 없다 ──────────
    print("\n" + "=" * 96)
    print(f"1단계 — 괴리 자체의 크기  ({len(data)}개 코인 / 최근 {args.days}일 / 1분)")
    print("=" * 96)
    print(f"{'코인':<14}{'USDC $/일':>12}{'USDT스프':>9}{'괴리 표준편차':>14}"
          f"{'잔차 표준편차':>14}{'|잔차|>2σ 빈도':>14}")
    print("-" * 96)
    resid = {}
    for uc, d in sorted(data.items(), key=lambda kv: -kv[1]["dvol_c"]):
        b = (d["pc"] / d["pt"] - 1.0) * 1e4                      # 괴리 bp
        slow = b.rolling(DETREND_MIN, min_periods=DETREND_MIN // 4).median()
        r = b - slow                                             # 환율 성분 제거
        sd = float(r.std())
        if not np.isfinite(sd) or sd <= 0:
            continue
        z = r / r.rolling(DETREND_MIN, min_periods=DETREND_MIN // 4).std()
        freq = float((z.abs() > 2).mean())
        resid[uc] = {"r": r, "z": z, "sd": sd}
        print(f"{uc:<14}{d['dvol_c']/1e6:>11,.0f}M{d['sp_t']:>8.2f}bp"
              f"{float(b.std()):>13.1f}bp{sd:>13.1f}bp{freq*100:>13.1f}%")

    med_sd = float(np.median([v["sd"] for v in resid.values()]))
    print("-" * 96)
    print(f"  잔차 표준편차 중앙값 {med_sd:.1f}bp")
    print(f"  두 다리 왕복 마찰 ≈ 스프레드 2개 + 테이커 {TAKER_FEE_BP*4:.0f}bp"
          f" = 대략 {TAKER_FEE_BP*4 + 8:.0f}bp 이상")
    print("=" * 96 + "\n")

    # ── 2단계: 벌어졌을 때 정말 되돌아오는가 (겹치지 않는 표본) ────────────────
    res = []
    for zt in ENTRY_Z:
        for H in HOLDS_MIN:
            pnl, cnt = [], 0
            for uc, d in data.items():
                if uc not in resid:
                    continue
                r, z = resid[uc]["r"], resid[uc]["z"]
                fwd = r.shift(-H) - r          # 괴리가 얼마나 좁혀졌나 (bp)
                sig = np.where(z > zt, -1.0, np.where(z < -zt, 1.0, 0.0))
                sig = pd.Series(sig, index=z.index)
                hit = np.flatnonzero((sig != 0).values & fwd.notna().values)
                # 겹침 금지 — 앞 거래가 끝난 뒤에만 다음 표본을 뜬다
                last = -10**9
                for k in hit:
                    if k - last < H:
                        continue
                    last = k
                    pnl.append(float(sig.iloc[k] * fwd.iloc[k]))
                    cnt += 1
            if cnt < MIN_CELL:
                continue
            a = np.array(pnl)
            gross = float(a.mean())
            se = float(a.std(ddof=1) / np.sqrt(len(a)))
            res.append({"z": zt, "hold_min": H, "n": cnt,
                        "gross_bp": gross, "se_bp": se,
                        "t": gross / se if se > 0 else float("nan")})

    if not res:
        log.error("판정 가능한 칸 없음")
        return 1
    res.sort(key=lambda r: -r["gross_bp"])

    print("=" * 96)
    print("2단계 — 벌어진 뒤 좁혀지는가 (겹치지 않는 표본, gross = 마찰 이전)")
    print("=" * 96)
    print(f"{'진입 z':>8}{'보유(분)':>10}{'표본':>10}{'gross bp':>12}{'오차':>9}{'t':>8}"
          f"   마찰 대비")
    print("-" * 96)
    FRIC = TAKER_FEE_BP * 4 + 8
    for r in res:
        print(f"{r['z']:>8.1f}{r['hold_min']:>10}{r['n']:>10,}"
              f"{r['gross_bp']:>+12.2f}{r['se_bp']:>9.2f}{r['t']:>+8.2f}"
              f"   {'★ 넘음' if r['gross_bp'] > FRIC else f'{r['gross_bp']-FRIC:+.1f}bp'}")
    best = res[0]
    print("=" * 96)
    print(f"  최고: z>={best['z']} / 보유 {best['hold_min']}분 → "
          f"gross {best['gross_bp']:+.2f} ± {best['se_bp']:.2f}bp "
          f"(표본 {best['n']:,})")
    print(f"  마찰 {FRIC:.0f}bp 를 넘는 칸 "
          f"{sum(1 for r in res if r['gross_bp'] > FRIC)}/{len(res)}\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_pairs": len(data), "days": args.days,
                   "median_resid_sd_bp": med_sd,
                   "friction_bp": FRIC, "results": res}, fh,
                  indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
