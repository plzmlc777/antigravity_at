"""스윕 결과 조회 API — 읽기 전용.

  GET /api/v1/research-track/files                 스윕 JSON 목록
  GET /api/v1/research-track/files/{name}/schema   추론된 축·지표 + 출처
  GET /api/v1/research-track/files/{name}/grid     2D 격자

설계 `.claude/plans/param_sweep_heatmap_component.md` §10.1

⚠ 경로 순회 방어
    파일명은 **디렉터리 실제 목록과 대조**한다. `..`·절대경로·심볼릭 링크를
    거부한다. 사용자 입력을 경로에 붙이지 않는다.

⚠ 출처를 숨기지 않는다 (§9)
    히트맵은 숫자를 설득력 있게 만드는 도구라 출처 없이 렌더하면 무효 데이터를
    세탁한다. `schema` 응답의 `warnings` 는 **프론트가 반드시 표시해야 한다.**
    실측 8개 파일 중 7개가 IS/OOS 구분이 없다.

쓰기 엔드포인트는 없다. 백테스트 실행 트리거도 아니다(§1 명시적 비목표).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()

BACKEND = Path(__file__).resolve().parents[2]
RT = BACKEND / "runs" / "research_track"

# 스윕 결과가 아닌 대용량 원자료를 목록에서 거른다 (§12 미결 사항)
MAX_BYTES = 3_000_000
MIN_RECORDS = 4


def _reader():
    sp = str(BACKEND / "scripts")
    if sp not in sys.path:
        sys.path.insert(0, sp)
    from research import sweep_read  # type: ignore
    return sweep_read


def _resolve(name: str) -> Path:
    """파일명 → 경로. **실제 목록과 대조**해서만 통과시킨다."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "허용되지 않는 파일명")
    try:
        actual = {f for f in os.listdir(RT) if f.endswith(".json")}
    except OSError:
        raise HTTPException(503, "연구 산출물 디렉터리를 읽을 수 없다")
    if name not in actual:
        raise HTTPException(404, "그런 스윕 파일이 없다")
    p = RT / name
    if p.is_symlink() or not p.is_file():
        raise HTTPException(400, "일반 파일이 아니다")
    return p


@router.get("/files")
def list_files() -> Dict[str, Any]:
    """스윕 형태인 JSON 만 나열한다.

    형태 판별은 **읽어봐야** 알 수 있으므로 크기 상한을 먼저 건다 —
    `funding_history.json`(7.8MB)은 스윕 결과가 아니라 원자료다.
    """
    sr = _reader()
    out = []
    skipped = []
    try:
        names = sorted(f for f in os.listdir(RT) if f.endswith(".json"))
    except OSError:
        raise HTTPException(503, "연구 산출물 디렉터리를 읽을 수 없다")

    for name in names:
        p = RT / name
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > MAX_BYTES:
            skipped.append({"file": name, "why": f"크기 {size/1e6:.1f}MB — 상한 초과"})
            continue
        try:
            info = sr.infer(p)
        except Exception as exc:
            skipped.append({"file": name, "why": f"{type(exc).__name__}"})
            continue
        if info.get("n_records", 0) < MIN_RECORDS or not info.get("ok"):
            skipped.append({"file": name,
                            "why": info.get("reason") or "스윕 형태 아님"})
            continue
        out.append({
            "file": name, "size": size, "mtime": info["mtime"],
            "n_records": info["n_records"],
            "axes": list(info["axes"]),
            "n_metrics": len(info["metrics"]),
            "standard": info.get("meta", {}).get("schema_version") is not None,
            "n_warnings": len(info["warnings"]),
        })
    out.sort(key=lambda r: -r["mtime"])
    return {"files": out, "skipped": skipped, "dir": str(RT)}


@router.get("/files/{name}/schema")
def file_schema(name: str) -> Dict[str, Any]:
    """추론된 축·지표 후보 + **출처 경고**.

    `warnings` 는 프론트가 반드시 표시해야 한다 — 안 보이면 컴포넌트가
    거짓말에 가담한다(§9).
    """
    sr = _reader()
    p = _resolve(name)
    try:
        return sr.infer(p)
    except Exception as exc:
        logger.warning("schema 추론 실패 %s: %s", name, exc)
        raise HTTPException(422, f"추론 실패: {type(exc).__name__}")


@router.get("/files/{name}/grid")
def file_grid(name: str, x: str, y: str, metric: str,
              fix: str = Query("", description="고정축 k:v,k:v"),
              split: Optional[str] = Query(None, description="IS / OOS"),
              agg: str = Query("none", pattern="^(none|mean|max|min)$"),
              ) -> Dict[str, Any]:
    """2D 격자.

    **집계는 옵트인이다** (§5). 남은 축을 평균 내면 절벽이 고원으로 위장된다 —
    한 축에서 급락하는 조합이 다른 값에서 상쇄되면 셀 색이 멀쩡해진다.
    기본은 슬라이스(`fix`)이고, `agg` 를 쓰면 응답에 경고를 실어 보낸다.
    """
    sr = _reader()
    p = _resolve(name)
    fixed = {}
    for part in (fix or "").split(","):
        if not part.strip():
            continue
        if ":" not in part:
            raise HTTPException(400, f"fix 형식은 k:v 다: {part!r}")
        k, v = part.split(":", 1)
        fixed[k.strip()] = v.strip()
    try:
        g = sr.grid(p, x=x, y=y, metric=metric, fix=fixed, split=split, agg=agg)
        info = sr.infer(p)
    except Exception as exc:
        logger.warning("grid 실패 %s: %s", name, exc)
        raise HTTPException(422, f"격자 생성 실패: {type(exc).__name__}: {exc}")

    warnings = list(info["warnings"])
    if agg != "none":
        warnings.insert(0, "**집계 모드** — 남은 축을 뭉개면 절벽이 고원으로 위장된다")
    remaining = [k for k in info["axes"] if k not in (x, y) and k not in fixed]
    if remaining and agg == "none":
        warnings.insert(0, f"고정하지 않은 축이 있다: {remaining} — 셀이 첫 값만 보여준다")
    return {**g, "provenance": {
        "file": name, "mtime": info["mtime"],
        "meta": info["meta"], "split": info["split"],
        "data_window": info["data_window"],
    }, "warnings": warnings}
