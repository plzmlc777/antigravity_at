"""스윕 산출물 표준 형식 — 기록기이자 명세.

왜 표준이 필요한가
    `runs/research_track/` 의 스윕 JSON 이 파일마다 형태가 달라서, 축·지표를
    읽는 규칙이 소비자마다 따로 생긴다. 설계 문서
    `.claude/plans/param_sweep_heatmap_component.md` §12 의 미결 사항이었다.

    더 중요한 건 **출처 필드가 없다**는 것이다. 같은 문서 §9:

        우리는 lookahead 구간 산출물을 무효 처리한 전례가 있다. 히트맵은 숫자를
        설득력 있게 만드는 도구라, 출처 표시 없이 렌더하면 **무효 데이터를
        세탁한다.** … **IS 전용 스윕의 히트맵은 장식이다.**

    2026-08-14 에 그 말이 증명됐다. 익절 20칸 격자에서 IS 최고였던
    `d7@tp50/w3`(1338%p, t 2.19)이 표본 밖에서 **-11.4%p** 로 부호가 뒤집혔다.
    분할을 안 붙였으면 그대로 채택했을 것이다.

⚠ `split` 은 **필수**다
    MT5 Strategy Tester 가 Forward 기간을 최적화 UI 에 내장한 이유와 같다 —
    표본 밖 선언 없이는 최적화를 시작할 수 없어야 한다. 선택 사항이면 안 붙인다.

형식
    {
      "schema_version": 1,
      "engine": "canon_kernel",
      "script": "scripts/research/...",
      "commit": "<산출 시점 HEAD>",          # 머신별 값
      "generated_at": "...",
      "data_window": {"start": ..., "end": ...},
      "split": {"date": "2026-05-13", "is_events": 241, "oos_events": 10},
      "axes":    {"sl": [...], "tp": [...], "window": [...], "variant": [...]},
      "metrics": ["total_ret", "mean", "t", "win", "worst", "n_trades", ...],
      "results": [ {<축 키...>, <지표 키...>, "split": "IS"|"OOS"|"ALL"}, ... ]
    }

    `results` 는 **평평한 레코드 배열**이다. 설계 §3 의 스키마 추론이 그대로
    돈다 — 축은 고유값 2~16 개, 지표는 실수형 다양값.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1


def commit_here(root: Path) -> str | None:
    """산출 시점 HEAD. **머신별 값**이다 — 민트는 별도 미러 이력을 갖는다."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
            stderr=subprocess.DEVNULL, timeout=10).decode().strip()
    except Exception:
        return None


class SweepWriter:
    """표준 스윕 결과를 모으고 검증해 쓴다.

    `split_date` 없이 만들 수 없다 — 생성자에서 막는다.
    """

    def __init__(self, *, script: str, engine: str, root: Path,
                 split_date: str, axes: dict[str, list],
                 data_window: dict | None = None, notes: str = "") -> None:
        if not split_date:
            raise ValueError(
                "split_date 는 필수다. 표본 밖 선언 없는 최적화는 과최적화 기계다 "
                "(설계 §9). 분할일을 정할 수 없으면 스윕을 돌리지 마라.")
        self.meta = {
            "schema_version": SCHEMA_VERSION,
            "engine": engine,
            "script": script,
            "commit": commit_here(root),
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "data_window": data_window or {},
            "split": {"date": split_date},
            "axes": {k: list(v) for k, v in axes.items()},
            "notes": notes,
        }
        self.results: list[dict] = []

    def add(self, *, axis_values: dict[str, Any], metrics: dict[str, Any],
            split: str) -> None:
        if split not in ("IS", "OOS", "ALL"):
            raise ValueError(f"split 은 IS/OOS/ALL 이어야 한다: {split!r}")
        unknown = set(axis_values) - set(self.meta["axes"])
        if unknown:
            raise ValueError(f"선언하지 않은 축: {sorted(unknown)}")
        self.results.append({**axis_values, **_clean(metrics), "split": split})

    def write(self, path: str | Path) -> dict:
        metrics: set[str] = set()
        for r in self.results:
            metrics |= {k for k, v in r.items()
                        if k not in self.meta["axes"] and k != "split"
                        and isinstance(v, (int, float))}
        counts = {s: sum(1 for r in self.results if r["split"] == s)
                  for s in ("IS", "OOS", "ALL")}
        self.meta["split"].update({f"{k.lower()}_cells": v
                                   for k, v in counts.items() if v})
        out = {**self.meta, "metrics": sorted(metrics), "results": self.results}
        Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=2))
        return out


def _clean(o):
    """NaN/Infinity → None. PostgreSQL JSONB 도 프론트 JSON.parse 도 받지 않는다."""
    import math
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def validate(path: str | Path) -> list[str]:
    """표준 위반을 목록으로. 빈 목록이면 통과."""
    problems: list[str] = []
    try:
        d = json.loads(Path(path).read_text())
    except Exception as exc:
        return [f"읽기 실패: {exc}"]

    if d.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version 불일치: {d.get('schema_version')}")
    for k in ("engine", "script", "axes", "metrics", "results"):
        if k not in d:
            problems.append(f"필수 키 없음: {k}")
    sp = d.get("split") or {}
    if not sp.get("date"):
        problems.append("split.date 없음 — 표본 밖 선언이 필수다 (설계 §9)")
    if not sp.get("oos_cells"):
        problems.append("표본 밖 셀 0 — IS 전용 스윕은 장식이다 (설계 §9)")
    if not d.get("commit"):
        problems.append("commit 없음 — 어느 코드가 낸 수치인지 알 수 없다")
    if not (d.get("data_window") or {}).get("start"):
        problems.append("data_window 미기재")
    axes = d.get("axes") or {}
    if len(axes) < 1:
        problems.append("축이 없다")
    for r in d.get("results") or []:
        if r.get("split") not in ("IS", "OOS", "ALL"):
            problems.append("split 라벨 없는 레코드 존재")
            break
    return problems


def iter_cells(d: dict, split: str = "IS") -> Iterable[dict]:
    for r in d.get("results") or []:
        if r.get("split") == split:
            yield r
