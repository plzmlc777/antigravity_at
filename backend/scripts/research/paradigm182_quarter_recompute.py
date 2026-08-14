"""Recompute paradigm 182 quarter breakdown properly (paradigm 181 had strftime bug)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path("/home/hcpark/antigravity/backend/runs/research_track/alt_per_sym_30d_risk_adjusted_sharpe_z_continuous_weighted_long_only_daily_rebal")

ts = pd.read_csv(OUT_DIR / "r1__timeseries.csv", index_col=0, parse_dates=True)

def q_breakdown(ret: pd.Series):
    out = []
    grouped = ret.groupby(pd.Grouper(freq="QS"))
    for q_start, q_ret in grouped:
        if len(q_ret) < 5:
            continue
        eq = (1.0 + q_ret).cumprod()
        total = float(eq.iloc[-1] - 1.0)
        sh = float(q_ret.mean() / q_ret.std() * np.sqrt(365)) if q_ret.std() > 0 else 0.0
        out.append({
            "quarter": f"{q_start.year}Q{q_start.quarter}",
            "n_days": int(len(q_ret)),
            "total_return_pct": round(total * 100, 3),
            "sharpe": round(sh, 3),
            "positive": bool(total > 0),
        })
    return out

ts["net_ret"] = ts["net_ret"].astype(float)
ts["eq_basket"] = ts["eq_basket"].astype(float)
ts["btc_bnh"] = ts["btc_bnh"].astype(float)

port_q = q_breakdown(ts["net_ret"])
eq_q = q_breakdown(ts["eq_basket"])
btc_q = q_breakdown(ts["btc_bnh"])

# Util by quarter
ts["active_syms"] = ts["active_syms"].astype(int)
ts["total_weight"] = ts["total_weight"].astype(float)
util_by_q = []
for q_start, sub in ts.groupby(pd.Grouper(freq="QS")):
    if len(sub) < 5:
        continue
    util_by_q.append({
        "quarter": f"{q_start.year}Q{q_start.quarter}",
        "n_days": int(len(sub)),
        "util_pct_capital": round(float(sub["total_weight"].mean()) * 100, 2),
        "avg_active_syms": round(float(sub["active_syms"].mean()), 2),
    })

alpha = ts["net_ret"] - ts["eq_basket"]
alpha_q = q_breakdown(alpha)

result = {
    "portfolio_net_quarters": port_q,
    "equal_weight_quarters": eq_q,
    "btc_bnh_quarters": btc_q,
    "alpha_vs_eq_quarters": alpha_q,
    "util_by_quarter": util_by_q,
    "n_quarters": len(port_q),
    "quarters_port_positive": sum(1 for q in port_q if q["positive"]),
    "quarters_alpha_positive": sum(1 for q in alpha_q if q["positive"]),
}

with open(OUT_DIR / "r1__quarter_breakdown_fixed.json", "w") as f:
    json.dump(result, f, indent=2)

# Print summary
print("\n=== Quarter-by-quarter portfolio_net vs eq_basket ===")
print(f"{'Q':<8} {'n':<4} {'Port%':<10} {'EqBkt%':<10} {'Alpha%':<10} {'Sharpe':<8} {'Util%':<8} {'ActSym':<8}")
for i, q in enumerate(port_q):
    eq = eq_q[i] if i < len(eq_q) else {"total_return_pct": 0}
    al = alpha_q[i] if i < len(alpha_q) else {"total_return_pct": 0}
    u = util_by_q[i] if i < len(util_by_q) else {"util_pct_capital": 0, "avg_active_syms": 0}
    print(f"{q['quarter']:<8} {q['n_days']:<4} {q['total_return_pct']:<10} {eq['total_return_pct']:<10} {al['total_return_pct']:<10} {q['sharpe']:<8} {u['util_pct_capital']:<8} {u['avg_active_syms']:<8}")

print(f"\nQuarters port positive: {result['quarters_port_positive']}/{result['n_quarters']}")
print(f"Quarters alpha positive: {result['quarters_alpha_positive']}/{result['n_quarters']}")
