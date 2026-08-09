#!/usr/bin/env python3
"""paradigm 251 유니버스 횡단면 — 214종목에서 스테이블코인 공급 신호를 검증한다.

왜 필요한가 (2026-08-09):
  DefiLlama 전체 이력(880일) 판정에서 6종목 중 BNBUSDT h3d 하나만 통과했다.
  6개 중 1개는 운과 구별되지 않는다. 게다가 그 6종목은 dispatch 에이전트가
  임의로 고른 것이다. DB 에 214종목이 있으므로 횡단면 분포로 판단한다.

통계 설계 — 여기가 핵심이다:
  신호는 **단일 시계열**(USDT+USDC 순공급 z)이고 모든 종목이 같은 날 같은 방향을
  잡는다. 따라서 214종목은 독립 시행이 **아니다**. 종목별 t-stat 을 214개 모아
  최댓값을 취하면 그건 다중검정이고, 214개 중 하나가 통과하는 건 당연하다.

  정직한 검정은 **이벤트별 동일가중 포트폴리오 수익**이다:
    각 트리거 날짜마다 그 날 진입한 전 종목 net_ret 을 평균 → 관측치 1개
    → 관측치 시계열(트리거 수만큼)에 t-stat / tier3_gate G1
  이러면 횡단면 상관이 자동으로 흡수된다. Lesson #76 의 universe-aggregate
  양방향 fee-drag 함정도 피한다 — 방향은 z 부호 하나로 결정되므로 미러가 없고
  수수료는 거래당 한 번만 낸다.

  종목별 분포(양수 비율 등)는 **기술통계**로만 쓴다 — 검정이 아니다.

Lesson #78: 자동구성 유니버스는 유동성 필터가 필수다. 전체 / 일평균
거래대금 중간값 $5M 이상 두 가지로 나눠 본다.

사용:
  cd backend && source venv/bin/activate
  python3 scripts/research/p251_universe_cross_section.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research.tier3_gate import (  # noqa: E402
    ExecContext, Trade, evaluate_g1, evaluate_g2,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p251_xsec")

OUT = ROOT / "runs" / "research_track" / "readjudication_2026_08_09"
OUT.mkdir(parents=True, exist_ok=True)
DL_CACHE = OUT / "defillama_stablecoin_supply_full.json"

FEE_RT = 0.0008
Z_THRESH = 1.0
ROLL_WIN = 60
NET_DAYS = 7
HOLDS = [1, 2, 3]
ROUNDTRIP_FRICTION = 0.0008
CYCLE_MINUTES = 1440.0
CG_WINDOW_START = date(2025, 8, 9)   # CoinGecko 창 시작 — 그 이전이 out-of-window
LIQ_MIN_USD = 5_000_000.0            # Lesson #78 유동성 하한 (일 거래대금 중간값)

# 최신성 필터 (2026-08-09 추가) — DB 1m 이 168종목에 대해 2026-05-12 에 멈춰 있다.
# 그걸 섞으면 포트폴리오 구성이 그 날짜에 132 → 32 로 조용히 축소되고,
# recent_edge / decay_ratio 가 구성변화 아티팩트를 알파로 오독한다.
# FRESH_ONLY=1 이면 최신 종목만 쓴다.
FRESH_MIN_END = date(2026, 8, 7)
FRESH_ONLY = os.environ.get("FRESH_ONLY", "0") == "1"

DAILY_SQL = """
WITH bounds AS (
  SELECT symbol, timestamp::date AS d,
         min(timestamp) AS t0, max(timestamp) AS t1
  FROM ohlcv WHERE time_frame='1m'
  GROUP BY symbol, timestamp::date
)
SELECT b.symbol, b.d, o.open AS open, c.close AS close, dv.quote_vol
FROM bounds b
JOIN ohlcv o ON o.symbol=b.symbol AND o.time_frame='1m' AND o.timestamp=b.t0
JOIN ohlcv c ON c.symbol=b.symbol AND c.time_frame='1m' AND c.timestamp=b.t1
JOIN (
  SELECT symbol, timestamp::date AS d, sum(close*volume) AS quote_vol
  FROM ohlcv WHERE time_frame='1m' GROUP BY symbol, timestamp::date
) dv ON dv.symbol=b.symbol AND dv.d=b.d
ORDER BY b.symbol, b.d
"""


def build_signal() -> pd.DataFrame:
    raw = json.loads(DL_CACHE.read_text())
    frames = {}
    for k in ("usdt", "usdc"):
        d = pd.DataFrame(raw[k])
        d["date"] = pd.to_datetime(d["date"], utc=True)
        frames[k] = d.groupby("date", as_index=False)["supply"].last()
    df = frames["usdt"].merge(frames["usdc"], on="date", suffixes=("_usdt", "_usdc"))
    df["combined"] = df["supply_usdt"] + df["supply_usdc"]
    df = df.sort_values("date").reset_index(drop=True)
    df["net_7d"] = df["combined"].diff(NET_DAYS)
    df["z"] = ((df["net_7d"] - df["net_7d"].rolling(ROLL_WIN).mean())
               / df["net_7d"].rolling(ROLL_WIN).std())
    df = df[["date", "z"]].dropna().reset_index(drop=True)
    df["d"] = df["date"].dt.date
    return df


def raw_t(x: np.ndarray) -> float:
    if len(x) < 2:
        return float("nan")
    sd = float(np.std(x, ddof=1))
    return float(np.mean(x) / (sd / np.sqrt(len(x)))) if sd > 0 else float("nan")


def judge(nets_by_exit: list[tuple[date, float]], delayed: list[float],
          hold: int, now: datetime) -> dict:
    gt = [Trade(entry_ts=datetime.combine(ex - timedelta(days=hold), datetime.min.time()),
                exit_ts=datetime.combine(ex, datetime.min.time()), net_ret=r)
          for ex, r in nets_by_exit]
    g1 = evaluate_g1(gt, now=now)
    de = float(np.mean(delayed)) if delayed else None
    g2 = evaluate_g2(ExecContext(
        lookahead_clean=True, edge_after_1bar_delay=de,
        roundtrip_friction=ROUNDTRIP_FRICTION,
        hold_minutes=hold * 1440.0, cycle_minutes=CYCLE_MINUTES), g1)
    x = np.array([r for _, r in nets_by_exit], dtype=float)
    return {"G1": g1, "G2": g2, "passed": bool(g1.get("ok") and g2.get("ok")),
            "raw_t_unweighted": None if np.isnan(raw_t(x)) else round(raw_t(x), 3),
            "win_rate": round(float(np.mean(x > 0)), 4) if len(x) else None}


def main() -> int:
    sig = build_signal()
    trig = sig[sig["z"].abs() >= Z_THRESH][["d", "z"]].reset_index(drop=True)
    log.info(f"신호 {len(sig)}일 {sig['d'].min()} ~ {sig['d'].max()} | 트리거 {len(trig)}건")
    z_by_date = dict(zip(trig["d"], trig["z"]))

    db = SessionLocal()
    try:
        log.info("일봉 롤업 조회 중 (214종목)...")
        rows = db.execute(text(DAILY_SQL)).fetchall()
        log.info(f"  {len(rows):,}행 수신")
        px = pd.DataFrame(rows, columns=["symbol", "d", "open", "close", "quote_vol"])
        for c in ("open", "close", "quote_vol"):
            px[c] = pd.to_numeric(px[c], errors="coerce")
        px = px.dropna(subset=["open", "close"])

        liq = px.groupby("symbol")["quote_vol"].median()
        ends = px.groupby("symbol")["d"].max()
        fresh = set(ends[ends.map(lambda x: x >= FRESH_MIN_END)].index)
        liquid = set(liq[liq >= LIQ_MIN_USD].index)
        if FRESH_ONLY:
            before = len(liquid)
            liquid = liquid & fresh
            log.info(f"FRESH_ONLY — 유동성 통과 {before} → 최신 교집합 {len(liquid)}")
        else:
            log.info(f"최신 종목 {len(fresh)} / 전체 {px['symbol'].nunique()} "
                     f"(정지분 포함 — 구성변화 주의)")
        cover = px.groupby("symbol")["d"].agg(["min", "max", "count"])
        log.info(f"종목 {px['symbol'].nunique()}개 | 유동성 통과 {len(liquid)}개 "
                 f"(일거래대금 중간값 >= ${LIQ_MIN_USD:,.0f})")

        # 종목별 {날짜: (open, close)}
        book = {s: {r.d: (r.open, r.close) for r in g.itertuples()}
                for s, g in px.groupby("symbol")}

        per_symbol = {h: {} for h in HOLDS}
        # 이벤트별 수익 누적: hold → exit_date → [net_ret...]
        event_pool = {h: defaultdict(list) for h in HOLDS}
        event_pool_liq = {h: defaultdict(list) for h in HOLDS}
        event_pool_delayed = {h: defaultdict(list) for h in HOLDS}

        for sym, by_date in book.items():
            for hold in HOLDS:
                nets, nets_d = [], []
                for sig_d, z in z_by_date.items():
                    side = 1.0 if z > 0 else -1.0
                    for lag, sink in ((1, nets), (2, nets_d)):
                        e = by_date.get(sig_d + timedelta(days=lag))
                        x = by_date.get(sig_d + timedelta(days=lag + hold))
                        if e is None or x is None:
                            continue
                        ep, xp = float(e[0]), float(x[1])
                        if not np.isfinite(ep) or not np.isfinite(xp) or ep <= 0:
                            continue
                        net = side * (xp - ep) / ep - FEE_RT
                        sink.append((sig_d + timedelta(days=lag + hold), net))
                if len(nets) < 20:
                    continue
                arr = np.array([r for _, r in nets], dtype=float)
                per_symbol[hold][sym] = {
                    "n": len(arr),
                    "raw_edge_pct": round(float(arr.mean()) * 100, 4),
                    "raw_t": None if np.isnan(raw_t(arr)) else round(raw_t(arr), 3),
                    "win_rate": round(float(np.mean(arr > 0)), 4),
                    "liquid": sym in liquid,
                    "median_quote_vol_usd": round(float(liq.get(sym, 0.0)), 0),
                }
                for ex, r in nets:
                    event_pool[hold][ex].append(r)
                    if sym in liquid:
                        event_pool_liq[hold][ex].append(r)
                for ex, r in nets_d:
                    if sym in liquid:
                        event_pool_delayed[hold][ex].append(r)

        results = {}
        for hold in HOLDS:
            ps = per_symbol[hold]
            edges = np.array([v["raw_edge_pct"] for v in ps.values()])
            edges_liq = np.array([v["raw_edge_pct"] for v in ps.values() if v["liquid"]])

            def pool_stats(pool, label, delayed_pool=None):
                if not pool:
                    return None
                items = sorted((ex, float(np.mean(v))) for ex, v in pool.items() if v)
                x = np.array([r for _, r in items])
                dly = ([float(np.mean(v)) for ex, v in sorted(delayed_pool.items()) if v]
                       if delayed_pool else [])
                out = {
                    "n_events": len(items),
                    "edge_pct": round(float(x.mean()) * 100, 4),
                    "t_stat": None if np.isnan(raw_t(x)) else round(raw_t(x), 3),
                    "win_rate_events": round(float(np.mean(x > 0)), 4),
                    "verdict": judge(items, dly, hold, datetime.utcnow()),
                }
                # 창 밖 구간만 (2025-08-09 이전 청산)
                oow = [(ex, r) for ex, r in items if ex < CG_WINDOW_START]
                if len(oow) >= 20:
                    xo = np.array([r for _, r in oow])
                    out["out_of_window"] = {
                        "n_events": len(oow),
                        "edge_pct": round(float(xo.mean()) * 100, 4),
                        "t_stat": None if np.isnan(raw_t(xo)) else round(raw_t(xo), 3),
                        "verdict": judge(oow, [], hold,
                                         datetime.combine(max(e for e, _ in oow),
                                                          datetime.min.time())),
                    }
                return out

            results[f"h{hold}d"] = {
                "n_symbols": len(ps),
                "n_symbols_liquid": int(sum(1 for v in ps.values() if v["liquid"])),
                "pct_symbols_positive_edge": round(float(np.mean(edges > 0)), 4) if len(edges) else None,
                "pct_symbols_positive_edge_liquid": (round(float(np.mean(edges_liq > 0)), 4)
                                                    if len(edges_liq) else None),
                "median_symbol_edge_pct": round(float(np.median(edges)), 4) if len(edges) else None,
                "median_symbol_edge_pct_liquid": (round(float(np.median(edges_liq)), 4)
                                                 if len(edges_liq) else None),
                "portfolio_all": pool_stats(event_pool[hold], "all"),
                "portfolio_liquid": pool_stats(event_pool_liq[hold], "liquid",
                                               event_pool_delayed[hold]),
                "per_symbol": ps,
            }
            r = results[f"h{hold}d"]
            pa, pl = r["portfolio_all"], r["portfolio_liquid"]
            log.info(f"[h{hold}d] 종목 {r['n_symbols']} (유동 {r['n_symbols_liquid']}) | "
                     f"양수엣지 비율 {r['pct_symbols_positive_edge']:.1%} "
                     f"(유동 {r['pct_symbols_positive_edge_liquid']:.1%}) | "
                     f"포트폴리오(유동) 이벤트 {pl['n_events']} edge {pl['edge_pct']:+.4f}% "
                     f"t {pl['t_stat']} → {'PASS' if pl['verdict']['passed'] else 'FAIL'}")

        # BNBUSDT 백분위
        ranks = {}
        for hold in HOLDS:
            ps = per_symbol[hold]
            if "BNBUSDT" not in ps:
                continue
            ed = np.array([v["raw_edge_pct"] for v in ps.values()])
            ranks[f"h{hold}d"] = {
                "bnb_edge_pct": ps["BNBUSDT"]["raw_edge_pct"],
                "bnb_percentile": round(float(np.mean(ed <= ps["BNBUSDT"]["raw_edge_pct"])), 4),
                "n_symbols": len(ed),
            }
        log.info("BNBUSDT 백분위: " + json.dumps(ranks, ensure_ascii=False))

        payload = {
            "generated_at_kst": (datetime.utcnow() + timedelta(hours=9)).isoformat(),
            "paradigm": "alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d",
            "purpose": "214종목 횡단면 — 단일 시계열 신호이므로 이벤트별 동일가중 포트폴리오로 검정",
            "signal": {"days": int(len(sig)), "start": str(sig["d"].min()),
                       "end": str(sig["d"].max()), "triggers": int(len(trig))},
            "liquidity_floor_usd": LIQ_MIN_USD,
            "fresh_only": FRESH_ONLY,
            "fresh_min_end": FRESH_MIN_END.isoformat(),
            "cg_window_start": CG_WINDOW_START.isoformat(),
            "spec": {"fee_rt": FEE_RT, "z_thresh": Z_THRESH, "roll_win": ROLL_WIN,
                     "net_days": NET_DAYS, "holds": HOLDS},
            "bnb_rank": ranks,
            "results": results,
        }
        suffix = "_freshonly" if FRESH_ONLY else ""
        (OUT / f"p251_universe_cross_section{suffix}.json").write_text(
            json.dumps(payload, indent=1, ensure_ascii=False, default=str))
        log.info(f"기록 → {OUT / ('p251_universe_cross_section' + suffix + '.json')}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
