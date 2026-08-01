#!/usr/bin/env python3
"""
미국 트랙 가설 큐 — 수동 추가/조회/상태전이 CLI.

왜 별도 큐인가:
    바이낸스 3군은 `paradigm-dispatch-daily` 가 queue.json 에서 하루 1건씩 꺼내
    자동 발굴한다. 미국 트랙은 (a) 아직 자동 디스패치가 없고, (b) 축이 검증되지
    않아 자동화보다 사람이 축을 골라 넣는 편이 낫다. 대표님 지시(2026-08-01):
    "하루 한 개 추가 형식이 아니라 수동으로 계속 추가할 수 있어야 한다".

    따라서 이 큐는 **대량 수동 등록 + 우선순위 기반 수동 소비**를 전제로 한다.
    나중에 자동 디스패치를 붙일 때도 같은 파일을 그대로 읽으면 된다.

상태 전이:
    pending → in_progress → {r0_halt | graveyard | r1_pass | ... | promoted}

필드:
    id            자동 부여 (us-001 …)
    title         한 줄 요약
    hypothesis    검증할 내용 (R-0 프리스크린이 읽을 수준으로 구체적으로)
    source        출처 (커뮤니티/논문/자체 발상)
    axis_class    축 분류 — 중복 발의 차단용
    data_deps     필요한 데이터. 미확보면 먼저 substrate 작업
    constraints   이 가설이 우리 제약에 걸리는 지점 (미리 적어두면 R-0 이 빨라짐)
    priority      1(높음)~5
    status        위 전이표
    notes         자유 기술

사용:
  python -m scripts.us_hypothesis_queue list [--status pending]
  python -m scripts.us_hypothesis_queue add --title "..." --hypothesis "..." \
      --source "r/LETFs" --axis-class letf_trend_timing --priority 1
  python -m scripts.us_hypothesis_queue add-bulk seeds.json
  python -m scripts.us_hypothesis_queue show us-003
  python -m scripts.us_hypothesis_queue set-status us-003 graveyard --note "R-1 0/12"
  python -m scripts.us_hypothesis_queue next          # 우선순위 최상위 pending 1건
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

QUEUE_PATH = BACKEND_DIR / "configs" / "us_hypothesis_queue.json"

STATUSES = ("pending", "in_progress", "r0_halt", "graveyard",
            "r1_pass", "r2_pass", "r4_pass", "promoted", "shelved")


def load() -> dict:
    if QUEUE_PATH.exists():
        return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    return {"queue": [], "updated_at": None}


def save(data: dict) -> None:
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def next_id(data: dict) -> str:
    n = 0
    for e in data["queue"]:
        try:
            n = max(n, int(str(e.get("id", "us-0")).split("-")[-1]))
        except ValueError:
            continue
    return f"us-{n + 1:03d}"


def add_entry(data: dict, rec: dict) -> dict:
    dup = [e for e in data["queue"]
           if e.get("axis_class") and e["axis_class"] == rec.get("axis_class")]
    entry = {
        "id": next_id(data),
        "title": rec["title"],
        "hypothesis": rec["hypothesis"],
        "source": rec.get("source", ""),
        "axis_class": rec.get("axis_class", ""),
        "data_deps": rec.get("data_deps", []),
        "constraints": rec.get("constraints", []),
        "priority": int(rec.get("priority", 3)),
        "status": "pending",
        "added_at": datetime.now().isoformat(timespec="seconds"),
        "notes": rec.get("notes", ""),
    }
    if dup:
        entry["notes"] = (entry["notes"] + f" [주의: axis_class 중복 — {', '.join(d['id'] for d in dup)}]").strip()
    data["queue"].append(entry)
    return entry


def cmd_list(args) -> int:
    data = load()
    rows = data["queue"]
    if args.status:
        rows = [e for e in rows if e["status"] == args.status]
    rows.sort(key=lambda e: (e["priority"], e["id"]))
    if not rows:
        print("(비어 있음)")
        return 0
    print(f"{'ID':7} {'P':2} {'상태':12} {'축분류':24} 제목")
    for e in rows:
        print(f"{e['id']:7} {e['priority']:<2} {e['status']:12} "
              f"{(e['axis_class'] or '—')[:24]:24} {e['title'][:56]}")
    counts = {}
    for e in data["queue"]:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"\n총 {len(data['queue'])}건 — " +
          " / ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


def cmd_show(args) -> int:
    data = load()
    e = next((x for x in data["queue"] if x["id"] == args.id), None)
    if not e:
        print(f"없음: {args.id}")
        return 1
    print(json.dumps(e, ensure_ascii=False, indent=1))
    return 0


def cmd_add(args) -> int:
    data = load()
    e = add_entry(data, {
        "title": args.title, "hypothesis": args.hypothesis,
        "source": args.source, "axis_class": args.axis_class,
        "data_deps": args.data_deps.split(",") if args.data_deps else [],
        "constraints": args.constraints.split("|") if args.constraints else [],
        "priority": args.priority, "notes": args.notes or "",
    })
    save(data)
    print(f"추가: {e['id']} {e['title']}")
    if "주의" in e["notes"]:
        print(f"  {e['notes']}")
    return 0


def cmd_add_bulk(args) -> int:
    data = load()
    recs = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if isinstance(recs, dict):
        recs = recs.get("queue", [])
    for r in recs:
        e = add_entry(data, r)
        print(f"추가: {e['id']} [P{e['priority']}] {e['title']}")
    save(data)
    print(f"\n총 {len(recs)}건 추가 (큐 {len(data['queue'])}건)")
    return 0


def cmd_set_status(args) -> int:
    data = load()
    e = next((x for x in data["queue"] if x["id"] == args.id), None)
    if not e:
        print(f"없음: {args.id}")
        return 1
    if args.status not in STATUSES:
        print(f"상태는 {STATUSES} 중 하나여야 합니다")
        return 1
    old = e["status"]
    e["status"] = args.status
    e[f"{args.status}_at"] = datetime.now().isoformat(timespec="seconds")
    if args.note:
        e["notes"] = (e.get("notes", "") + f" | {args.status}: {args.note}").strip(" |")
    save(data)
    print(f"{args.id}: {old} → {args.status}")
    return 0


def cmd_next(args) -> int:
    data = load()
    pend = [e for e in data["queue"] if e["status"] == "pending"]
    if not pend:
        print("pending 없음")
        return 1
    pend.sort(key=lambda e: (e["priority"], e["id"]))
    print(json.dumps(pend[0], ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="미국 트랙 가설 큐")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list"); p.add_argument("--status"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("id"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("next"); p.set_defaults(fn=cmd_next)

    p = sub.add_parser("add")
    p.add_argument("--title", required=True)
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--source", default="")
    p.add_argument("--axis-class", dest="axis_class", default="")
    p.add_argument("--data-deps", dest="data_deps", default="")
    p.add_argument("--constraints", default="", help="| 로 구분")
    p.add_argument("--priority", type=int, default=3)
    p.add_argument("--notes", default="")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("add-bulk"); p.add_argument("file"); p.set_defaults(fn=cmd_add_bulk)

    p = sub.add_parser("set-status")
    p.add_argument("id"); p.add_argument("status"); p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_set_status)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
