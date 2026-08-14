"""커뮤니티 전략 검증 — **델타 중립 펀딩 수확** (cash-and-carry).

왜 이걸 고르나
  크립토 커뮤니티(r/algotrading·Elite Trader 계열)에서 가장 널리 논의되는 전략이다.
  현물 매수 + 무기한 매도로 방향 위험을 없애고 **펀딩만 걷는다**.
  오늘 우리를 열 번 막은 문제를 정면으로 피한다 — **예측이 아니라 캐리**다.
  신호가 필요 없고, 마찰을 한 번 내고 몇 주에 걸쳐 나눈다.

  (검색에서 확인된 커뮤니티 통념: "스캘핑은 소매에게 거의 불가능하다. $100K+
   와 전용 인프라·거래소 직계약이 없으면 단순한 전략보다 못하다. 속도 엣지는
   기관이 이미 차익거래로 없앴다." — 오늘 우리 실측과 정확히 일치한다.)

손익 구조 (여기가 핵심)
  포지션: 현물 롱 + 무기한 숏.  basis = (무기한 - 현물) / 현물
      손익 = -(basis_청산 - basis_진입) + Σ펀딩 - 마찰

  커뮤니티 논의가 자주 빠뜨리는 것: **펀딩이 공짜가 아니다.**
  펀딩이 높다는 건 무기한이 현물보다 비싸다는 뜻(basis 양수)이고, 그 상태에서
  숏을 치면 basis 수렴이 이익이 된다 — 여기까진 좋다. 그러나 basis 가 더
  벌어지면 손실이고, 그 손실이 펀딩 수입을 넘을 수 있다. **둘을 같이 재야 한다.**

마찰 (API 원본, 낙관 금지)
  현물 taker **10bp** (`/sapi/v1/asset/tradeFee` 실측, VIP0)
  무기한 taker **5bp** (`/fapi/v1/commissionRate` 실측, feeTier 0)
      진입 15bp + 청산 15bp = **왕복 30bp** + 양쪽 스프레드
  펀딩이 일 2~3bp 수준이면 **본전까지만 10~15일**이다. 그래서 장기 보유 전략이다.

무엇을 조심하는가
  · **겹치는 창 금지** — 보유 간격 >= 보유 기간.
  · basis 를 진입·청산 **같은 방식**으로 잰다 (둘 다 8시간 경계 종가).
  · 펀딩은 **보유 구간에 실제로 정산된 것만** 합산 (미래 펀딩 금지).
  · 유동성 관문 — 현물·무기한 양쪽 다 두꺼운 종목만.
  · 표본 300건 미만 셀은 판정하지 않는다.

사용:
  python3 scripts/research/cash_and_carry_scan.py --days 365
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
log = logging.getLogger("cash_and_carry")

FAPI, SAPI = "https://fapi.binance.com", "https://api.binance.com"
SPOT_TAKER_BP, PERP_TAKER_BP = 10.0, 5.0
ROUND_TRIP_BP = 2 * (SPOT_TAKER_BP + PERP_TAKER_BP)   # 진입+청산 4다리
HOLD_DAYS = (7, 14, 30, 60)
MIN_CELL = 300


def klines(base: str, path: str, sym: str, interval: str, start_ms: int) -> pd.DataFrame:
    rows, cur = [], start_ms
    end = int(time.time() * 1000)
    while cur < end:
        try:
            r = requests.get(f"{base}{path}",
                             params={"symbol": sym, "interval": interval,
                                     "startTime": cur, "limit": 1000}, timeout=30)
            if r.status_code != 200:
                time.sleep(0.5)
                break
            d = r.json()
        except Exception:
            time.sleep(0.5)
            break
        if not d:
            break
        rows.extend(d)
        nxt = int(d[-1][0]) + 1
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.06)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).iloc[:, :6]
    df.columns = ["ot", "o", "h", "l", "c", "v"]
    df["ts"] = pd.to_datetime(df["ot"].astype("int64"), unit="ms")
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df[["c"]].astype(float).rename(columns={"c": "px"})


def funding(sym: str, start_ms: int) -> pd.Series:
    rows, cur = [], start_ms
    end = int(time.time() * 1000)
    while cur < end:
        try:
            r = requests.get(f"{FAPI}/fapi/v1/fundingRate",
                             params={"symbol": sym, "startTime": cur, "limit": 1000},
                             timeout=30)
            if r.status_code != 200:
                break
            d = r.json()
        except Exception:
            break
        if not d:
            break
        rows.extend(d)
        nxt = int(d[-1]["fundingTime"]) + 1
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.06)
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series({pd.to_datetime(int(x["fundingTime"]), unit="ms"): float(x["fundingRate"])
                   for x in rows}).sort_index()
    return s[~s.index.duplicated(keep="last")]


def main() -> int:
    p = argparse.ArgumentParser(description="델타 중립 펀딩 수확")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--top", type=int, default=60, help="유동성 상위 몇 종목")
    p.add_argument("--cache", default=str(ROOT / "runs" / "carry_cache"))
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "cash_and_carry_scan.json"))
    args = p.parse_args()
    os.makedirs(args.cache, exist_ok=True)

    sp = requests.get(f"{SAPI}/api/v3/exchangeInfo", timeout=30).json()
    spot = {s["symbol"] for s in sp["symbols"]
            if s["status"] == "TRADING" and s["quoteAsset"] == "USDT"}
    bn = requests.get(f"{FAPI}/fapi/v1/exchangeInfo", timeout=30).json()
    per = {s["symbol"] for s in bn["symbols"]
           if s["contractType"] == "PERPETUAL" and s["status"] == "TRADING"
           and s.get("underlyingType") == "COIN"}
    both = sorted(spot & per)
    tk = requests.get(f"{FAPI}/fapi/v1/ticker/24hr", timeout=30).json()
    vol = {d["symbol"]: float(d.get("quoteVolume") or 0) for d in tk}
    both.sort(key=lambda s: -vol.get(s, 0))
    syms = both[:args.top]
    log.info("현물·무기한 양쪽 %d종목 → 유동성 상위 %d 사용", len(both), len(syms))

    start_ms = int((time.time() - args.days * 86400) * 1000)
    recs = []
    for i, sym in enumerate(syms, 1):
        cf = os.path.join(args.cache, f"{sym}.joblib")
        if os.path.exists(cf):
            df = joblib.load(cf)
        else:
            pp = klines(FAPI, "/fapi/v1/klines", sym, "8h", start_ms)
            ss = klines(SAPI, "/api/v3/klines", sym, "8h", start_ms)
            fr = funding(sym, start_ms)
            if pp.empty or ss.empty or fr.empty:
                log.info("  %s 데이터 부족 — 제외", sym)
                continue
            df = pd.DataFrame({"perp": pp["px"], "spot": ss["px"]}).dropna()
            # 펀딩은 정산 시각 그대로 8시간 격자에 맞춘다
            df["fr"] = fr.reindex(df.index, method="nearest",
                                  tolerance=pd.Timedelta("10min")).fillna(0.0)
            joblib.dump(df, cf)
        if len(df) < 200:
            continue
        df["basis"] = (df["perp"] / df["spot"] - 1.0)
        recs.append((sym, df))
        if i % 10 == 0:
            log.info("%d/%d", i, len(syms))

    if len(recs) < 15:
        log.error("사용 가능 종목 부족: %d", len(recs))
        return 1
    log.info("사용 종목 %d", len(recs))

    res = []
    for H in HOLD_DAYS:
        n8 = H * 3                       # 8시간 봉 개수
        for qlab, lo, hi in (("전체", 0.0, 1.0), ("펀딩 상위30%", 0.7, 1.0),
                             ("펀딩 상위10%", 0.9, 1.0), ("펀딩 하위30%", 0.0, 0.3)):
            pnl = []
            for sym, df in recs:
                fr = df["fr"]
                pr = fr.rolling(90 * 3, min_periods=30).rank(pct=True)
                b = df["basis"].values
                f = fr.values
                pv = pr.values
                for k in range(0, len(df) - n8, n8):     # 겹침 없음
                    if not np.isfinite(pv[k]) or not (lo <= pv[k] < hi):
                        continue
                    carry = float(np.nansum(f[k + 1:k + 1 + n8])) * 1e4   # 보유 중 실제 정산분
                    conv = -(b[k + n8] - b[k]) * 1e4                      # basis 수렴 손익
                    pnl.append(carry + conv - ROUND_TRIP_BP)
            if len(pnl) < MIN_CELL:
                continue
            a = np.array(pnl)
            se = a.std(ddof=1) / np.sqrt(len(a))
            ann = a.mean() / 1e4 * (365.0 / H) * 100
            res.append({"hold_d": H, "filter": qlab, "n": len(a),
                        "net_bp": float(a.mean()), "se_bp": float(se),
                        "t": float(a.mean() / se) if se else np.nan,
                        "ann_pct": float(ann),
                        "win": float((a > 0).mean() * 100)})

    df = pd.DataFrame(res)
    print("\n" + "=" * 104)
    print(f"델타 중립 펀딩 수확 — {len(recs)}종목 / 최근 {args.days}일 / 겹침 없음")
    print("=" * 104)
    print(f"  마찰: 현물 taker {SPOT_TAKER_BP:.0f}bp + 무기한 taker {PERP_TAKER_BP:.0f}bp, "
          f"진입·청산 4다리 = **왕복 {ROUND_TRIP_BP:.0f}bp** (스프레드 별도)")
    print(f"  손익 = 보유 중 실제 정산 펀딩 + basis 수렴 - 왕복 마찰")
    print("-" * 104)
    print(f"{'보유(일)':>9}{'진입조건':<16}{'표본':>8}{'net bp':>10}{'오차':>8}{'t':>8}"
          f"{'승률%':>8}{'연환산%':>10}  판정")
    print("-" * 104)
    for _, r in df.sort_values(["hold_d", "filter"]).iterrows():
        ok = r.net_bp > 0 and r.t >= 3.0
        print(f"{r.hold_d:>9.0f}{r['filter']:<16}{r.n:>8,.0f}{r.net_bp:>+10.2f}"
              f"{r.se_bp:>8.2f}{r.t:>+8.2f}{r.win:>8.1f}{r.ann_pct:>+10.2f}  "
              f"{'★ PASS' if ok else ''}")
    n_pass = int(((df.net_bp > 0) & (df.t >= 3.0)).sum())
    print("-" * 104)
    print(f"  net>0 & t>=3.0 통과 {n_pass}/{len(df)}")
    if len(df):
        b = df.sort_values("net_bp", ascending=False).iloc[0]
        print(f"  최고: 보유 {b.hold_d:.0f}일 / {b['filter']} → {b.net_bp:+.2f} ± {b.se_bp:.2f}bp "
              f"(연환산 {b.ann_pct:+.2f}%, 승률 {b.win:.1f}%, 표본 {b.n:,.0f})")
    print("=" * 104 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"n_symbols": len(recs), "days": args.days,
                   "round_trip_bp": ROUND_TRIP_BP, "results": res}, fh,
                  indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
