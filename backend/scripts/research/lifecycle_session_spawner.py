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
KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"

POLICY_BASELINE = "baseline"
POLICY_EARLY_EXIT = "early_exit"
POLICY_BEAR_SKIP = "bear_skip"
POLICY_CHOICES = (POLICY_BASELINE, POLICY_EARLY_EXIT, POLICY_BEAR_SKIP)

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


def compute_btc_30d_pre_ret(listing_date_str: str) -> float | None:
    """Return BTC's 30-day pre-listing log return (close-to-close).

    Anchor: BTC daily close on the trading day BEFORE listing_date_str.
    Lookback: BTC daily close 30 calendar days before the anchor.
    Returns `(anchor_close / lookback_close) - 1.0` as a float.

    Used to gate the lifecycle_decay_bear_skip variant per R-3 regime analysis
    (BEAR := pre_ret <= -0.05 → suppress short entry). Returns None on any
    fetch error or insufficient data, in which case the spawner SKIPS the
    bear_skip variant for that listing (conservative default — no session
    rather than a session with unknown regime).
    """
    try:
        ld = datetime.strptime(listing_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_ms = int(ld.timestamp() * 1000)
        start_ms = end_ms - int(35 * 86400 * 1000)
        r = requests.get(
            KLINES_URL,
            params={
                "symbol": "BTCUSDT",
                "interval": "1d",
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 40,
            },
            timeout=30,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows or len(rows) < 31:
            log.warning(
                "compute_btc_30d_pre_ret(%s): insufficient klines (%d)",
                listing_date_str, len(rows) if rows else 0,
            )
            return None
        # Use the LAST candle (anchor = trading day before listing) and the
        # candle 30 days earlier (index -31). Binance klines are returned
        # oldest-first; close is index 4.
        anchor_close = float(rows[-1][4])
        lookback_close = float(rows[-31][4])
        if lookback_close <= 0:
            return None
        return anchor_close / lookback_close - 1.0
    except Exception as exc:
        log.warning("compute_btc_30d_pre_ret(%s) failed: %s", listing_date_str, exc)
        return None


def update_listings(known: dict) -> tuple[dict, list[str]]:
    """Returns (updated_dict, new_symbol_list)."""
    info = fetch_exchange_info()
    new_syms = []
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    upcoming = []  # crypto listings whose onboardDate is still in the future
    for s in info.get("symbols", []):
        if s.get("quoteAsset") != "USDT":
            continue
        # Capture both live (TRADING) and scheduled (PENDING_TRADING) listings.
        # PENDING_TRADING + future onboardDate = a forward-announced listing visible
        # in exchangeInfo before go-live (e.g. SLXUSDT). It is recorded now for
        # forward visibility; eligible_for_session is age-based (onboard_date), so a
        # future onboard → age<1 → it is NOT spawned until it has been live ≥1 day.
        st = s.get("status")
        if st not in ("TRADING", "PENDING_TRADING"):
            continue
        # Crypto-only: the lifecycle pump-decay paradigm targets crypto listings,
        # NOT tokenized stocks (underlyingType=='EQUITY' / contractType=='TRADIFI_PERPETUAL').
        if s.get("underlyingType") != "COIN" or s.get("contractType") != "PERPETUAL":
            continue
        onboard_ms = s.get("onboardDate")
        if not onboard_ms:
            continue
        sym = s["symbol"]
        if sym in known:
            # refresh status (PENDING→TRADING transition) without re-adding
            if known[sym].get("status") != st:
                known[sym]["status"] = st
            continue
        dt = datetime.fromtimestamp(onboard_ms / 1000, tz=timezone.utc)
        known[sym] = {
            "onboard_date": dt.strftime("%Y-%m-%d"),
            "onboard_ts_ms": onboard_ms,
            "contract_type": s.get("contractType", ""),
            "base": s.get("baseAsset", ""),
            "status": st,
        }
        new_syms.append(sym)
        if onboard_ms > now_ms:
            upcoming.append((onboard_ms, sym))
    for onboard_ms, sym in sorted(upcoming):
        dt = datetime.fromtimestamp(onboard_ms / 1000, tz=timezone.utc)
        log.info("UPCOMING crypto listing: %s onboard=%s (forward-detected, PENDING_TRADING)",
                 sym, dt.strftime("%Y-%m-%d %H:%M UTC"))
    return known, new_syms


def eligible_for_session(sym: str, meta: dict, today: date) -> tuple[bool, str]:
    """Returns (eligible, reason_if_not)."""
    # Only spawn once the listing is actually live (forward-detected PENDING_TRADING
    # entries wait here until they transition to TRADING + accrue ≥1 day of data).
    if meta.get("status") not in (None, "TRADING"):
        return False, f"status={meta.get('status')!r} (not yet trading)"
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


def session_exists_for(
    symbol: str,
    policy_variant: str = POLICY_BASELINE,
    check_day: int | None = None,
    baseline_hold_days: int | None = None,
) -> bool:
    """Check existing paper sessions for symbol + variant name suffix.

    For `POLICY_EARLY_EXIT`, the `_earlyexit_d{check_day}` tag must match.
    For `POLICY_BEAR_SKIP`, the `_bearskip_` tag must be present.
    For `POLICY_BASELINE`, the optional `_h{hold_days}` tag distinguishes
    non-default hold horizons (default hold=30 has no tag — back-compat with
    existing `lifecycle_{SYMBOL}_{DATE}` names) and the name must not contain
    any other variant tag.
    """
    sessions_dir = ROOT / "runs" / "paper_sessions"
    if not sessions_dir.exists():
        return False
    target_ee_tag = f"earlyexit_d{int(check_day)}" if check_day is not None else "earlyexit"
    is_default_hold = baseline_hold_days is None or int(baseline_hold_days) == 30
    target_hold_tag = None if is_default_hold else f"_h{int(baseline_hold_days)}_"
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
            has_bs = "bearskip" in n
            if policy_variant == POLICY_EARLY_EXIT and has_ee:
                if check_day is None or target_ee_tag in n:
                    return True
            elif policy_variant == POLICY_BEAR_SKIP and has_bs:
                return True
            elif policy_variant == POLICY_BASELINE and not has_ee and not has_bs:
                # Detect any "_h{N}_" hold-variant tag in the name.
                has_hold_tag = bool(re.search(r"_h\d+_", n))
                if is_default_hold and not has_hold_tag:
                    return True
                if not is_default_hold and target_hold_tag and target_hold_tag in n:
                    return True
        except Exception:
            continue
    return False


def backfill_ohlcv_for(symbol: str, days: int = 30, dry_run: bool = False) -> bool:
    """Idempotent 1m ohlcv backfill via Binance REST klines (fapi/v1/klines).

    Switched from data.binance.vision archive (backfill_ohlcv_archive) to REST:
    the archive publishes daily ZIPs at T+1, so a brand-new listing had NO archive
    data for days → System-2 cycle failed "insufficient eval bars" → no entry signal
    for ~4 days (SLXUSDT 2026-06-01→06-05). REST klines return live data immediately,
    so a fresh listing has usable daily bars at spawn time. fetch_history is
    smart-incremental + ON CONFLICT DO NOTHING (idempotent)."""
    log.info("[%s] backfilling 1m ohlcv (%d days) via REST klines", symbol, days)
    if dry_run:
        log.info("  [dry-run] would REST-fetch %s 1m %dd", symbol, days)
        return True
    try:
        import time as _time
        import pandas as pd
        import requests
        from scripts.backfill_ohlcv_archive import insert_to_db
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = end_ms - days * 86_400_000
        url = "https://fapi.binance.com/fapi/v1/klines"
        rows: list = []
        # Synchronous paginated fetch — self-contained (no asyncio/global HTTP client,
        # which broke on per-symbol asyncio.run loops with "Event loop is closed").
        while cur < end_ms:
            resp = requests.get(url, params={"symbol": symbol, "interval": "1m",
                                             "startTime": cur, "limit": 1000}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            rows.extend(data)
            cur = data[-1][0] + 60_000
            if len(data) < 1000:
                break
            _time.sleep(0.12)
        if not rows:
            log.info("[%s] no klines returned (pre-listing/empty) — ok", symbol)
            return True
        cols = ["open_time", "open", "high", "low", "close", "volume",
                "close_time", "qav", "n_trades", "tbbav", "tbqav", "ignore"]
        df = pd.DataFrame(rows, columns=cols)
        n = insert_to_db(symbol, df[["open_time", "open", "high", "low", "close", "volume"]])
        log.info("[%s] REST backfill: %d rows fetched, inserted (new) into ohlcv", symbol, len(df))
        return True
    except Exception as exc:
        log.error("[%s] REST backfill exception: %s", symbol, exc)
        return False


def build_session_spec(
    symbol: str,
    listing_date: str,
    *,
    policy_variant: str = POLICY_BASELINE,
    early_exit_check_day: int = 14,
    early_exit_vc_threshold: float = 0.40,
    baseline_hold_days: int = 30,
    bear_skip_btc_30d_pre_ret: float | None = None,
    bear_skip_threshold: float = -0.05,
) -> dict:
    """Build a paper-session spec for one of two lifecycle policy variants.

    `policy_variant`:
      - "baseline" — Day 1 close short, hold to Day `baseline_hold_days`
        (R-4 PASS paradigm: default 30; R-3 plateau optimum: 21).
      - "early_exit" — same entry; at `early_exit_check_day` compute
        vol_cliff = mean(vol[7:14])/vol[0] (check_day=14) or partial proxy
        (check_day=7); if >= threshold, EARLY EXIT.

    The variants share entry semantics so parallel sessions on the same
    listing measure the hold-horizon / early-exit edge cleanly.
    """
    if policy_variant == POLICY_BASELINE:
        hold_days = int(baseline_hold_days)
        name_suffix = "" if hold_days == 30 else f"_h{hold_days}"
        # 재진입 차단 (2026-08-12). 소스가 -1.0 을 영원히 내보내 익절 뒤 즉시
        # 재진입했다 — DATAIPUSDT 는 30일 안에 네 번, REUSDT 실계좌는 8회
        # 진입했다. 패러다임은 "상장 Day-1 종가 숏 **한 번**" 이다.
        # listing_date 를 넘겨 진입 신호 창을 상장 직후 3일로 닫는다.
        sources = [{"type": "bn_lifecycle_decay",
                    "kwargs": {"listing_date": str(listing_date),
                               "max_age_days": hold_days,
                               "entry_window_days": 1}}]
        composer = {"type": "passthrough",
                    "kwargs": {"feature_col": "bnld_signal", "scale": 1.0}}
        policy = {
            "type": "long_short_threshold",
            "kwargs": {
                "entry_threshold": 0.5,
                "sl_pct": 0.50,
                "tp_pct": 0.50,
                "max_hold_bars": hold_days,
            },
        }
        notes = (
            f"Lifecycle short paradigm BASELINE for {symbol}. Listing date "
            f"{listing_date}. Short Day 1 close, exit Day {hold_days} close "
            f"OR TP -50% OR SL +50%. Auto-generated by lifecycle_session_spawner."
        )
    elif policy_variant == POLICY_EARLY_EXIT:
        name_suffix = f"_earlyexit_d{early_exit_check_day}"
        sources = [{
            "type": "bn_lifecycle_decay_early_exit",
            "kwargs": {
                "check_day": int(early_exit_check_day),
                "vol_cliff_hi_threshold": float(early_exit_vc_threshold),
                # 재진입 차단 — 상세는 BASELINE 분기 주석 참조
                "listing_date": str(listing_date),
                "max_age_days": 30,
                "entry_window_days": 1,
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
                "tp_pct": 0.50,
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
    elif policy_variant == POLICY_BEAR_SKIP:
        if bear_skip_btc_30d_pre_ret is None:
            raise ValueError(
                "bear_skip_btc_30d_pre_ret must be provided for POLICY_BEAR_SKIP"
            )
        name_suffix = "_bearskip"
        pre_ret = float(bear_skip_btc_30d_pre_ret)
        thr = float(bear_skip_threshold)
        sources = [{
            "type": "bn_lifecycle_decay_bear_skip",
            "kwargs": {
                "btc_30d_pre_ret": pre_ret,
                "bear_threshold": thr,
                # 재진입 차단 — 상세는 BASELINE 분기 주석 참조
                "listing_date": str(listing_date),
                "max_age_days": 30,
                "entry_window_days": 1,
            },
        }]
        composer = {"type": "passthrough",
                    "kwargs": {"feature_col": "bnldbs_signal", "scale": 1.0}}
        policy = {
            "type": "long_short_threshold",
            "kwargs": {
                "entry_threshold": 0.5,
                "sl_pct": 0.50,
                "tp_pct": 0.50,
                "max_hold_bars": 30,
            },
        }
        regime_label = "BEAR_SKIP" if pre_ret <= thr else "ACTIVE"
        notes = (
            f"Lifecycle short BEAR-SKIP variant for {symbol}. Listing date "
            f"{listing_date}. BTC 30d pre-listing return = {pre_ret:+.4f} "
            f"(threshold {thr:+.2f}) → regime {regime_label}. R-3 BEAR cohort "
            f"(n=38, median -50.08%, win 42.1%) suppressed — emit signal 0 "
            f"(no entry) when BEAR, else identical to baseline (Day 1 short, "
            f"hold 30 days, TP -50%, SL +50%). Auto-generated by lifecycle_session_spawner."
        )
    else:
        raise ValueError(f"Unknown policy_variant: {policy_variant!r}")

    # forward_bars matches the policy's max_hold_bars so the orchestrator
    # tracks horizon correctly. Early-exit variants keep hold=30 (decay window
    # unchanged); baseline non-default hold (e.g. h21) shortens the horizon.
    forward_bars = (
        int(baseline_hold_days) if policy_variant == POLICY_BASELINE else 30
    )
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
                "forward_bars": forward_bars,
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
    baseline_hold_days: int = 30,
    bear_skip_btc_30d_pre_ret: float | None = None,
    bear_skip_threshold: float = -0.05,
    dry_run: bool = False,
) -> bool:
    SESSIONS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if policy_variant == POLICY_BASELINE:
        suffix = "" if int(baseline_hold_days) == 30 else f"_h{int(baseline_hold_days)}"
    elif policy_variant == POLICY_EARLY_EXIT:
        suffix = f"_earlyexit_d{early_exit_check_day}"
    elif policy_variant == POLICY_BEAR_SKIP:
        suffix = "_bearskip"
    else:
        raise ValueError(f"Unknown policy_variant: {policy_variant!r}")
    spec_path = SESSIONS_CONFIG_DIR / f"{symbol}_lifecycle{suffix}_{listing_date}.json"
    spec = build_session_spec(
        symbol,
        listing_date,
        policy_variant=policy_variant,
        early_exit_check_day=early_exit_check_day,
        baseline_hold_days=baseline_hold_days,
        bear_skip_btc_30d_pre_ret=bear_skip_btc_30d_pre_ret,
        bear_skip_threshold=bear_skip_threshold,
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
        choices=("baseline", "early_exit", "bear_skip", "both", "all"),
        default="both",
        help=(
            "Which policy variant(s) to spawn. 'baseline' = R-4 PASS pure "
            "hold-30. 'early_exit' = vol_cliff-gated early exit. 'bear_skip' "
            "= regime-gated (R-3 BEAR cohort median -50.08% suppressed). "
            "'both' (default) seeds baseline+early_exit. 'all' seeds "
            "baseline+early_exit+bear_skip — parallel A/B/C on every listing."
        ),
    )
    p.add_argument("--early-exit-check-day", type=int, default=None,
                   choices=(7, 14),
                   help="DEPRECATED single check_day (use --early-exit-check-days). Kept for backward compat.")
    p.add_argument("--early-exit-check-days", default="7,14",
                   help=("Comma-separated list of check_day values to spawn as "
                         "PARALLEL early-exit variants (default '7,14'). Each "
                         "becomes a distinct session: _earlyexit_d7, _earlyexit_d14. "
                         "Single value (e.g. '14') = original behavior."))
    p.add_argument("--early-exit-vc-threshold", type=float, default=0.40,
                   help="vol_cliff threshold above which early-exit fires (default 0.40).")
    p.add_argument("--baseline-hold-days", default="30",
                   help=("Comma-separated list of hold horizons (days) to spawn "
                         "as PARALLEL baseline variants (default '30' = R-4 PASS "
                         "horizon). '30,21' seeds both the R-4 PASS hold-30 and "
                         "the R-3 plateau-optimum hold-21 variant (median "
                         "+24-28%, win 62-66%). Non-30 values produce a "
                         "_h{N} session-name suffix; hold=30 keeps the original "
                         "name shape for back-compat."))
    p.add_argument("--bear-skip-threshold", type=float, default=-0.05,
                   help=("BTC 30d pre-listing return threshold below which the "
                         "bear_skip variant suppresses entry (default -0.05 per "
                         "R-3 regime analysis: BEAR cohort n=38 median -50.08%)."))
    p.add_argument("--list-upcoming", action="store_true",
                   help="just report forward-detected crypto listings (PENDING_TRADING + "
                        "future onboardDate) from exchangeInfo and exit (no spawning)")
    args = p.parse_args()

    if args.list_upcoming:
        info = fetch_exchange_info()
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        rows = []
        for s in info.get("symbols", []):
            if s.get("underlyingType") != "COIN" or s.get("contractType") != "PERPETUAL":
                continue
            ob = s.get("onboardDate") or 0
            if s.get("status") == "PENDING_TRADING" or ob > now_ms:
                rows.append((ob, s.get("status"), s["symbol"]))
        rows.sort()
        future = [(ob, st, sym) for ob, st, sym in rows if ob > now_ms]
        log.info("forward-detected upcoming crypto listings: %d", len(future))
        for ob, st, sym in future:
            dt = datetime.fromtimestamp(ob / 1000, tz=timezone.utc)
            log.info("  %s  onboard=%s  status=%s", sym, dt.strftime("%Y-%m-%d %H:%M UTC"), st)
        if not future:
            log.info("  (none scheduled with future onboardDate)")
        return 0

    if args.policy == "both":
        variants = [POLICY_BASELINE, POLICY_EARLY_EXIT]
    elif args.policy == "all":
        variants = [POLICY_BASELINE, POLICY_EARLY_EXIT, POLICY_BEAR_SKIP]
    else:
        variants = [args.policy]

    # Resolve early-exit check_days: explicit --early-exit-check-day overrides
    # the list (back-compat), else parse --early-exit-check-days.
    if args.early_exit_check_day is not None:
        ee_check_days = [int(args.early_exit_check_day)]
    else:
        ee_check_days = sorted({int(x) for x in args.early_exit_check_days.split(",") if x.strip()})
    log.info("early-exit check_days = %s", ee_check_days)

    baseline_hold_days_list = sorted({int(x) for x in args.baseline_hold_days.split(",") if x.strip()})
    log.info("baseline hold_days = %s", baseline_hold_days_list)

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
        # Bear_skip needs BTC 30d pre-listing return — compute once per symbol
        # so all bear_skip variants for the same listing share the same regime
        # decision (and the cost is one Binance klines fetch per listing).
        bear_skip_pre_ret = None
        if POLICY_BEAR_SKIP in variants:
            bear_skip_pre_ret = compute_btc_30d_pre_ret(meta["onboard_date"])
            if bear_skip_pre_ret is None:
                log.warning(
                    "[%s] bear_skip btc_30d_pre_ret unavailable — variant will be skipped",
                    sym,
                )

        for variant in variants:
            # For early_exit, iterate every requested check_day (each is a
            # distinct paper session). For baseline, iterate every requested
            # hold_days horizon. For bear_skip, single variant per listing.
            if variant == POLICY_EARLY_EXIT:
                axis_iter = [("cd", cd) for cd in ee_check_days]
            elif variant == POLICY_BEAR_SKIP:
                axis_iter = [("bs", None)]
            else:
                axis_iter = [("hold", h) for h in baseline_hold_days_list]
            for axis_kind, axis_val in axis_iter:
                if axis_kind == "cd":
                    tag = f"{sym}/{variant}_d{axis_val}"
                    cd_arg, hold_arg = int(axis_val), 30
                elif axis_kind == "bs":
                    tag = f"{sym}/{variant}"
                    cd_arg, hold_arg = None, 30
                    if bear_skip_pre_ret is None:
                        skipped.append((tag, "btc_30d_pre_ret unavailable"))
                        continue
                else:
                    suffix_tag = "" if int(axis_val) == 30 else f"_h{int(axis_val)}"
                    tag = f"{sym}/{variant}{suffix_tag}"
                    cd_arg, hold_arg = None, int(axis_val)
                if session_exists_for(
                    sym,
                    policy_variant=variant,
                    check_day=cd_arg,
                    baseline_hold_days=hold_arg,
                ):
                    skipped.append((tag, "session already exists"))
                    continue
                ok_spawn = spawn_session(
                    sym,
                    meta["onboard_date"],
                    policy_variant=variant,
                    early_exit_check_day=(cd_arg if cd_arg is not None else 14),
                    early_exit_vc_threshold=args.early_exit_vc_threshold,
                    baseline_hold_days=hold_arg,
                    bear_skip_btc_30d_pre_ret=bear_skip_pre_ret,
                    bear_skip_threshold=args.bear_skip_threshold,
                    dry_run=args.dry_run,
                )
                if not ok_spawn:
                    skipped.append((tag, "spawn failed"))
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
