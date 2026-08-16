"""BTC → 알트 **시간 단위** 리드-래그 — 일봉이 대답할 수 없는 칸.

왜 다시 재는가
    일봉으로는 이미 기각했다 — 동시 상관 +0.807 인데 t+1 은 **-0.066**,
    t+2~5 는 ±0.03. 그런데 일봉은 **1~4시간 전파를 볼 수 없다.** BTC 가 먼저
    움직이고 알트가 두어 시간 뒤 따라온다면 일봉에서는 같은 봉 안에 묻힌다.
    2026-08-15 에 574종목 167만 행 시간봉을 깔았으므로 이제 볼 수 있다.

⚠ 기대는 낮게 잡는다
    · 2026년 시장에서 시간 단위 교차자산 전파는 차익거래됐을 가능성이 크다.
    · 설령 있어도 [[feedback-lesson-80-cross-market-transfer-edge-fee-ratio]] —
      고빈도·소폭엣지는 마찰에 죽는다.
    그래서 이 스크립트는 상관을 재는 데서 멈추지 않고 **마찰 손익분기 상관**을
    같이 낸다. 관측 상관이 그보다 작으면 유의해도 거래가 아니다.

⚠ 격자를 훑으므로 **최대통계량** 귀무가 필요하다 (교훈 #95)
    되돌아보기 5종 × 보유 5종 = 25칸에서 최고를 고르는 건 다중검정이다.
    귀무는 **원형회전한 BTC 로 같은 25칸을 전부 다시 훑은 최고 |t|** 다.
    칸별 위약은 이미 선택된 칸이라 통과한다.

⚠ 원형회전을 쓰는 이유 (뒤섞기가 아니라)
    BTC 시간봉은 자기상관이 있다. 뒤섞으면 그 구조가 파괴돼 귀무가 너무
    쉬워진다. 통째로 밀면 자기상관은 살고 **알트와의 짝만** 깨진다.

⚠ 유니버스는 기성 대조 풀이다
    신규 상장 코호트는 시간봉이 자기 상장창에만 있어 달력이 안 맞는다.
    풀 85종목은 2025-01~2026-08 전 구간이 있다.

사용:
  python3 -m scripts.research.btc_alt_hourly_leadlag --rot 200
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
log = logging.getLogger("leadlag")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT = ROOT / "runs" / "research_track" / "btc_alt_hourly_leadlag.json"

BENCH = "BTCUSDT"
CONTROL_LISTED_BEFORE = "2024-07-01"
CONTROL_MIN_ADV = 3e6
CONTROL_MIN_DAYS = 500
FEE = 0.0005                       # 테이커 5bp — 왕복 10bp
LOOKBACKS = [1, 2, 4, 6, 12]       # BTC 신호 창(시간)
HORIZONS = [1, 2, 4, 6, 12]        # 알트 보유(시간)
SPLIT = "2026-01-01"


def load(conn, syms):
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT symbol, ts, close FROM ohlcv_hourly WHERE symbol = ANY(:s) "
        "ORDER BY ts, symbol"), {"s": syms}).fetchall()
    df = pd.DataFrame(r, columns=["symbol", "ts", "close"])
    df["ts"] = pd.to_datetime(df["ts"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.pivot(index="ts", columns="symbol", values="close").sort_index()


def cells(alt: np.ndarray, btc: np.ndarray, split_i: int) -> dict:
    """25칸 전부. 각 칸 = (BTC 되돌아보기 L 누적) → (알트 보유 H 누적).

    신호와 수익 구간이 **겹치지 않게** 자른다 — 겹치면 동시 상관을 예측으로
    착각한다. 그리고 표본을 H 간격으로 솎아 **비겹침**으로 t 를 낸다(교훈 #92).
    """
    out = {}
    n = len(alt)
    for L in LOOKBACKS:
        # BTC 의 직전 L시간 누적 수익률 (시각 i 까지 **관측 완료**)
        sig = pd.Series(btc).rolling(L).sum().values
        for H in HORIZONS:
            # 알트의 앞으로 H시간 누적 — i+1 부터 i+H
            fwd = pd.Series(alt).rolling(H).sum().shift(-H).values
            m = ~(np.isnan(sig) | np.isnan(fwd))
            idx = np.flatnonzero(m)
            if len(idx) < 100:
                continue
            # 비겹침 — H 간격으로만
            idx = idx[::H]
            s, f = sig[idx], fwd[idx]
            if len(s) < 30 or s.std() == 0:
                continue
            r = float(np.corrcoef(s, f)[0, 1])
            # 부호 거래: BTC 가 오르면 알트 롱, 내리면 숏 (신호 방향 그대로)
            pnl = np.sign(s) * f
            se = pnl.std(ddof=1) / np.sqrt(len(pnl))
            t = float(pnl.mean() / se) if se else float("nan")
            # IS/OOS
            is_m = idx < split_i
            out[(L, H)] = {
                "n": int(len(pnl)), "corr": r, "t": t,
                "gross_bp": float(pnl.mean() * 1e4),
                "is_gross_bp": float(pnl[is_m].mean() * 1e4) if is_m.any() else None,
                "oos_gross_bp": float(pnl[~is_m].mean() * 1e4) if (~is_m).any() else None,
                # 마찰 손익분기 상관 — |r| 이 이보다 작으면 유의해도 거래가 아니다
                "breakeven_corr": float(2 * FEE / (f.std() or np.inf)),
            }
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="BTC→알트 시간 단위 리드-래그")
    p.add_argument("--since", default="2025-01-01")
    p.add_argument("--rot", type=int, default=200)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine
    listings = json.loads(LISTINGS.read_text())
    cand = sorted(k for k, m in listings.items()
                  if isinstance(m, dict) and m.get("onboard_date")
                  and m["onboard_date"] <= CONTROL_LISTED_BEFORE)
    with engine.connect() as conn:
        liq = {r[0]: (r[1], float(r[2] or 0)) for r in conn.execute(text(
            "SELECT symbol, count(*), avg(close*volume) FROM ohlcv_daily "
            "WHERE date >= :d GROUP BY symbol"), {"d": a.since}).fetchall()}
        pool = [s for s in cand if liq.get(s, (0, 0))[0] >= CONTROL_MIN_DAYS
                and liq.get(s, (0, 0))[1] >= CONTROL_MIN_ADV]
        close = load(conn, sorted(set(pool) | {BENCH}))
    close = close[close.index >= a.since]
    ret = np.log(close / close.shift(1))        # 로그 — 누적이 합이 된다
    alt_s = ret[pool].mean(axis=1, skipna=True)
    btc_s = ret[BENCH]
    d = pd.concat([alt_s.rename("alt"), btc_s.rename("btc")], axis=1).dropna()
    log.info("풀 %d종목 · 시간봉 %d개 · %s ~ %s", len(pool), len(d),
             d.index[0], d.index[-1])

    alt, btc = d["alt"].values, d["btc"].values
    split_i = int(np.searchsorted(d.index.values,
                                  np.datetime64(SPLIT)))

    print("=" * 100)
    print(f"  **BTC → 알트 시간 단위 리드-래그** — 기성 풀 {len(pool)}종목 동일가중 "
          f"· {len(d):,}시간봉 · {d.index[0].date()} ~ {d.index[-1].date()}")
    print("=" * 100)

    # ── ① 원시 리드-래그 상관 ─────────────────────────────────────────
    print(f"\n  ① 시차별 상관 — corr(BTC[t], 알트[t+k])")
    ll = {}
    for k in range(-4, 7):
        if k >= 0:
            x, y = btc[:len(btc)-k], alt[k:]
        else:
            x, y = btc[-k:], alt[:len(alt)+k]
        c = float(np.corrcoef(x, y)[0, 1])
        ll[k] = c
        tag = ("  ← 동시" if k == 0 else
               "  ← 알트가 선행" if k < 0 else "")
        print(f"     k={k:>+3}h   {c:+.4f}{tag}")
    print("     ⚠ k>0 이 0 근처면 BTC 로 알트를 **선행 예측**할 수 없다")

    # ── ② 격자 ────────────────────────────────────────────────────────
    obs = cells(alt, btc, split_i)
    print(f"\n  ② 격자 {len(obs)}칸 — BTC 직전 L시간 → 알트 앞 H시간 (비겹침)")
    print(f"     {'L→H':>8}{'표본':>7}{'상관':>9}{'t':>7}{'총액bp':>9}"
          f"{'IS bp':>8}{'OOS bp':>8}{'손익분기상관':>12}{'거래가능':>9}")
    ranked = sorted(obs.items(), key=lambda kv: -abs(kv[1]["t"]))
    for (L, H), v in ranked:
        ok = "○" if abs(v["corr"]) > v["breakeven_corr"] else "✗"
        print(f"     {f'{L}→{H}':>8}{v['n']:>7}{v['corr']:>9.4f}{v['t']:>7.2f}"
              f"{v['gross_bp']:>9.2f}{(v['is_gross_bp'] or 0):>8.2f}"
              f"{(v['oos_gross_bp'] or 0):>8.2f}{v['breakeven_corr']:>12.4f}"
              f"{ok:>9}")
    best = ranked[0]
    obs_max_t = abs(best[1]["t"])

    # ── ③ 최대통계량 귀무 (원형회전) ──────────────────────────────────
    rng = np.random.default_rng(20260816)
    null = []
    for _ in range(a.rot):
        k = int(rng.integers(24, len(btc) - 24))
        rb = np.roll(btc, k)
        c = cells(alt, rb, split_i)
        null.append(max((abs(v["t"]) for v in c.values()), default=0.0))
    null = np.array(null)
    p_max = float((null >= obs_max_t).mean())
    print(f"\n  ③ **최대통계량** 귀무 — 원형회전 {a.rot}회 × 같은 격자 전부 재훑기")
    print(f"     관측 최고 |t| **{obs_max_t:.2f}** (칸 {best[0][0]}→{best[0][1]}h)")
    print(f"     귀무 최고 |t| 중앙 {np.median(null):.2f} · p95 "
          f"{np.percentile(null,95):.2f} · 최대 {null.max():.2f}")
    print(f"     → **p {p_max:.3f}**")

    # ── ④ 마찰 ────────────────────────────────────────────────────────
    print(f"\n  ④ 마찰 — 왕복 {2*FEE*1e4:.0f}bp (테이커 5bp × 2)")
    tradable = [k for k, v in obs.items()
                if abs(v["corr"]) > v["breakeven_corr"]]
    print(f"     |상관| 이 손익분기를 넘는 칸: **{len(tradable)}/{len(obs)}**")
    net = {k: v["gross_bp"] - 2 * FEE * 1e4 for k, v in obs.items()}
    pos = [k for k, v in net.items() if v > 0]
    print(f"     마찰 뺀 뒤 순익이 양수인 칸: **{len(pos)}/{len(obs)}**")
    if pos:
        for k in sorted(pos, key=lambda x: -net[x])[:5]:
            print(f"       {k[0]}→{k[1]}h  순 {net[k]:+.2f}bp  "
                  f"(OOS 총액 {obs[k]['oos_gross_bp']:+.2f}bp)")

    print("\n" + "=" * 100)
    print("  읽는 법")
    print("    · p 가 크면 이 격자에서 나온 최고 t 는 **우연히 나올 수 있는 크기**다.")
    print("    · 손익분기 상관을 못 넘으면 t 가 유의해도 거래가 아니다 — 교훈 #82.")
    print("    · IS 와 OOS 의 부호가 다르면 그 칸은 표본 안 인공물이다.")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n_bars": int(len(d)), "pool": pool,
         "lead_lag": {str(k): v for k, v in ll.items()},
         "grid": {f"{k[0]}->{k[1]}": v for k, v in obs.items()},
         "max_stat": {"obs": obs_max_t, "p": p_max,
                      "null_median": float(np.median(null)),
                      "null_p95": float(np.percentile(null, 95))},
         "n_tradable": len(tradable), "n_net_positive": len(pos)},
        ensure_ascii=False, indent=2, default=str))
    print(f"  → {a.out}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
