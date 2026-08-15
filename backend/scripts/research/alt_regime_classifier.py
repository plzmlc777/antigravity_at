"""알트 국면(강세·약세·횡보) 판별 — **그리는 법**과 **쓸모**를 나눠서 잰다.

라벨을 그리는 건 쉽다. 문제는 그 라벨이 **앞으로**에 대해 뭘 말하느냐다.
그래서 이 스크립트는 두 가지를 따로 낸다:

    ① 판별   오늘 국면이 무엇인가 (사후적으로는 항상 답이 나온다)
    ② 쓸모   그 라벨을 알면 **다음 30일**을 더 잘 아는가

⚠ 임계값을 탐색하지 않는다 (교훈 #95)
    격자를 훑어 제일 잘 나뉘는 칸을 고르면 그건 이미 선택된 칸이라 통과한다.
    그래서 **관행적인 값 3종을 미리 못박고** 그것만 낸다. 잘 안 나뉘면
    "안 나뉜다"가 결론이다.

⚠ 국면 라벨의 유용성은 이미 한 번 부정됐다
    2026-08-15, 신상저격수 맥락에서 열한 번째 기각 —
    [[project-regime-detection-closed-2026-08-15]]. 갈림 폭이 위약을 통과했는데
    (p 0.026) 최대통계량·내적일관성·방향대조 세 장치에서 전부 죽었다.
    여기서는 **전략이 아니라 시장 지수 자체**에 대해 다시 묻는다 — 더 쉬운
    질문이다. 이것도 안 되면 국면 라벨은 판별용 서술어일 뿐이다.

⚠ 유니버스 선정에 **미래를 쓰지 않는다**
    앞선 `alt_market_drift_check` 의 풀은 전 구간 ADV 로 걸렀다 — 끝까지
    살아남은 종목만 남는다(생존 편향). 여기서는 **직전 30일** 거래대금으로
    그 날짜 시점에 자격을 판정한다.

정의 3종 (전부 60일 창 · 사전 확정)
    A 추세      지수 60일 수익률   > +10% 강세 / < -10% 약세 / 그 사이 횡보
    B 폭        50일선 위 종목 비율 > 60% 강세 / < 40% 약세 / 그 사이 횡보
    C 상대      지수 60일 − BTC 60일 > +10% 알트강세 / < -10% 알트약세

사용:
  python3 -m scripts.research.alt_regime_classifier
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
log = logging.getLogger("regime")

OUT = ROOT / "runs" / "research_track" / "alt_regime_classifier.json"

MIN_ADV = 3e6          # 직전 30일 평균 거래대금
MIN_HIST = 60          # 지수에 들어가려면 최소 60일 이력
TREND_W = 60           # 국면 판정 창
FWD = 30               # 앞으로 며칠을 예측하려는가
MA_W = 50

# 사전 확정 임계값 — **탐색하지 않는다**
TREND_HI, TREND_LO = 10.0, -10.0
BREADTH_HI, BREADTH_LO = 60.0, 40.0
REL_HI, REL_LO = 10.0, -10.0


def load(conn) -> tuple[pd.DataFrame, pd.DataFrame]:
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT symbol, date, close, volume FROM ohlcv_daily "
        "ORDER BY date, symbol")).fetchall()
    df = pd.DataFrame(r, columns=["symbol", "ts", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    close = df.pivot(index="ts", columns="symbol", values="close").sort_index()
    dv = (df.assign(dv=df["close"] * df["volume"])
            .pivot(index="ts", columns="symbol", values="dv").sort_index())
    return close, dv


def build_index(close: pd.DataFrame, dv: pd.DataFrame) -> pd.DataFrame:
    """알트 국면 지표 + 폭. 자격은 **그 날짜까지의 정보로만** 판정한다.

    ⚠ 지수를 '일별 중앙수익률 누적'으로 만들지 않는다
        그건 **어떤 포트폴리오의 수익률도 아니다.** 매일 중앙값을 곱하면
        분산이 큰 자산군에서 실제 보유 수익률보다 훨씬 나쁘게 복리된다.
        그 왜곡이 60일 창에 쌓이면 국면 라벨 자체가 편향된다.

        대신 **개별 종목의 보유 수익률을 먼저 계산하고 그 횡단면 중앙값**을
        쓴다 — "중간쯤 되는 알트를 60일 들고 있으면 얼마였나"라는 뜻이 되고
        복리 왜곡이 없다.
    """
    # ⚠ shift(1) — 오늘 거래대금으로 오늘 자격을 정하면 미세하지만 미래를 쓴다.
    adv = dv.rolling(30, min_periods=20).mean().shift(1)
    hist = close.notna().rolling(MIN_HIST, min_periods=1).sum().shift(1)
    elig = (adv >= MIN_ADV) & (hist >= MIN_HIST) & close.notna()
    # BTC/ETH 는 '알트' 가 아니다 — 지표에서 뺀다(벤치마크로만 쓴다)
    for b in ("BTCUSDT", "ETHUSDT"):
        if b in elig.columns:
            elig[b] = False

    # 개별 보유 수익률 → 횡단면 중앙값
    trend = 100 * (close / close.shift(TREND_W) - 1).where(elig).median(axis=1)
    fwd = 100 * (close.shift(-FWD) / close - 1).where(elig).median(axis=1)
    n_elig = elig.sum(axis=1)

    ma = close.rolling(MA_W, min_periods=MA_W).mean()
    above = (close > ma).where(elig)
    breadth = 100 * above.mean(axis=1, skipna=True)

    out = pd.DataFrame({"trend": trend, "fwd": fwd, "n": n_elig,
                        "breadth": breadth})
    return out[out["n"] >= 20]        # 종목이 너무 적은 초기 구간 제외


def label_frame(ix: pd.DataFrame, btc: pd.Series) -> pd.DataFrame:
    d = ix.copy()
    b = btc.reindex(d.index).ffill()
    d["btc_trend"] = 100 * (b / b.shift(TREND_W) - 1)
    d["rel"] = d["trend"] - d["btc_trend"]

    def cut(col, hi, lo, names):
        return pd.cut(d[col], [-np.inf, lo, hi, np.inf], labels=names)

    d["A_추세"] = cut("trend", TREND_HI, TREND_LO, ["약세", "횡보", "강세"])
    d["B_폭"] = cut("breadth", BREADTH_HI, BREADTH_LO, ["약세", "횡보", "강세"])
    d["C_상대"] = cut("rel", REL_HI, REL_LO, ["알트약세", "중립", "알트강세"])
    return d


def report(d: pd.DataFrame, col: str) -> dict:
    """라벨별 **앞으로 30일**. 겹침을 뺀 표본으로만 판정한다(교훈 #92).

    ⚠ 솎기 오프셋을 **하나만** 쓰지 않는다
        `iloc[::30]` 은 시작점 하나에 운명을 건다. 실제로 첫 판에서 B_폭 횡보가
        n=0 이 나왔다 — 186일이나 되는 라벨인데 그 오프셋에 하나도 안 걸린 것뿐.
        오프셋 0~29 를 **전부** 돌려 그 분포를 낸다.
    """
    print(f"\n  ── {col} " + "─" * 74)
    print(f"     {'국면':>8}{'일수':>7}{'비중%':>7} | "
          f"{'앞30일 중앙%':>13}{'평균%':>9} | {'비겹침n':>8}{'평균%':>9}"
          f"{'t중앙':>8}{'t범위':>16}")
    nz = d.dropna(subset=["fwd", col])
    out = {}
    for lab in d[col].cat.categories:
        g = nz[nz[col] == lab]
        means, ts, ns = [], [], []
        for off in range(FWD):
            tv = nz.iloc[off::FWD]
            tv = tv[tv[col] == lab]["fwd"].values
            ns.append(len(tv))
            if len(tv) >= 2 and tv.std(ddof=1) > 0:
                means.append(tv.mean())
                ts.append(tv.mean() / (tv.std(ddof=1) / np.sqrt(len(tv))))
        mm = float(np.median(means)) if means else float("nan")
        tt = float(np.median(ts)) if ts else float("nan")
        out[str(lab)] = {"days": int(len(g)), "share": float(100*len(g)/max(1,len(nz))),
                         "fwd_med": float(g["fwd"].median()) if len(g) else None,
                         "fwd_mean": float(g["fwd"].mean()) if len(g) else None,
                         "thin_n": float(np.median(ns)) if ns else 0,
                         "thin_mean": mm if mm == mm else None,
                         "thin_t": tt if tt == tt else None,
                         "thin_t_lo": float(min(ts)) if ts else None,
                         "thin_t_hi": float(max(ts)) if ts else None}
        rng = f"{min(ts):+.2f}~{max(ts):+.2f}" if ts else "—"
        print(f"     {str(lab):>8}{len(g):>7}{100*len(g)/max(1,len(nz)):>7.1f} | "
              f"{g['fwd'].median():>13.2f}{g['fwd'].mean():>9.2f} | "
              f"{np.median(ns):>8.0f}{mm:>9.2f}{tt:>8.2f}{rng:>16}")
    # 갈림 폭 — 강세 라벨과 약세 라벨의 앞30일 차이 (비겹침)
    cats = list(d[col].cat.categories)
    lo_, hi_ = out[str(cats[0])], out[str(cats[-1])]
    if lo_["thin_mean"] is not None and hi_["thin_mean"] is not None:
        spread = hi_["thin_mean"] - lo_["thin_mean"]
        print(f"     갈림 폭(강세−약세, 비겹침) **{spread:+.2f}%p**")
        out["_spread"] = spread
    # 끈적임 — 30일 뒤에도 같은 라벨인가
    s = d[col]
    same = (s == s.shift(-FWD))
    st = float(100 * same[s.notna() & s.shift(-FWD).notna()].mean())
    out["_sticky_30d"] = st
    print(f"     끈적임 — 30일 뒤 같은 라벨일 확률 **{st:.1f}%** "
          f"(무작위 기대 ~{100/len(cats):.0f}%)")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="알트 국면 판별")
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine
    with engine.connect() as conn:
        close, dv = load(conn)
        btc = pd.Series(dtype=float)
        if "BTCUSDT" in close.columns:
            btc = close["BTCUSDT"].dropna()
    log.info("일봉 %d일 × %d종목", len(close), close.shape[1])
    ix = build_index(close, dv)
    d = label_frame(ix, btc)
    log.info("지수 구간 %s ~ %s · 자격 종목 중앙 %d",
             d.index[0].date(), d.index[-1].date(), int(d["n"].median()))

    print("=" * 100)
    print("  **알트 국면 판별** — 동일가중(중앙값) 알트 지수 · 자격은 직전 30일 "
          f"거래대금 ≥ $3M · 판정창 {TREND_W}일 · 예측대상 앞으로 {FWD}일")
    print("  ⚠ 임계값은 사전 확정이다 — 탐색하면 제일 잘 나뉘는 칸이 뽑혀 "
          "무조건 좋아 보인다(교훈 #95)")
    print("=" * 100)

    res = {}
    for col in ("A_추세", "B_폭", "C_상대"):
        res[col] = report(d, col)

    # ── 지금은 무슨 국면인가 ──────────────────────────────────────────
    last = d.dropna(subset=["trend"]).iloc[-1]
    print("\n" + "=" * 100)
    print(f"  **오늘({last.name.date()}) 국면**")
    print(f"     지수 {TREND_W}일 수익률   {last['trend']:+7.2f}%   "
          f"→ A_추세  **{last['A_추세']}**")
    print(f"     50일선 위 종목 비율   {last['breadth']:+7.1f}%   "
          f"→ B_폭    **{last['B_폭']}**")
    print(f"     BTC {TREND_W}일 {last['btc_trend']:+.2f}% · 상대 "
          f"{last['rel']:+.2f}%p   → C_상대 **{last['C_상대']}**")
    print(f"     자격 종목 {int(last['n'])}개")

    # 최근 12개월 라벨 흐름
    print(f"\n  최근 12개월 월말 라벨")
    m = d.dropna(subset=["trend"]).resample("ME").last().tail(12)
    for ts, row in m.iterrows():
        print(f"     {ts.date()}  추세 {row['trend']:+7.1f}% {str(row['A_추세']):>4}"
              f" · 폭 {row['breadth']:>5.1f}% {str(row['B_폭']):>4}"
              f" · 상대 {row['rel']:+7.1f}%p {str(row['C_상대']):>5}")

    print("\n" + "=" * 100)
    print("  읽는 법")
    print("    · **갈림 폭**이 0 근처면 라벨은 '지금 상태의 서술'일 뿐 예측이 아니다.")
    print("    · **끈적임**이 무작위 기대보다 크게 높아야 라벨을 보고 행동할 시간이 있다.")
    print("      낮으면 라벨을 확인한 순간 이미 다른 국면이다.")
    print("    · 비겹침 t 를 봐라 — 겹치는 표본의 t 는 한 번의 급락을 수십 번 센다.")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"labels": res,
         "today": {"date": str(last.name.date()), "trend": float(last["trend"]),
                   "breadth": float(last["breadth"]), "rel": float(last["rel"]),
                   "A": str(last["A_추세"]), "B": str(last["B_폭"]),
                   "C": str(last["C_상대"]), "n_eligible": int(last["n"])},
         "params": {"MIN_ADV": MIN_ADV, "TREND_W": TREND_W, "FWD": FWD,
                    "thresholds": {"trend": [TREND_LO, TREND_HI],
                                   "breadth": [BREADTH_LO, BREADTH_HI],
                                   "rel": [REL_LO, REL_HI]}}},
        ensure_ascii=False, indent=2, default=str))
    print(f"  → {a.out}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
