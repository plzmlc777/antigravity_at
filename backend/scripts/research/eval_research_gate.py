"""Research Track elite gate evaluator.

Reads a paradigm's metrics.json from backend/runs/research_track/{paradigm}/
and reports PASS/FAIL with explicit failure reasons. Supports two paradigm
shapes (auto-detected):

  Type T — Time-series strategy
    metrics fields required:
      alpha_pct, sharpe_ann, max_dd_pct, win_rate_pct, profit_factor,
      perm_p, wf_positive_folds, wf_total_folds, n_trades, oos_days
    Gate (research_track_master.md §2-A + 2-B):
      alpha_pct ≥ 150 AND sharpe_ann ≥ 2.0 AND max_dd_pct ≤ 28
        AND win_rate_pct ≥ 50 AND profit_factor ≥ 2.0
      AND perm_p ≤ 0.05 AND wf_positive_folds / wf_total_folds ≥ 5/6
      AND n_trades ≥ 30

  Type E — Event-study / cross-sectional
    metrics fields required (under "all_cohort_short_30d_ret_net" or root):
      n, median_pct, win_rate_positive, perm_p, bootstrap_ci_lo_pct,
      quarterly_n_positive, quarterly_n_total
    Gate (proposed for event-study):
      n ≥ 100 AND median_pct ≥ 15 AND win_rate_positive ≥ 0.55
      AND perm_p ≤ 0.05 AND bootstrap_ci_lo_pct > 0
      AND quarterly_n_positive / quarterly_n_total ≥ 3/4

Type detection: if metrics contains "alpha_pct" → T, if contains
"all_cohort_*_ret_net" or has "permutation_test" + "quarterly_folds" → E.
Override with --type.

Usage:
  python -m scripts.research.eval_research_gate \\
      --metrics backend/runs/research_track/lifecycle_phase/r2__metrics.json

Output: prints PASS/FAIL report + writes gate_eval__{paradigm}.md sibling.
Exit code: 0 = PASS, 1 = FAIL (so scripts can chain).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("eval_research_gate")

# Time-series strategy gate thresholds (research_track_master.md §2-A + 2-B)
GATE_T = {
    "alpha_pct_min": 150.0,
    "sharpe_ann_min": 2.0,
    "max_dd_pct_max": 28.0,
    "win_rate_pct_min": 50.0,
    "profit_factor_min": 2.0,
    "perm_p_max": 0.05,
    "wf_pos_fold_ratio_min": 5 / 6,
    "n_trades_min": 30,
    "vf_alpha_diff_max": 0.30,
}

# Event-study / cross-sectional gate thresholds (proposed extension)
GATE_E = {
    "n_min": 100,
    "median_pct_min": 15.0,
    "win_rate_min": 0.55,
    "perm_p_max": 0.05,
    "bootstrap_ci_lo_min": 0.0,    # CI lower bound must be > 0
    "quarterly_pos_ratio_min": 3 / 4,
    "quarterly_n_min": 3,
}

# Event-study (new _perm_utils schema, fee-aware) gate thresholds
# Introduced 2026-05-14 after fee-drag-trap lesson; paradigms using
# scripts.research._perm_utils emit heavy_perm_best_cell + heavy_bootstrap_best_cell.
GATE_E_NEW = {
    "n_trades_min": 100,
    "signal_t_excess_min": 2.5,
    "perm_p_above_max": 0.05,
    "ci_lower_bp_min": 0.0,
    "plateau_min": 10,
    "quarter_sig_t_excess_min": 2.0,
    "quarter_min_count_required": 2,
}


def detect_type(metrics: dict) -> str:
    if "alpha_pct" in metrics or "sharpe_ann" in metrics:
        return "T"
    # E-type heuristics: has cohort summary stats + permutation
    if any(k.endswith("_ret_net") or k.endswith("_short_30d_ret_net") for k in metrics):
        return "E"
    if "permutation_test" in metrics and "quarterly_folds" in metrics:
        return "E"
    # New _perm_utils-based event-study (heavy_perm_best_cell marker)
    if "heavy_perm_best_cell" in metrics and "heavy_bootstrap_best_cell" in metrics:
        return "E"
    return "T"  # default


def _is_new_schema(m: dict) -> bool:
    """Detect new _perm_utils-based event-study schema (introduced 2026-05-14)."""
    return "heavy_perm_best_cell" in m and "heavy_bootstrap_best_cell" in m


def evaluate_e_new(m: dict) -> tuple[bool, list[str], dict]:
    """Event-study gate for new _perm_utils-based schema.

    Required blocks:
      - best_cell_recheck: {n_trades, net_mean_bp, t, win, sharpe}
      - heavy_perm_best_cell: {signal_t_excess, perm_p_one_sided_above, ...}
      - heavy_bootstrap_best_cell: {ci_lower_bp, ci_upper_bp, prob_positive, ...}
      - plateau_pass_count (int)
      - sample_bias_quarters: per-quarter dict with sig_t_excess + perm_p_above
      - look_ahead_clean (bool)
    """
    fails: list[str] = []
    parsed: dict = {}

    best = m.get("best_cell_recheck") or {}
    perm = m.get("heavy_perm_best_cell") or {}
    boot = m.get("heavy_bootstrap_best_cell") or {}

    n_trades = best.get("n_trades", 0)
    sig_t_excess = perm.get("signal_t_excess")
    perm_p_above = perm.get("perm_p_one_sided_above")
    ci_lower_bp = boot.get("ci_lower_bp")
    plateau = m.get("plateau_pass_count", 0)
    look_ahead_clean = m.get("look_ahead_clean", False)

    parsed.update({
        "n_trades": n_trades,
        "signal_t_excess": sig_t_excess,
        "perm_p_one_sided_above": perm_p_above,
        "ci_lower_bp": ci_lower_bp,
        "plateau_pass_count": plateau,
        "look_ahead_clean": look_ahead_clean,
        "net_mean_bp": best.get("net_mean_bp"),
        "t_stat": best.get("t"),
    })

    if n_trades < GATE_E_NEW["n_trades_min"]:
        fails.append(f"n_trades {n_trades} < {GATE_E_NEW['n_trades_min']}")
    if sig_t_excess is None or sig_t_excess < GATE_E_NEW["signal_t_excess_min"]:
        fails.append(f"signal_t_excess {sig_t_excess} < {GATE_E_NEW['signal_t_excess_min']}")
    if perm_p_above is None or perm_p_above > GATE_E_NEW["perm_p_above_max"]:
        fails.append(f"perm_p_one_sided_above {perm_p_above} > {GATE_E_NEW['perm_p_above_max']}")
    if ci_lower_bp is None or ci_lower_bp <= GATE_E_NEW["ci_lower_bp_min"]:
        fails.append(f"bootstrap ci_lower_bp {ci_lower_bp} ≤ {GATE_E_NEW['ci_lower_bp_min']}")
    if plateau < GATE_E_NEW["plateau_min"]:
        fails.append(f"plateau_pass_count {plateau} < {GATE_E_NEW['plateau_min']}")
    if not look_ahead_clean:
        fails.append("look_ahead_clean is False (potential lookahead bias)")

    # Per-quarter robustness check (sample_bias_quarters: each quarter must independently pass)
    sbq = m.get("sample_bias_quarters") or {}
    quarter_dicts = [v for v in sbq.values() if isinstance(v, dict)]
    n_quarters_pass = 0
    n_quarters_present = 0
    for q in quarter_dicts:
        q_n = q.get("n", 0)
        if q_n < 30:
            continue
        n_quarters_present += 1
        q_sig = q.get("signal_t_excess") or q.get("sig_t_excess")
        q_perm_p = q.get("perm_p_one_sided_above")
        if q_sig is not None and q_sig >= GATE_E_NEW["quarter_sig_t_excess_min"] and (q_perm_p is None or q_perm_p <= 0.05):
            n_quarters_pass += 1
    parsed["quarters_present"] = n_quarters_present
    parsed["quarters_passing"] = n_quarters_pass
    if n_quarters_present < GATE_E_NEW["quarter_min_count_required"]:
        fails.append(f"sample_bias_quarters present {n_quarters_present} < {GATE_E_NEW['quarter_min_count_required']} (need ≥2 independent quarters)")
    elif n_quarters_pass < n_quarters_present:
        fails.append(f"quarters_passing {n_quarters_pass}/{n_quarters_present} (each present quarter must independently pass sig_t_excess≥{GATE_E_NEW['quarter_sig_t_excess_min']})")

    return len(fails) == 0, fails, parsed


def _ratio(num: float, denom: float) -> float | None:
    if denom <= 0:
        return None
    return num / denom


def evaluate_t(m: dict) -> tuple[bool, list[str], dict]:
    """Time-series gate. Returns (passed, failure_reasons, parsed_values)."""
    fails: list[str] = []
    parsed: dict = {}
    required = ["alpha_pct", "sharpe_ann", "max_dd_pct", "win_rate_pct",
                "profit_factor", "perm_p", "wf_positive_folds",
                "wf_total_folds", "n_trades"]
    for k in required:
        if k not in m:
            fails.append(f"missing required metric: {k}")
            return False, fails, parsed

    parsed = {k: m[k] for k in required}
    if "vf_alpha_diff" in m:
        parsed["vf_alpha_diff"] = m["vf_alpha_diff"]

    if parsed["alpha_pct"] < GATE_T["alpha_pct_min"]:
        fails.append(f"alpha {parsed['alpha_pct']:.1f}% < {GATE_T['alpha_pct_min']}")
    if parsed["sharpe_ann"] < GATE_T["sharpe_ann_min"]:
        fails.append(f"sharpe {parsed['sharpe_ann']:.2f} < {GATE_T['sharpe_ann_min']}")
    if parsed["max_dd_pct"] > GATE_T["max_dd_pct_max"]:
        fails.append(f"max_dd {parsed['max_dd_pct']:.1f}% > {GATE_T['max_dd_pct_max']}")
    if parsed["win_rate_pct"] < GATE_T["win_rate_pct_min"]:
        fails.append(f"win_rate {parsed['win_rate_pct']:.1f}% < {GATE_T['win_rate_pct_min']}")
    if parsed["profit_factor"] < GATE_T["profit_factor_min"]:
        fails.append(f"profit_factor {parsed['profit_factor']:.2f} < {GATE_T['profit_factor_min']}")
    if parsed["perm_p"] > GATE_T["perm_p_max"]:
        fails.append(f"perm_p {parsed['perm_p']:.4f} > {GATE_T['perm_p_max']}")
    if parsed["n_trades"] < GATE_T["n_trades_min"]:
        fails.append(f"n_trades {parsed['n_trades']} < {GATE_T['n_trades_min']}")
    wf_ratio = _ratio(parsed["wf_positive_folds"], parsed["wf_total_folds"])
    if wf_ratio is None or wf_ratio < GATE_T["wf_pos_fold_ratio_min"]:
        fails.append(f"wf_positive_folds {parsed['wf_positive_folds']}/{parsed['wf_total_folds']} < 5/6")
    if "vf_alpha_diff" in parsed and abs(parsed["vf_alpha_diff"]) > GATE_T["vf_alpha_diff_max"]:
        fails.append(f"vf_alpha_diff {parsed['vf_alpha_diff']:.2f} > {GATE_T['vf_alpha_diff_max']}")

    return len(fails) == 0, fails, parsed


def evaluate_e(m: dict) -> tuple[bool, list[str], dict]:
    """Event-study gate."""
    fails: list[str] = []
    parsed: dict = {}

    # Find the cohort summary block (e.g., "all_cohort_short_30d_ret_net")
    cohort = None
    for k, v in m.items():
        if isinstance(v, dict) and v.get("n") and ("median_pct" in v or "win_rate_positive" in v):
            if k.startswith("all_") or k == "cohort_summary" or "all_cohort" in k:
                cohort = v
                break
    if cohort is None:
        # Fallback: top-level fields
        if "median_pct" in m and "n" in m:
            cohort = m
        else:
            fails.append("could not locate cohort summary block (need {n, median_pct, win_rate_positive})")
            return False, fails, parsed

    n = cohort.get("n", 0)
    median_pct = cohort.get("median_pct", 0)
    win_rate = cohort.get("win_rate_positive", 0)
    parsed["n"] = n
    parsed["median_pct"] = median_pct
    parsed["win_rate_positive"] = win_rate

    if n < GATE_E["n_min"]:
        fails.append(f"n={n} < {GATE_E['n_min']}")
    if median_pct < GATE_E["median_pct_min"]:
        fails.append(f"median {median_pct:.1f}% < {GATE_E['median_pct_min']}")
    if win_rate < GATE_E["win_rate_min"]:
        fails.append(f"win_rate {win_rate:.3f} < {GATE_E['win_rate_min']}")

    # Permutation
    perm = m.get("permutation_test", {})
    perm_p = perm.get("p_value_one_sided", 1.0)
    parsed["perm_p"] = perm_p
    parsed["perm_sigma"] = perm.get("sigma")
    if perm_p > GATE_E["perm_p_max"]:
        fails.append(f"perm_p {perm_p:.4f} > {GATE_E['perm_p_max']}")

    # Bootstrap CI lower bound
    bs_block = None
    for k in m:
        if "bootstrap" in k and isinstance(m[k], dict):
            bs_block = m[k]
            break
    if bs_block:
        ci_lo = bs_block.get("median_ci_lo_pct")
        parsed["bootstrap_median_ci_lo_pct"] = ci_lo
        if ci_lo is None or ci_lo <= GATE_E["bootstrap_ci_lo_min"]:
            fails.append(f"bootstrap median CI lower bound {ci_lo} ≤ {GATE_E['bootstrap_ci_lo_min']}")
    else:
        fails.append("bootstrap CI block missing")

    # Quarterly stability
    q_folds = m.get("quarterly_folds") or m.get("quarterly_regime_breakdown")
    if q_folds and isinstance(q_folds, dict):
        valid = {q: v for q, v in q_folds.items() if isinstance(v, dict) and v.get("n", 0) >= 5}
        # determine sign of each quarter
        n_pos = sum(1 for q, v in valid.items()
                    if (v.get("median_pct") or v.get("median_ret_pct") or 0) > 0)
        n_total = len(valid)
        parsed["quarterly_n_positive"] = n_pos
        parsed["quarterly_n_total"] = n_total
        if n_total < GATE_E["quarterly_n_min"]:
            fails.append(f"quarterly_n_total {n_total} < {GATE_E['quarterly_n_min']}")
        elif (n_pos / n_total) < GATE_E["quarterly_pos_ratio_min"]:
            fails.append(f"quarterly_positive {n_pos}/{n_total} < {GATE_E['quarterly_pos_ratio_min']:.0%}")
    else:
        fails.append("quarterly_folds / quarterly_regime_breakdown missing")

    return len(fails) == 0, fails, parsed


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--metrics", required=True, help="Path to paradigm metrics.json")
    p.add_argument("--type", choices=["T", "E"], default=None, help="Force gate type")
    p.add_argument("--out", default=None, help="Output gate_eval markdown (default: sibling of metrics)")
    p.add_argument("--paradigm-name", default=None, help="Paradigm name for report")
    args = p.parse_args()

    metrics_path = Path(args.metrics).resolve()
    if not metrics_path.exists():
        log.error("metrics file not found: %s", metrics_path)
        return 2

    metrics = json.loads(metrics_path.read_text())
    gate_type = args.type or detect_type(metrics)
    paradigm = args.paradigm_name or metrics_path.parent.name

    log.info("evaluating paradigm=%s type=%s metrics=%s", paradigm, gate_type, metrics_path.name)

    if gate_type == "T":
        passed, fails, parsed = evaluate_t(metrics)
        gate_thresholds = GATE_T
    elif _is_new_schema(metrics):
        passed, fails, parsed = evaluate_e_new(metrics)
        gate_thresholds = GATE_E_NEW
        log.info("using new _perm_utils-based event-study gate")
    else:
        passed, fails, parsed = evaluate_e(metrics)
        gate_thresholds = GATE_E

    # Generate markdown report
    lines = [
        f"# Research Gate Evaluation — {paradigm}",
        "",
        f"- **metrics**: `{metrics_path.relative_to(metrics_path.parents[3]) if len(metrics_path.parents) > 3 else metrics_path}`",
        f"- **type**: {gate_type} ({'time-series' if gate_type == 'T' else 'event-study / cross-sectional'})",
        f"- **verdict**: {'✅ PASS' if passed else '❌ FAIL'}",
        "",
        "## Parsed values",
        "",
    ]
    for k, v in parsed.items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    lines.append("## Thresholds")
    lines.append("")
    for k, v in gate_thresholds.items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    if fails:
        lines.append("## Failures")
        lines.append("")
        for f in fails:
            lines.append(f"- ❌ {f}")
    else:
        lines.append("## All gate criteria satisfied ✅")
    lines.append("")

    out_path = Path(args.out) if args.out else metrics_path.parent / f"gate_eval__{paradigm}.md"
    out_path.write_text("\n".join(lines))
    log.info("verdict: %s — wrote %s", "PASS" if passed else "FAIL", out_path)
    if fails:
        for f in fails:
            log.warning("  - %s", f)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
