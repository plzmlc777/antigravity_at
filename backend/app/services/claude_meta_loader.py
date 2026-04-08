"""Claude meta loader: parses .claude/ agent + skill + decision log files for the API.

Read-only. Provides cached parsing of agent/skill markdown frontmatter, decision log
sections, and strategy candidates.
"""
from __future__ import annotations

import ast
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Project root: backend/app/services/claude_meta_loader.py -> ../../../..
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CLAUDE_DIR = PROJECT_ROOT / ".claude"
AGENTS_DIR = CLAUDE_DIR / "agents"
SKILLS_DIR = CLAUDE_DIR / "skills"
STRATEGY_CANDIDATES_DIR = CLAUDE_DIR / "strategy_candidates"
DECISION_LOG = CLAUDE_DIR / "skills" / "at-strategy" / "references" / "decision_log.md"
META_LEARNINGS = CLAUDE_DIR / "skills" / "at-strategy" / "references" / "meta_learnings.md"
AUTHORIZED_SESSIONS = CLAUDE_DIR / "authorized_sessions.json"
BACKEND_CORE_DIR = PROJECT_ROOT / "backend" / "app" / "core"

# at-* skills are the auto-trading custom skills (others are imports we don't expose).
AT_SKILL_PREFIX = "at-"

# Role classification for agent org chart layout (column placement).
AGENT_ROLE = {
    "cio": "orchestrator",
    "ops-monitor": "assess",
    "market-researcher": "assess",
    "strategy-advisor": "plan",
    "backtest-analyst": "plan",
    "risk-manager": "plan",
    "trade-executor": "execute",
    "signal-synthesizer": "execute",
    "meta-learner": "intelligence",
    "strategy-evolver": "intelligence",
    "self-critic": "intelligence",
    "tech-scout": "intelligence",
    "symbol-evaluator": "utility",
    "symbol-scout": "utility",
    "strategy-builder": "user-facing",
    "stock-searcher": "user-facing",
}

# In-memory cache (TTL 60s) — .claude files change rarely.
_CACHE: Dict[str, Any] = {}
_CACHE_TS: Dict[str, float] = {}
_CACHE_TTL = 60.0


def _cached(key: str, loader):
    now = time.time()
    if key in _CACHE and (now - _CACHE_TS.get(key, 0)) < _CACHE_TTL:
        return _CACHE[key]
    val = loader()
    _CACHE[key] = val
    _CACHE_TS[key] = now
    return val


def _split_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """Parse YAML-ish frontmatter (simple key:value). Returns (front, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    front: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        # multi-line value (continuation)
        if line.startswith(" ") and current_key:
            front[current_key] = (str(front[current_key]) + " " + line.strip()).strip()
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            current_key = k.strip()
            v = v.strip()
            if v == "|" or v == ">":
                front[current_key] = ""
            else:
                front[current_key] = v
    return front, body


def _parse_tools(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(t).strip() for t in value]
    s = str(value).strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return [t.strip() for t in s.split(",") if t.strip()]


def _extract_dispatch_targets(body: str) -> List[str]:
    """Find subagent_type='xxx' references in agent body to build dispatch graph."""
    targets = set()
    for m in re.finditer(r'subagent_type\s*[=:]\s*["\']([^"\']+)["\']', body):
        targets.add(m.group(1))
    return sorted(targets)


@dataclass
class AgentMeta:
    name: str
    description: str
    model: Optional[str]
    tools: List[str]
    role: str
    dispatch_targets: List[str]
    file_path: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_agent_file(path: Path) -> Optional[AgentMeta]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    front, body = _split_frontmatter(text)
    name = front.get("name") or path.stem
    return AgentMeta(
        name=name,
        description=str(front.get("description", "")),
        model=front.get("model"),
        tools=_parse_tools(front.get("tools")),
        role=AGENT_ROLE.get(name, "other"),
        dispatch_targets=_extract_dispatch_targets(body),
        file_path=str(path.relative_to(PROJECT_ROOT)),
    )


def list_agents() -> List[Dict[str, Any]]:
    def _load():
        out: List[Dict[str, Any]] = []
        if not AGENTS_DIR.exists():
            return out
        for p in sorted(AGENTS_DIR.glob("*.md")):
            if p.name.endswith(".deprecated") or p.name == "AGENT_INVOCATION.md":
                continue
            meta = _parse_agent_file(p)
            if meta:
                out.append(meta.to_dict())
        return out
    return _cached("agents", _load)


def get_agent(name: str) -> Optional[Dict[str, Any]]:
    path = AGENTS_DIR / f"{name}.md"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    front, body = _split_frontmatter(text)
    meta = _parse_agent_file(path)
    if not meta:
        return None
    d = meta.to_dict()
    d["body"] = body
    d["raw"] = text
    return d


@dataclass
class SkillMeta:
    name: str
    description: str
    version: Optional[str]
    scripts: List[str]
    file_path: str
    disabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _is_truthy_flag(value: Any) -> bool:
    """Parse frontmatter boolean-ish value (YAML true/false/yes/no/1/0)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in {"true", "yes", "1", "on"}


def _parse_skill_dir(skill_dir: Path) -> Optional[SkillMeta]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        text = skill_md.read_text(encoding="utf-8")
    except Exception:
        return None
    front, _body = _split_frontmatter(text)
    scripts_dir = skill_dir / "scripts"
    scripts = []
    if scripts_dir.is_dir():
        for s in sorted(scripts_dir.iterdir()):
            if s.suffix in {".py", ".sh"}:
                scripts.append(s.name)
    return SkillMeta(
        name=front.get("name") or skill_dir.name,
        description=str(front.get("description", "")),
        version=front.get("version"),
        scripts=scripts,
        file_path=str(skill_md.relative_to(PROJECT_ROOT)),
        disabled=_is_truthy_flag(front.get("disabled")),
    )


def list_skills(include_disabled: bool = False) -> List[Dict[str, Any]]:
    """List at-* skills. Disabled skills (frontmatter `disabled: true`) are
    excluded by default — this is the primary mechanism for risk-manager VETO
    of AI-generated skills (see skill-architect agent)."""
    cache_key = "skills_all" if include_disabled else "skills"

    def _load():
        out: List[Dict[str, Any]] = []
        if not SKILLS_DIR.exists():
            return out
        for d in sorted(SKILLS_DIR.iterdir()):
            if not d.is_dir() or not d.name.startswith(AT_SKILL_PREFIX):
                continue
            meta = _parse_skill_dir(d)
            if not meta:
                continue
            if meta.disabled and not include_disabled:
                continue
            out.append(meta.to_dict())
        return out
    return _cached(cache_key, _load)


def get_skill(name: str) -> Optional[Dict[str, Any]]:
    skill_dir = SKILLS_DIR / name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        text = skill_md.read_text(encoding="utf-8")
    except Exception:
        return None
    front, body = _split_frontmatter(text)
    meta = _parse_skill_dir(skill_dir)
    if not meta:
        return None
    d = meta.to_dict()
    d["body"] = body
    d["raw"] = text
    return d


# Decision log parsing -----------------------------------------------------

_DECISION_HEADER_RE = re.compile(
    r"^##\s*\[(?P<date>\d{4}-\d{2}-\d{2})\]\s*(?P<id>(?:CIO|AUDIT)-\d{8}-\d+)\s*:\s*(?P<title>.+?)\s*$",
    re.MULTILINE,
)


def list_decisions() -> List[Dict[str, Any]]:
    def _load():
        if not DECISION_LOG.exists():
            return []
        text = DECISION_LOG.read_text(encoding="utf-8")
        # split by ## headings matching CIO/AUDIT pattern
        matches = list(_DECISION_HEADER_RE.finditer(text))
        out: List[Dict[str, Any]] = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            decision_id = m.group("id")
            out.append({
                "id": decision_id,
                "date": m.group("date"),
                "title": m.group("title"),
                "kind": "audit" if decision_id.startswith("AUDIT") else "cio",
                "body_preview": body[:400],
            })
        # newest first
        out.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
        return out
    return _cached("decisions", _load)


def get_decision(decision_id: str) -> Optional[Dict[str, Any]]:
    if not DECISION_LOG.exists():
        return None
    text = DECISION_LOG.read_text(encoding="utf-8")
    matches = list(_DECISION_HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group("id") == decision_id:
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return {
                "id": decision_id,
                "date": m.group("date"),
                "title": m.group("title"),
                "kind": "audit" if decision_id.startswith("AUDIT") else "cio",
                "body": text[start:end].strip(),
            }
    return None


# Strategy candidates ------------------------------------------------------

_CAND_FNAME_RE = re.compile(
    r"^(?P<ts>\d{8}T\d{6}Z)_(?P<symbol>[A-Z0-9]+)_(?P<strategy>.+?)(?:_STATUS)?\.(?P<ext>md|txt)$"
)


def list_strategy_candidates() -> List[Dict[str, Any]]:
    def _load():
        if not STRATEGY_CANDIDATES_DIR.exists():
            return []
        # Group by base name (without _STATUS suffix).
        groups: Dict[str, Dict[str, Any]] = {}
        for p in STRATEGY_CANDIDATES_DIR.iterdir():
            if not p.is_file():
                continue
            m = _CAND_FNAME_RE.match(p.name)
            if not m:
                continue
            base = f"{m.group('ts')}_{m.group('symbol')}_{m.group('strategy')}"
            entry = groups.setdefault(base, {
                "id": base,
                "timestamp": m.group("ts"),
                "symbol": m.group("symbol"),
                "strategy": m.group("strategy"),
                "status": "UNKNOWN",
                "doc_filename": None,
                "status_filename": None,
            })
            if p.name.endswith("_STATUS.txt"):
                try:
                    txt = p.read_text(encoding="utf-8").strip()
                    first = txt.splitlines()[0] if txt else "UNKNOWN"
                    entry["status"] = first.strip()
                    entry["status_filename"] = p.name
                except Exception:
                    pass
            elif p.suffix == ".md":
                entry["doc_filename"] = p.name
        out = list(groups.values())
        out.sort(key=lambda x: x["timestamp"], reverse=True)
        return out
    return _cached("strategy_candidates", _load)


def get_strategy_candidate(filename: str) -> Optional[Dict[str, Any]]:
    # Whitelist filename to prevent directory traversal.
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    p = STRATEGY_CANDIDATES_DIR / filename
    if not p.exists() or not p.is_file():
        return None
    try:
        return {"filename": filename, "body": p.read_text(encoding="utf-8")}
    except Exception:
        return None


# Misc helpers -------------------------------------------------------------

def get_meta_learnings() -> Optional[Dict[str, str]]:
    if not META_LEARNINGS.exists():
        return None
    try:
        return {"body": META_LEARNINGS.read_text(encoding="utf-8")}
    except Exception:
        return None


def get_authorized_sessions() -> Optional[Dict[str, Any]]:
    if not AUTHORIZED_SESSIONS.exists():
        return None
    try:
        import json
        return json.loads(AUTHORIZED_SESSIONS.read_text(encoding="utf-8"))
    except Exception:
        return None


# Backend core function introspection ---------------------------------------
# skill-architect needs a machine-readable catalog of pure functions in
# backend/app/core/*.py so it can compose thin-wrapper skills without
# generating new logic. Read-only. AST parsing only — never imports the
# modules (safe against side effects).

# Private modules and files that are not part of the public "building blocks"
# catalog that skill-architect is allowed to reference.
_CORE_EXCLUDE_FILES = {
    "__init__.py",
}


def _format_signature(func: ast.AST) -> str:
    """Render a function signature back to source using ast.unparse (3.9+)."""
    try:
        args_src = ast.unparse(func.args)  # type: ignore[attr-defined]
    except Exception:
        args_src = ""
    ret = ""
    returns = getattr(func, "returns", None)
    if returns is not None:
        try:
            ret = " -> " + ast.unparse(returns)  # type: ignore[attr-defined]
        except Exception:
            ret = ""
    return f"({args_src}){ret}"


def _docstring_first_line(node: ast.AST) -> str:
    doc = ast.get_docstring(node)  # type: ignore[arg-type]
    if not doc:
        return ""
    for line in doc.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def list_core_functions() -> List[Dict[str, Any]]:
    """Enumerate public top-level functions in backend/app/core/*.py.

    Returns a flat list of dicts: module, name, signature, doc, is_async.
    Only `def`/`async def` at module level are included. Private names
    (starting with `_`) are excluded — skill-architect must not rely on
    private helpers.
    """
    def _load():
        out: List[Dict[str, Any]] = []
        if not BACKEND_CORE_DIR.exists():
            return out
        for py in sorted(BACKEND_CORE_DIR.glob("*.py")):
            if py.name in _CORE_EXCLUDE_FILES:
                continue
            try:
                source = py.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py))
            except Exception:
                continue
            module = py.stem
            module_doc = _docstring_first_line(tree)
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                name = node.name
                if name.startswith("_"):
                    continue
                out.append({
                    "module": module,
                    "name": name,
                    "qualname": f"app.core.{module}.{name}",
                    "signature": _format_signature(node),
                    "doc": _docstring_first_line(node),
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "module_doc": module_doc,
                    "lineno": node.lineno,
                })
        return out
    return _cached("core_functions", _load)


def list_agent_activity(since_hours: int = 24) -> List[Dict[str, Any]]:
    """Best-effort agent activity from at-orchestrator runs and logs/cron."""
    out: List[Dict[str, Any]] = []
    runs_dir = CLAUDE_DIR / "skills" / "at-orchestrator" / "runs"
    cutoff = time.time() - since_hours * 3600
    if runs_dir.is_dir():
        for p in sorted(runs_dir.iterdir(), reverse=True):
            try:
                if p.stat().st_mtime < cutoff:
                    continue
                out.append({
                    "source": "at-orchestrator",
                    "timestamp": p.stat().st_mtime,
                    "name": p.name,
                })
            except Exception:
                continue
    cron_dir = PROJECT_ROOT / "logs" / "cron"
    if cron_dir.is_dir():
        for p in sorted(cron_dir.iterdir(), reverse=True)[:50]:
            try:
                if p.stat().st_mtime < cutoff:
                    continue
                out.append({
                    "source": "cron",
                    "timestamp": p.stat().st_mtime,
                    "name": p.name,
                })
            except Exception:
                continue
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out
