"""Ad-hoc 후속: 2026 Q1 잠정실적 후 '진입점' 탐색.

질문: 발표 D+1 반응 이후에 매수해서 들어갈 창이 있는가?
  - 반응(D+1) 이후 close 진입 → D+1+K close 청산 forward return
  - D+1 이 급등이었는지 급락이었는지로 분할
  - 급등 후 계속 오르면 = 추격 매수 창 (momentum/PEAD)
  - 급락 후 반등하면 = 저가 매수 창 (mean-reversion / 과잉반응)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from app.services.dart_adapter import iter_disclosures_chunked  # noqa: E402
from app.services.disclosure_parser import is_earnings_event, is_subsidiary_only  # noqa: E402
from scripts.research._naver_kr_equity import build_universe, get_ohlcv_cached, warm_cache  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("q1_drift")

PRELIM_BGN, PRELIM_END = "20260401", "20260525"
OHLCV_BGN, OHLCV_END = "20260301", "20260630"
HOLDS = [1, 3, 5]           # D+1 이후 추가 보유일 (진입=D+1 close)
JUMP_THR = 0.03             # D+1 |ret| >= 3% 를 급등/급락으로 간주


def sweep(universe_codes):
    rows = []
    for cls in ("Y", "K"):
        for r in iter_disclosures_chunked(bgn_de=PRELIM_BGN, end_de=PRELIM_END,
                                          corp_cls=cls, pblntf_ty="I", chunk_days=30):
            nm = r.get("report_nm", "")
            if not is_earnings_event(nm) or is_subsidiary_only(nm):
                continue
            code = (r.get("stock_code") or "").strip()
            if code not in universe_codes:
                continue
            rows.append({"rcept_dt": r["rcept_dt"], "rcept_no": r.get("rcept_no"),
                         "code": code})
    df = pd.DataFrame(rows).drop_duplicates("rcept_no")
    df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d")
    return df.sort_values("rcept_dt").drop_duplicates("code", keep="first")


def main():
    uni = build_universe(200, 150)
    codes_all = set(uni["itemCode"].astype(str).str.zfill(6))
    ev = sweep(codes_all)
    warm_cache(sorted(ev["code"].unique()), OHLCV_BGN, OHLCV_END, sleep_s=0.05)

    recs = []
    for _, e in ev.iterrows():
        df = get_ohlcv_cached(e["code"], OHLCV_BGN, OHLCV_END)
        if df.empty:
            continue
        df = df.set_index("date").sort_index()
        pos = int(np.searchsorted(df.index.values, e["rcept_dt"].to_datetime64(), side="right"))
        if pos < 1 or pos >= len(df):
            continue
        c_prev, c_d1 = float(df["close"].iloc[pos - 1]), float(df["close"].iloc[pos])
        if c_prev <= 0 or c_d1 <= 0:
            continue
        rec = {"code": e["code"], "d1_ret": c_d1 / c_prev - 1.0}
        for k in HOLDS:
            j = pos + k
            rec[f"fwd{k}"] = (float(df["close"].iloc[j]) / c_d1 - 1.0) if j < len(df) else np.nan
        recs.append(rec)
    r = pd.DataFrame(recs)

    up = r[r["d1_ret"] >= JUMP_THR]
    dn = r[r["d1_ret"] <= -JUMP_THR]
    print(f"\n=== 2026 Q1 잠정실적 반응 후 진입점 탐색 (n={len(r)}) ===")
    print(f"급등군(D+1 ≥ +3%): {len(up)}종 | 급락군(D+1 ≤ -3%): {len(dn)}종")
    print(f"\n[진입 = D+1 종가, 청산 = D+1 이후 K거래일 종가 / 순수 gross, 수수료 미차감]")
    print(f"{'':<18}{'D+1반응':>9}{'  →+1d':>9}{'  →+3d':>9}{'  →+5d':>9}")
    for label, g in [("급등군 후 (추격)", up), ("급락군 후 (저가매수)", dn), ("전체", r)]:
        row = f"{label:<18}{g['d1_ret'].mean()*100:>+8.2f}%"
        for k in HOLDS:
            row += f"{g[f'fwd{k}'].mean()*100:>+8.2f}%"
        print(row)
    print("\n[+5d 진입 후 상승 비율 (win rate)]")
    for label, g in [("급등군 후", up), ("급락군 후", dn)]:
        wr = (g["fwd5"] > 0).mean() * 100
        print(f"  {label}: {wr:.0f}%  (n={g['fwd5'].notna().sum()})")


if __name__ == "__main__":
    main()
