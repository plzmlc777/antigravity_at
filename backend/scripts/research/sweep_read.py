"""스윕 JSON 읽기 — 스키마 추론 + 출처 검사.

설계 `.claude/plans/param_sweep_heatmap_component.md` §3(추론) · §4(지표 레지스트리)
· §9(출처 게이트)

**표준 파일과 구형 파일을 함께 읽는다.**
    `sweep_format.SweepWriter` 가 낸 것은 축·지표·출처가 선언돼 있다. 그 이전
    파일(실측 7건)은 아무것도 없다. 소급해 채우지 않는다 — 7건 중 6건이
    2026-08-11 에 종결된 초단타 리그 산출물이라 채울 값이 없다.

    대신 **읽는 쪽이 결손을 크게 말한다.** §9:

        히트맵은 숫자를 **설득력 있게** 만드는 도구라, 출처 표시 없이 렌더하면
        **무효 데이터를 세탁한다.** … IS 전용 스윕의 히트맵은 장식이다.

추론 규칙 (§3)
    제외    값이 dict/list           → `reasons` 같은 중첩
    축      고유값 2~16 개
    지표    실수형 AND 고유값 > 레코드 수 × 0.5
    축 후보 2 미만이면 히트맵 불가로 표시한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MAX_AXIS_CARD = 16
MIN_AXIS_CARD = 2

# ── 지표 레지스트리 (§4) — 이름은 파일마다 달라도 의미는 몇 가지뿐 ──────────
METRIC_KINDS = [
    ("signed",  r"^(mean|net|total|per_cycle|diff|worst|best)", "발산", "높을수록"),
    ("tstat",   r"^t$|_t$", "발산", "높을수록"),
    ("ratio",   r"^(win|pos_pct)", "순차", "높을수록"),
    ("risk",    r"^(ruin|sd|se|std|mdd|drawdown)", "순차", "**낮을수록**"),
    ("count",   r"^(n$|n_|trades|cycles|fills|events)", "순차", "중립"),
]


def metric_kind(name: str) -> dict:
    for kind, pat, ramp, polarity in METRIC_KINDS:
        if re.search(pat, name):
            return {"kind": kind, "ramp": ramp, "polarity": polarity}
    # 미등록 — 부호 있으면 발산, 아니면 순차. 극성은 미상 (§4)
    return {"kind": "unknown", "ramp": "발산", "polarity": "미상"}


def _records(d: Any) -> list[dict]:
    if isinstance(d, dict):
        r = d.get("results")
        if isinstance(r, list) and r and isinstance(r[0], dict):
            return r
    return []


def infer(path: str | Path) -> dict:
    """축·지표 추론 + 출처 판정. 히트맵 API 가 그대로 쓴다."""
    p = Path(path)
    d = json.loads(p.read_text())
    recs = _records(d)
    if not recs:
        return {"ok": False, "reason": "results 레코드 배열이 없다"}

    scalar_keys, card = [], {}
    for k in recs[0]:
        vals = [r.get(k) for r in recs]
        if any(isinstance(v, (dict, list)) for v in vals):
            continue                      # 중첩 제외 (§3)
        scalar_keys.append(k)
        card[k] = len({json.dumps(v, sort_keys=True, default=str) for v in vals})

    n = len(recs)
    axes, metrics = [], []
    for k in scalar_keys:
        if k == "split":
            continue                      # 표준 라벨은 축이 아니다
        c = card[k]
        is_num = all(isinstance(r.get(k), (int, float)) or r.get(k) is None
                     for r in recs)
        if MIN_AXIS_CARD <= c <= MAX_AXIS_CARD:
            axes.append(k)
        if is_num and c > n * 0.5:
            metrics.append(k)

    # 선언된 축이 있으면 그것이 권위다 — 추론은 기본값이지 강제가 아니다 (§3)
    declared = list((d.get("axes") or {}).keys())
    if declared:
        axes = declared
        metrics = [m for m in metrics if m not in declared]

    # ── 출처 (§9) ──────────────────────────────────────────────────────
    sp, dw = d.get("split") or {}, d.get("data_window") or {}
    warnings = []
    if not sp.get("date"):
        warnings.append("IS/OOS 구분 불명 — **IS 전용 스윕의 히트맵은 장식이다**")
    if not dw.get("start"):
        warnings.append("데이터 구간 미기재")
    if not d.get("commit"):
        warnings.append("산출 커밋 미기재 — 어느 코드가 낸 수치인지 알 수 없다")
    if d.get("schema_version") is None:
        warnings.append("구형 형식 — sweep_format 표준 이전 산출물")

    complete = None
    if axes:
        prod = 1
        for k in axes:
            prod *= card.get(k, 1)
        complete = (prod == n) or (prod * 2 == n)   # ×2 는 IS/OOS 두 벌

    return {
        "ok": len(axes) >= 2 and bool(metrics),
        "reason": ("" if len(axes) >= 2 else "축 후보가 2개 미만 — 히트맵 불가")
                  or ("" if metrics else "지표 후보 없음"),
        "file": p.name,
        "mtime": p.stat().st_mtime,
        "n_records": n,
        "axes": {k: sorted({r.get(k) for r in recs}, key=lambda x: (x is None, str(x)))
                 for k in axes},
        "metrics": [{"name": m, **metric_kind(m)} for m in sorted(metrics)],
        "meta": {k: v for k, v in d.items()
                 if k not in ("results",) and not isinstance(v, (list, dict))},
        "split": sp, "data_window": dw,
        "grid_complete": complete,
        "warnings": warnings,
    }


def grid(path: str | Path, *, x: str, y: str, metric: str,
         fix: dict | None = None, split: str | None = None,
         agg: str = "none") -> dict:
    """2D 격자. 나머지 축은 고정(기본)하거나 집계(옵트인, §5)."""
    d = json.loads(Path(path).read_text())
    recs = [r for r in _records(d)
            if split is None or r.get("split") == split]
    for k, v in (fix or {}).items():
        recs = [r for r in recs if str(r.get(k)) == str(v)]

    xs = sorted({r.get(x) for r in recs}, key=lambda v: (v is None, _num(v), str(v)))
    ys = sorted({r.get(y) for r in recs}, key=lambda v: (v is None, _num(v), str(v)))
    cells: list[list] = [[None] * len(xs) for _ in ys]
    # 셀별 **전체 지표**. 툴팁이 t·n·se 를 항상 숫자로 보여야 하기 때문이다(§7) —
    # 색만으로 판단하지 않게 하는 것이 요구사항이고, 지표 하나만 내보내면
    # 프론트가 그걸 못 지킨다.
    records: list[list] = [[None] * len(xs) for _ in ys]
    for r in recs:
        v = r.get(metric)
        if v is None:
            continue
        i, j = ys.index(r.get(y)), xs.index(r.get(x))
        if records[i][j] is None:
            records[i][j] = {k: r.get(k) for k in r
                             if not isinstance(r.get(k), (dict, list))}
        cur = cells[i][j]
        if cur is None:
            cells[i][j] = v
        elif agg == "mean":
            cells[i][j] = (cur + v) / 2
        elif agg == "max":
            cells[i][j] = max(cur, v)
        elif agg == "min":
            cells[i][j] = min(cur, v)
        # agg == "none" 이면 첫 값 유지 — 고정축이 남아 있다는 뜻이라
        # 호출자가 fix 로 좁혀야 한다

    return {
        "x": x, "y": y, "metric": metric, "metric_kind": metric_kind(metric),
        "x_values": xs, "y_values": ys, "cells": cells, "records": records,
        "agg": agg, "split": split, "fix": fix or {},
        # 결측과 정확히 0 은 다르다 — 발산 램프에서 둘 다 중립색이라
        # 프론트가 반드시 구분해 그려야 한다 (설계 §10.3)
        "missing": [[cells[i][j] is None for j in range(len(xs))]
                    for i in range(len(ys))],
    }


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("inf")
