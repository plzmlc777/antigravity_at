"""Ad-hoc: 2026 Q1 — 분기보고서 D+1 상승률 > 잠정실적 D+1 상승률 역전 케이스.

전체 잠정실적 종목(181)에 대해 잠정 D+1 vs 분기보고서 D+1 을 매칭하고,
분기보고서 반응이 더 컸던(역전) 케이스를 찾는다. 같은 날 동시제출은 제외.
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
from app.services.disclosure_parser import (  # noqa: E402
    is_earnings_event, is_subsidiary_only, classify, PERIODIC_REPORT,
)
from scripts.research._naver_kr_equity import build_universe, get_ohlcv_cached, warm_cache  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("report_beats_prelim")

PRELIM_BGN, PRELIM_END = "20260401", "20260525"
QREPORT_BGN, QREPORT_END = "20260501", "20260531"
OHLCV_BGN, OHLCV_END = "20260301", "20260630"
CSV_PATH = ROOT / "runs" / "dart_track" / "q1_2026_report_beats_prelim.csv"


def sweep(pblntf_ty, bgn, end, universe_codes, keep):
    rows = []
    for cls in ("Y", "K"):
        for r in iter_disclosures_chunked(bgn_de=bgn, end_de=end, corp_cls=cls,
                                          pblntf_ty=pblntf_ty, chunk_days=30):
            nm = r.get("report_nm", "")
            if not keep(nm):
                continue
            code = (r.get("stock_code") or "").strip()
            if code not in universe_codes:
                continue
            rows.append({"rcept_dt": r["rcept_dt"], "rcept_no": r.get("rcept_no"),
                         "code": code, "corp_name": r.get("corp_name")})
    df = pd.DataFrame(rows).drop_duplicates("rcept_no")
    df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d")
    return df.sort_values("rcept_dt").drop_duplicates("code", keep="first")


def d1_ret(code, event_dt):
    df = get_ohlcv_cached(code, OHLCV_BGN, OHLCV_END)
    if df.empty:
        return None, None
    df = df.set_index("date").sort_index()
    pos = int(np.searchsorted(df.index.values, event_dt.to_datetime64(), side="right"))
    if pos < 1 or pos >= len(df):
        return None, None
    cp, cd = float(df["close"].iloc[pos - 1]), float(df["close"].iloc[pos])
    if cp <= 0 or cd <= 0:
        return None, None
    return pd.Timestamp(df.index[pos]).strftime("%Y-%m-%d"), cd / cp - 1.0


def is_q_report(nm):
    return classify(nm) is PERIODIC_REPORT and "분기보고서" in nm.replace("[정정]", "")


def main():
    uni = build_universe(200, 150)
    codes_all = set(uni["itemCode"].astype(str).str.zfill(6))
    name_by = dict(zip(uni["itemCode"].astype(str).str.zfill(6), uni["stockName"]))

    prelim = sweep("I", PRELIM_BGN, PRELIM_END, codes_all,
                   lambda nm: is_earnings_event(nm) and not is_subsidiary_only(nm))
    qrep = sweep("A", QREPORT_BGN, QREPORT_END, codes_all, is_q_report)
    qmap = {r["code"]: r for _, r in qrep.iterrows()}

    warm_cache(sorted(prelim["code"].unique()), OHLCV_BGN, OHLCV_END, sleep_s=0.05)

    recs = []
    for _, e in prelim.iterrows():
        code = e["code"]
        q = qmap.get(code)
        if q is None:
            continue
        p_date, p_ret = e["rcept_dt"].strftime("%Y-%m-%d"), None
        pd1, p_ret = d1_ret(code, e["rcept_dt"])
        qd1, q_ret = d1_ret(code, q["rcept_dt"])
        if p_ret is None or q_ret is None:
            continue
        # 같은 날 동시제출(=동일 이벤트) 제외
        if e["rcept_dt"] == q["rcept_dt"]:
            continue
        recs.append({
            "code": code, "name": name_by.get(code, e["corp_name"]),
            "prelim_date": p_date, "prelim_d1_ret": p_ret,
            "qreport_date": q["rcept_dt"].strftime("%Y-%m-%d"), "qreport_d1_ret": q_ret,
            "gap_q_minus_p": q_ret - p_ret,
        })
    df = pd.DataFrame(recs)
    beats = df[df["qreport_d1_ret"] > df["prelim_d1_ret"]].sort_values(
        "qreport_d1_ret", ascending=False).reset_index(drop=True)
    df.sort_values("gap_q_minus_p", ascending=False).to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

    print(f"\n=== 2026 Q1: 분기보고서 D+1 > 잠정실적 D+1 역전 케이스 ===")
    print(f"매칭된 종목 {len(df)}종 중 역전(분기보고서 반응이 더 큼) {len(beats)}종\n")
    print(f"{'종목':<14}{'잠정일':<12}{'잠정D+1':>9}  {'분기보고일':<12}{'보고D+1':>9}{'  격차':>9}")
    for r in beats.itertuples():
        print(f"{str(r.name)[:12]:<14}{r.prelim_date:<12}{r.prelim_d1_ret*100:>+8.2f}%  "
              f"{r.qreport_date:<12}{r.qreport_d1_ret*100:>+8.2f}%{r.gap_q_minus_p*100:>+8.2f}%p")
    if len(beats):
        print(f"\n역전군 분기보고서 D+1 평균: {beats['qreport_d1_ret'].mean()*100:+.2f}% | "
              f"양(+) 비율 {(beats['qreport_d1_ret']>0).mean()*100:.0f}%")
    print(f"\nCSV(전체 매칭, 격차순): {CSV_PATH}")


if __name__ == "__main__":
    main()
