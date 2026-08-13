"""Competition-pool ranking + snapshot (Phase 1 of the strategy tournament).

Category B = paper strategies COMPETING for promotion to real (everything that
is NOT the lifecycle family, which runs in parallel with real). This ranks them
by a noise-resistant metric and writes a timestamped snapshot so performance can
be tracked across the 2-week accumulation window before any elimination.

Ranking metric (the hard part — chosen to resist the small-sample / concentration
traps seen repeatedly: a couple of lucky wins must NOT win the tournament):

  1. Eligibility gate: n_trades >= MIN_TRADES_TO_RANK (default 5). Below this a
     strategy is WARMING_UP — reported but NOT rankable and NOT eliminable
     (protected from being culled on noise).
  2. Primary score = Sharpe of per-trade returns = mean(return_pct) /
     std(return_pct). This rewards CONSISTENCY and penalizes concentration
     (a few big wins amid many losses → high variance → low score), unlike raw
     total return. Directly counters the "2 wins carry it" fragility.
  3. Tie-break: total_return_pct, then profit_factor.

Elimination (Phase 2 will consume this): among ELIGIBLE strategies, the lowest
primary score is the cull candidate. WARMING_UP strategies are never culled.

This is a read-only reporter — it ranks and snapshots, it does not eliminate or
promote. Phase 2's tournament_controller will act on these rankings.

Usage:
  python -m scripts.competition_pool_report            # rank + snapshot
  python -m scripts.competition_pool_report --no-save  # print only
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "runs" / "paper_sessions"
SNAP_DIR = ROOT / "runs" / "competition"

MIN_TRADES_TO_RANK = 5
_KR = re.compile(r"^\d{6}$")


def _family(name: str, symbol: str) -> str:
    rest = name.replace(symbol + "_", "", 1)
    return rest.split("_paper")[0].split("_reseed")[0].split("_2026")[0][:34]


def _load_trades(sid: str) -> list[dict]:
    p = STORE / sid / "trades.jsonl"
    if not p.exists():
        return []
    out = []
    for ln in p.read_text().splitlines():
        ln = ln.strip()
        if ln:
            try:
                _t = json.loads(ln)
            except Exception:
                continue
            if _t.get("invalid"):        # 무효 표시 제외 (INVALID_TRADES.json)
                continue
            out.append(_t)
    return out


def _metrics(sid: str, sess: dict) -> dict:
    trades = _load_trades(sid)
    rets = [float(t.get("return_pct", 0)) for t in trades]
    pnls = [float(t.get("pnl_cash", 0)) for t in trades]
    n = len(trades)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_w, gross_l = sum(wins), abs(sum(losses))
    # Sharpe of per-trade returns — the primary ranking score.
    if n >= 2 and statistics.pstdev(rets) > 0:
        sharpe = statistics.mean(rets) / statistics.pstdev(rets)
    else:
        sharpe = 0.0
    top2 = sum(sorted(wins, reverse=True)[:2])
    return {
        "n_trades": n,
        "return_pct": float(sess.get("total_return_pct", 0.0)) * 100.0,
        "win_rate": (len(wins) / n * 100.0) if n else 0.0,
        "profit_factor": (gross_w / gross_l) if gross_l > 0 else (float("inf") if gross_w > 0 else 0.0),
        "sharpe": sharpe,
        "top2_win_share": (top2 / gross_w * 100.0) if gross_w > 0 else 0.0,
        "eligible": n >= MIN_TRADES_TO_RANK,
    }


def scan() -> list[dict]:
    rows = []
    for sj in STORE.glob("*/session.json"):
        try:
            s = json.loads(sj.read_text())
        except Exception:
            continue
        if s.get("status") != "active":
            continue
        name = s.get("name", "")
        if "lifecycle" in name:
            continue  # Category A (parallel with real) — not in the competition
        sid = sj.parent.name
        sym = s.get("symbol", "")
        m = _metrics(sid, s)
        rows.append({
            "session_id": sid,
            "symbol": sym,
            "family": _family(name, sym),
            "exchange": "KR" if _KR.match(sym) else "Binance",
            **m,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--stamp", default=None, help="snapshot timestamp label (else derived from newest cycle)")
    args = ap.parse_args()

    rows = scan()
    eligible = [r for r in rows if r["eligible"]]
    warming = [r for r in rows if not r["eligible"]]
    eligible.sort(key=lambda r: (r["sharpe"], r["return_pct"], r["profit_factor"]))

    print(f"=== Competition pool (Category B): {len(rows)} strategies "
          f"({len(eligible)} rankable, {len(warming)} warming-up) ===\n")
    print(f"{'rank':>4s} {'family':34s} {'sym':9s} {'ex':7s} {'n':>3s} {'ret%':>7s} {'WR%':>5s} {'PF':>5s} {'sharpe':>7s}")
    for i, r in enumerate(eligible, 1):
        pf = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.2f}"
        print(f"{i:>4d} {r['family'][:34]:34s} {r['symbol'][:9]:9s} {r['exchange']:7s} "
              f"{r['n_trades']:>3d} {r['return_pct']:>+7.2f} {r['win_rate']:>5.0f} {pf:>5s} {r['sharpe']:>+7.3f}")
    if eligible:
        cull = eligible[0]
        print(f"\n  → cull candidate (lowest sharpe): {cull['family']} {cull['symbol']} "
              f"(sharpe {cull['sharpe']:+.3f}, ret {cull['return_pct']:+.2f}%)")
    print(f"\n  WARMING_UP (n_trades < {MIN_TRADES_TO_RANK}, protected): {len(warming)} "
          f"[{', '.join(sorted({r['family'] for r in warming}))}]")

    if not args.no_save:
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = args.stamp or "latest"
        out = SNAP_DIR / f"snapshot_{stamp}.json"
        out.write_text(json.dumps({"rows": rows, "min_trades": MIN_TRADES_TO_RANK}, indent=2))
        print(f"\n  snapshot saved → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
