"""**성질**로 숏 대상을 고를 수 있는가 — 종목 이름이 아니라 측정값으로.

왜 성질인가
    2026-08-15 실측: 표본 안 순위가 표본 밖을 **전혀 예측하지 못한다**
    (Spearman rho -0.058 · p 0.574, 98종목). IS 상위 12개 중 8개가 OOS 에서
    마이너스였다. 즉 **"과거에 잘 된 종목 고르기"는 죽었다.**

    남은 길은 성질이다 — "어떤 종목이 잘 되나"가 아니라 "**어떤 상태의 종목이
    잘 되나**". 결정적 차이는 성질이 **매 시점 측정 가능**하다는 것이다.
    종목 이름은 미래에 못 쓰지만 "변동성 상위 20%" 는 언제든 쓸 수 있다.

무엇을 재나 — 진입 **직전** 값만 쓴다
    ⚠ 성질은 앵커 **이전** 데이터로만 계산한다. 앵커 당일이나 이후를 섞으면
      그 순간 lookahead 다. 오늘 하루에 그 병으로 두 번 물렸다
      (volume_burst 트리거, 커널 진입 바).

      rv_30d        직전 30일 일수익률 표준편차 (연율 아님, 일 단위 %)
      ret_30d       직전 30일 누적 수익률 %
      ret_7d        직전 7일 누적 수익률 %
      dd_from_high  직전 90일 고가 대비 낙폭 %
      dollar_vol    직전 30일 일 거래대금 중앙값 (로그)
      age_days      상장 후 경과일 (일봉 첫날 기준)

어떻게 판정하나
    성질별로 **오분위(quintile)** 를 나눠 각 구간의 숏 수익을 본다.
    · IS 에서 단조(monotone)인가 — 성질이 커질수록 수익이 늘거나 주는가
    · **그 방향이 OOS 에서 유지되는가** ← 이게 유일한 판정 기준

    단조가 아니거나 OOS 에서 뒤집히면 그 성질은 버린다.

사용:
  python3 -m scripts.research.short_trait_scan --split 2026-02-01
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
log = logging.getLogger("trait_scan")

OUT = ROOT / "runs" / "research_track" / "short_trait_scan.json"
N_BINS = 5
MIN_PER_BIN = 20        # 이보다 적으면 구간 통계가 안 선다


def traits_at(bars: pd.DataFrame, anchor) -> dict | None:
    """앵커 **직전**까지의 데이터로만 성질을 잰다."""
    past = bars[bars.index.date < anchor]
    if len(past) < 90:
        return None
    c = past["close"]
    r = c.pct_change().dropna()
    if len(r) < 30:
        return None
    r30 = r.tail(30)
    hi90 = float(past["high"].tail(90).max())
    last = float(c.iloc[-1])
    dv = float((past["close"] * past["volume"]).tail(30).median())
    return {
        "rv_30d": float(r30.std() * 100),
        "ret_30d": float((last / float(c.iloc[-31]) - 1) * 100) if len(c) > 31 else None,
        "ret_7d": float((last / float(c.iloc[-8]) - 1) * 100) if len(c) > 8 else None,
        "dd_from_high": float((last / hi90 - 1) * 100) if hi90 else None,
        "log_dollar_vol": float(np.log10(dv)) if dv > 0 else None,
        "age_days": float((anchor - past.index[0].date()).days),
    }


def quintile_table(df: pd.DataFrame, trait: str, split_date) -> dict | None:
    """성질 오분위별 IS/OOS 수익. 경계는 **IS 에서만** 정한다."""
    d = df[df[trait].notna()]
    if len(d) < N_BINS * MIN_PER_BIN:
        return None
    is_d = d[d["anchor"] < split_date]
    oos_d = d[d["anchor"] >= split_date]
    if len(is_d) < N_BINS * MIN_PER_BIN or len(oos_d) < N_BINS * 3:
        return None
    # ⚠ 경계를 전체에서 잡으면 표본 밖 정보가 새어든다. IS 에서만 잡는다.
    try:
        edges = np.unique(np.quantile(is_d[trait], np.linspace(0, 1, N_BINS + 1)))
    except Exception:
        return None
    if len(edges) < 3:
        return None

    def agg(sub):
        out = []
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            m = ((sub[trait] >= lo) & (sub[trait] < hi)) if i < len(edges) - 2 \
                else ((sub[trait] >= lo) & (sub[trait] <= hi))
            v = sub.loc[m, "ret"].values
            if len(v) < 2:
                out.append({"n": int(len(v))})
                continue
            se = v.std(ddof=1) / np.sqrt(len(v))
            out.append({"n": int(len(v)), "mean": float(v.mean()),
                        "t": float(v.mean() / se) if se else None})
        return out

    is_b, oos_b = agg(is_d), agg(oos_d)
    is_means = [b.get("mean") for b in is_b]
    ok = [m for m in is_means if m is not None]
    # 단조성 — 스피어만으로 잰다(구간 순서 대 평균)
    mono = None
    if len(ok) >= 3:
        from scipy import stats as sps
        idx = [i for i, m in enumerate(is_means) if m is not None]
        mono = float(sps.spearmanr(idx, ok).correlation)
    oos_means = [b.get("mean") for b in oos_b]
    ok_o = [m for m in oos_means if m is not None]
    mono_o = None
    if len(ok_o) >= 3:
        from scipy import stats as sps
        idx = [i for i, m in enumerate(oos_means) if m is not None]
        mono_o = float(sps.spearmanr(idx, ok_o).correlation)

    return {"trait": trait, "edges": [float(e) for e in edges],
            "IS": is_b, "OOS": oos_b,
            "is_monotone": mono, "oos_monotone": mono_o,
            # **판정**: IS 단조가 뚜렷하고 OOS 가 같은 부호로 따라오는가
            "survives": bool(mono is not None and mono_o is not None
                             and abs(mono) >= 0.8 and mono * mono_o > 0)}


def main() -> int:
    p = argparse.ArgumentParser(description="성질 기반 숏 대상 선별")
    p.add_argument("--split", required=True)
    p.add_argument("--sl", type=float, default=0.2)
    p.add_argument("--tp", type=float, default=0.3)
    p.add_argument("--hold", type=int, default=30)
    p.add_argument("--min-dollar-vol", type=float, default=1_000_000)
    p.add_argument("--min-days", type=int, default=120)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from app.db.session import engine
    from research.short_universe_scan import full_daily, run_anchor, universe

    split_date = datetime.fromisoformat(a.split).date()
    with engine.connect() as c0:
        uni = universe(c0, a.min_dollar_vol, a.min_days)
    if a.limit:
        uni = uni[:a.limit]
    log.info("유동성 통과 %d종목 · 손절 %.0f%% · 익절 %.0f%% · 보유 %d일",
             len(uni), a.sl * 100, a.tp * 100, a.hold)

    recs = []
    with engine.connect() as conn:
        for i, u in enumerate(uni, 1):
            sym = u["symbol"]
            bars = full_daily(conn, sym)
            if len(bars) < a.hold + 100:
                continue
            d0, d1 = bars.index[0].date(), bars.index[-1].date()
            anchor = d0 + timedelta(days=90)      # 성질 계산에 90일 필요
            while anchor <= d1 - timedelta(days=a.hold + 2):
                tr = traits_at(bars, anchor)
                if tr:
                    seg = bars[(bars.index.date >= anchor)
                               & (bars.index.date <= anchor + timedelta(days=a.hold + 5))]
                    if len(seg) >= a.hold - 2:
                        try:
                            trades = run_anchor(sym, anchor, seg, a.sl, a.tp, a.hold)
                        except Exception:
                            trades = []
                        for t in trades:
                            recs.append({"symbol": sym, "anchor": anchor,
                                         "ret": float(t.return_pct) * 100, **tr})
                anchor += timedelta(days=a.hold)   # 겹치지 않는 앵커
            if i % 25 == 0:
                log.info("%d/%d · 표본 %d", i, len(uni), len(recs))

    if not recs:
        raise SystemExit("표본이 없다")
    df = pd.DataFrame(recs)
    log.info("총 표본 %d (IS %d / OOS %d)", len(df),
             int((df["anchor"] < split_date).sum()),
             int((df["anchor"] >= split_date).sum()))

    traits = ["rv_30d", "ret_30d", "ret_7d", "dd_from_high",
              "log_dollar_vol", "age_days"]
    tables = [t for t in (quintile_table(df, tr, split_date) for tr in traits) if t]

    out = {"params": {"sl": a.sl, "tp": a.tp, "hold": a.hold, "split": a.split,
                      "n_bins": N_BINS},
           "n_samples": len(df),
           "n_is": int((df["anchor"] < split_date).sum()),
           "n_oos": int((df["anchor"] >= split_date).sum()),
           "traits": tables}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    print("=" * 92)
    print(f"성질 기반 숏 선별 — 표본 {len(df)} (IS {out['n_is']} / OOS {out['n_oos']})")
    print(f"손절 {a.sl:.0%} · 익절 {a.tp:.0%} · 보유 {a.hold}일 · 분할 {a.split}")
    print("=" * 92)
    for tb in tables:
        mark = "  ★ 살아남음" if tb["survives"] else ""
        print(f"\n── {tb['trait']} "
              f"(IS 단조 {tb['is_monotone']:+.2f} · OOS 단조 "
              f"{(tb['oos_monotone'] if tb['oos_monotone'] is not None else 0):+.2f})"
              f"{mark}")
        print(f"   {'구간':<6}{'경계':>22}{'IS n':>7}{'IS 평균%':>10}{'IS t':>7}"
              f"{'OOS n':>7}{'OOS 평균%':>11}")
        for i, (b_is, b_oos) in enumerate(zip(tb["IS"], tb["OOS"])):
            lo, hi = tb["edges"][i], tb["edges"][i + 1]
            print(f"   Q{i+1:<5}{f'{lo:.2f}~{hi:.2f}':>22}{b_is.get('n', 0):>7}"
                  f"{(b_is.get('mean') or 0):>10.2f}{(b_is.get('t') or 0):>7.2f}"
                  f"{b_oos.get('n', 0):>7}{(b_oos.get('mean') or 0):>11.2f}")
    print()
    print("-" * 92)
    alive = [t["trait"] for t in tables if t["survives"]]
    if alive:
        print(f"  **표본 밖까지 방향이 유지된 성질**: {', '.join(alive)}")
        print("     → 이걸로 선별 규칙을 만들 값어치가 있다.")
    else:
        print("  **살아남은 성질이 없다.** IS 에서 단조여도 OOS 에서 뒤집히거나,")
        print("     애초에 단조가 아니다. 이 성질 집합으로는 선별할 수 없다.")
    print("=" * 92)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
