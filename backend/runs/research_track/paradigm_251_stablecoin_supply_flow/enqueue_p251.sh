#!/usr/bin/env bash
# paradigm 251 — 3군 게이트 판정 + 2군 승격 큐 등록 (코드로 강제)
# 생성: p251_emit_specs_and_trades.py
set -euo pipefail
cd "$(dirname "$0")/../../.."

echo '=== BNBUSDT ==='
python3 scripts/research/tier3_gate.py \
  --trades runs/research_track/paradigm_251_stablecoin_supply_flow/gate_trades_BNBUSDT_h3d.json \
  --label 'p251 stablecoin_supply_flow BNBUSDT h3d' \
  --lookahead-clean true --edge-after-1bar 0.01368667 \
  --friction 0.0008 --hold-min 4320 --cycle-min 1440 \
  --out runs/research_track/paradigm_251_stablecoin_supply_flow/tier3_gate__BNBUSDT.json \
  --enqueue --name BNBUSDT_stablecoin_supply_flow_paper_seed \
  --spec configs/paper_sessions/BNBUSDT_stablecoin_supply_flow.json \
  --paradigm alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d --symbol BNBUSDT

echo '=== XRPUSDT ==='
python3 scripts/research/tier3_gate.py \
  --trades runs/research_track/paradigm_251_stablecoin_supply_flow/gate_trades_XRPUSDT_h3d.json \
  --label 'p251 stablecoin_supply_flow XRPUSDT h3d' \
  --lookahead-clean true --edge-after-1bar 0.02283955 \
  --friction 0.0008 --hold-min 4320 --cycle-min 1440 \
  --out runs/research_track/paradigm_251_stablecoin_supply_flow/tier3_gate__XRPUSDT.json \
  --enqueue --name XRPUSDT_stablecoin_supply_flow_paper_seed \
  --spec configs/paper_sessions/XRPUSDT_stablecoin_supply_flow.json \
  --paradigm alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d --symbol XRPUSDT

echo '=== AVAXUSDT ==='
python3 scripts/research/tier3_gate.py \
  --trades runs/research_track/paradigm_251_stablecoin_supply_flow/gate_trades_AVAXUSDT_h3d.json \
  --label 'p251 stablecoin_supply_flow AVAXUSDT h3d' \
  --lookahead-clean true --edge-after-1bar 0.01142924 \
  --friction 0.0008 --hold-min 4320 --cycle-min 1440 \
  --out runs/research_track/paradigm_251_stablecoin_supply_flow/tier3_gate__AVAXUSDT.json \
  --enqueue --name AVAXUSDT_stablecoin_supply_flow_paper_seed \
  --spec configs/paper_sessions/AVAXUSDT_stablecoin_supply_flow.json \
  --paradigm alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d --symbol AVAXUSDT

echo '=== LINKUSDT ==='
python3 scripts/research/tier3_gate.py \
  --trades runs/research_track/paradigm_251_stablecoin_supply_flow/gate_trades_LINKUSDT_h3d.json \
  --label 'p251 stablecoin_supply_flow LINKUSDT h3d' \
  --lookahead-clean true --edge-after-1bar 0.00818621 \
  --friction 0.0008 --hold-min 4320 --cycle-min 1440 \
  --out runs/research_track/paradigm_251_stablecoin_supply_flow/tier3_gate__LINKUSDT.json \
  --enqueue --name LINKUSDT_stablecoin_supply_flow_paper_seed \
  --spec configs/paper_sessions/LINKUSDT_stablecoin_supply_flow.json \
  --paradigm alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d --symbol LINKUSDT

echo '=== DOGEUSDT ==='
python3 scripts/research/tier3_gate.py \
  --trades runs/research_track/paradigm_251_stablecoin_supply_flow/gate_trades_DOGEUSDT_h3d.json \
  --label 'p251 stablecoin_supply_flow DOGEUSDT h3d' \
  --lookahead-clean true --edge-after-1bar 0.00775910 \
  --friction 0.0008 --hold-min 4320 --cycle-min 1440 \
  --out runs/research_track/paradigm_251_stablecoin_supply_flow/tier3_gate__DOGEUSDT.json \
  --enqueue --name DOGEUSDT_stablecoin_supply_flow_paper_seed \
  --spec configs/paper_sessions/DOGEUSDT_stablecoin_supply_flow.json \
  --paradigm alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d --symbol DOGEUSDT

