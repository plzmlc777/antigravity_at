"""Workflow Execution Aggregation API — CIO-20260408-016 (Level 2 live dashboard).

Provides a single endpoint that aggregates SAS + gap_signal execution activity
across the last N days, returning per-node statistics and recent timeline events.

Data sources (read-only, no writes):
- gap_signals table    — agent-emitted capability gap signals
- strategy_audition    — strategy lifecycle transitions
- (future) agent_invocations — detailed per-dispatch ledger, not yet wired

The frontend Workflow.jsx view overlays these stats on top of a hardcoded
node graph representing the SAS pipeline.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.gap_signal import GapSignal
from ..models.strategy_audition import StrategyAudition

router = APIRouter()


def _iso(dt):
    return dt.isoformat() if dt else None


@router.get("/executions/recent")
def recent_executions(
    days: int = Query(7, ge=1, le=90, description="Lookback window in days"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Aggregate SAS + gap_signal execution activity over the last N days.

    Returns a structure keyed by the logical nodes/edges used by the
    frontend Workflow.jsx visualization so the view can render counts,
    last-run timestamps, and a recent timeline without additional queries.
    """
    now = datetime.utcnow()
    since = now - timedelta(days=days)

    # -----------------------------------------------------------------
    # Pull raw rows
    # -----------------------------------------------------------------
    gaps: List[GapSignal] = (
        db.query(GapSignal)
        .filter(GapSignal.created_at >= since)
        .order_by(GapSignal.created_at.desc())
        .limit(200)
        .all()
    )
    auditions: List[StrategyAudition] = (
        db.query(StrategyAudition)
        .filter(StrategyAudition.created_at >= since)
        .order_by(StrategyAudition.created_at.desc())
        .limit(200)
        .all()
    )

    # -----------------------------------------------------------------
    # Per-node statistics (counts + last run + status breakdown)
    # -----------------------------------------------------------------
    node_stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "last_run_at": None,
            "last_status": None,
            "status_counts": defaultdict(int),
        }
    )

    def touch(node_id: str, when: datetime, status: str):
        ns = node_stats[node_id]
        ns["count"] += 1
        ns["status_counts"][status] += 1
        if ns["last_run_at"] is None or (when and when > ns["last_run_at"]):
            ns["last_run_at"] = when
            ns["last_status"] = status

    # gap_signals → emitter + router + consumer nodes
    for g in gaps:
        emit_status = "success"  # signal was successfully recorded
        emitter_node = {
            "meta-learner": "meta-learner",
            "self-critic": "self-critic",
            "cio": "cio",
            "audition-judge": "audition-judge",
        }.get(g.source, g.source or "unknown-emitter")
        touch(emitter_node, g.created_at, emit_status)
        touch("gap-signals-db", g.created_at, emit_status)

        # Consumer inference from proposed_intent.family
        family = (g.proposed_intent or {}).get("family") if isinstance(g.proposed_intent, dict) else None
        if family:
            if family == "strategy":
                consumer = "strategy-builder"
            elif isinstance(family, str) and family.startswith("at-"):
                consumer = "skill-architect"
            else:
                consumer = None
            if consumer and g.status in ("consumed", "rejected", "failed"):
                touch(
                    "main-turn",
                    g.consumed_at or g.created_at,
                    g.status,
                )
                touch(
                    consumer,
                    g.consumed_at or g.created_at,
                    "success" if g.status == "consumed" else g.status,
                )

    # strategy_audition → strategy-builder + audition-judge + graveyard
    for a in auditions:
        touch("strategy-builder", a.created_at, "success")
        touch("strategies-dir", a.created_at, "success")
        touch("audition-db", a.created_at, "success")

        if a.status == "graduated":
            touch("audition-judge", a.judged_at or a.created_at, "winner")
        elif a.status == "eliminated":
            touch("audition-judge", a.judged_at or a.created_at, "eliminated")
            touch("graveyard", a.judged_at or a.created_at, "moved")
        elif a.status == "error":
            touch("audition-judge", a.judged_at or a.created_at, "error")
        elif a.status == "resurrected":
            touch("monthly-resurrect", a.last_resurrected_at or a.created_at, "resurrected")

    # Normalize defaultdicts → regular dicts for JSON
    node_stats_out: Dict[str, Dict[str, Any]] = {}
    for node_id, ns in node_stats.items():
        node_stats_out[node_id] = {
            "count": ns["count"],
            "last_run_at": _iso(ns["last_run_at"]),
            "last_status": ns["last_status"],
            "status_counts": dict(ns["status_counts"]),
        }

    # -----------------------------------------------------------------
    # Edge flow counts — "how many times data flowed on this edge"
    # -----------------------------------------------------------------
    edge_flow: Dict[str, int] = defaultdict(int)
    for g in gaps:
        emitter = {
            "meta-learner": "meta-learner",
            "self-critic": "self-critic",
            "cio": "cio",
            "audition-judge": "audition-judge",
        }.get(g.source, g.source or "unknown-emitter")
        edge_flow[f"{emitter}->gap-signals-db"] += 1

        family = (g.proposed_intent or {}).get("family") if isinstance(g.proposed_intent, dict) else None
        if g.status == "consumed":
            edge_flow["gap-signals-db->main-turn"] += 1
            if family == "strategy":
                edge_flow["main-turn->strategy-builder"] += 1
            elif isinstance(family, str) and family.startswith("at-"):
                edge_flow["main-turn->skill-architect"] += 1

    for a in auditions:
        edge_flow["strategy-builder->strategies-dir"] += 1
        edge_flow["strategy-builder->audition-db"] += 1
        if a.status == "graduated":
            edge_flow["audition-judge->audition-db"] += 1
        elif a.status == "eliminated":
            edge_flow["audition-judge->audition-db"] += 1
            edge_flow["audition-judge->graveyard"] += 1
        elif a.status == "resurrected":
            edge_flow["monthly-resurrect->audition-db"] += 1

    # -----------------------------------------------------------------
    # Recent timeline (latest 30 events, merged + sorted desc)
    # -----------------------------------------------------------------
    timeline: List[Dict[str, Any]] = []
    for g in gaps[:30]:
        timeline.append({
            "type": "gap_signal",
            "timestamp": _iso(g.created_at),
            "node": g.source or "unknown-emitter",
            "status": g.status,
            "label": f"gap_signal emit: {g.signal_id}",
            "ref_id": g.signal_id,
        })
        if g.consumed_at:
            timeline.append({
                "type": "gap_signal_consumed",
                "timestamp": _iso(g.consumed_at),
                "node": "main-turn",
                "status": g.status,
                "label": f"gap_signal {g.status}: {g.signal_id}",
                "ref_id": g.signal_id,
            })
    for a in auditions[:30]:
        timeline.append({
            "type": "audition_created",
            "timestamp": _iso(a.created_at),
            "node": "strategy-builder",
            "status": "created",
            "label": f"audition created: {a.strategy_id} ({a.category})",
            "ref_id": a.strategy_id,
        })
        if a.judged_at:
            timeline.append({
                "type": "audition_judged",
                "timestamp": _iso(a.judged_at),
                "node": "audition-judge",
                "status": a.status,
                "label": f"audition {a.status}: {a.strategy_id} rank={a.rank_in_week}",
                "ref_id": a.strategy_id,
            })

    timeline.sort(key=lambda e: e["timestamp"] or "", reverse=True)
    timeline = timeline[:50]

    return {
        "time_range": {
            "from": _iso(since),
            "to": _iso(now),
            "days": days,
        },
        "totals": {
            "gap_signals_in_window": len(gaps),
            "auditions_in_window": len(auditions),
        },
        "node_stats": node_stats_out,
        "edge_flow": dict(edge_flow),
        "timeline": timeline,
    }
