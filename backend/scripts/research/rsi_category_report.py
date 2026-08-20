"""RSI 격자 결과를 **종목 카테고리별**로 가른다.

판정 주축은 **총손익**이다 — 빈도 × 엣지. 거래당 엣지만 보면 결론이
뒤집힌다(대표님 지시). 승률은 성과가 아니다.

⚠ 분류 기준은 `rsi_symbol_meta.py` 가 만든 것만 쓴다.
   거래는 `ohlcv_1m` 에서 나왔으므로 분류도 `ohlcv_1m` 에서 나와야 한다.
   다른 테이블을 섞으면 **그 테이블의 커버리지 결손이 종목의 성질로 읽힌다**
   (2026-08-19 "신규상장 39종목" 오보의 정체 — 실제 1종목).

각 칸마다 세 가지를 같이 낸다. 하나만 보면 속는다:
  · 총손익            — 주축
  · 상위 10거래 절삭  — 소수 대박에 얹혀 있는가 (교훈 #81)
  · 회전 위약 대비    — 규칙이 번 건가 국면이 번 건가

사용:
  python3 -m scripts.research.rsi_category_report \
      --trades runs/research_track/rsi_tp_sl/trades_long_5mfrom1m_h288_..._Y1_5M.csv \
      --meta   runs/research_track/rsi_tp_sl/symbol_meta.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def qbucket(s: pd.Series, n: int, labels: list[str]) -> pd.Series:
    """분위 구간. 동률이 많아 분위가 무너지면 순위 기반으로 물러선다."""
    try:
        return pd.qcut(s, n, labels=labels)
    except ValueError:
        return pd.qcut(s.rank(method="first"), n, labels=labels)


def summarize(g: pd.DataFrame, rot: pd.DataFrame | None) -> dict:
    r = g["ret_pct"].astype(float)
    n = len(r)
    top = r.nlargest(min(10, n)).sum()
    d = {
        "종목": g["symbol"].nunique(),
        "거래": n,
        "총손익%": r.sum(),
        "거래당%": r.mean() if n else np.nan,
        "중앙%": r.median() if n else np.nan,
        "승률%": 100.0 * (r > 0).mean() if n else np.nan,
        "상위10절삭": r.sum() - top,
        "상위10비중%": 100.0 * top / r.sum() if r.sum() else np.nan,
    }
    if rot is not None and len(rot):
        rr = rot["ret_pct"].astype(float)
        d["위약총손익%"] = rr.sum()
        d["실측-위약"] = r.sum() - rr.sum()
    return d


def table(df: pd.DataFrame, rotdf: pd.DataFrame | None, col: str,
          title: str) -> pd.DataFrame:
    out = {}
    for k, g in df.groupby(col, observed=True):
        rot = rotdf[rotdf[col] == k] if rotdf is not None else None
        out[k] = summarize(g, rot)
    t = pd.DataFrame(out).T
    print(f"\n■ {title}")
    print(t.to_string(float_format=lambda x: f"{x:,.1f}"))
    return t


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trades", required=True)
    p.add_argument("--meta", required=True)
    p.add_argument("--out", default="")
    a = p.parse_args()

    T = pd.read_csv(a.trades)
    meta = json.loads(Path(a.meta).read_text())
    M = pd.DataFrame(meta["symbols"]).T.rename_axis("symbol").reset_index()
    for c in ("dv_med", "daily_vol", "px_med", "days"):
        M[c] = pd.to_numeric(M[c], errors="coerce")

    print(f"거래 {len(T):,}행 · 메타 {len(M)}종목 · 창 {meta['window']} "
          f"· 출처 {meta['source']}")

    real = T[T["placebo"] == "real"].merge(M, on="symbol", how="left")
    rot = T[T["placebo"] != "real"].merge(M, on="symbol", how="left")
    miss = real["dv_med"].isna().sum()
    if miss:
        print(f"⚠ 메타 없는 거래 {miss}행 — 제외")
        real, rot = real.dropna(subset=["dv_med"]), rot.dropna(subset=["dv_med"])
    print(f"실측 {len(real):,}거래 / 위약 {len(rot):,}거래 "
          f"· 거래 발생 종목 {real['symbol'].nunique()}")

    # 분위는 **종목 단위**로 나눈다. 거래 단위로 나누면 거래 많은 종목이
    # 자기 분위를 혼자 채운다.
    S = M[M["symbol"].isin(real["symbol"])].copy()
    S["유동성"] = qbucket(S["dv_med"], 5, ["Q1최저", "Q2", "Q3", "Q4", "Q5최고"])
    S["변동성"] = qbucket(S["daily_vol"], 5, ["V1최저", "V2", "V3", "V4", "V5최고"])
    S["가격대"] = qbucket(S["px_med"], 4, ["P1저가", "P2", "P3", "P4고가"])
    yr = S["onboard"].astype(str).str[:4]
    S["상장연도"] = np.where(yr <= "2021", "~2021", yr)
    S["상태"] = S["status"].fillna("UNKNOWN")

    keys = ["유동성", "변동성", "가격대", "상장연도", "상태"]
    real = real.merge(S[["symbol", *keys]], on="symbol", how="left")
    rot = rot.merge(S[["symbol", *keys]], on="symbol", how="left")

    tot = real["ret_pct"].sum()
    print(f"\n전체 총손익 {tot:,.1f}% · 거래 {len(real):,} "
          f"· 거래당 {real['ret_pct'].mean():+.3f}%")

    tabs = {k: table(real, rot, k, k) for k in keys}

    print("\n■ 청산 사유")
    print(real.groupby("exit_reason")["ret_pct"]
          .agg(거래="size", 총손익="sum", 거래당="mean")
          .to_string(float_format=lambda x: f"{x:,.1f}"))

    if a.out:
        with open(a.out, "w") as fh:
            fh.write(f"거래 {len(real):,} · 총손익 {tot:,.1f}%\n")
            for k, t in tabs.items():
                fh.write(f"\n== {k} ==\n{t.to_string()}\n")
        print(f"\n저장 {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
