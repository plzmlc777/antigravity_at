"""Agents/Skills/Decisions metadata API.

Read-only endpoints exposing .claude/ contents (agent definitions, skill definitions,
decision log entries, strategy candidates, meta-learnings) to the frontend Mission
Control + Org Chart pages.

All endpoints are read-only and serve project metadata (no user data, no secrets),
mirroring the no-auth policy of /api/v1/live/monitor/*.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..services import claude_meta_loader as loader

router = APIRouter()


# --- Agents -------------------------------------------------------------
@router.get("/agents")
def list_agents() -> List[Dict[str, Any]]:
    return loader.list_agents()


@router.get("/agents/activity")
def agent_activity(since_hours: int = Query(24, ge=1, le=168)) -> List[Dict[str, Any]]:
    return loader.list_agent_activity(since_hours=since_hours)


@router.get("/agents/{name}")
def get_agent(name: str) -> Dict[str, Any]:
    data = loader.get_agent(name)
    if not data:
        raise HTTPException(status_code=404, detail=f"agent '{name}' not found")
    return data


# --- Skills -------------------------------------------------------------
@router.get("/skills")
def list_skills() -> List[Dict[str, Any]]:
    return loader.list_skills()


@router.get("/skills/{name}")
def get_skill(name: str) -> Dict[str, Any]:
    data = loader.get_skill(name)
    if not data:
        raise HTTPException(status_code=404, detail=f"skill '{name}' not found")
    return data


# --- Decisions ----------------------------------------------------------
@router.get("/decisions")
def list_decisions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    kind: Optional[str] = Query(None, description="cio | audit"),
) -> Dict[str, Any]:
    items = loader.list_decisions()
    if kind in {"cio", "audit"}:
        items = [d for d in items if d["kind"] == kind]
    total = len(items)
    page = items[offset : offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "items": page}


@router.get("/decisions/{decision_id}")
def get_decision(decision_id: str) -> Dict[str, Any]:
    data = loader.get_decision(decision_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"decision '{decision_id}' not found")
    return data


# --- Strategy Candidates ------------------------------------------------
@router.get("/strategy-candidates")
def list_strategy_candidates() -> List[Dict[str, Any]]:
    return loader.list_strategy_candidates()


@router.get("/strategy-candidates/{filename}")
def get_strategy_candidate(filename: str) -> Dict[str, Any]:
    data = loader.get_strategy_candidate(filename)
    if not data:
        raise HTTPException(status_code=404, detail=f"candidate '{filename}' not found")
    return data


# --- Meta Learnings + Authorized Sessions -------------------------------
@router.get("/meta-learnings")
def get_meta_learnings() -> Dict[str, Any]:
    data = loader.get_meta_learnings()
    if not data:
        raise HTTPException(status_code=404, detail="meta_learnings.md not found")
    return data


@router.get("/whitelist/sessions")
def get_authorized_sessions() -> Dict[str, Any]:
    data = loader.get_authorized_sessions()
    if data is None:
        raise HTTPException(status_code=404, detail="authorized_sessions.json not found")
    return {"sessions": data}


# --- Backend Core Introspection (skill-architect building blocks) -------
# Read-only catalog of public pure functions in backend/app/core/*.py.
# Consumed by skill-architect to enforce Reuse Before Create (D-018) and
# to inform the thin-wrapper skill generation pattern.
@router.get("/backend-core/functions")
def list_backend_core_functions(
    module: Optional[str] = Query(None, description="Filter by module name, e.g. 'position_math'"),
) -> Dict[str, Any]:
    items = loader.list_core_functions()
    if module:
        items = [f for f in items if f["module"] == module]
    modules = sorted({f["module"] for f in items})
    return {
        "total": len(items),
        "modules": modules,
        "functions": items,
    }
