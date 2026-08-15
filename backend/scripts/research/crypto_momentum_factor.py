"""횡단면 모멘텀 요인 — **마찰부터 재고** 시작한다.

왜 이 방향인가
    2026-08-15 에 방향성 접근이 넷 다 기각됐다. 마지막 실패(무차별 규칙)의
    원인은 **시장 방향에 그대로 노출**된 것이었다 — 숏·롱이 거울로 나왔다.

    요인 방식은 구조가 다르다. 매 시점 **상위 롱 / 하위 숏을 동시에** 쥐므로
    시장 방향이 상쇄된다. 어제의 실패 모드가 원리적으로 발생하지 않는다.
    그게 이 방향을 볼 값어치의 전부다.

⚠ 논문들이 공통으로 회피하는 자리
    Sparkline: "거래비용을 모델링하지 않았다. 실무에서는 순수익이 줄어든다 —
    특히 모멘텀은 거래를 많이 해야 한다"
    Crypto factor zoo: "낮은 유동성이 거래비용을 높여 이상현상이 지속된다"

    **알파가 남았다고 보고된 곳이 곧 거래가 안 되는 곳이다.** 교훈 #78·#82 와
    같은 이야기다. 그래서 이 스크립트는 총수익보다 **회전율과 마찰을 먼저**
    낸다. 마찰이 총수익의 절반을 넘으면 그 자리에서 닫는다.

⚠ 정본 커널을 쓰지 않는다
    커널은 **한 종목 한 포지션**을 다룬다. 횡단면 롱숏 포트폴리오는 그 위층의
    객체라 커널로 표현되지 않는다(`notional_cap_portfolio_sim` 이 같은 이유로
    커널 밖에 있다). 대신 수익 계산을 여기 한 곳에 두고 주석으로 못박는다.

구성 (Sparkline / Liu-Tsyvinski-Wu 계열)
    유니버스   유동성 게이트 통과 종목
    정렬       `lookback` 일 수익률
    선택       상위/하위 **3분위**, 동일가중
    보유       `hold` 일 (기본 7)
    ⚠ 정렬은 **리밸런싱 시점까지의** 데이터만 쓴다. 보유 구간을 섞으면 lookahead 다.

사용:
  python3 -m scripts.research.crypto_momentum_factor --split 2026-02-01
  python3 -m scripts.research.crypto_momentum_factor --split 2026-02-01 \\
      --lookback 14 --hold 7 --fee-bp 5
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mom_factor")

OUT = ROOT / "runs" / "research_track" / "crypto_momentum_factor.json"
MIN_NAMES = 20      # 이보다 적으면 3분위가 의미 없다


def price_matrix(conn, symbols: list[str]) -> pd.DataFrame:
    """날짜 × 종목 종가 행렬. 부분봉은 제외한다."""
    from sqlalchemy import text
    q = text("SELECT symbol, date, close FROM ohlcv_daily "
             "WHERE is_partial = false AND symbol = ANY(:syms) ORDER BY date")
    rows = conn.execute(q, {"syms": symbols}).fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df.pivot(index="date", columns="symbol", values="close").astype(float)


def newey_west_t(a: np.ndarray, lags: int) -> float | None:
    """중첩 표본의 t — HAC(Newey-West) 보정.

    ⚠ 보유 30일을 7일마다 진입하면 관측이 4겹으로 겹친다. 겹친 표본을 독립으로
      세면 표준오차가 과소평가돼 **t 가 부풀려진다**. 기억의 교훈:
      "겹치는 창으로 상관·지속성 재지 마라 — r +0.470 → 비겹침 +0.001".

      그 교훈은 상관·지속성 측정 이야기이고, 여기서는 중첩 슬리브를 실제로
      **동시에 운용**하는 방식이라 수익 자체는 유효하다. 다만 **유의성은
      반드시 보정**해야 한다. lags = 보유/진입간격 - 1.
    """
    n = len(a)
    if n < 3 or lags < 1:
        return None
    x = a - a.mean()
    g0 = float(np.dot(x, x) / n)
    var = g0
    for j in range(1, min(lags, n - 1) + 1):
        gj = float(np.dot(x[j:], x[:-j]) / n)
        var += 2.0 * (1.0 - j / (lags + 1.0)) * gj
    if var <= 0:
        return None
    return float(a.mean() / np.sqrt(var / n))


def stats(a: np.ndarray) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"n": int(len(a)), "total": float(a.sum()), "mean": float(a.mean()),
            "med": float(np.median(a)), "win": float(100 * (a > 0).mean()),
            "t": float(a.mean() / se) if se else None,
            "std": float(a.std(ddof=1)), "worst": float(a.min())}


def main() -> int:
    p = argparse.ArgumentParser(description="횡단면 모멘텀 요인 (마찰 우선)")
    p.add_argument("--split", required=True, help="표본 안/밖 분할 날짜 (필수)")
    p.add_argument("--lookback", type=int, default=14, help="정렬용 수익률 기간")
    p.add_argument("--hold", type=int, default=7, help="보유 기간(일)")
    p.add_argument("--stride", type=int, default=0,
                   help="진입 간격(일). 기본은 보유와 같다(비겹침). "
                        "보유보다 짧으면 **중첩 슬리브**가 되고 t 는 HAC 보정된다")
    p.add_argument("--tercile", type=float, default=1 / 3)
    p.add_argument("--fee-bp", type=float, default=5.0,
                   help="편도 수수료 bp (바이낸스 선물 테이커 5bp)")
    p.add_argument("--min-dollar-vol", type=float, default=1_000_000)
    p.add_argument("--min-days", type=int, default=120)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine
    from research.short_universe_scan import universe

    split = pd.Timestamp(datetime.fromisoformat(a.split))
    with engine.connect() as conn:
        uni = [u["symbol"] for u in universe(conn, a.min_dollar_vol, a.min_days)]
        log.info("유동성 통과 %d종목 · 정렬 %d일 · 보유 %d일 · 수수료 %.1fbp",
                 len(uni), a.lookback, a.hold, a.fee_bp)
        px = price_matrix(conn, uni)
    log.info("가격 행렬 %s (날짜 × 종목)", px.shape)

    dates = px.index
    recs = []
    prev_long: set = set()
    prev_short: set = set()

    stride = a.stride or a.hold
    if stride > a.hold:
        raise SystemExit(f"진입 간격 {stride} > 보유 {a.hold} — 자본이 논다")
    nw_lags = max(0, a.hold // stride - 1)
    if nw_lags:
        log.info("중첩 슬리브 %d겹 — t 는 HAC(Newey-West, lags=%d) 보정",
                 a.hold // stride, nw_lags)

    i = a.lookback
    while i + a.hold < len(dates):
        t0, t1 = dates[i], dates[i + a.hold]
        # ⚠ 정렬은 t0 **까지의** 데이터만. 보유 구간(t0~t1)을 섞으면 lookahead.
        past = px.iloc[i - a.lookback:i + 1]
        mom = (past.iloc[-1] / past.iloc[0] - 1).dropna()
        fwd = (px.iloc[i + a.hold] / px.iloc[i] - 1)
        both = mom.index.intersection(fwd.dropna().index)
        mom, fwd_ok = mom[both], fwd[both]
        if len(both) < MIN_NAMES:
            i += a.hold
            continue

        k = max(3, int(len(both) * a.tercile))
        order = mom.sort_values()
        short_names = set(order.index[:k])          # 최저 모멘텀 → 숏
        long_names = set(order.index[-k:])          # 최고 모멘텀 → 롱

        r_long = float(fwd_ok[list(long_names)].mean()) * 100
        r_short = float(-fwd_ok[list(short_names)].mean()) * 100
        gross = r_long + r_short
        # 유니버스 평균 = 시장 수익. 달러 중립이라 **공통 움직임은 이미
        # 상쇄**되지만, 고모멘텀 코인의 베타가 높으면 잔여 노출이 남는다.
        # 그걸 재려면 시장 수익을 함께 기록해야 한다.
        r_mkt = float(fwd_ok.mean()) * 100

        # ── 회전율과 마찰 ──────────────────────────────────────────────
        # 각 다리의 명목을 1 로 본다. 교체된 비중만큼 청산+진입 수수료를 낸다.
        def leg_turnover(new: set, old: set) -> float:
            # ⚠ 중첩 슬리브에서는 직전 **슬리브**가 아니라 같은 슬리브의 직전
            #   구성과 비교해야 정확하다. 여기서는 직전 시점과 비교해
            #   회전율을 **높게(보수적으로)** 잡는다 — 마찰을 과소평가하면
            #   교훈 #82 를 정면으로 어긴다.
            if not old:
                return 1.0                      # 최초 구축은 전량 진입
            return len(new - old) / max(len(new), 1)

        to_l = leg_turnover(long_names, prev_long)
        to_s = leg_turnover(short_names, prev_short)
        turnover = (to_l + to_s) / 2
        # 교체분은 나가고(청산) 들어온다(진입) → 편도 수수료 × 2
        fric = (to_l + to_s) * a.fee_bp / 100.0   # % 단위
        recs.append({
            "date": str(t0.date()), "t1": str(t1.date()),
            "n_names": len(both), "k": k,
            "long": r_long, "short": r_short, "mkt": r_mkt,
            "gross": gross, "turnover": turnover, "friction": fric,
            "net": gross - fric,
            "split": "OOS" if t0 >= split else "IS",
        })
        prev_long, prev_short = long_names, short_names
        i += stride

    if not recs:
        raise SystemExit("표본이 없다")
    df = pd.DataFrame(recs)

    res = {}
    # ── 베타 중립화 ────────────────────────────────────────────────────
    # 달러 중립은 종목 수만 맞춘 것이고, 고모멘텀 코인의 베타가 높으면
    # 시장 상승이 롱에 더 크게 든다. **표본 안에서만** 베타를 추정해
    # (표본 밖에서 추정하면 그 순간 표본 밖이 아니다) 총수익에서 뺀다.
    is_m = df["split"] == "IS"
    beta = np.nan
    if is_m.sum() >= 10 and df.loc[is_m, "mkt"].std() > 0:
        beta = float(np.polyfit(df.loc[is_m, "mkt"], df.loc[is_m, "gross"], 1)[0])
        df["gross_bn"] = df["gross"] - beta * df["mkt"]
        df["net_bn"] = df["gross_bn"] - df["friction"]
    else:
        df["gross_bn"] = df["gross"]
        df["net_bn"] = df["net"]

    for sp in ("IS", "OOS"):
        m = df["split"] == sp
        for col in ("gross", "net", "gross_bn", "net_bn", "long", "short",
                    "mkt", "friction", "turnover"):
            st = stats(df.loc[m, col].values)
            if nw_lags and "mean" in st:
                st["t_naive"] = st["t"]
                st["t"] = newey_west_t(df.loc[m, col].values, nw_lags)
                st["t_hac"] = True
            res[f"{sp}/{col}"] = st
        # 총수익과 시장의 상관 — 잔여 방향 노출의 크기
        if m.sum() >= 5 and df.loc[m, "mkt"].std() > 0:
            res[f"{sp}/corr_mkt"] = float(
                np.corrcoef(df.loc[m, "gross"], df.loc[m, "mkt"])[0, 1])

    per_year = 365 / stride
    out = {"beta_is": (None if np.isnan(beta) else beta),
           "nw_lags": nw_lags, "stride": stride,
           "params": {"lookback": a.lookback, "hold": a.hold, "fee_bp": a.fee_bp,
                      "tercile": a.tercile, "split": a.split,
                      "min_dollar_vol": a.min_dollar_vol},
           "n_periods": len(df), "periods_per_year": per_year,
           "results": res, "periods": recs}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print("=" * 86)
    print(f"횡단면 모멘텀 요인 — 기간 {len(df)}회 · 정렬 {a.lookback}일 · "
          f"보유 {a.hold}일 · 진입 {stride}일 · "
          f"종목 {int(df['n_names'].mean())} (3분위 {int(df['k'].mean())})")
    if nw_lags:
        print(f"⚠ 중첩 {a.hold // stride}겹 — t 는 **HAC 보정**(lags={nw_lags}). "
              f"보정 전 t 는 부풀려진 값이다")
    print(f"수수료 편도 {a.fee_bp}bp · 분할 {a.split}")
    print("=" * 86)

    # ── 마찰부터 ───────────────────────────────────────────────────────
    tv, fr = df["turnover"].mean(), df["friction"].mean()
    g_all = df["gross"].mean()
    print(f"  **마찰 먼저** (교훈 #82 — 차익형은 σ 대 마찰부터 재라)")
    print(f"     평균 회전율 {tv*100:>5.1f}% · 기간당 마찰 {fr:>5.3f}% · "
          f"연환산 마찰 {fr*per_year:>5.2f}%")
    print(f"     기간당 총수익 {g_all:>5.3f}% · **마찰/총수익 "
          f"{(fr/abs(g_all)*100 if g_all else float('inf')):>5.1f}%**")
    if g_all <= 0 or fr / abs(g_all) >= 0.5:
        print(f"     ⚠ **마찰이 총수익의 절반 이상**이거나 총수익이 음수다.")
        print(f"        여기서 닫는 것이 맞다 — 파라미터를 다듬어도 자릿수가 다르다.")
    print("-" * 86)

    print(f"  {'구간':<6}{'항목':<10}{'n':>5}{'평균%':>9}{'총%':>10}"
          f"{'승률%':>8}{'t':>8}{'연환산%':>10}")
    for sp in ("IS", "OOS"):
        for col in ("gross", "net", "gross_bn", "net_bn", "long", "short", "mkt"):
            s = res[f"{sp}/{col}"]
            if "mean" not in s:
                continue
            print(f"  {sp:<6}{col:<10}{s['n']:>5}{s['mean']:>9.3f}{s['total']:>10.2f}"
                  f"{s['win']:>8.1f}{(s['t'] or 0):>8.2f}{s['mean']*per_year:>10.2f}")
        print()
    print("-" * 86)
    print("-" * 86)
    print(f"  **시장 노출** — 표본 안 베타 {beta:+.3f} · "
          f"총수익-시장 상관 IS {res.get('IS/corr_mkt', 0):+.3f} / "
          f"OOS {res.get('OOS/corr_mkt', 0):+.3f}")
    bi, bo = res["IS/net_bn"].get("mean"), res["OOS/net_bn"].get("mean")
    if bi is not None:
        print(f"  **베타 중립 후 순수익** — 표본 안 {bi:+.3f}%/기간 "
              f"(연 {bi*per_year:+.1f}%) · 표본 밖 {(bo or 0):+.3f}%/기간 "
              f"(연 {(bo or 0)*per_year:+.1f}%)")
        if abs(res.get("IS/corr_mkt", 0)) < 0.2:
            print("     시장 상관이 낮다 — 달러 중립만으로 이미 중립에 가깝다")
        else:
            print("     ⚠ 시장 상관이 뚜렷하다 — 베타 중립 전 수치는 방향 베팅이 섞여 있다")

    gi = res["IS/net"].get("mean")
    go = res["OOS/net"].get("mean")
    li, si = res["IS/long"].get("mean"), res["IS/short"].get("mean")
    if gi is not None:
        print(f"  순수익 표본 안 {gi:+.3f}%/기간 (연 {gi*per_year:+.1f}%) · "
              f"표본 밖 {go:+.3f}%/기간 (연 {(go or 0)*per_year:+.1f}%)")
    if li is not None and si is not None:
        print(f"  다리별 표본 안 — 롱 {li:+.3f}% · 숏 {si:+.3f}%")
        print(f"     한쪽만 벌면 방향성이 남아 있다는 뜻이다(교훈 #91)")
    print("=" * 86)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
