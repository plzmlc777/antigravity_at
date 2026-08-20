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


def concentration(df: pd.DataFrame) -> None:
    """신호가 **뭉쳐서** 나오면 슬롯 20개는 분산이 아니라 한 번의 베팅이다.

    실측 동기(2026-08-20): 기대 빈도는 하루 21건인데 최근 25시간 실측은
    **0건**이었다(63종목 18,018관측 독립 측정). 평균이 아니라 군집이다.
    """
    if "entry_ts" not in df.columns:
        print("\n■ 집중도 — entry_ts 없음, 생략")
        return
    t = pd.to_datetime(df["entry_ts"], errors="coerce", utc=True)
    d = df.assign(_d=t.dt.floor("D"), _h=t.dt.floor("h")).dropna(subset=["_d"])
    n = len(d)
    byday = d.groupby("_d")["ret_pct"].agg(["size", "sum"]).sort_values(
        "size", ascending=False)
    ndays = int((d["_d"].max() - d["_d"].min()).days) + 1
    print(f"\n■ 집중도 — 거래 {n:,} · 거래발생일 {len(byday)}일 / 달력 {ndays}일 "
          f"({100*len(byday)/ndays:.0f}%)")
    tot = d["ret_pct"].sum()
    for k in (1, 5, 10, 20):
        if k <= len(byday):
            sh = 100.0 * byday["size"].head(k).sum() / n
            amt = byday["sum"].head(k).sum()
            # ⚠ 총손익이 0 근처면 비율이 폭발한다. 절대값을 먼저 읽어라.
            share = f"{100.0 * amt / tot:6.1f}%" if abs(tot) > 1e-9 else "   n/a"
            print(f"   상위 {k:>2}일: 거래 {sh:5.1f}% · 손익 {amt:+9.1f}%p "
                  f"(전체 {tot:+.1f}%p 의 {share})")
    # 동시 보유 — 진입/청산을 시간순 이벤트로 훑는다
    if "exit_ts" in d.columns:
        x = pd.to_datetime(d["exit_ts"], errors="coerce", utc=True)
        ev = pd.concat([pd.Series(1, index=t.loc[d.index]),
                        pd.Series(-1, index=x)]).sort_index()
        conc = ev.cumsum()
        print(f"   동시 보유 — 중앙 {conc.median():.0f} · 90% {conc.quantile(.9):.0f}"
              f" · 최대 {conc.max():.0f}  (슬롯 20 기준)")
        over = 100.0 * (conc > 20).mean()
        print(f"   슬롯 20 초과 시간 비중 {over:.1f}%  "
              f"— 초과분은 실제로는 체결되지 않는다")


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
    p.add_argument("--tp-maker-bp", type=float, default=0.0,
                   help="익절이 테이커로 계산된 원장을 메이커로 되돌린다(편도 차 bp). "
                        "2026-08-20 이전 격자는 3.0 — 그날 하네스가 "
                        "fee_rate_maker 를 백테스터에 안 넘겼다. 이후 실행은 0")
    a = p.parse_args()

    T = pd.read_csv(a.trades)
    meta = json.loads(Path(a.meta).read_text())
    M = pd.DataFrame(meta["symbols"]).T.rename_axis("symbol").reset_index()
    for c in ("dv_med", "daily_vol", "px_med", "days"):
        M[c] = pd.to_numeric(M[c], errors="coerce")

    print(f"거래 {len(T):,}행 · 메타 {len(M)}종목 · 창 {meta['window']} "
          f"· 출처 {meta['source']}")

    if a.tp_maker_bp:
        # ⚠ 사후 보정. 커널은 익절을 메이커로 표시하는데 하네스가 메이커
        #   요율을 안 넘겨 테이커로 계산된 원장이 있다. 재실행 2.5시간 대신
        #   청산사유로 되돌린다 — 차액은 **익절 거래의 청산 다리에만** 붙는다.
        if "exit_reason" not in T.columns:
            raise SystemExit("--tp-maker-bp 를 쓰려면 원장에 exit_reason 이 있어야 한다")
        istp = T["exit_reason"].astype(str).str.lower().eq("tp")
        T.loc[istp, "ret_pct"] = T.loc[istp, "ret_pct"] + a.tp_maker_bp / 100.0
        print(f"  ↺ 익절 {int(istp.sum()):,}건에 +{a.tp_maker_bp:.1f}bp 되돌림 "
              f"(테이커로 계산돼 있었다) — 나머지 {int((~istp).sum()):,}건 불변")

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

    concentration(real)

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
