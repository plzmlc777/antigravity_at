#!/usr/bin/env bash
# weekly_cycle.sh — Trigger the LEARN→EVOLVE→REFLECT weekly AI cycle.
#
# This script does NOT call agents directly (Claude Code agents must be
# invoked from a Claude Code session). Instead, it prepares a single
# prompt file that the user (or a Claude Code cron) can submit.
#
# Usage:
#   ./weekly_cycle.sh                       # generates prompt to stdout
#   ./weekly_cycle.sh > /tmp/cycle.txt      # save prompt
#   claude -p "$(./weekly_cycle.sh)"        # submit to claude CLI
#
# The generated prompt instructs Claude Code (main conversation) to
# orchestrate the LEARN→EVOLVE→REFLECT workflow per the cio.md template.

set -euo pipefail

API_URL="${API_URL:-http://localhost:8001}"
PROJECT_ROOT="/home/hcpark/antigravity"
WEEK_END="$(date -u +%Y-%m-%d)"
WEEK_START="$(date -u -d '7 days ago' +%Y-%m-%d)"

cat <<EOF
You are running the WEEKLY AI LEARNING CYCLE (learn-evolve-reflect workflow).
Reference: ${PROJECT_ROOT}/.claude/agents/cio.md (Template 5).

Period: ${WEEK_START} ~ ${WEEK_END}
API URL: ${API_URL}

Execute the following sequence using parallel general-purpose Agent dispatches
where independent. Each sub-agent should be invoked by reading its .md spec
from ${PROJECT_ROOT}/.claude/agents/<name>.md (per AGENT_INVOCATION.md pattern).

PHASE 1 — LEARN (parallel where possible):
  1a. Dispatch meta-learner:
      - scope: full
      - focus: all
      - period: last 7 days
      - Must update ${PROJECT_ROOT}/.claude/skills/at-strategy/references/meta_learnings.md
  1b. Dispatch ops-monitor (deep) for current health snapshot

PHASE 2 — EVOLVE (sequential, depends on LEARN):
  For each underperforming strategy identified by meta-learner:
    2a. Dispatch strategy-evolver:
        - base strategy: <from meta-learner>
        - meta-learner insights: <inline from 1a>
        - mode: parameter
    2b. For each "promising" or "recommended" mutation:
        Dispatch risk-manager for approval
    2c. For approved mutations: record in decision_log.md (do NOT auto-execute
        in live trading without explicit user approval)

PHASE 3 — REFLECT (parallel with PHASE 2):
  3a. Dispatch self-critic:
      - decision log: read ${PROJECT_ROOT}/.claude/skills/at-strategy/references/decision_log.md
      - time horizon: 7 days
      - focus: decisions+biases+calibration
      - Must append audit entry to decision_log.md
      - Must populate Improvement Directives Tracker table

PHASE 4 — SYNTHESIZE:
  Produce a single executive summary in Korean covering:
  - LEARN: key patterns discovered
  - EVOLVE: mutations tested, recommendations
  - REFLECT: bias findings, improvement directives
  - Health score trend
  - Recommended user actions

Output the executive summary as the FINAL response.

CRITICAL: This is a real run that updates knowledge files on disk.
Do NOT execute any live trading actions. All EVOLVE recommendations
require human review before live deployment.
EOF
