"""Paradigm state registry CLI.

Manages backend/runs/research_track/INDEX.json — single source of truth for
every paradigm's research-track state.

Schema per entry:
{
  "name": "lifecycle_pump_decay",
  "hypothesis": "Newly listed Binance perpetuals decay 20-30% in first 30 days...",
  "data_dependencies": ["ohlcv 1m all USDT perps", "listing_dates.json"],
  "current_phase": "R-3" | "R-1" | "graveyard" | "R-5_seeded" | ...,
  "metrics_files": {
     "R-1": "backend/runs/research_track/lifecycle_phase/poc__metrics.json",
     "R-2": "backend/runs/research_track/lifecycle_phase/r2__metrics.json",
     "R-3": "backend/runs/research_track/lifecycle_phase/r3__metrics.json"
  },
  "gate_evals": {
     "R-2": "backend/runs/research_track/lifecycle_phase/gate_eval__lifecycle_phase.md"
  },
  "type": "E" | "T",
  "created_at": "...", "updated_at": "...",
  "graveyard_reason": null | "...",
  "seed_spec": null | "backend/configs/paper_sessions/lifecycle_pump_decay.json"
}

Commands:
  list                                  — show all paradigms + phase
  show <name>                           — full record
  register <name> --hypothesis "..."    — new R-1 entry
  promote <name> --to-phase R-2 --metrics <path> [--type T|E]
  graveyard <name> --reason "..."
  attach-gate <name> --phase R-3 --path <gate_eval.md>

INDEX_PATH: backend/runs/research_track/INDEX.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "runs" / "research_track" / "INDEX.json"

VALID_PHASES = {"R-1", "R-2", "R-3", "R-4", "R-5_seeded", "graveyard"}


def load_index() -> dict:
    if not INDEX_PATH.exists():
        return {"paradigms": {}, "schema_version": 1}
    return json.loads(INDEX_PATH.read_text())


def save_index(idx: dict) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    idx["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    INDEX_PATH.write_text(json.dumps(idx, indent=2, sort_keys=False, ensure_ascii=False))


def cmd_list(args, idx: dict) -> int:
    paradigms = idx.get("paradigms", {})
    if not paradigms:
        print("(empty registry)")
        return 0
    rows = []
    for name, p in paradigms.items():
        rows.append((name, p.get("current_phase", "-"),
                     p.get("type", "?"),
                     p.get("created_at", "")[:10],
                     p.get("updated_at", "")[:10]))
    rows.sort(key=lambda r: (r[1], r[0]))
    print(f"{'name':28s} {'phase':14s} {'type':4s} {'created':10s} {'updated':10s}")
    print("-" * 70)
    for r in rows:
        print(f"{r[0]:28s} {r[1]:14s} {r[2]:4s} {r[3]:10s} {r[4]:10s}")
    return 0


def cmd_show(args, idx: dict) -> int:
    p = idx.get("paradigms", {}).get(args.name)
    if not p:
        print(f"paradigm '{args.name}' not found")
        return 1
    print(json.dumps(p, indent=2, ensure_ascii=False))
    return 0


def cmd_register(args, idx: dict) -> int:
    if args.name in idx.get("paradigms", {}):
        print(f"paradigm '{args.name}' already exists (use promote/graveyard)")
        return 1
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    idx.setdefault("paradigms", {})[args.name] = {
        "name": args.name,
        "hypothesis": args.hypothesis,
        "data_dependencies": args.data_deps.split(",") if args.data_deps else [],
        "current_phase": "R-1",
        "metrics_files": {},
        "gate_evals": {},
        "type": args.type,
        "created_at": now,
        "updated_at": now,
        "graveyard_reason": None,
        "seed_spec": None,
    }
    save_index(idx)
    print(f"registered '{args.name}' at R-1")
    return 0


def cmd_promote(args, idx: dict) -> int:
    paradigm = idx.get("paradigms", {}).get(args.name)
    if not paradigm:
        print(f"paradigm '{args.name}' not found")
        return 1
    if args.to_phase not in VALID_PHASES:
        print(f"invalid phase '{args.to_phase}', valid: {VALID_PHASES}")
        return 1
    paradigm["current_phase"] = args.to_phase
    if args.metrics:
        paradigm.setdefault("metrics_files", {})[args.to_phase] = args.metrics
    if args.type:
        paradigm["type"] = args.type
    paradigm["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_index(idx)
    print(f"promoted '{args.name}' → {args.to_phase}")
    return 0


def cmd_graveyard(args, idx: dict) -> int:
    paradigm = idx.get("paradigms", {}).get(args.name)
    if not paradigm:
        print(f"paradigm '{args.name}' not found")
        return 1
    paradigm["current_phase"] = "graveyard"
    paradigm["graveyard_reason"] = args.reason
    paradigm["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_index(idx)
    print(f"graveyard '{args.name}' — {args.reason}")
    return 0


def cmd_attach_gate(args, idx: dict) -> int:
    paradigm = idx.get("paradigms", {}).get(args.name)
    if not paradigm:
        print(f"paradigm '{args.name}' not found")
        return 1
    paradigm.setdefault("gate_evals", {})[args.phase] = args.path
    paradigm["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_index(idx)
    print(f"attached gate '{args.name}' phase={args.phase} → {args.path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    sp = sub.add_parser("show"); sp.add_argument("name")

    sp = sub.add_parser("register")
    sp.add_argument("name")
    sp.add_argument("--hypothesis", required=True)
    sp.add_argument("--data-deps", default="")
    sp.add_argument("--type", choices=["T", "E"], default=None)

    sp = sub.add_parser("promote")
    sp.add_argument("name")
    sp.add_argument("--to-phase", required=True)
    sp.add_argument("--metrics", default=None)
    sp.add_argument("--type", choices=["T", "E"], default=None)

    sp = sub.add_parser("graveyard")
    sp.add_argument("name")
    sp.add_argument("--reason", required=True)

    sp = sub.add_parser("attach-gate")
    sp.add_argument("name")
    sp.add_argument("--phase", required=True)
    sp.add_argument("--path", required=True)

    args = p.parse_args()
    idx = load_index()
    if args.cmd == "list":
        return cmd_list(args, idx)
    if args.cmd == "show":
        return cmd_show(args, idx)
    if args.cmd == "register":
        return cmd_register(args, idx)
    if args.cmd == "promote":
        return cmd_promote(args, idx)
    if args.cmd == "graveyard":
        return cmd_graveyard(args, idx)
    if args.cmd == "attach-gate":
        return cmd_attach_gate(args, idx)
    return 1


if __name__ == "__main__":
    sys.exit(main())
