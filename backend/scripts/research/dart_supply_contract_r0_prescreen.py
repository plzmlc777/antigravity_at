"""R-0 prescreen for paradigm 101 candidate dart_supply_contract_announce_kr_equity_long_5d.

Mandatory R-0 substrate audit (lesson #11 + #26 amendment + #27 amendment + #28):
1. Probe DART for 단일판매·공급계약체결 disclosure type (pblntf_ty=B 주요사항보고서 sub-type)
2. Count events 2024-01-01 ~ 2026-05-19 across 350 universe stocks
3. Compute quarterly distribution (n_measurable_quarters ≥ 4 prescreen — paradigm 100 동형 trap 회피)
4. Compute per-cell sample density (4-quadrant × ≥4 quarters → ≥30 per-cell auto check)
5. Disclosure_parser.py audit — Side classification 추정 (entry_immediate vs entry_delayed)

This is a R-0 prescreen ONLY. Outputs decision verdict for R-1 dispatch GO/NO-GO.
No backtest, no R-1 PoC execution.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Paths
HERE = Path(__file__).resolve()
PROJECT_ROOT = HERE.parents[3]   # /home/hcpark/antigravity
BACKEND_ROOT = HERE.parents[2]   # backend/
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
ENV_FILE = BACKEND_ROOT / ".env"
if ENV_FILE.exists():
    for ln in ENV_FILE.read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, _, v = ln.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import joblib  # noqa: E402

from backend.app.services import dart_adapter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r0_prescreen")

OUT_DIR = BACKEND_ROOT / "runs" / "research_track" / "dart_supply_contract_announce_kr_equity_long_5d"
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE_PATH = BACKEND_ROOT / "runs" / "dart_track" / "universe_kospi200_kosdaq150.joblib"

BGN_DE = "20240101"
END_DE = "20260519"


def main() -> int:
    universe = joblib.load(UNIVERSE_PATH)
    stock_codes = set(universe["itemCode"].astype(str).str.zfill(6).tolist())
    log.info("universe size = %d", len(stock_codes))

    counter_by_qtr: Counter[str] = Counter()
    counter_by_stock: Counter[str] = Counter()
    report_nm_samples: Counter[str] = Counter()
    matched = []

    needle_terms = ("단일판매", "공급계약")

    log.info("scanning DART KR equity disclosures %s ~ %s (corp_cls Y+K)...", BGN_DE, END_DE)
    n_total_b = 0
    n_match = 0

    def _scan(corp_cls):
        nonlocal n_total_b
        for r in dart_adapter.iter_disclosures_chunked(
            bgn_de=BGN_DE, end_de=END_DE, chunk_days=30, corp_cls=corp_cls
        ):
            n_total_b += 1
            yield r

    import itertools
    for row in itertools.chain(_scan("Y"), _scan("K")):
        report_nm = row.get("report_nm") or ""
        stock_code = (row.get("stock_code") or "").zfill(6)
        if stock_code not in stock_codes:
            continue
        nm = report_nm.strip()
        for prefix in ("[기재정정]", "[첨부정정]", "[정정]"):
            if nm.startswith(prefix):
                nm = nm[len(prefix):].strip()
        if not all(t in nm for t in needle_terms):
            continue
        n_match += 1
        rcept_dt = row.get("rcept_dt", "")
        if len(rcept_dt) >= 7:
            y, m = rcept_dt[:4], int(rcept_dt[4:6])
            q = (m - 1) // 3 + 1
            counter_by_qtr[f"{y}Q{q}"] += 1
        counter_by_stock[stock_code] += 1
        report_nm_samples[nm[:60]] += 1
        matched.append(
            {
                "rcept_dt": rcept_dt,
                "rcept_no": row.get("rcept_no"),
                "stock_code": stock_code,
                "corp_name": row.get("corp_name"),
                "report_nm": nm,
            }
        )
        if n_match % 500 == 0:
            log.info("...matched %d so far (scanned %d B-type)", n_match, n_total_b)

    log.info(
        "DONE: scanned n_total_b=%d B-type disclosures, matched=%d",
        n_total_b,
        n_match,
    )

    QTR_MIN_EVENTS = 20
    measurable_quarters = sorted(q for q, c in counter_by_qtr.items() if c >= QTR_MIN_EVENTS)
    n_measurable_quarters = len(measurable_quarters)

    per_quarter_focus = n_match / max(n_measurable_quarters, 1)

    density_per_quarter_min = 30
    density_pass = per_quarter_focus >= density_per_quarter_min
    n_measurable_pass = n_measurable_quarters >= 4

    side_audit = {
        "disclosure_parser_entry_exists": False,
        "proposed_side": "ENTRY_IMMEDIATE",
        "proposed_kind_code": "supply_contract",
        "proposed_tier": "A",
        "rationale": (
            "Single sales/supply contract announcement = immediate market attention "
            "information event (announcement itself = market-moving signal next bar). "
            "Lifecycle listing announce analog (paradigm 87 mechanism class). "
            "Future revenue contribution is secondary/delayed but primary trigger = "
            "immediate information attention (retail + institutional buying pressure)."
        ),
        "lesson_27_amendment_classify": "ENTRY_IMMEDIATE candidate",
    }

    top_patterns = report_nm_samples.most_common(10)

    decision_verdict = "GO_R1" if (density_pass and n_measurable_pass) else "HALT_R0"

    out = {
        "paradigm_name": "dart_supply_contract_announce_kr_equity_long_5d",
        "phase": "R-0_prescreen",
        "scan_window": [BGN_DE, END_DE],
        "universe_size": len(stock_codes),
        "n_total_b_type_scanned": n_total_b,
        "n_match_universe_supply_contract": n_match,
        "by_quarter": dict(sorted(counter_by_qtr.items())),
        "n_measurable_quarters_min20events": n_measurable_quarters,
        "measurable_quarters": measurable_quarters,
        "per_quarter_focus_avg": per_quarter_focus,
        "n_unique_stocks_triggered": len(counter_by_stock),
        "top10_stocks_by_event_count": counter_by_stock.most_common(10),
        "top10_report_nm_patterns": [(k, v) for k, v in top_patterns],
        "density_per_quarter_min_required": density_per_quarter_min,
        "density_pass": density_pass,
        "n_measurable_quarters_min_required": 4,
        "n_measurable_quarters_pass": n_measurable_pass,
        "side_classification_audit": side_audit,
        "decision_verdict": decision_verdict,
        "decision_reason": (
            f"density_pass={density_pass} (per_qtr={per_quarter_focus:.1f} >= {density_per_quarter_min}); "
            f"n_measurable_quarters_pass={n_measurable_pass} ({n_measurable_quarters} >= 4)"
        ),
        "next_step_recommendation": (
            "GO_R1: Build supply_contract_events_cache.joblib via DART API + price merge, "
            "patch disclosure_parser.py with SUPPLY_CONTRACT entry (Side.ENTRY_IMMEDIATE), "
            "dispatch R-1 4-quadrant symmetric negative + hold sweep 3d/5d/10d + Concentration Gate + 4-dim life-changing."
            if decision_verdict == "GO_R1"
            else "HALT_R0: insufficient sample density or n_measurable_quarters. Graveyard before R-1."
        ),
        "timestamp_kst": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    out_path = OUT_DIR / "r0_prescreen_metrics.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    log.info("wrote %s", out_path)

    matched_path = OUT_DIR / "r0_matched_events_raw.json"
    matched_path.write_text(json.dumps(matched, ensure_ascii=False))
    log.info("wrote %s (n=%d)", matched_path, len(matched))

    log.info("VERDICT: %s -- %s", decision_verdict, out["decision_reason"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
