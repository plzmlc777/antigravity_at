"""초단타 새 부류 — 종목 간 lead-lag 를 분 단위로 잰다.

배경 (2026-08-10, 대표님 지시 "새 부류 시작"):
  지금까지 초단타에서 검증한 것은 둘뿐이다.
    · 자기 종목 주문흐름 방향성 — **닫힘** (283종목 340칸, gross -1.3~+0.5bp)
    · 마켓메이킹 — 진행 중 (가설 1~6, 아직 흑자 없음)
  둘 다 **한 종목 안의 정보**만 썼다. 종목 **사이**의 정보는 초단타에서 한 번도
  안 봤다.

  캠페인에 `cross_symbol_lead_lag` 가 있었으나 **일봉 기준**이다. "BTC 가 움직이면
  알트가 몇 분 뒤 따라간다" 는 시간 척도가 다른 현상이고, 초단타 고유 영역이다.

가설
  선도 종목(BTC/ETH)이 움직였는데 알트가 아직 안 따라왔다면, 그 격차는 메워진다.
    잔차 = 알트수익률 − beta × 선도수익률      (beta 는 롤링 추정)
    잔차가 크게 음수 = 선도는 올랐는데 알트가 안 올랐다 → 알트 롱
  방향을 맞히는 전략이므로 **시장가로 들어간다** — 마찰은 스프레드+테이커 왕복.

인프라를 짓기 전에 디스크 데이터로 먼저 잰다. 오늘 메이킹에서 배운 순서다.

한계 (정직하게)
  1분 해상도다. 진짜 lead-lag 가 2~10초 규모라면 여기서 안 보인다. 여기서
  보이면 그건 **1분 이상 지속되는** 격차라는 뜻이고, WS 로 초 단위를 볼 근거가 된다.
  안 보인다고 초 단위도 없다는 뜻은 아니다 — 그 경우 결론은 "1분 척도엔 없다" 다.

방어 조건 (오늘 데인 것들)
  · lookahead: 신호는 봉 t 종가까지, 체결은 t+1 봉 시가
  · 겹침 금지: 같은 종목에서 보유가 겹치는 거래를 만들지 않는다
  · 마찰은 실측 스프레드(eff_spread_bp_adj) + 테이커 왕복
  · 표본 1,000건 미만 셀은 판정하지 않는다 (오늘 세 번 뒤집혔다)

사용:
  python3 scripts/research/ultra_leadlag_scan.py --days 60 --min-dvol-usd 3000000
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
log = logging.getLogger("ultra_leadlag_scan")

TAKER_FEE_BP = 4.0
BETA_WIN = 1440              # 롤링 beta 창 (분) = 24시간
LOOKBACKS = (1, 2, 3, 5)     # 잔차 계산 창 (분)
HOLDS = (1, 2, 3, 5, 10)     # 보유 (분)
Z_THRESHS = (1.5, 2.0, 3.0)
MIN_CELL = 1000              # 이보다 적은 셀은 판정하지 않는다


def load_close(path: str, days: int) -> pd.Series:
    d = joblib.load(path)
    d = d[~d.index.duplicated(keep="last")].sort_index()
    d = d.loc[d.index >= d.index.max() - pd.Timedelta(days=days)]
    return d


def main() -> int:
    p = argparse.ArgumentParser(description="분 단위 종목간 lead-lag")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--leader", default="BTCUSDT")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--min-dvol-usd", type=float, default=3_000_000)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "ultra_leadlag_scan.json"))
    args = p.parse_args()

    lead_path = os.path.join(args.data_dir, f"{args.leader}_agg1m.joblib")
    if not os.path.exists(lead_path):
        log.error("선도 종목 없음: %s", lead_path)
        return 1
    L = load_close(lead_path, args.days)
    lead_ret = {k: L["vwap"].pct_change(k) for k in LOOKBACKS}
    log.info("선도 %s — %d분 (%s ~ %s)", args.leader, len(L),
             L.index[0].date(), L.index[-1].date())

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if args.limit:
        files = files[:args.limit]

    acc: dict[tuple, list] = {}
    n_used = 0
    for i, f in enumerate(files, 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        if sym == args.leader:
            continue
        try:
            d = load_close(f, args.days)
        except Exception:
            continue
        if len(d) < BETA_WIN * 2:
            continue
        dv = d["quote_volume"].resample("1D").sum().median()
        if not np.isfinite(dv) or dv < args.min_dvol_usd:
            continue
        # 선도와 시각 정렬
        idx = d.index.intersection(L.index)
        if len(idx) < BETA_WIN * 2:
            continue
        n_used += 1
        px = d["vwap"].reindex(idx)
        sp = d["eff_spread_bp_adj"].reindex(idx)
        o = d["px_open"].reindex(idx)

        for k in LOOKBACKS:
            ar = px.pct_change(k)
            lr = lead_ret[k].reindex(idx)
            # 롤링 beta = cov/var (선도 대비 민감도)
            cov = ar.rolling(BETA_WIN, min_periods=BETA_WIN // 4).cov(lr)
            var = lr.rolling(BETA_WIN, min_periods=BETA_WIN // 4).var()
            beta = (cov / var.replace(0, np.nan)).clip(-5, 5)
            resid = ar - beta * lr
            rz = ((resid - resid.rolling(BETA_WIN, min_periods=BETA_WIN // 4).mean())
                  / resid.rolling(BETA_WIN, min_periods=BETA_WIN // 4).std())
            for zt in Z_THRESHS:
                # 잔차가 음수 = 선도 대비 덜 올랐다 → 따라잡는다 → 롱
                d_sig = pd.Series(0.0, index=idx)
                d_sig[(rz < -zt).fillna(False)] = 1.0
                d_sig[(rz > zt).fillna(False)] = -1.0
                fired = np.flatnonzero(d_sig.values != 0)
                if len(fired) == 0:
                    continue
                ov, spv = o.values, sp.values
                for h in HOLDS:
                    rows, last = [], -1
                    for j in fired:
                        ei, xi = j + 1, j + 1 + h
                        if ei <= last or xi >= len(idx):
                            continue
                        e, x = ov[ei], ov[xi]
                        if not (np.isfinite(e) and np.isfinite(x)) or e <= 0:
                            continue
                        g = (x / e - 1.0) * d_sig.values[j]
                        s_ = spv[ei] if np.isfinite(spv[ei]) else np.nanmedian(spv)
                        rows.append((g, s_))
                        last = xi
                    if rows:
                        acc.setdefault((k, zt, h), []).append(np.array(rows))
        if i % 100 == 0:
            log.info("%d/%d (사용 %d)", i, len(files), n_used)

    if not acc:
        log.error("신호 0건")
        return 1
    log.info("사용 %d종목", n_used)

    res = []
    for (k, zt, h), chunks in sorted(acc.items()):
        a = np.vstack(chunks)
        gross, spread = a[:, 0], a[:, 1]
        fric = (spread + 2 * TAKER_FEE_BP) / 1e4
        net = gross - fric
        n = len(net)
        sd = net.std(ddof=1) if n > 1 else 0.0
        t = float(net.mean() / (sd / np.sqrt(n))) if n > 2 and sd > 0 else float("nan")
        res.append({"lookback": k, "z": zt, "hold": h, "n": n,
                    "gross_bp": float(gross.mean() * 1e4),
                    "fric_bp": float(fric.mean() * 1e4),
                    "net_bp": float(net.mean() * 1e4), "t": t})

    res.sort(key=lambda r: -(r["t"] if np.isfinite(r["t"]) else -99))
    print("\n" + "=" * 92)
    print(f"분 단위 lead-lag — 선도 {args.leader} / {n_used}종목 / 최근 {args.days}일 "
          f"/ 시장가 왕복 마찰")
    print("=" * 92)
    print(f"{'창(분)':>7}{'z':>6}{'보유(분)':>9}{'거래수':>10}{'gross bp':>11}"
          f"{'마찰':>8}{'net bp':>10}{'t':>8}  판정")
    print("-" * 92)
    shown = 0
    for r in res:
        if r["n"] < MIN_CELL:
            continue
        shown += 1
        if shown > 20:
            break
        ok = r["net_bp"] > 0 and np.isfinite(r["t"]) and r["t"] >= 3.0
        print(f"{r['lookback']:>7}{r['z']:>6.1f}{r['hold']:>9}{r['n']:>10,}"
              f"{r['gross_bp']:>+11.2f}{r['fric_bp']:>8.2f}{r['net_bp']:>+10.2f}"
              f"{r['t']:>+8.2f}  {'★ PASS' if ok else ''}")
    big = [r for r in res if r["n"] >= MIN_CELL]
    n_pass = sum(1 for r in big if r["net_bp"] > 0 and np.isfinite(r["t"]) and r["t"] >= 3.0)
    print("=" * 92)
    print(f"  표본 {MIN_CELL}건 이상 셀 {len(big)}/{len(res)}  |  "
          f"net>0 & t>=3.0 통과 {n_pass}/{len(big)}")
    if big:
        best = max(big, key=lambda r: r["net_bp"])
        print(f"  최고 net: 창{best['lookback']}분 z{best['z']} 보유{best['hold']}분 "
              f"→ gross {best['gross_bp']:+.2f} net {best['net_bp']:+.2f}bp "
              f"(t {best['t']:+.2f}, {best['n']:,}건)")
    print()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"leader": args.leader, "n_symbols": n_used, "days": args.days,
                   "min_cell": MIN_CELL, "results": res}, fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
