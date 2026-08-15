"""알트 ↔ BTC 관계 — **거래 가능한 축이 있는가**.

출발점
    2025-01 이후 알트 중앙값 **-82.3%** · BTC **-32.2%**. 알트가 훨씬 더 빠졌다.
    그러면 "알트 숏 / BTC 롱"은 구조적으로 버는가? 그리고 그 관계에 타이밍을
    얹을 수 있는가?

⚠ 중앙값 -82% 를 그대로 믿고 들어가면 안 된다
    **중앙값은 거래할 수 없다.** 동일가중 바스켓을 실제로 숏 치면 ZEC(+771%)
    같은 종목도 같이 숏이다. 거래 가능한 것은 횡단면 **평균**이고, 그래서 이
    스크립트는 처음부터 끝까지 평균(= 동일가중 바스켓 수익률)으로만 잰다.
    이 한 줄 차이로 결론이 뒤집힐 수 있다.

재는 축
    ① **비대칭 베타** BTC 하락일 베타 > 상승일 베타인가. 크면 "알트 숏 / BTC
       롱"이 구조적으로 유리하다는 **기전**이 된다.
       위약 = **원형회전** (BTC 계열을 통째로 밀어 짝을 깬다). 자기상관을
       살리면서 짝만 깨므로 뒤섞기보다 엄격하다.
    ② **시장중립 실현 손익** 알트 바스켓 숏 $1 / BTC 롱 $1. 수수료·펀딩 포함.
       이게 실제로 거래할 물건이다. 나머지는 이걸 설명하는 부속이다.
       방향 대조(교훈 #91) — 거울(알트 롱/BTC 숏)이 정확히 음수여야 한다.
    ③ **리드-래그** BTC 가 먼저 움직이고 알트가 따라오는가. 따라온다면 오늘의
       BTC 로 내일 알트를 거래할 수 있다.

⚠ 마찰을 처음부터 넣는다 (교훈 #82)
    · 수수료 — 리밸런스 회전율 × 5bp(테이커). 일간 리밸런스는 이것만으로 죽는다.
    · **펀딩** — 8시간마다 정산이라 연 1,095회다. 숏은 양수 펀딩에서 **번다.**
      펀딩 없이 낸 숏 바스켓 수익은 전부 과대평가다.

⚠ 유니버스 자격은 그 날짜까지의 정보로만 (직전 30일 거래대금)
    전 구간 ADV 로 거르면 끝까지 살아남은 종목만 남아 숏 수익이 과소평가된다.

사용:
  python3 -m scripts.research.alt_btc_relation_scan --split 2025-01-01
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("altbtc")

OUT = ROOT / "runs" / "research_track" / "alt_btc_relation_scan.json"

MIN_ADV = 3e6
MIN_HIST = 60
FEE = 0.0005           # 테이커 5bp
BENCH = "BTCUSDT"
EXCLUDE = {"BTCUSDT", "ETHUSDT"}     # ETH 는 '알트'로 안 본다


def load(conn):
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT symbol, date, close, volume FROM ohlcv_daily ORDER BY date, symbol"
    )).fetchall()
    df = pd.DataFrame(r, columns=["symbol", "ts", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    close = df.pivot(index="ts", columns="symbol", values="close").sort_index()
    dv = (df.assign(dv=df["close"] * df["volume"])
            .pivot(index="ts", columns="symbol", values="dv").sort_index())
    # 펀딩 — 일별 합계(하루 3회 정산). 양수 = 롱이 숏에게 지급 = **숏이 번다**
    f = conn.execute(text(
        "SELECT symbol, date_trunc('day', funding_time) d, sum(funding_rate) fr "
        "FROM binance_funding_rate GROUP BY symbol, d")).fetchall()
    fund = pd.DataFrame(f, columns=["symbol", "ts", "fr"])
    if len(fund):
        fund["ts"] = pd.to_datetime(fund["ts"])
        fund["fr"] = pd.to_numeric(fund["fr"], errors="coerce")
        fund = fund.pivot(index="ts", columns="symbol", values="fr").sort_index()
    else:
        fund = pd.DataFrame()
    return close, dv, fund


def eligibility(close, dv):
    adv = dv.rolling(30, min_periods=20).mean().shift(1)
    hist = close.notna().rolling(MIN_HIST, min_periods=1).sum().shift(1)
    e = (adv >= MIN_ADV) & (hist >= MIN_HIST) & close.notna()
    for b in EXCLUDE:
        if b in e.columns:
            e[b] = False
    return e


def block_t(x: np.ndarray, block: int = 21) -> tuple[float, float]:
    """블록 평균의 t. 일별 t 는 자기상관 때문에 부푼다(교훈 #92).

    한 달(21거래일)씩 **겹치지 않게** 잘라 그 평균들로 t 를 낸다.
    """
    n = len(x) // block
    if n < 2:
        return float("nan"), float("nan")
    b = x[:n * block].reshape(n, block).mean(axis=1)
    se = b.std(ddof=1) / np.sqrt(n)
    return float(b.mean()), (float(b.mean() / se) if se else float("nan"))


def mdd(cum: np.ndarray) -> float:
    peak = np.maximum.accumulate(cum)
    return float(np.min(cum / peak - 1) * 100)


def main() -> int:
    p = argparse.ArgumentParser(description="알트-BTC 관계 스캔")
    p.add_argument("--since", default="2021-03-01")
    p.add_argument("--split", default="2025-01-01", help="표본 밖 시작일")
    p.add_argument("--rot", type=int, default=200, help="원형회전 위약 횟수")
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine
    with engine.connect() as conn:
        close, dv, fund = load(conn)
    elig = eligibility(close, dv)
    ret = close.pct_change()

    # ── 동일가중 알트 바스켓 (거래 가능한 물건) ────────────────────────
    # ⚠ **평균**이다. 중앙값은 어떤 포트폴리오도 아니다.
    alt = ret.where(elig).mean(axis=1, skipna=True)
    n_el = elig.sum(axis=1)
    btc = ret[BENCH] if BENCH in ret.columns else pd.Series(dtype=float)
    d = pd.DataFrame({"alt": alt, "btc": btc, "n": n_el}).dropna()
    d = d[(d.index >= a.since) & (d["n"] >= 20)]
    log.info("구간 %s ~ %s · %d일 · 자격 종목 중앙 %d",
             d.index[0].date(), d.index[-1].date(), len(d), int(d["n"].median()))

    # 펀딩 — 바스켓 평균(자격 종목만) / BTC
    fund_cov = 0.0
    if len(fund):
        fa = fund.reindex(index=d.index, columns=elig.columns)
        fa = fa.where(elig.reindex(d.index))
        d["f_alt"] = fa.mean(axis=1, skipna=True)
        d["f_btc"] = (fund[BENCH].reindex(d.index)
                      if BENCH in fund.columns else 0.0)
        fund_cov = float(100 * fa.notna().sum(axis=1).div(
            elig.reindex(d.index).sum(axis=1)).mean())
    else:
        d["f_alt"] = np.nan
        d["f_btc"] = np.nan
    d[["f_alt", "f_btc"]] = d[["f_alt", "f_btc"]].fillna(0.0)
    log.info("펀딩 커버리지 — 자격 종목 중 이력 보유 평균 %.1f%%", fund_cov)

    print("=" * 100)
    print(f"  **알트 ↔ BTC 관계 스캔** — 동일가중 알트 바스켓(자격 중앙 "
          f"{int(d['n'].median())}종목) vs {BENCH} · {d.index[0].date()} ~ "
          f"{d.index[-1].date()}")
    print(f"  ⚠ 바스켓은 **평균**이다. 앞서 본 중앙값 -82% 는 거래할 수 없다 — "
          f"숏이면 폭등 종목도 같이 숏이다")
    print("=" * 100)

    res: dict = {}

    # ── ① 비대칭 베타 ─────────────────────────────────────────────────
    up = np.maximum(d["btc"].values, 0.0)
    dn = np.minimum(d["btc"].values, 0.0)
    X = np.column_stack([np.ones(len(d)), up, dn])
    y = d["alt"].values
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    a0, bu, bd = coef
    obs_gap = float(bd - bu)

    # 위약 — **원형회전**. BTC 계열을 통째로 밀어 짝만 깬다(자기상관 보존).
    rng = np.random.default_rng(20260815)
    null = []
    bv = d["btc"].values
    for _ in range(a.rot):
        k = int(rng.integers(60, len(bv) - 60))
        r_ = np.roll(bv, k)
        Xr = np.column_stack([np.ones(len(d)), np.maximum(r_, 0), np.minimum(r_, 0)])
        c_, *_ = np.linalg.lstsq(Xr, y, rcond=None)
        null.append(c_[2] - c_[1])
    null = np.array(null)
    p_rot = float((np.abs(null) >= abs(obs_gap)).mean())

    print(f"\n  ① 비대칭 베타 — 알트 = α + β⁺·max(BTC,0) + β⁻·min(BTC,0)")
    print(f"     α {a0*100:+.4f}%/일 · β⁺(상승일) **{bu:.3f}** · "
          f"β⁻(하락일) **{bd:.3f}**")
    print(f"     β⁻ − β⁺ = **{obs_gap:+.3f}**   (양수면 하락을 더 크게 따라간다 "
          f"= 알트숏/BTC롱에 유리)")
    print(f"     원형회전 위약 {a.rot}회 — |귀무| 중앙 {np.median(np.abs(null)):.3f}"
          f" · p95 {np.percentile(np.abs(null),95):.3f} · **p {p_rot:.3f}**")
    res["asymmetric_beta"] = {"alpha_daily_pct": float(a0*100), "beta_up": float(bu),
                              "beta_down": float(bd), "gap": obs_gap,
                              "p_rotation": p_rot}

    # ── ② 시장중립 실현 손익 ──────────────────────────────────────────
    print(f"\n  ② 시장중립 — **알트 바스켓 숏 $1 / BTC 롱 $1** (일간 리밸런스)")
    print(f"     {'판본':>22}{'연환산%':>10}{'Sharpe':>8}{'MDD%':>9}"
          f"{'월t':>7}{'IS연%':>9}{'OOS연%':>9}")
    variants = {
        "총액(마찰 前)": lambda: -d["alt"] + d["btc"],
        "+ 수수료": lambda: -d["alt"] + d["btc"] - 2 * FEE * turnover,
        "+ 수수료 + 펀딩": lambda: (-d["alt"] + d["btc"] - 2 * FEE * turnover
                                + d["f_alt"] - d["f_btc"]),
        "거울(알트롱/BTC숏)": lambda: d["alt"] - d["btc"] - 2 * FEE * turnover
                                    - d["f_alt"] + d["f_btc"],
    }
    # 일간 리밸런스 회전율 — 바스켓 양쪽 다 되돌리므로 대략 |수익률| 만큼
    turnover = (d["alt"].abs() + d["btc"].abs())
    pnl_store = {}
    for name, fn in variants.items():
        r_ = fn().values
        cum = np.cumprod(1 + r_)
        ann = float((cum[-1] ** (365 / len(r_)) - 1) * 100)
        sh = float(r_.mean() / r_.std(ddof=1) * np.sqrt(365)) if r_.std() else np.nan
        _, t_ = block_t(r_)
        m = d.index >= a.split
        ris, ros = r_[~m], r_[m]
        ais = float((np.prod(1+ris) ** (365/max(1, len(ris))) - 1) * 100)
        aos = float((np.prod(1+ros) ** (365/max(1, len(ros))) - 1) * 100)
        pnl_store[name] = {"ann_pct": ann, "sharpe": sh, "mdd_pct": mdd(cum),
                           "month_t": t_, "IS_ann": ais, "OOS_ann": aos}
        print(f"     {name:>22}{ann:>10.1f}{sh:>8.2f}{mdd(cum):>9.1f}"
              f"{t_:>7.2f}{ais:>9.1f}{aos:>9.1f}")
    res["market_neutral"] = pnl_store

    # 펀딩 규모 — 얼마나 큰 항목인가
    fnet = (d["f_alt"] - d["f_btc"])
    print(f"     펀딩 순액(숏 관점) 일평균 {fnet.mean()*100:+.4f}% → "
          f"연 **{fnet.mean()*365*100:+.1f}%** · 커버리지 {fund_cov:.0f}%")
    print(f"     수수료 부담 일평균 {(2*FEE*turnover).mean()*100:.4f}% → "
          f"연 **-{(2*FEE*turnover).mean()*365*100:.1f}%**  ← 일간 리밸런스 비용")
    res["funding_annual_pct"] = float(fnet.mean()*365*100)
    res["fee_annual_pct"] = float((2*FEE*turnover).mean()*365*100)
    res["funding_coverage_pct"] = fund_cov

    # 연도별 — 국면에 따라 뒤집히는가
    net = (-d["alt"] + d["btc"] - 2 * FEE * turnover + d["f_alt"] - d["f_btc"])
    print(f"\n     연도별 순손익(수수료+펀딩 포함)")
    yr = {}
    for y_, g in net.groupby(net.index.year):
        v = float((np.prod(1 + g.values) - 1) * 100)
        yr[int(y_)] = v
        print(f"       {y_}  {v:+8.1f}%   {'▲'*min(20,int(max(0,v)/5))}"
              f"{'▼'*min(20,int(max(0,-v)/5))}")
    res["by_year"] = yr

    # ── ③ 리드-래그 ───────────────────────────────────────────────────
    print(f"\n  ③ 리드-래그 — BTC 가 먼저 움직이는가")
    ll = {}
    for k in range(0, 6):
        c = float(d["btc"].corr(d["alt"].shift(-k)))
        ll[k] = c
        tag = "  ← 동시" if k == 0 else ""
        print(f"     BTC(t) vs 알트(t+{k})   상관 {c:+.4f}{tag}")
    res["lead_lag"] = ll
    print("     ⚠ k≥1 상관이 0 근처면 BTC 로 알트를 **선행 예측**할 수 없다 —")
    print("        동시 상관이 아무리 높아도 그건 거래가 아니다")

    print("\n" + "=" * 100)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n_days": int(len(d)), "results": res},
        ensure_ascii=False, indent=2, default=str))
    print(f"  → {a.out}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
