"""마켓 메이킹 경제성 실측 — 종목별로 "호가를 대면 버는가"를 markout 으로 잰다.

배경 (2026-08-09, 대표님 지시로 방향 전환):
  방향성 단타는 데이터가 부정했다. `ultra_signal_scan.py` 를 5분·1분 두 해상도로
  283종목 60일에 돌려 약 340칸을 훑었으나, 진짜 단타 빈도(종목당 일 5~10회)에서
  gross 엣지가 -1.3 ~ +5.3bp 였고 마찰은 테이커 11bp / 메이커 4bp 였다. 표본이
  수만 건이라 검정력 문제가 아니라 **엣지가 없다**.

  빈도를 올릴수록 마찰이 곱해지는데 방향성 엣지는 0 에 수렴하므로, 이 빈도대에서
  성립하는 형태는 **마찰을 내는 쪽이 아니라 받는 쪽** — 마켓 메이킹이다.

  그런데 즉시 걸리는 산술 문제가 있다. Binance USDS-M VIP0 메이커 수수료는
  **리베이트가 아니라 +2bp 지불**이라 양방향 체결이면 왕복 4bp 다. 실측 스프레드는
  BTC 0.015bp / SOL 1.31bp 이므로 **가장 유동적인 종목은 스프레드를 다 먹어도
  수수료를 못 낸다.** 그래서 "어느 종목에서 성립하는가"를 먼저 갈라야 한다.

무엇을 재는가 — markout
  테이커 매수는 **매도호가**에, 테이커 매도는 **매수호가**에 체결된다. 내가 그
  반대편에 서 있었다면의 손익이 곧 메이킹 손익이다.

    내가 ask 에 팔았다면   :  (체결가 − Δ분 뒤 중간가)
    내가 bid 에 샀다면     :  (Δ분 뒤 중간가 − 체결가)

  체결가는 aggTrades 에서 방향별 VWAP 로 얻는다(`vwap_buy` / `vwap_sell`).
  이 값이 **스프레드 획득에서 역선택 비용을 뺀 순액**이다 — 스프레드가 넓어도
  내가 판 직후 가격이 오르면(정보 있는 매수자에게 당하면) 손실이다. 그래서
  스프레드만 보고 판단하면 안 되고 markout 으로 봐야 한다.

  체결량 가중으로 합산하고 메이커 수수료를 뺀다.

**이 측정은 상한이다** — 아래를 낙관적으로 가정한다
  1. 항상 최우선 호가에 있고, 흐름에 비례해 체결된다 (실제로는 큐 위치가 결정한다)
  2. 재고 한도·헤지·호가 조정이 없다
  3. 취소/재게시 지연이 없다
  따라서 여기서 **음수가 나오면 메이킹은 죽은 것**이고, 양수라도 그 값이 그대로
  실현되지는 않는다. 실현 여부는 큐 데이터(WS bookTicker, `ultra_ws_collector.py`)가
  쌓여야 판정된다.

사용:
  python3 scripts/research/ultra_mm_feasibility.py --days 60 --min-dvol-usd 1000000
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
log = logging.getLogger("ultra_mm_feasibility")

MAKER_FEE_BP = 2.0                     # VIP0 편도. 리베이트 아님 — 지불이다.
HORIZONS = (1, 5, 15, 30, 60)          # markout 지평 (분)


def markout(df: pd.DataFrame, h: int) -> dict:
    """분 단위 markout. 방향별 VWAP 를 체결가로, h분 뒤 VWAP 를 중간가 대용으로 쓴다."""
    mid_fwd = df["vwap"].shift(-h)
    px = df["vwap"]
    ok = (df["vwap_buy"].notna() & df["vwap_sell"].notna()
          & mid_fwd.notna() & (px > 0))
    if ok.sum() < 500:
        return {}
    d = df[ok]
    fwd = mid_fwd[ok]
    p = px[ok]

    # 내가 ask 에 판 손익 / bid 에 산 손익 (bp)
    sell_bp = (d["vwap_buy"] - fwd) / p * 1e4
    buy_bp = (fwd - d["vwap_sell"]) / p * 1e4
    wq_s, wq_b = d["taker_buy_quote"], d["taker_sell_quote"]   # 각 방향 체결량
    tot = float(wq_s.sum() + wq_b.sum())
    if tot <= 0:
        return {}

    gross = float((sell_bp * wq_s).sum() + (buy_bp * wq_b).sum()) / tot
    # 참고: 스프레드 절반(역선택 없을 때의 이론 획득).
    # 분 단위 원시추정(vwap_buy-vwap_sell)은 이상치에 끌려가므로 **틱 하한이 적용된
    # 안정 측정치**를 쓴다 (예: ASMLUSDT 스프레드 0.06bp 인데 원시추정 반스프 3.73bp).
    half_spread = float((d["eff_spread_bp_adj"] / 2 * (wq_s + wq_b)).sum() / tot)
    net = gross - MAKER_FEE_BP

    # 재고 위험 대리지표 — 한쪽 흐름 쏠림 (0=균형, 1=완전 편향)
    imb = float(abs(wq_s.sum() - wq_b.sum()) / tot)
    # 분당 체결 흐름(내 호가를 지나가는 양)
    flow = float((wq_s + wq_b).mean())
    n = int(ok.sum())
    # 분 단위 markout 은 자기상관이 있어 유효표본이 n 보다 작다. 지평 h 만큼 겹치므로
    # n/h 로 낮춰 t 를 보수적으로 계산한다 — 겹침으로 t 를 부풀린 전례가 있다
    # (2026-08-09 창 겹침 사건, feedback-overlapping-window-persistence-artifact).
    n_eff = max(n // max(h, 1), 2)
    sd = float(((sell_bp * wq_s + buy_bp * wq_b) / (wq_s + wq_b)).std(ddof=1))
    t = float((gross - MAKER_FEE_BP) / (sd / np.sqrt(n_eff))) if sd > 0 else float("nan")
    return {"h": h, "n_min": n, "n_eff": n_eff, "gross_bp": gross, "half_spread_bp": half_spread,
            "adverse_bp": half_spread - gross, "net_bp": net, "t": t,
            "flow_usd_per_min": flow, "imbalance": imb}


def main() -> int:
    p = argparse.ArgumentParser(description="마켓 메이킹 경제성 (markout)")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=1_000_000)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "ultra_mm_feasibility.json"))
    args = p.parse_args()

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if args.limit:
        files = files[:args.limit]

    rows = []
    for i, f in enumerate(files, 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        try:
            df = joblib.load(f)
        except Exception:
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df.loc[df.index >= df.index.max() - pd.Timedelta(days=args.days)]
        if len(df) < 5000:
            continue
        dv = df["quote_volume"].resample("1D").sum().median()
        if not np.isfinite(dv) or dv < args.min_dvol_usd:
            continue
        rec = {"symbol": sym, "dvol_usd": float(dv),
               "spread_bp": float(df["eff_spread_bp_adj"].median())}
        any_h = False
        for h in HORIZONS:
            m = markout(df, h)
            if m:
                any_h = True
                for k, v in m.items():
                    if k != "h":
                        rec[f"{k}_h{h}"] = v
        if any_h:
            rows.append(rec)
        if i % 100 == 0:
            log.info("%d/%d (적격 %d)", i, len(files), len(rows))

    if not rows:
        log.error("적격 종목 0")
        return 1
    R = pd.DataFrame(rows)

    print("\n" + "=" * 100)
    print(f"마켓 메이킹 경제성 — {len(R)}종목 / 최근 {args.days}일 / "
          f"메이커 수수료 {MAKER_FEE_BP}bp 편도 (VIP0, 지불)")
    print("=" * 100)
    print("  ── 지평별 전체 요약 (종목 중앙값) ──")
    print(f"      {'Δ':>5}{'반스프레드':>12}{'역선택':>10}{'gross':>10}"
          f"{'수수료':>8}{'net':>10}{'net>0 종목':>12}")
    for h in HORIZONS:
        c = f"_h{h}"
        if f"net_bp{c}" not in R:
            continue
        pos = int((R[f"net_bp{c}"] > 0).sum())
        print(f"      {h:>4}분{R[f'half_spread_bp{c}'].median():>12.3f}"
              f"{R[f'adverse_bp{c}'].median():>10.3f}{R[f'gross_bp{c}'].median():>10.3f}"
              f"{MAKER_FEE_BP:>8.1f}{R[f'net_bp{c}'].median():>10.3f}"
              f"{pos:>7}/{len(R):<5}")

    h0 = HORIZONS[1]
    c = f"_h{h0}"
    if f"net_bp{c}" in R:
        top = R.nlargest(15, f"net_bp{c}")
        print(f"\n  ── Δ={h0}분 기준 상위 15종목 ──")
        print(f"      {'종목':<14}{'일거래대금':>12}{'스프레드':>10}{'반스프':>9}"
              f"{'역선택':>9}{'net bp':>9}{'t':>8}{'흐름$/분':>11}{'쏠림':>7}")
        for r in top.itertuples():
            print(f"      {r.symbol:<14}{getattr(r, 'dvol_usd')/1e6:>10.0f}M"
                  f"{r.spread_bp:>10.2f}{getattr(r, f'half_spread_bp{c}'):>9.2f}"
                  f"{getattr(r, f'adverse_bp{c}'):>9.2f}{getattr(r, f'net_bp{c}'):>9.2f}"
                  f"{getattr(r, f't{c}'):>8.2f}"
                  f"{getattr(r, f'flow_usd_per_min{c}')/1e3:>9.0f}k"
                  f"{getattr(r, f'imbalance{c}'):>7.2f}")
        n_ok = int(((R[f"net_bp{c}"] > 0) & (R[f"t{c}"] > 3.0)).sum())
        print(f"\n  net>0 이고 t>3 인 종목: {n_ok}/{len(R)}")
    print("=" * 100 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    R.to_json(args.out, orient="records", indent=2)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
