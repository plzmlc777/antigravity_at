#!/usr/bin/env python3
"""Manage the ops-monitor authorized_sessions whitelist.

This is the ONLY tool that should write to .claude/authorized_sessions.json.
trade-executor calls it after a USER-AUTHORIZED start/stop. Self-initiated
AI sessions must NOT be added here — that defeats the unauthorized-session
guard.

Usage:
    whitelist_session.py add <session_id> --profile <name> --symbol <sym> \
        --strategy <s> --exchange <ex> [--note <note>]
    whitelist_session.py remove <session_id>
    whitelist_session.py list
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone


def find_whitelist_path() -> str:
    """Locate authorized_sessions.json — try at-asia path first, then local repo."""
    candidates = [
        "/home/hcpark/auto_trading/.claude/authorized_sessions.json",
        "/home/hcpark/antigravity/.claude/authorized_sessions.json",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # default: at-asia path (creates if missing on that host)
    return candidates[0]


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {"version": 1, "updated_at": "", "authorized": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(path: str, data: dict) -> None:
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def cmd_add(args: argparse.Namespace) -> int:
    path = find_whitelist_path()
    data = load(path)
    if any(e.get("session_id") == args.session_id for e in data["authorized"]):
        print(f"already whitelisted: {args.session_id}", file=sys.stderr)
        return 0
    entry = {
        "session_id": args.session_id,
        "profile_name": args.profile or "",
        "symbol": args.symbol or "",
        "strategy": args.strategy or "",
        "exchange": args.exchange or "",
        "owner": args.owner or "user",
        "note": args.note or "",
    }
    data["authorized"].append(entry)
    save(path, data)
    print(f"added: {args.session_id} ({args.profile or args.symbol})")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    path = find_whitelist_path()
    data = load(path)
    before = len(data["authorized"])
    data["authorized"] = [e for e in data["authorized"] if e.get("session_id") != args.session_id]
    if len(data["authorized"]) == before:
        print(f"not found: {args.session_id}", file=sys.stderr)
        return 1
    save(path, data)
    print(f"removed: {args.session_id}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    path = find_whitelist_path()
    data = load(path)
    print(f"# whitelist: {path}")
    print(f"# updated_at: {data.get('updated_at')}")
    print(f"# count: {len(data['authorized'])}")
    for e in data["authorized"]:
        sid = e.get("session_id", "?")
        prof = e.get("profile_name") or "(no profile)"
        sym = e.get("symbol", "?")
        strat = e.get("strategy", "?")
        print(f"  {sid[:8]}  {prof:20s}  {sym:12s}  {strat}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="add a session to the whitelist")
    a.add_argument("session_id")
    a.add_argument("--profile", default="")
    a.add_argument("--symbol", default="")
    a.add_argument("--strategy", default="")
    a.add_argument("--exchange", default="")
    a.add_argument("--owner", default="user")
    a.add_argument("--note", default="")
    a.set_defaults(func=cmd_add)

    r = sub.add_parser("remove", help="remove a session from the whitelist")
    r.add_argument("session_id")
    r.set_defaults(func=cmd_remove)

    l = sub.add_parser("list", help="list whitelisted sessions")
    l.set_defaults(func=cmd_list)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
