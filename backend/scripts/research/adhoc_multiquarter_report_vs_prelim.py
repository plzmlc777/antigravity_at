"""Ad-hoc: 다분기 확장 — 정기보고서 D+1 vs 잠정실적 D+1 (시장중립 abnormal return).

질문: "잠정실적보다 정기보고서 발표 후 반응이 더 큰(=보고서 세부가 촉매)" 패턴이
      여러 분기에 걸쳐 반복되는 실재 현상인가?

방법:
  - 2024Q1 ~ 2026Q1 (9개 분기). 분기별 잠정실적(공정공시) → 해당 정기보고서 매칭.
    Q1/Q3 = 분기보고서, Q2 = 반기보고서, Q4 = 사업보고서.
  - 상승률 = 공시일 이후 첫 거래일 D+1 당일 종가 등락률.
  - 시장중립: abnormal = 종목 D+1 - 지수ETF D+1 (KOSPI→069500 KODEX200,
    KOSDAQ→229200 KODEX KOSDAQ150). 5/15 등 날짜 쏠림 교란 제거.
  - 같은 날 동시제출(=동일 이벤트) 제외.

산출:
  - 분기별: 매칭 n, 역전율(보고서 abn > 잠정 abn), 보고서 abn 평균/승률.
  - 풀링: 보고서 abn 평균이 0과 유의하게 다른가(t), prelim abn과 상관.
  - 보고서 단독 촉매 후보(잠정 abn ≤ +1% & 보고서 abn ≥ +3%) 반복 등장 종목.
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
log = logging.getLogger("multiq")

OHLCV_BGN, OHLCV_END = "20231201", "20260630"
ETF = {"Y": "069500", "K": "229200"}  # KODEX200 / KODEX KOSDAQ150
CSV_PATH = ROOT / "runs" / "dart_track" / "multiquarter_report_vs_prelim.csv"

# (label, prelim window, report window, report keyword)
QUARTERS = [
    ("2024Q1", ("20240401", "20240525"), ("20240501", "20240531"), "분기보고서"),
    ("2024Q2", ("20240701", "20240825"), ("20240801", "20240831"), "반기보고서"),
    ("2024Q3", ("20241001", "20241125"), ("20241101", "20241130"), "분기보고서"),
    ("2024Q4", ("20250115", "20250228"), ("20250301", "20250405"), "사업보고서"),
    ("2025Q1", ("20250401", "20250525"), ("20250501", "20250531"), "분기보고서"),
    ("2025Q2", ("20250701", "20250825"), ("20250801", "20250831"), "반기보고서"),
    ("2025Q3", ("20251001", "20251125"), ("20251101", "20251130"), "분기보고서"),
    ("2025Q4", ("20260115", "20260228"), ("20260301", "20260405"), "사업보고서"),
    ("2026Q1", ("20260401", "20260525"), ("20260501", "20260531"), "분기보고서"),
]


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
                         "code": code, "cls": cls, "corp_name": r.get("corp_name")})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates("rcept_no")
    df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d")
    return df.sort_values("rcept_dt").drop_duplicates("code", keep="first")


_series_cache: dict[str, pd.DataFrame] = {}


def series(code):
    if code not in _series_cache:
        df = get_ohlcv_cached(code, OHLCV_BGN, OHLCV_END)
        _series_cache[code] = df.set_index("date").sort_index() if not df.empty else df
    return _series_cache[code]


def d1_ret(df, event_dt):
    if df is None or df.empty:
        return None, None
    pos = int(np.searchsorted(df.index.values, event_dt.to_datetime64(), side="right"))
    if pos < 1 or pos >= len(df):
        return None, None
    cp, cd = float(df["close"].iloc[pos - 1]), float(df["close"].iloc[pos])
    if cp <= 0 or cd <= 0:
        return None, None
    return pd.Timestamp(df.index[pos]).strftime("%Y-%m-%d"), cd / cp - 1.0


def q_report_keep(kw):
    return lambda nm: classify(nm) is PERIODIC_REPORT and kw in nm.replace("[정정]", "")


def main():
    uni = build_universe(200, 150)
    codes_all = set(uni["itemCode"].astype(str).str.zfill(6))
    name_by = dict(zip(uni["itemCode"].astype(str).str.zfill(6), uni["stockName"]))

    # 이벤트 수집 (분기별)
    all_events = []  # dict rows
    for label, (pb, pe), (rb, re_), kw in QUARTERS:
        prelim = sweep("I", pb, pe, codes_all,
                       lambda nm: is_earnings_event(nm) and not is_subsidiary_only(nm))
        report = sweep("A", rb, re_, codes_all, q_report_keep(kw))
        if prelim.empty or report.empty:
            log.warning("%s: prelim=%d report=%d skip", label, len(prelim), len(report))
            continue
        rmap = {r["code"]: r for _, r in report.iterrows()}
        for _, e in prelim.iterrows():
            rr = rmap.get(e["code"])
            if rr is None:
                continue
            all_events.append({
                "q": label, "code": e["code"], "cls": e["cls"],
                "name": name_by.get(e["code"], e["corp_name"]),
                "prelim_dt": e["rcept_dt"], "report_dt": rr["rcept_dt"],
            })
        log.info("%s: prelim=%d report=%d matched=%d",
                 label, len(prelim), len(report),
                 sum(1 for x in all_events if x["q"] == label))

    ev = pd.DataFrame(all_events)
    log.info("total matched events across quarters: %d", len(ev))

    # OHLCV warm (종목 + ETF)
    codes_needed = sorted(set(ev["code"]) | set(ETF.values()))
    warm_cache(codes_needed, OHLCV_BGN, OHLCV_END, sleep_s=0.05)

    # 수익률 계산
    recs = []
    for _, e in ev.iterrows():
        if e["prelim_dt"] == e["report_dt"]:
            continue
        s = series(e["code"])
        m = series(ETF[e["cls"]])
        pd1, p_ret = d1_ret(s, e["prelim_dt"])
        qd1, q_ret = d1_ret(s, e["report_dt"])
        _, p_mkt = d1_ret(m, e["prelim_dt"])
        _, q_mkt = d1_ret(m, e["report_dt"])
        if None in (p_ret, q_ret, p_mkt, q_mkt):
            continue
        recs.append({
            "q": e["q"], "code": e["code"], "name": e["name"], "cls": e["cls"],
            "prelim_date": e["prelim_dt"].strftime("%Y-%m-%d"),
            "report_date": e["report_dt"].strftime("%Y-%m-%d"),
            "prelim_d1": p_ret, "report_d1": q_ret,
            "prelim_abn": p_ret - p_mkt, "report_abn": q_ret - q_mkt,
        })
    r = pd.DataFrame(recs)
    r.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    log.info("valid pairs: %d", len(r))

    # ── 분기별 요약 ──
    print("\n=== 다분기: 정기보고서 D+1 vs 잠정 D+1 (시장중립 abnormal) ===")
    print(f"{'분기':<9}{'n':>5}{'역전율':>8}{'보고서abn평균':>13}{'보고서abn승률':>13}{'잠정abn평균':>12}")
    for label, _, _, _ in QUARTERS:
        g = r[r["q"] == label]
        if g.empty:
            continue
        rev = (g["report_abn"] > g["prelim_abn"]).mean() * 100
        print(f"{label:<9}{len(g):>5}{rev:>7.0f}%{g['report_abn'].mean()*100:>+12.2f}%"
              f"{(g['report_abn']>0).mean()*100:>12.0f}%{g['prelim_abn'].mean()*100:>+11.2f}%")

    # ── 풀링 통계 ──
    n = len(r)
    ra = r["report_abn"].values
    pa = r["prelim_abn"].values
    t_report = ra.mean() / ra.std(ddof=1) * np.sqrt(n)
    corr = np.corrcoef(pa, ra)[0, 1]
    print(f"\n[풀링 n={n}]")
    print(f"  보고서 abn 평균 {ra.mean()*100:+.3f}%  t={t_report:+.2f}  (0과 유의?)")
    print(f"  잠정  abn 평균 {pa.mean()*100:+.3f}%")
    print(f"  역전율(보고서 abn > 잠정 abn): {(ra>pa).mean()*100:.0f}%")
    print(f"  corr(잠정abn, 보고서abn) = {corr:+.3f}  (<0 이면 mean-reversion)")

    # ── 보고서 단독 촉매 후보 (잠정 밋밋/음 & 보고서 강한 +) ──
    cand = r[(r["prelim_abn"] <= 0.01) & (r["report_abn"] >= 0.03)]
    print(f"\n[보고서 단독 촉매 후보: 잠정abn ≤+1% & 보고서abn ≥+3%]  {len(cand)}건")
    rep = cand["name"].value_counts()
    print("  반복 등장(≥2개 분기):", dict(rep[rep >= 2]) or "없음")
    print(f"{'분기':<9}{'종목':<14}{'잠정abn':>9}{'보고서abn':>10}{'  보고일':>12}")
    for x in cand.sort_values("report_abn", ascending=False).head(20).itertuples():
        print(f"{x.q:<9}{str(x.name)[:12]:<14}{x.prelim_abn*100:>+8.2f}%"
              f"{x.report_abn*100:>+9.2f}%  {x.report_date}")
    print(f"\nCSV(전체 쌍): {CSV_PATH}")


if __name__ == "__main__":
    main()
