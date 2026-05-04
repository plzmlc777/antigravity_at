#!/usr/bin/env python3
"""Research Track Hard Gate evaluator (paradigm-agnostic).

Reads a metrics JSON describing a candidate spec's trade-sim baseline + robustness
diagnostics, and returns PASS/FAIL with the failing reasons.

Gate definition (research_track_master.md §2):
  Quantitative cutoffs (5 AND):
    alpha_pct >= 150, sharpe_ann >= 2.0, max_dd_pct <= 28,
    win_rate_pct >= 50, profit_factor >= 2.0
  Robustness (4 AND, optional fields skipped if missing):
    perm_p <= 0.05, wf_positive_folds >= wf_total_folds - 1,
    |vf_alpha_pct - alpha_pct| / |alpha_pct| <= 0.30,
    n_trades >= 30, oos_days >= 365

Usage:
  python -m scripts.eval_research_gate --metrics path/to/metrics.json
  python -m scripts.eval_research_gate --metrics path/to/metrics.json --md path/to/gate_eval.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CUTOFFS = {
    "alpha_pct_min": 150.0,
    "sharpe_ann_min": 2.0,
    "max_dd_pct_max": 28.0,
    "win_rate_pct_min": 50.0,
    "profit_factor_min": 2.0,
    "perm_p_max": 0.05,
    "vf_dependency_max": 0.30,
    "n_trades_min": 30,
    "oos_days_min": 365,
}


def evaluate_gate(metrics: dict[str, Any]) -> tuple[bool, list[str], dict[str, str]]:
    """Return (passed, fail_reasons, per_check_status)."""
    fails: list[str] = []
    status: dict[str, str] = {}

    # 2-A quantitative cutoffs
    alpha = float(metrics.get("alpha_pct", float("-inf")))
    if alpha < CUTOFFS["alpha_pct_min"]:
        fails.append(f"alpha={alpha:.1f} < {CUTOFFS['alpha_pct_min']}")
        status["alpha"] = f"FAIL ({alpha:.1f})"
    else:
        status["alpha"] = f"PASS ({alpha:.1f})"

    sharpe = float(metrics.get("sharpe_ann", float("-inf")))
    if sharpe < CUTOFFS["sharpe_ann_min"]:
        fails.append(f"sharpe={sharpe:.2f} < {CUTOFFS['sharpe_ann_min']}")
        status["sharpe"] = f"FAIL ({sharpe:.2f})"
    else:
        status["sharpe"] = f"PASS ({sharpe:.2f})"

    mdd = float(metrics.get("max_dd_pct", float("inf")))
    if mdd > CUTOFFS["max_dd_pct_max"]:
        fails.append(f"mdd={mdd:.1f} > {CUTOFFS['max_dd_pct_max']}")
        status["max_dd"] = f"FAIL ({mdd:.1f})"
    else:
        status["max_dd"] = f"PASS ({mdd:.1f})"

    wr = float(metrics.get("win_rate_pct", float("-inf")))
    if wr < CUTOFFS["win_rate_pct_min"]:
        fails.append(f"wr={wr:.1f} < {CUTOFFS['win_rate_pct_min']}")
        status["win_rate"] = f"FAIL ({wr:.1f})"
    else:
        status["win_rate"] = f"PASS ({wr:.1f})"

    pf = float(metrics.get("profit_factor", float("-inf")))
    if pf < CUTOFFS["profit_factor_min"]:
        fails.append(f"pf={pf:.2f} < {CUTOFFS['profit_factor_min']}")
        status["profit_factor"] = f"FAIL ({pf:.2f})"
    else:
        status["profit_factor"] = f"PASS ({pf:.2f})"

    # 2-B robustness
    if "perm_p" in metrics:
        perm_p = float(metrics["perm_p"])
        if perm_p > CUTOFFS["perm_p_max"]:
            fails.append(f"perm_p={perm_p:.3f} > {CUTOFFS['perm_p_max']}")
            status["perm_test"] = f"FAIL (p={perm_p:.3f})"
        else:
            status["perm_test"] = f"PASS (p={perm_p:.3f})"
    else:
        status["perm_test"] = "SKIP (missing)"

    wf_pos = metrics.get("wf_positive_folds")
    wf_tot = metrics.get("wf_total_folds")
    if wf_pos is not None and wf_tot is not None:
        wf_pos = int(wf_pos)
        wf_tot = int(wf_tot)
        if wf_pos < (wf_tot - 1):
            fails.append(f"wf {wf_pos}/{wf_tot} < {wf_tot - 1}/{wf_tot}")
            status["walk_forward"] = f"FAIL ({wf_pos}/{wf_tot})"
        else:
            status["walk_forward"] = f"PASS ({wf_pos}/{wf_tot})"
    else:
        status["walk_forward"] = "SKIP (missing)"

    if "vf_alpha_pct" in metrics:
        vf_alpha = float(metrics["vf_alpha_pct"])
        denom = max(abs(alpha), 1.0)
        diff = abs(vf_alpha - alpha) / denom
        if diff > CUTOFFS["vf_dependency_max"]:
            fails.append(f"vf_dependency {diff*100:.0f}% > {int(CUTOFFS['vf_dependency_max']*100)}%")
            status["vf_dependency"] = f"FAIL ({diff*100:.0f}%)"
        else:
            status["vf_dependency"] = f"PASS ({diff*100:.0f}%)"
    else:
        status["vf_dependency"] = "SKIP (missing)"

    n_trades = int(metrics.get("n_trades", 0))
    if n_trades < CUTOFFS["n_trades_min"]:
        fails.append(f"n_trades={n_trades} < {CUTOFFS['n_trades_min']}")
        status["n_trades"] = f"FAIL ({n_trades})"
    else:
        status["n_trades"] = f"PASS ({n_trades})"

    oos_days = int(metrics.get("oos_days", 0))
    if oos_days < CUTOFFS["oos_days_min"]:
        fails.append(f"oos_days={oos_days} < {CUTOFFS['oos_days_min']}")
        status["oos_days"] = f"FAIL ({oos_days}d)"
    else:
        status["oos_days"] = f"PASS ({oos_days}d)"

    return (len(fails) == 0, fails, status)


def render_markdown(metrics: dict[str, Any], passed: bool, fails: list[str],
                    status: dict[str, str]) -> str:
    sym = metrics.get("symbol", "?")
    paradigm = metrics.get("paradigm", "?")
    spec = metrics.get("spec_name", "?")
    verdict = "✅ PASS" if passed else "❌ FAIL"

    lines = [
        f"# Research Track Gate Evaluation — {sym}",
        "",
        f"- **Paradigm**: `{paradigm}`",
        f"- **Spec**: `{spec}`",
        f"- **Evaluated**: {datetime.now(tz=timezone.utc).isoformat()}",
        f"- **Verdict**: **{verdict}**",
        "",
        "## Quantitative cutoffs (5 AND)",
        "",
        "| Metric | Status | Threshold |",
        "|---|---|---|",
        f"| alpha_pct | {status['alpha']} | >= {CUTOFFS['alpha_pct_min']} |",
        f"| sharpe_ann | {status['sharpe']} | >= {CUTOFFS['sharpe_ann_min']} |",
        f"| max_dd_pct | {status['max_dd']} | <= {CUTOFFS['max_dd_pct_max']} |",
        f"| win_rate_pct | {status['win_rate']} | >= {CUTOFFS['win_rate_pct_min']} |",
        f"| profit_factor | {status['profit_factor']} | >= {CUTOFFS['profit_factor_min']} |",
        "",
        "## Robustness (4 AND)",
        "",
        "| Check | Status | Threshold |",
        "|---|---|---|",
        f"| perm_test | {status['perm_test']} | p <= {CUTOFFS['perm_p_max']} |",
        f"| walk_forward | {status['walk_forward']} | >= total-1 / total |",
        f"| vf_dependency | {status['vf_dependency']} | <= {int(CUTOFFS['vf_dependency_max']*100)}% |",
        f"| n_trades | {status['n_trades']} | >= {CUTOFFS['n_trades_min']} |",
        f"| oos_days | {status['oos_days']} | >= {CUTOFFS['oos_days_min']} |",
        "",
    ]
    if fails:
        lines.append("## Failures")
        lines.append("")
        for f in fails:
            lines.append(f"- {f}")
        lines.append("")
    if passed:
        lines.append(
            "## Next step\n\n"
            "Gate auto-PASS. Present spec to user for explicit approval before "
            "`paper_session_cli create` (research_track_master.md §5-B).\n"
        )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Evaluate research track gate.")
    p.add_argument("--metrics", required=True, help="Path to metrics JSON.")
    p.add_argument("--md", help="Optional path to write markdown report.")
    args = p.parse_args()

    metrics_path = Path(args.metrics)
    metrics = json.loads(metrics_path.read_text())

    passed, fails, status = evaluate_gate(metrics)

    print(json.dumps({
        "symbol": metrics.get("symbol"),
        "paradigm": metrics.get("paradigm"),
        "spec_name": metrics.get("spec_name"),
        "passed": passed,
        "fails": fails,
        "status": status,
    }, indent=2))

    if args.md:
        Path(args.md).write_text(render_markdown(metrics, passed, fails, status))
        print(f"\nMarkdown written: {args.md}", file=sys.stderr)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
