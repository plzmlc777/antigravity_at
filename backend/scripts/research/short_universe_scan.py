"""숏 규칙을 **전 종목**에 적용 — 종목 선별이 가능한지부터 묻는다.

왜 이걸 먼저 묻나
    2026-08-14 위약 대조에서 신상저격수의 전제가 무너졌다. 규칙 없이 30일 숏만
    들고 있으면 신규 상장 -8.80% / 기성 종목 -0.17% 로 **둘 다 마이너스**이고,
    규칙(손절·익절·보유)을 얹으면 신규 +2.24% / 기성 **+6.13%** 로 **기성이 더
    낫다**. 엣지의 출처가 '신규 상장'이 아니라 규칙 자체였다.

    그래서 대상을 전 종목으로 넓힌다. 다만 **"과거에 잘 된 종목을 고른다"는
    과최적화 기계다.** 먼저 물어야 할 것은:

        표본 안에서 좋았던 종목이 표본 밖에서도 좋은가?

    이 순위 상관이 0 이면 종목 선별은 불가능하고, 성질(변동성·펀딩·거래대금
    같은)로 고르는 수밖에 없다. 그 판정을 안 하고 상위 N 종목을 뽑으면
    오늘 하루에 세 번 본 함정을 네 번째로 밟는 것이다.

⚠ 겹치지 않는 앵커
    진입 간격(stride)을 보유기간 이상으로 둔다. 기억의 교훈:
    "겹치는 창으로 상관·지속성 재지 마라. r +0.470 → 비겹침 +0.001".

사용:
  python3 -m scripts.research.short_universe_scan --split 2026-02-01 --limit 40
  python3 -m scripts.research.short_universe_scan --split 2026-02-01 \\
      --sl 0.2 --tp 0.3 --hold 30
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("short_scan")

OUT = ROOT / "runs" / "research_track" / "short_universe_scan.json"
MIN_ANCHORS = 4          # 이보다 적으면 종목 수준 통계가 안 선다


def universe(conn, min_dollar_vol: float, min_days: int) -> list[dict]:
    """유동성 게이트를 통과한 종목만.

    ⚠ 게이트 없이 전 종목을 훑으면 **거래도 못 할 잡코인이 결과를 만든다.**
      기억의 교훈 #78: "자동구성 코호트는 유동성 필터 필수. 실측 +0.60% →
      $1M 필터 시 **-0.25% 로 부호 반전**".

    거래대금은 `close * volume` 의 **중앙값**을 쓴다. 평균은 상장일 폭발
    거래량 하나에 끌려간다.
    """
    from sqlalchemy import text
    rows = conn.execute(text("""
        SELECT symbol,
               count(*)                                   AS n_days,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY close * volume) AS med_dv,
               min(date) AS d0, max(date) AS d1
        FROM ohlcv_daily
        WHERE is_partial = false
        GROUP BY symbol
        HAVING count(*) >= :min_days
           AND percentile_cont(0.5) WITHIN GROUP (ORDER BY close * volume) >= :mdv
        ORDER BY 3 DESC
    """), {"min_days": min_days, "mdv": min_dollar_vol}).fetchall()
    return [{"symbol": r[0], "n_days": r[1], "med_dollar_vol": float(r[2]),
             "first": str(r[3]), "last": str(r[4])} for r in rows]


def full_daily(conn, sym: str) -> pd.DataFrame:
    """일봉 — **캐시 테이블에서** 읽는다.

    예전엔 1분봉을 끌어와 파이썬에서 리샘플했다. 45GB · 2.5억 행이라 종목당
    수십 초였고 608 종목이면 몇 시간이었다(실측: 11분에 25종목도 못 넘김).
    `ohlcv_daily` 로 내려서 종목당 수십 밀리초가 됐다.

    **부분 봉은 제외한다** — 1분봉이 1440개에 못 미치는 날은 시가·종가가
    믿을 수 없다(오늘·상장 첫날·결손 구간).
    """
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT date, open, high, low, close, volume FROM ohlcv_daily "
        "WHERE symbol = :s AND is_partial = false ORDER BY date"),
        {"s": sym}).fetchall()
    if not r:
        return pd.DataFrame()
    df = pd.DataFrame(r, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    return df.set_index("ts").astype(float)


def run_anchor(sym: str, anchor, bars: pd.DataFrame, sl: float, tp: float,
               hold: int):
    """앵커 하나 — 그 날 숏 진입, 손절/익절/보유 규칙. 정본 커널로 실행."""
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import SourceContext
    from research.lifecycle_session_spawner import build_session_spec
    from research.sweep_engine import apply_all

    spec = build_session_spec(sym, str(anchor), policy_variant="baseline",
                              baseline_hold_days=hold)
    ps = apply_all(spec["pipeline_spec"], {
        "policy.sl_pct": sl,
        "policy.tp_pct": (1.0 if tp is None else tp),
        "policy.max_hold_bars": hold,
        # 앵커 당일 **한 번만** 진입한다 — 재진입은 이 측정의 대상이 아니다
        "source.entry_window_days": 1,
        "source.max_age_days": hold + 5,
    })
    ctx = SourceContext(symbol=sym, eval_freq_minutes=1440,
                        ohlcv_1m=None, ohlcv_eval=bars)
    bt = GenericBacktester(initial_capital=1_000_000.0,
                           fee_rate=float(spec["fee_rate"]),
                           apply_fee_to_short=True)
    return bt.run_rule_based(pipeline=build_pipeline(ps, {}), ctx=ctx,
                             signal_lag_bars=1).trades


def stats(a: np.ndarray) -> dict:
    if len(a) < 2:
        return {"n": int(len(a))}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"n": int(len(a)), "total": float(a.sum()), "mean": float(a.mean()),
            "med": float(np.median(a)), "win": float(100 * (a > 0).mean()),
            "t": float(a.mean() / se) if se else None, "worst": float(a.min())}


def main() -> int:
    p = argparse.ArgumentParser(description="전 종목 숏 규칙 스캔")
    p.add_argument("--split", required=True, help="표본 안/밖 분할 날짜 (필수)")
    p.add_argument("--sl", type=float, default=0.2)
    p.add_argument("--tp", type=float, default=0.3, help="1.0 이면 익절 없음")
    p.add_argument("--hold", type=int, default=30)
    p.add_argument("--stride", type=int, default=0,
                   help="앵커 간격(일). 기본은 hold 와 같다 — **겹치면 안 된다**")
    p.add_argument("--min-dollar-vol", type=float, default=1_000_000,
                   help="일 거래대금 중앙값 하한 (기본 $1M — 교훈 #78)")
    p.add_argument("--min-days", type=int, default=120,
                   help="완전한 일봉 최소 일수")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    stride = a.stride or a.hold
    if stride < a.hold:
        raise SystemExit(
            f"앵커 간격 {stride}일 < 보유 {a.hold}일 — **창이 겹친다**.\n"
            f"  겹치는 창으로 상관·지속성을 재면 가짜가 나온다 "
            f"(실측 r +0.470 → 비겹침 +0.001).")

    split = datetime.fromisoformat(a.split).date()
    from app.db.session import engine
    with engine.connect() as c0:
        uni = universe(c0, a.min_dollar_vol, a.min_days)
    if a.limit:
        uni = uni[:a.limit]
    if not uni:
        raise SystemExit(
            "유동성 게이트를 통과한 종목이 없다. ohlcv_daily 가 적재됐는지 "
            "확인하라: python3 -m scripts.build_ohlcv_daily --all")
    log.info("유동성 통과 %d종목 (일 거래대금 중앙값 >= $%s, 완전일봉 >= %d일)",
             len(uni), f"{a.min_dollar_vol:,.0f}", a.min_days)
    log.info("손절 %.0f%% · 익절 %s · 보유 %d일 · 앵커 %d일 간격 · 분할 %s",
             a.sl * 100, ("없음" if a.tp >= 1.0 else f"{a.tp*100:.0f}%"),
             a.hold, stride, split)
    symbol_meta = {u["symbol"]: u for u in uni}

    rows = []
    with engine.connect() as conn:
        for i, sym in enumerate([u["symbol"] for u in uni], 1):
            try:
                bars = full_daily(conn, sym)
            except Exception as exc:
                log.warning("%s 데이터 실패: %s", sym, exc)
                continue
            if len(bars) < a.hold + 10:
                continue
            is_r, oos_r, n_anch = [], [], 0
            d0, d1 = bars.index[0].date(), bars.index[-1].date()
            anchor = d0
            while anchor <= d1 - timedelta(days=a.hold + 2):
                seg = bars[(bars.index.date >= anchor)
                           & (bars.index.date <= anchor + timedelta(days=a.hold + 5))]
                if len(seg) >= a.hold - 2:
                    try:
                        tr = run_anchor(sym, anchor, seg, a.sl, a.tp, a.hold)
                    except Exception:
                        tr = []
                    for t in tr:
                        n_anch += 1
                        r = float(t.return_pct) * 100
                        (oos_r if anchor >= split else is_r).append(r)
                anchor += timedelta(days=stride)
            if len(is_r) + len(oos_r) < MIN_ANCHORS:
                continue
            rows.append({"symbol": sym, "first": str(d0), "last": str(d1),
                         "med_dollar_vol": symbol_meta[sym]["med_dollar_vol"],
                         "IS": stats(np.array(is_r)),
                         "OOS": stats(np.array(oos_r))})
            if i % 25 == 0:
                log.info("%d/%d (사용 %d)", i, len(uni), len(rows))

    # ── 핵심 질문: 표본 안 순위가 표본 밖을 예측하는가 ──────────────────
    both = [r for r in rows
            if r["IS"].get("mean") is not None and r["OOS"].get("mean") is not None
            and r["IS"]["n"] >= 3 and r["OOS"]["n"] >= 3]
    rank = None
    if len(both) >= 8:
        from scipy import stats as sps
        x = [r["IS"]["mean"] for r in both]
        y = [r["OOS"]["mean"] for r in both]
        rho, pval = sps.spearmanr(x, y)
        rank = {"n_symbols": len(both), "spearman_rho": float(rho),
                "p_value": float(pval)}

    out = {"params": {"sl": a.sl, "tp": a.tp, "hold": a.hold, "stride": stride,
                      "split": a.split, "min_dollar_vol": a.min_dollar_vol,
                      "min_days": a.min_days},
           "n_symbols": len(rows), "rank_persistence": rank, "symbols": rows}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print("=" * 88)
    print(f"전 종목 숏 규칙 스캔 — {len(rows)}종목 · 손절 {a.sl:.0%} · "
          f"익절 {'없음' if a.tp >= 1.0 else f'{a.tp:.0%}'} · 보유 {a.hold}일")
    print("=" * 88)
    if rank:
        print(f"  **표본 안 → 표본 밖 순위 상관 (Spearman)**: "
              f"rho {rank['spearman_rho']:+.3f} · p {rank['p_value']:.4f} "
              f"(종목 {rank['n_symbols']})")
        if rank["p_value"] > 0.05 or abs(rank["spearman_rho"]) < 0.2:
            print("     → **종목 선별은 근거가 없다.** 과거에 좋았던 종목이")
            print("        앞으로 좋다는 증거가 없으므로, 성질(변동성·펀딩 등)로")
            print("        고르는 방법을 찾아야 한다.")
        else:
            print("     → 순위가 이어진다. 종목 선별을 더 볼 값어치가 있다.")
    else:
        print("  순위 상관을 낼 표본이 부족하다")
    print("-" * 88)
    ranked = sorted([r for r in rows if r["IS"].get("mean") is not None],
                    key=lambda r: -r["IS"]["mean"])
    print(f"  {'종목':<12}{'IS n':>6}{'IS 평균%':>10}{'IS t':>7}"
          f"{'OOS n':>7}{'OOS 평균%':>11}{'OOS t':>7}")
    for r in ranked[:12]:
        i_, o_ = r["IS"], r["OOS"]
        print(f"  {r['symbol']:<12}{i_.get('n', 0):>6}{i_.get('mean', 0):>10.2f}"
              f"{(i_.get('t') or 0):>7.2f}{o_.get('n', 0):>7}"
              f"{(o_.get('mean') or 0):>11.2f}{(o_.get('t') or 0):>7.2f}")
    print("=" * 88)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
