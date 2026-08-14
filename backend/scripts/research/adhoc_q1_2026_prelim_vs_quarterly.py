"""Ad-hoc: 2026 Q1 잠정실적 D+1 상승률 top-30 vs 분기보고서 D+1 상승률 비교.

사용자 요청 (2026-07-11):
  올해(2026) 1분기 잠정실적 발표일 +1일(발표 다음 거래일) 상승률 top-30을 뽑고,
  같은 종목들의 분기보고서 제출일 +1일 상승률과 비교.

상승률 정의: 공시일(rcept_dt) 이후 첫 거래일 D+1의 '당일 종가 등락률'
  ret = close[D+1] / close[D] - 1
  (D = 공시일 또는 그 직전 거래일의 종가 기준. 잠정실적은 장 마감 후 공시가
   많아 반응이 다음 거래일에 온전히 나타남 → 다음 거래일 종가 등락률로 포착.)

이건 paradigm R-1 이 아니라 단순 기술(記述) 비교 (fee/perm/CI 없음).
"""
from __future__ import annotations

import json
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
from scripts.research._naver_kr_equity import (  # noqa: E402
    build_universe, get_ohlcv_cached, warm_cache,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("q1_2026_adhoc")

TOP_KOSPI = 200
TOP_KOSDAQ = 150
# 잠정실적 sweep 창: Q1(3/31 결산) 잠정실적은 4월~5월 중순 발표
PRELIM_BGN = "20260401"
PRELIM_END = "20260525"
# 분기보고서 sweep 창: Q1 분기보고서는 5/15 전후 제출 (45일)
QREPORT_BGN = "20260501"
QREPORT_END = "20260531"
# OHLCV 창 (앞뒤 여유)
OHLCV_BGN = "20260301"
OHLCV_END = "20260630"
TOP_N = 30

OUT_DIR = ROOT / "runs" / "dart_track"
OUT_PATH = OUT_DIR / "q1_2026_prelim_vs_quarterly.json"
CSV_PATH = OUT_DIR / "q1_2026_prelim_vs_quarterly.csv"


def sweep(pblntf_ty: str, bgn: str, end: str, universe_codes: set[str],
          keep) -> pd.DataFrame:
    """DART list.json sweep across KOSPI+KOSDAQ, filter by `keep(report_nm)`."""
    rows = []
    for corp_cls in ("Y", "K"):
        for r in iter_disclosures_chunked(
            bgn_de=bgn, end_de=end, corp_cls=corp_cls,
            pblntf_ty=pblntf_ty, chunk_days=30,
        ):
            nm = r.get("report_nm", "")
            if not keep(nm):
                continue
            code = (r.get("stock_code") or "").strip()
            if code not in universe_codes:
                continue
            rows.append({
                "rcept_dt": r["rcept_dt"],
                "rcept_no": r.get("rcept_no"),
                "stock_code": code,
                "corp_name": r.get("corp_name"),
                "report_nm": nm.strip(),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["rcept_no"]).reset_index(drop=True)
        df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d")
    return df


def next_day_return(code: str, event_dt: pd.Timestamp) -> dict | None:
    """공시일 이후 첫 거래일 D+1 의 당일 종가 등락률."""
    df = get_ohlcv_cached(code, OHLCV_BGN, OHLCV_END)
    if df.empty:
        return None
    df = df.set_index("date").sort_index()
    dates = df.index.values
    ev = event_dt.to_datetime64()
    pos = int(np.searchsorted(dates, ev, side="right"))  # 첫 거래일 strictly after
    if pos < 1 or pos >= len(df):
        return None
    prev_close = float(df["close"].iloc[pos - 1])
    d1_close = float(df["close"].iloc[pos])
    if prev_close <= 0 or d1_close <= 0:
        return None
    return {
        "d1_date": pd.Timestamp(df.index[pos]).strftime("%Y-%m-%d"),
        "d1_ret": d1_close / prev_close - 1.0,
    }


def is_q_report(nm: str) -> bool:
    return classify(nm) is PERIODIC_REPORT and "분기보고서" in nm.replace("[정정]", "")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    universe = build_universe(TOP_KOSPI, TOP_KOSDAQ)
    universe_codes = set(universe["itemCode"].astype(str).str.zfill(6).tolist())
    name_by_code = dict(zip(
        universe["itemCode"].astype(str).str.zfill(6), universe["stockName"]))
    log.info("universe=%d", len(universe_codes))

    # 1) 잠정실적 (Q1 2026) sweep
    prelim = sweep("I", PRELIM_BGN, PRELIM_END, universe_codes,
                   keep=lambda nm: is_earnings_event(nm) and not is_subsidiary_only(nm))
    log.info("잠정실적 events=%d (distinct=%d)",
             len(prelim), prelim["stock_code"].nunique() if not prelim.empty else 0)
    if prelim.empty:
        json.dump({"status": "no_prelim_events"}, OUT_PATH.open("w"))
        return

    # 종목당 첫 잠정실적만 (연결/별도 중복 제거)
    prelim = prelim.sort_values("rcept_dt").drop_duplicates("stock_code", keep="first")

    codes = sorted(prelim["stock_code"].unique())
    log.info("OHLCV warm for %d codes", len(codes))
    warm_cache(codes, OHLCV_BGN, OHLCV_END, sleep_s=0.08)

    # 2) 잠정 D+1 상승률
    recs = []
    for _, ev in prelim.iterrows():
        r = next_day_return(ev["stock_code"], ev["rcept_dt"])
        if r is None:
            continue
        recs.append({
            "code": ev["stock_code"],
            "name": name_by_code.get(ev["stock_code"], ev["corp_name"]),
            "prelim_date": ev["rcept_dt"].strftime("%Y-%m-%d"),
            "prelim_report": ev["report_nm"],
            "prelim_d1_date": r["d1_date"],
            "prelim_d1_ret": r["d1_ret"],
        })
    pr = pd.DataFrame(recs).sort_values("prelim_d1_ret", ascending=False)
    top = pr.head(TOP_N).reset_index(drop=True)
    log.info("top-%d by 잠정 D+1 ret computed (of %d with returns)", len(top), len(pr))

    top_codes = set(top["code"])

    # 3) 분기보고서 (Q1 2026) sweep — top 종목만 필요
    qrep = sweep("A", QREPORT_BGN, QREPORT_END, universe_codes, keep=is_q_report)
    qrep = qrep[qrep["stock_code"].isin(top_codes)]
    # 종목당 첫 분기보고서만
    qrep = qrep.sort_values("rcept_dt").drop_duplicates("stock_code", keep="first")
    qmap = {row["stock_code"]: row for _, row in qrep.iterrows()}
    log.info("분기보고서 matched for %d/%d top codes", len(qmap), len(top))

    # 4) 분기보고서 D+1 상승률
    q_d1_date, q_d1_ret, q_rep_date = [], [], []
    for _, t in top.iterrows():
        row = qmap.get(t["code"])
        if row is None:
            q_rep_date.append(None); q_d1_date.append(None); q_d1_ret.append(None)
            continue
        r = next_day_return(t["code"], row["rcept_dt"])
        q_rep_date.append(row["rcept_dt"].strftime("%Y-%m-%d"))
        if r is None:
            q_d1_date.append(None); q_d1_ret.append(None)
        else:
            q_d1_date.append(r["d1_date"]); q_d1_ret.append(r["d1_ret"])
    top["qreport_date"] = q_rep_date
    top["qreport_d1_date"] = q_d1_date
    top["qreport_d1_ret"] = q_d1_ret
    top["diff_prelim_minus_qreport"] = top["prelim_d1_ret"] - pd.to_numeric(
        top["qreport_d1_ret"], errors="coerce")

    # 5) 저장 + 요약
    top.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    valid = top.dropna(subset=["qreport_d1_ret"])
    summary = {
        "window": {"prelim": [PRELIM_BGN, PRELIM_END], "qreport": [QREPORT_BGN, QREPORT_END]},
        "universe": f"top-{TOP_KOSPI} KOSPI + top-{TOP_KOSDAQ} KOSDAQ",
        "n_prelim_events": int(len(pr)),
        "top_n": int(len(top)),
        "n_with_qreport": int(len(valid)),
        "avg_prelim_d1_ret_top": float(top["prelim_d1_ret"].mean()),
        "avg_qreport_d1_ret_top": float(valid["qreport_d1_ret"].mean()) if len(valid) else None,
        "pct_qreport_positive": float((valid["qreport_d1_ret"] > 0).mean()) if len(valid) else None,
        "rows": top.to_dict(orient="records"),
    }

    def _clean(o):
        if isinstance(o, float):
            return None if not np.isfinite(o) else round(o, 6)
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_clean(v) for v in o]
        return o

    OUT_PATH.write_text(json.dumps(_clean(summary), ensure_ascii=False, indent=2))
    log.info("WROTE %s + %s", OUT_PATH, CSV_PATH)

    # 콘솔 출력
    print("\n=== 2026 Q1 잠정실적 D+1 상승률 top-30 vs 분기보고서 D+1 ===")
    print(f"유니버스: {summary['universe']} | 잠정실적 이벤트 {summary['n_prelim_events']}건")
    print(f"top30 평균 잠정 D+1: {summary['avg_prelim_d1_ret_top']*100:+.2f}%")
    if summary["avg_qreport_d1_ret_top"] is not None:
        print(f"top30 평균 분기보고서 D+1: {summary['avg_qreport_d1_ret_top']*100:+.2f}% "
              f"(분기보고서 매칭 {summary['n_with_qreport']}종, "
              f"양(+) 비율 {summary['pct_qreport_positive']*100:.0f}%)")
    print(f"{'종목':<14}{'잠정일':<12}{'잠정D+1':>9}  {'분기보고일':<12}{'보고D+1':>9}")
    for r in top.itertuples():
        q = f"{r.qreport_d1_ret*100:+.2f}%" if pd.notna(r.qreport_d1_ret) else "  N/A"
        qd = r.qreport_date or "-"
        print(f"{str(r.name)[:12]:<14}{r.prelim_date:<12}{r.prelim_d1_ret*100:>+8.2f}%  "
              f"{qd:<12}{q:>9}")


if __name__ == "__main__":
    main()
