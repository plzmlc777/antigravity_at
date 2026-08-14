"""가설 10 — **시장 전체 주문흐름**(world order flow)이 BTC 를 예측하는가.

배경 (2026-08-11)
  같은 날 세 대역이 전부 닫혔다. 셋 다 "예측 가능한 신호 < 마찰" 이라는 같은 형태다.
      초단기(초~분)   역선택 4~5bp   >  스프레드 획득 1~3bp
      경계(5~30분)    마찰 11~14bp   >  되돌림 0~3bp        (가설 9, 92칸 전부 음수)
      단기(30~90분)   사건 효과가 0.98시그마                 (펀딩 정산, 위약 2종에서 소멸)

  세 번 모두 **개별 종목 기준**으로 봤다 — 자기 종목 주문흐름, BTC 대비 잔차,
  횡단면 순위. 전 종목을 **합친** 압력은 한 번도 안 봤다.

착상
  Anastasopoulos & Gradojevic (EFMA 2025), "Order Flow and Cryptocurrency Returns":
  **world order flow** 가 크립토 수익 예측에서 계수가 가장 높고 유의하다.

  왜 다를 수 있나 — 개별 종목 OFI 는 그 종목 마켓메이커가 즉시 호가에 반영한다
  (그래서 우리 실측이 1~5bp 였다). 그러나 **250종목을 동시에 집계해야 보이는
  압력**은 어느 한 종목의 메이커도 전부 보지 못한다. 정보가 반영되는 경로가
  느릴 수 있다. 우리 아카이브(698종목 60일 1분)는 이미 그걸 갖고 있다.

실행 마찰 — 낙관 금지
  테이커 수수료는 종목과 무관하게 **편도 5bp**. BTC 로 옮긴다고 수수료가 줄지
  않는다. 줄어드는 건 스프레드뿐이다(얇은 종목 4~6bp → BTC 0.02bp).
      테이커 왕복 = 10bp + 스프레드 ≈ **10bp**
      메이커 왕복 =  4bp + 스프레드 ≈ **4bp** (단 체결 보장 없음·역선택 별도)
  둘 다 보고한다.

무엇을 조심하는가
  · **자기 자신 제외** — BTC 를 예측할 때 신호에서 BTC 를 뺀다. 안 빼면 자기상관
    을 예측력으로 착각한다.
  · **lookahead** — 봉 t 는 [t, t+1) 을 담으므로 t+1 이 되어야 안다. 진입은
    **t+1 시가**. 신호와 체결 사이에 한 봉을 반드시 둔다 (2026-08-11 교훈 #83).
  · **겹치는 창 금지** — step >= 보유 (교훈: 겹침만으로 r +0.470 → +0.001).
  · **다른 시계 자산 제외** — underlyingType != COIN 은 미국장 시간에만 움직인다.
  · 유동성 관문 (교훈 #78), 셀 1,000건 미만 판정 금지.

사용:
  python3 scripts/research/world_order_flow_scan.py --days 60
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
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("world_order_flow")

FAPI = "https://fapi.binance.com"
TAKER_RT_BP, MAKER_RT_BP = 10.0, 4.0
HOLDS_MIN = (5, 15, 30, 60, 120)
ZWIN = 1440                 # 신호 z 창 (분)
ZS = (1.0, 1.5, 2.0, 2.5)
MIN_CELL = 1000


def coin_symbols() -> set:
    ex = requests.get(f"{FAPI}/fapi/v1/exchangeInfo", timeout=30).json()
    return {s["symbol"] for s in ex["symbols"]
            if s["contractType"] == "PERPETUAL" and s["status"] == "TRADING"
            and s.get("underlyingType") == "COIN"}


def main() -> int:
    p = argparse.ArgumentParser(description="시장 전체 주문흐름 → BTC 예측")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=5_000_000)
    p.add_argument("--target", default="BTCUSDT")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "world_order_flow_scan.json"))
    args = p.parse_args()

    coins = coin_symbols()
    log.info("COIN 무기한 %d종목", len(coins))

    # 종목별 정규화 OFI 와 원시 순매수액을 모은다
    norm, raw, volm = {}, {}, {}
    tgt_px = None
    for i, f in enumerate(sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib"))), 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        if sym not in coins:
            continue
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
        buy = d["taker_buy_quote"].astype(float)
        sell = d["taker_sell_quote"].astype(float)
        qv = (buy + sell).replace(0, np.nan)
        norm[sym] = ((buy - sell) / qv)      # -1 ~ +1, 종목 크기 무관
        raw[sym] = (buy - sell)              # 달러 순매수
        volm[sym] = qv
        if sym == args.target:
            tgt_px = d["px_open"].astype(float)
            tgt_sp = float(d["eff_spread_bp_adj"].median())
        if i % 150 == 0:
            log.info("%d 파일 (사용 %d)", i, len(norm))

    if tgt_px is None:
        log.error("대상 %s 없음", args.target)
        return 1
    log.info("신호 구성 종목 %d / 대상 %s 스프레드 %.3fbp", len(norm), args.target, tgt_sp)
    if len(norm) < 50:
        log.error("종목 부족")
        return 1

    N = pd.DataFrame(norm).sort_index()
    R = pd.DataFrame(raw).reindex_like(N)
    V = pd.DataFrame(volm).reindex_like(N)
    # **자기 자신 제외** — 안 빼면 자기상관을 예측력으로 착각한다
    cols = [c for c in N.columns if c != args.target]
    N, R, V = N[cols], R[cols], V[cols]

    sigs = {
        "동일가중 (폭)": N.mean(axis=1),                       # 종목 하나씩 한 표
        "거래대금가중 (규모)": R.sum(axis=1) / V.sum(axis=1),    # 큰 종목이 지배
        "참여율 (몇 %가 매수우위)": (N > 0).mean(axis=1) - 0.5,   # 부호만
    }

    px = tgt_px.reindex(N.index).ffill()
    res = []
    for name, s in sigs.items():
        s = s.replace([np.inf, -np.inf], np.nan)
        z = (s - s.rolling(ZWIN, min_periods=ZWIN // 4).mean()) \
            / s.rolling(ZWIN, min_periods=ZWIN // 4).std()
        for H in HOLDS_MIN:
            # 봉 t 의 신호는 t+1 에야 안다 → t+1 시가 진입, t+1+H 시가 청산
            entry = px.shift(-1)
            exit_ = px.shift(-1 - H)
            fwd = (exit_ / entry - 1.0) * 1e4
            ok = z.notna() & fwd.notna()
            for zt in ZS:
                sig = pd.Series(np.where(z > zt, 1.0, np.where(z < -zt, -1.0, 0.0)),
                                index=z.index)
                hit = np.flatnonzero((sig != 0).values & ok.values)
                pnl, last = [], -10 ** 9
                for k in hit:
                    if k - last < H + 1:      # 겹침 금지
                        continue
                    last = k
                    pnl.append(float(sig.iloc[k] * fwd.iloc[k]))
                if len(pnl) < MIN_CELL:
                    continue
                a = np.array(pnl)
                se = a.std(ddof=1) / np.sqrt(len(a))
                res.append({"signal": name, "hold": H, "z": zt, "n": len(a),
                            "gross_bp": float(a.mean()), "se_bp": float(se),
                            "t": float(a.mean() / se) if se else np.nan,
                            "net_taker": float(a.mean() - TAKER_RT_BP - tgt_sp),
                            "net_maker": float(a.mean() - MAKER_RT_BP - tgt_sp)})

    if not res:
        log.error("판정 가능한 칸 없음")
        return 1
    df = pd.DataFrame(res).sort_values("gross_bp", ascending=False)

    print("\n" + "=" * 104)
    print(f"가설 10 — 시장 전체 주문흐름 → {args.target}  "
          f"({len(cols)}종목 신호 / 최근 {args.days}일 / 자기 자신 제외 / 겹침 없음)")
    print("=" * 104)
    print(f"  마찰: 테이커 왕복 {TAKER_RT_BP:.0f}bp / 메이커 왕복 {MAKER_RT_BP:.0f}bp "
          f"+ {args.target} 스프레드 {tgt_sp:.3f}bp")
    print("-" * 104)
    print(f"{'신호':<24}{'보유':>6}{'z':>6}{'표본':>9}{'gross bp':>11}{'오차':>8}"
          f"{'t':>8}{'net(테이커)':>13}{'net(메이커)':>13}")
    print("-" * 104)
    for _, r in df.head(20).iterrows():
        mark = ""
        if r.net_taker > 0 and r.t >= 3.0:
            mark = "  ★ 테이커 PASS"
        elif r.net_maker > 0 and r.t >= 3.0:
            mark = "  ○ 메이커만"
        print(f"{r.signal:<24}{r.hold:>6.0f}{r.z:>6.1f}{r.n:>9,.0f}{r.gross_bp:>+11.2f}"
              f"{r.se_bp:>8.2f}{r.t:>+8.2f}{r.net_taker:>+13.2f}{r.net_maker:>+13.2f}{mark}")
    print("-" * 104)
    nt = int(((df.net_taker > 0) & (df.t >= 3.0)).sum())
    nm = int(((df.net_maker > 0) & (df.t >= 3.0)).sum())
    print(f"  테이커 통과 {nt}/{len(df)}   메이커 통과 {nm}/{len(df)}")
    best = df.iloc[0]
    print(f"  최고 gross: {best.signal} / 보유 {best.hold:.0f}분 / z>={best.z} → "
          f"{best.gross_bp:+.2f} ± {best.se_bp:.2f}bp (표본 {best.n:,.0f})")
    print("=" * 104 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"target": args.target, "n_signal_symbols": len(cols),
                   "days": args.days, "target_spread_bp": tgt_sp,
                   "results": res}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
