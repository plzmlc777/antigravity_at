"""Insert paradigm 186 entry into INDEX.json after paradigm 185 entry."""
import json
from pathlib import Path
from datetime import datetime

INDEX_PATH = Path("/home/hcpark/antigravity/backend/runs/research_track/INDEX.json")

with open(INDEX_PATH) as f:
    idx = json.load(f)

paradigms = idx["paradigms"]
new_entry_key = "paradigm_186_short_only_btc_downtrend_filter_daily_rebal_r1_graveyard"

paradigms[new_entry_key] = {
    "id": 186,
    "slug": "alt_per_sym_30d_return_z_continuous_weighted_short_only_btc_downtrend_filter_daily_rebal",
    "name": "per-sym 30d return z SHORT-only + BTC 90d downtrend regime filter daily-rebal",
    "phase": "R1_GRAVEYARD",
    "verdict": "AXIS_STACKING_TRAP",
    "verdict_reason": "Lesson #21 axis stacking TRAP CONFIRMED (2nd dogfood after paradigm 122). paradigm 186 vs paradigm 185 baseline both dims degraded: Δz_excess=-1.6042 (2.27→0.66), Δsharpe=-0.509 (0.501→-0.008), perm_p 0.013→0.244, ann_ret +36.78%→-0.40%, max_dd worsened -47.30%→-52.98%. Hypothesis directly falsified: 2024Q3 large DD quarter (regime-active 68.5%) became DEEPER (-23.28%→-28.02%) with filter, while 2025Q3 (regime-inactive 100%) DD removed but alpha source quarters (2024Q4 / 2025Q1 BTC uptrend) gutted -23%/-22%pt each. paradigm 185 alpha is concentrated in BTC uptrend regime — filter excludes alpha-bearing windows.",
    "run_ts": "2026-05-22T01:10:11Z",
    "config_summary": {
        "regime_filter": "btc_90d_cum_return < 0 universe-level boolean gate",
        "regime_window_d": 90,
        "regime_active_days": 363,
        "regime_active_pct": 51.78,
        "z_return_window_d": 30,
        "z_window_d": 90,
        "z_floor": 0.5,
        "z_cap": 3.0,
        "fee_bp_one_way": 8.0,
        "funding_model": "actual_binance_funding_rate_db",
        "n_perm": 1000,
    },
    "paradigm_185_baseline_comparison": {
        "p185_sharpe": 0.501,
        "p186_sharpe": -0.008,
        "delta_sharpe": -0.509,
        "p185_z_excess": 2.2675,
        "p186_z_excess": 0.6633,
        "delta_z_excess": -1.6042,
        "p185_max_dd_pct": -47.299,
        "p186_max_dd_pct": -52.981,
        "delta_max_dd_pct": -5.682,
        "drawdown_trimmed": False,
        "quarters_positive_p185": 5,
        "quarters_positive_p186": 4,
    },
    "lessons_applied": [
        "#11_sample_density_PASS_alpha_destroyed",
        "#21_axis_stacking_TRAP_2nd_dogfood_CONFIRMED",
        "#61_slug_grep_0_collision",
        "#67_signal_vs_gate_distinction_ESCAPE_verified",
        "#68_continuous_rebal_ESCAPE_verified",
        "#70_corollary_scope_proceed_r1_followup_overlay",
        "#71_path_c_regime_active_util_68_37_pct_PASS",
    ],
    "continuous_weighting_framework_status": "4th consecutive sub-mode FAIL (paradigm 181 LONG / 184 LONG-SHORT / 185 SHORT-only NSLC / 186 SHORT+regime_filter AXIS_STACKING_TRAP) — framework 14-sym universe Tier 4 retire formal recommendation strengthened",
    "memory_compliance": {
        "no_freemium_trial": True,
        "life_changing_4dim_audited": True,
        "persistence_over_efficiency": True,
        "continuous_parallel_campaign": True,
        "actual_funding_rate_model": True,
    },
    "next_action_recommendation": "paradigm 187 = (A) continuous-weighting framework 14-sym universe Tier 4 retire formal decision; OR (B) framework abandon + fresh paradigm dimension (cross-asset / event-anchored / microstructure). Recommendation A — 4 sub-modes 4/4 life-changing FAIL implies framework structural limit not parameter tuning.",
}

idx["paradigms"] = paradigms
idx["updated_at"] = datetime.utcnow().isoformat() + "Z"
idx["last_updated_at_kst"] = "2026-05-22T10:11:00+09:00"

with open(INDEX_PATH, "w") as f:
    json.dump(idx, f, indent=2, ensure_ascii=False)

print(f"INDEX updated with paradigm 186 entry: {new_entry_key}")
print(f"paradigms total count: {len(paradigms)}")
