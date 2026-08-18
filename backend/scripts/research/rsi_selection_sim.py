"""슬롯 경쟁 시 **무엇을 고를 것인가** — 선택 규칙 시뮬레이션.

문제
    RSI 12 신호는 폭락 때 **뭉쳐서** 온다. 슬롯 1 이면 639건 중 173건만 잡고
    466건을 버리는데, 지금 배선은 고르는 기준이 **먼저 온 시각**뿐이다.
    우연히 먼저 온 것을 잡을 뿐 좋은 것을 고르지 않는다.

무엇을 재나
    같은 시각에 여러 신호가 있을 때 골라 잡는 규칙을 바꿔 본다:
        first   — 먼저 온 것 (현재 배선, 기준선)
        rsi_low — RSI 가 더 낮은 종목 (더 눌린 쪽)
        rv_high — 7일 실현변동성이 높은 종목
        rv_low  — **거울 대조**. rv_high 만 재면 반대가 나았을 가능성을 못 본다
        random  — 무작위 선택 (위약)

⚠ 신호는 **줄 서지 않는다**
    그 시각에 못 잡은 신호는 사라진다. 슬롯이 빌 때까지 대기시키면 실계좌에
    없는 기회를 만들어 낸다.

⚠ 지표는 **신호 봉**에서 읽는다
    체결은 신호 다음 봉 시가다(정본 규약). 그러므로 선택에 쓰는 RSI·변동성은
    `entry_ts - 1봉` 시점 값이어야 미래참조가 없다.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "runs" / "research_track" / "rsi_tp_sl"
RULES = ("first", "rsi_low", "rv_high", "rv_low", "random")


def sec(t):
    print("\n" + "=" * 100)
    print(t)
    print("=" * 100)


def enrich(T: pd.DataFrame) -> pd.DataFrame:
    """진입 **신호 봉**의 RSI·7일 변동성을 시간봉에서 직접 붙인다 (재실행 불필요)."""
    from sqlalchemy import text
    from app.db.session import engine
    from app.composer_framework.sources.rsi_threshold_source import wilder_rsi

    syms = sorted(T.symbol.unique())
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT symbol, ts, close FROM ohlcv_hourly WHERE symbol = ANY(:s) "
            "ORDER BY symbol, ts"), {"s": syms}).fetchall()
    px = pd.DataFrame(rows, columns=["symbol", "ts", "close"])
    px["ts"] = pd.to_datetime(px["ts"])

    feats = []
    for sym, g in px.groupby("symbol"):
        g = g.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
        c = g["close"].astype(float)
        lr = np.log(c).diff()
        feats.append(pd.DataFrame({
            "symbol": sym, "ts": g["ts"],
            "rsi": wilder_rsi(c, 14),
            "rv7": lr.rolling(24 * 7).std() * math.sqrt(24 * 365),
        }))
    F = pd.concat(feats, ignore_index=True)

    T = T.copy()
    T["entry_ts"] = pd.to_datetime(T.entry_ts)
    T["exit_ts"] = pd.to_datetime(T.exit_ts)
    # ⚠ 신호 봉 = 체결 봉의 한 봉 전. 체결 봉에서 읽으면 미래참조다.
    T["sig_ts"] = T.entry_ts - pd.Timedelta(hours=1)
    out = T.merge(F, left_on=["symbol", "sig_ts"], right_on=["symbol", "ts"],
                  how="left").drop(columns=["ts"])
    miss = int(out.rsi.isna().sum())
    if miss:
        print(f"  ⚠ 신호봉 지표를 못 붙인 거래 {miss}/{len(out)} — 그 거래는 제외")
    return out.dropna(subset=["rsi", "rv7"])


def run(T: pd.DataFrame, slots: int, rule: str, fee_bp: float,
        seed: int = 7) -> dict:
    """시각순으로 흘리며, 같은 시각의 경쟁 신호 중 `rule` 로 고른다."""
    rng = np.random.default_rng(seed)
    t = T.sort_values(["entry_ts", "symbol"]).reset_index(drop=True)
    free = np.full(slots, np.datetime64("1970-01-01"))
    taken = []
    for ts, grp in t.groupby("entry_ts", sort=True):
        n_free = int((free <= np.datetime64(ts)).sum())
        if n_free == 0:
            continue
        if rule == "first" or len(grp) == 1:
            pick = grp.index[:n_free]
        elif rule == "rsi_low":
            pick = grp.rsi.nsmallest(n_free).index
        elif rule == "rv_high":
            pick = grp.rv7.nlargest(n_free).index
        elif rule == "rv_low":
            pick = grp.rv7.nsmallest(n_free).index
        else:
            pick = rng.permutation(grp.index.to_numpy())[:n_free]
        for i in pick:
            j = int(np.argmin(free))
            free[j] = np.datetime64(t.at[i, "exit_ts"])
            taken.append(i)
    if len(taken) < 20:
        return {"n": len(taken)}
    q = t.loc[taken].sort_values("exit_ts")
    # ⚠ 슬롯당 자본은 **1/slots** 다. 전액으로 복리를 돌리면 슬롯 10 이
    #   10배 레버리지가 된다 (첫 판에서 CAGR +129% 가 그렇게 나왔다).
    raw = (q.ret_pct.to_numpy(float) - fee_bp / 100.0) / 100.0
    net = raw / slots
    eq = np.cumprod(1.0 + net)
    yrs = (q.exit_ts.max() - t.entry_ts.min()).total_seconds() / 3600 / 8766
    dd = float((eq / np.maximum.accumulate(eq) - 1.0).min())
    per_yr = {}
    for y, g2 in q.groupby(q.exit_ts.dt.year):
        nn = (g2.ret_pct.to_numpy(float) - fee_bp / 100.0) / 100.0 / slots
        per_yr[int(y)] = 100.0 * float(np.prod(1 + nn) - 1)
    return {
        "n": len(taken), "fill": 100.0 * len(taken) / len(t),
        "win": 100.0 * float((raw > 0).mean()),
        "avg": 100.0 * float(raw.mean()),   # 거래당은 **슬롯 분할 전** 값
        "total": 100.0 * float(eq[-1] - 1.0),
        "cagr": 100.0 * (float(eq[-1]) ** (1 / yrs) - 1.0),
        "mdd": 100.0 * dd, "per_yr": per_yr,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", default="1,2,3,5,10")
    ap.add_argument("--fee-bp", type=float, default=10.0)
    ap.add_argument("--thr", type=float, default=12.0)
    ap.add_argument("--sl", type=float, default=0.03)
    a = ap.parse_args()

    T = pd.read_csv(D / "trades_long_short_h48_PF.csv")
    T = T[(T.placebo == "real") & (T.side == "long") &
          (T.thr == a.thr) & (T.tp == 0.08) & (T.sl == a.sl)]
    sec(f"슬롯 경쟁 선택 규칙 — long · RSI {a.thr:.0f} · 익절 8% · 손절 {100*a.sl:.0f}%")
    print(f"  신호 {len(T):,}건 · 종목 {T.symbol.nunique()} · 왕복 마찰 {a.fee_bp:.0f}bp")
    T = enrich(T)
    dup = T.groupby("entry_ts").size()
    print(f"  같은 시각 경쟁 신호: 최대 {dup.max()}건 · "
          f"경쟁 발생 시각 {int((dup>1).sum())}/{len(dup)} "
          f"({100*float((dup>1).mean()):.1f}%)")
    print("  ⚠ 선택 지표는 **신호 봉**(체결 한 봉 전) 값 — 미래참조 없음")

    rows = []
    for s in [int(x) for x in a.slots.split(",")]:
        for r in RULES:
            d = run(T, s, r, a.fee_bp)
            if d.get("n", 0) < 20:
                continue
            rows.append({"slots": s, "rule": r, **d})
    R = pd.DataFrame(rows)

    sec("① 선택 규칙별 성과 (복리)")
    print(f"{'슬롯':>5}{'규칙':<10}{'체결':>7}{'체결률%':>9}{'승률%':>8}"
          f"{'거래당%':>10}{'총수익%':>10}{'CAGR%':>9}{'MDD%':>9}")
    print("-" * 100)
    for _, r in R.sort_values(["slots", "total"], ascending=[True, False]).iterrows():
        print(f"{r.slots:>5}{r.rule:<10}{r.n:>7}{r.fill:>9.1f}{r.win:>8.1f}"
              f"{r.avg:>+10.3f}{r.total:>+10.2f}{r.cagr:>+9.2f}{r.mdd:>+9.1f}")

    sec("② 기준선(first) 대비 — 고르는 게 이득인가")
    base = R[R.rule == "first"].set_index("slots")
    print(f"{'슬롯':>5}{'규칙':<10}{'총수익 차이%p':>15}{'CAGR 차이%p':>14}"
          f"{'MDD 차이%p':>13}")
    print("-" * 100)
    for _, r in R[R.rule != "first"].sort_values(["slots", "rule"]).iterrows():
        if r.slots not in base.index:
            continue
        b = base.loc[r.slots]
        print(f"{r.slots:>5}{r.rule:<10}{r.total-b.total:>+15.2f}"
              f"{r.cagr-b.cagr:>+14.2f}{r.mdd-b.mdd:>+13.1f}")

    sec("③ 연도별 (복리 %)")
    yrs = sorted({y for _, r in R.iterrows() for y in r.per_yr})
    print(f"{'슬롯':>5}{'규칙':<10}" + "".join(f"{y:>10}" for y in yrs))
    print("-" * 100)
    for _, r in R.sort_values(["slots", "rule"]).iterrows():
        print(f"{r.slots:>5}{r.rule:<10}"
              + "".join(f"{r.per_yr.get(y, float('nan')):>+10.2f}" for y in yrs))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
