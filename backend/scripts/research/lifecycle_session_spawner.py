"""Per-listing PaperSession spawner for the lifecycle_pump_decay paradigm.

Workflow:
  1. Re-fetch /fapi/v1/exchangeInfo. Compare to existing
     `backend/runs/research_track/lifecycle_phase/listing_dates.json` and
     identify NEW listings since last fetch.
  2. For each new listing, write its onboard_date into listing_dates.json
     so subsequent runs see it as known.
  3. Decide WHICH listings to spawn a paper session for:
       - listing's Day 1 close must already be present in `ohlcv` table
         (need at least 24h of post-listing 1m candles)
       - listing is NOT a known stock perpetual / commodity / quarterly
         (heuristic: base symbol must be alphanumeric ≤ 6 chars and not
         in a known stocks blocklist)
       - listing is NOT already covered by an existing paper session
         (idempotent — never double-spawn for the same symbol)
  4. For each spawnable listing: backfill that symbol's 1m ohlcv (30 days
     should be enough for the 30-day hold) via
     scripts.backfill_ohlcv_archive.
  5. Generate a paper_session spec JSON and create the session via
     `paper_session_cli create`.

Run via PM2 cron (proposed slot: daily 02:45 UTC, AFTER ohlcv-backfill
at 02:00 and BEFORE paper-cycle at 02:30 — actually slot AFTER cycle so
that next day's cycle picks up the new session: 03:00 UTC).

Single-run modes:
  - `--dry-run` lists what WOULD spawn without creating sessions
  - `--symbol XXX` spawns just one symbol's session if eligible
  - default: scan + spawn all eligible new listings

Output: writes paper session JSONs to
backend/configs/paper_sessions/lifecycle/{SYMBOL}_lifecycle_{LISTING_DATE}.json
and creates via paper_session_cli.

This is the dispatch script. The actual trade execution is handled by
paper_session_cli run --all on the daily binance-paper-cycle.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lifecycle_session_spawner")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
SESSIONS_CONFIG_DIR = ROOT / "configs" / "paper_sessions" / "lifecycle"
EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"

POLICY_BASELINE = "baseline"
POLICY_EARLY_EXIT = "early_exit"
POLICY_CHOICES = (POLICY_BASELINE, POLICY_EARLY_EXIT)

# Heuristic blocklist: tokenized stocks, commodities, ETFs we don't want to short
# (lifecycle hypothesis was tested on pure-crypto cohort).
SYMBOL_BLOCKLIST = {
    # tokenized stocks
    "AMD", "QCOM", "MSFT", "AVGO", "BABA", "TSM", "MU", "SNDK", "MSTR", "CRCL",
    "NVDA", "TSLA", "AAPL", "META", "GOOGL", "AMZN", "NFLX", "PYPL", "JPM", "V",
    "MA", "BAC", "WFC", "C", "SOFI", "COIN", "HOOD", "UBER", "ABNB", "SHOP", "SQ",
    "PLTR", "RIVN", "LCID", "SNOW", "CRWD", "NET", "DDOG", "ZS", "OKTA", "ADBE",
    "ORCL", "CSCO", "IBM", "INTC", "USAR", "BILL",
    # commodities / ETFs
    "XAU", "XAUT", "XAG", "XPT", "XPD", "COPPER", "NATGAS", "BZ", "CL",
    "QQQ", "SPY", "EWJ", "EWY", "INX",
}


def fetch_exchange_info() -> dict:
    r = requests.get(EXCHANGE_INFO_URL, timeout=30)
    r.raise_for_status()
    return r.json()


def update_listings(known: dict) -> tuple[dict, list[str]]:
    """Returns (updated_dict, new_symbol_list)."""
    info = fetch_exchange_info()
    new_syms = []
    for s in info.get("symbols", []):
        if s.get("quoteAsset") != "USDT":
            continue
        if s.get("status") != "TRADING":
            continue
        onboard_ms = s.get("onboardDate")
        if not onboard_ms:
            continue
        sym = s["symbol"]
        if sym in known:
            continue
        dt = datetime.fromtimestamp(onboard_ms / 1000, tz=timezone.utc)
        known[sym] = {
            "onboard_date": dt.strftime("%Y-%m-%d"),
            "onboard_ts_ms": onboard_ms,
            "contract_type": s.get("contractType", ""),
            "base": s.get("baseAsset", ""),
        }
        new_syms.append(sym)
    return known, new_syms


def eligible_for_session(sym: str, meta: dict, today: date) -> tuple[bool, str]:
    """Returns (eligible, reason_if_not)."""
    if meta.get("contract_type") != "PERPETUAL":
        return False, f"contract_type={meta.get('contract_type')!r} (not PERPETUAL)"
    if not re.fullmatch(r"[A-Z0-9]+USDT", sym):
        return False, f"non-ASCII or unusual symbol"
    base = meta.get("base", sym.replace("USDT", ""))
    if base in SYMBOL_BLOCKLIST:
        return False, f"blocklisted base {base}"
    ld = datetime.strptime(meta["onboard_date"], "%Y-%m-%d").date()
    age = (today - ld).days
    if age < 1:
        return False, f"too young (age={age}d) — Day 1 close not yet"
    if age > 14:
        return False, f"too old (age={age}d) — past entry window"
    return True, "ok"


def session_exists_for(symbol: str, policy_variant: str = POLICY_BASELINE) -> bool:
    """Check existing paper sessions for symbol + variant name suffix."""
    sessions_dir = ROOT / "runs" / "paper_sessions"
    if not sessions_dir.exists():
        return False
    # baseline session: name contains "lifecycle_" but NOT "earlyexit"
    # early_exit session: name contains "earlyexit"
    for p in sessions_dir.iterdir():
        sj = p / "session.json"
        if not sj.exists():
            continue
        try:
            d = json.load(open(sj))
            if d.get("symbol") != symbol:
                continue
            n = (d.get("name", "")).lower()
            if "lifecycle" not in n:
                continue
            has_ee = "earlyexit" in n
            if policy_variant == POLICY_EARLY_EXIT and has_ee:
                return True
            if policy_variant == POLICY_BASELINE and not has_ee:
                return True
        except Exception:
            continue
    return False


def backfill_ohlcv_for(symbol: str, days: int = 30, dry_run: bool = False) -> bool:
    """Idempotent backfill. Uses backend/scripts/backfill_ohlcv_archive.py.
    Returns True if at least 1 row inserted OR data already present."""
    cmd = [
        sys.executable, "-m", "scripts.backfill_ohlcv_archive",
        "--symbols", symbol,
        "--days", str(days),
        "--parallel", "8",
    ]
    log.info("[%s] backfilling 1m ohlcv (%d days)", symbol, days)
    if dry_run:
        log.info("  [dry-run] would run: %s", " ".join(cmd))
        return True
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=300)
        if result.returncode != 0:
            log.error("[%s] backfill stderr: %s", symbol, result.stderr[:500])
            return False
        return True
    except Exception as exc:
        log.error("[%s] backfill exception: %s", symbol, exc)
        return False


def build_session_spec(
    symbol: str,
    listing_date: str,
    *,
    policy_variant: str = POLICY_BASELINE,
    early_exit_check_day: int = 14,
    early_exit_vc_threshold: float = 0.40,
) -> dict:
    """Build a paper-session spec for one of two lifecycle policy variants.

    `policy_variant`:
      - "baseline" — Day 1 close short, hold to Day 30 (R-4 PASS paradigm).
      - "early_exit" — same entry; at `early_exit_check_day` compute
        vol_cliff = mean(vol[7:14])/vol[0] (check_day=14) or partial proxy
        (check_day=7); if >= threshold, EARLY EXIT.

    The two variants share entry semantics so a parallel pair of sessions
    on the same listing measures the early-exit edge cleanly.
    """
    if policy_variant == POLICY_BASELINE:
        name_suffix = ""
        sources = [{"type": "bn_lifecycle_decay", "kwargs": {}}]
        composer = {"type": "passthrough",
                    "kwargs": {"feature_col": "bnld_signal", "scale": 1.0}}
        policy = {
            "type": "long_short_threshold",
            "kwargs": {
                "entry_threshold": 0.5,
                "sl_pct": 0.50,
                "tp_pct": 1.0,
                "max_hold_bars": 30,
            },
        }
        notes = (
            f"Lifecycle short paradigm BASELINE for {symbol}. Listing date "
            f"{listing_date}. Short Day 1 close, exit Day 30 close OR SL "
            f"+50%. Auto-generated by lifecycle_session_spawner."
        )
    elif policy_variant == POLICY_EARLY_EXIT:
        name_suffix = f"_earlyexit_d{early_exit_check_day}"
        sources = [{
            "type": "bn_lifecycle_decay_early_exit",
            "kwargs": {
                "check_day": int(early_exit_check_day),
                "vol_cliff_hi_threshold": float(early_exit_vc_threshold),
            },
        }]
        composer = {"type": "passthrough",
                    "kwargs": {"feature_col": "bnldex_signal", "scale": 1.0}}
        policy = {
            "type": "lifecycle_decay_early_exit",
            "kwargs": {
                "entry_threshold": 0.5,
                "exit_signal_threshold": 0.5,
                "sl_pct": 0.50,
                "tp_pct": 1.0,
                "max_hold_bars": 30,
            },
        }
        notes = (
            f"Lifecycle short EARLY-EXIT variant for {symbol}. Listing date "
            f"{listing_date}. Day 1 short, vol_cliff check at Day "
            f"{early_exit_check_day} (threshold {early_exit_vc_threshold:.2f}) "
            f"— exit early if decay invalidated, else hold to Day 30. "
            f"Auto-generated by lifecycle_session_spawner."
        )
    else:
        raise ValueError(f"Unknown policy_variant: {policy_variant!r}")

    return {
        "name": f"lifecycle{name_suffix}_{symbol}_{listing_date}",
        "symbol": symbol,
        "mode": "paper",
        "initial_capital": 1000000,
        "fee_rate": 0.0004,
        "refit_interval_days": 30,
        "notes": notes,
        "pipeline_spec": {
            "sources": sources,
            "composer": composer,
            "policy": policy,
            "config": {
                "eval_freq_minutes": 1440,
                "forward_bars": 30,
            },
        },
    }


def spawn_session(
    symbol: str,
    listing_date: str,
    *,
    policy_variant: str = POLICY_BASELINE,
    early_exit_check_day: int = 14,
    early_exit_vc_threshold: float = 0.40,
    dry_run: bool = False,
) -> bool:
    SESSIONS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if policy_variant == POLICY_BASELINE else f"_earlyexit_d{early_exit_check_day}"
    spec_path = SESSIONS_CONFIG_DIR / f"{symbol}_lifecycle{suffix}_{listing_date}.json"
    spec = build_session_spec(
        symbol,
        listing_date,
        policy_variant=policy_variant,
        early_exit_check_day=early_exit_check_day,
        early_exit_vc_threshold=early_exit_vc_threshold,
    )
    if dry_run:
        log.info("[%s] [%s] [dry-run] would write spec: %s",
                 symbol, policy_variant, spec_path)
        log.info("  spec preview: %s", json.dumps(spec, indent=2)[:600])
        return True
    spec_path.write_text(json.dumps(spec, indent=2))
    log.info("[%s] [%s] spec written: %s", symbol, policy_variant, spec_path)
    cmd = [
        sys.executable, "-m", "scripts.paper_session_cli", "create",
        "--spec", str(spec_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=60)
        if result.returncode != 0:
            log.error("[%s] create failed stderr: %s", symbol, result.stderr[:400])
            return False
        log.info("[%s] create output: %s", symbol, result.stdout.strip())
        return True
    except Exception as exc:
        log.error("[%s] create exception: %s", symbol, exc)
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--symbol", default=None, help="Spawn only this symbol")
    p.add_argument("--refresh-listings", action="store_true",
                   help="Re-fetch exchangeInfo and update listing_dates.json")
    p.add_argument("--max-age-days", type=int, default=14,
                   help="Maximum age in days for spawn eligibility (default 14)")
    p.add_argument(
        "--policy",
        choices=("baseline", "early_exit", "both"),
        default="both",
        help=(
            "Which policy variant(s) to spawn. 'baseline' = R-4 PASS pure "
            "hold-30. 'early_exit' = vol_cliff-gated early exit. 'both' "
            "(default) seeds BOTH variants on every eligible listing — "
            "parallel A/B measurement."
        ),
    )
    p.add_argument("--early-exit-check-day", type=int, default=14,
                   choices=(7, 14),
                   help="Day at which vol_cliff is evaluated (default 14, matches R-2 metric).")
    p.add_argument("--early-exit-vc-threshold", type=float, default=0.40,
                   help="vol_cliff threshold above which early-exit fires (default 0.40).")
    args = p.parse_args()

    if args.policy == "both":
        variants = [POLICY_BASELINE, POLICY_EARLY_EXIT]
    else:
        variants = [args.policy]

    known = json.loads(LISTINGS_PATH.read_text()) if LISTINGS_PATH.exists() else {}
    log.info("known listings: %d", len(known))

    if args.refresh_listings or not LISTINGS_PATH.exists():
        known, new_syms = update_listings(known)
        if not args.dry_run:
            LISTINGS_PATH.write_text(json.dumps(known, indent=2, sort_keys=True))
        log.info("listings refreshed: %d total, %d new (%s)", len(known), len(new_syms),
                 ",".join(new_syms[:10]) if new_syms else "none")

    today = date.today()
    target_syms = [args.symbol] if args.symbol else list(known.keys())

    spawned = 0
    skipped = []
    for sym in target_syms:
        meta = known.get(sym)
        if not meta:
            log.warning("[%s] not in listings — skip", sym)
            continue
        ok, why = eligible_for_session(sym, meta, today)
        if not ok:
            skipped.append((sym, why))
            continue
        # Backfill ohlcv ONCE per symbol (shared across variants)
        backfilled_ok = backfill_ohlcv_for(sym, days=35, dry_run=args.dry_run)
        if not backfilled_ok:
            skipped.append((sym, "backfill failed"))
            continue
        for variant in variants:
            if session_exists_for(sym, policy_variant=variant):
                skipped.append((f"{sym}/{variant}", "session already exists"))
                continue
            ok_spawn = spawn_session(
                sym,
                meta["onboard_date"],
                policy_variant=variant,
                early_exit_check_day=args.early_exit_check_day,
                early_exit_vc_threshold=args.early_exit_vc_threshold,
                dry_run=args.dry_run,
            )
            if not ok_spawn:
                skipped.append((f"{sym}/{variant}", "spawn failed"))
                continue
            spawned += 1

    log.info("\n=== SUMMARY ===")
    log.info("spawned: %d", spawned)
    log.info("skipped: %d", len(skipped))
    if skipped[:20]:
        for sym, why in skipped[:20]:
            log.info("  %s — %s", sym, why)
    return 0


if __name__ == "__main__":
    sys.exit(main())
