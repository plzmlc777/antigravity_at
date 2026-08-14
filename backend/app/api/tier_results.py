"""1군/2군 결과 조회 API — 읽기 전용.

  GET /api/v1/tier-results/summary       한 화면 요약
  GET /api/v1/tier-results/tier1/layers  1군 4층 동기화 (BT/CANON/PA/REAL)
  GET /api/v1/tier-results/tier2/seats    2군 리그 좌석별 성과
  GET /api/v1/tier-results/gate-runs     정본 관문 실행 이력
  GET /api/v1/tier-results/research      백테스트·시뮬 수치

설계: `.claude/plans/tier1_result_store_schema.md`

⚠ 여기서 절대 하면 안 되는 것 두 가지

  1. **`paper_trade.tier == 2` 를 "2군"으로 쓰지 마라.**
     `ingest_tier_results.classify()` 는 lifecycle 이 아닌 것을 전부 tier 2 로
     찍는다. 실측(2026-08-14): tier=2 유효 거래 759건 / 54세션인데 **실제 리그는
     136건 / 11석**이다. 나머지는 리그에 앉은 적 없는 연구용 세션이다.
     2군 좌석은 `tier_governor.is_governed` 하나로만 정한다(아래 `_league_seats`).

  2. **성과를 인용할 때 `invalid` 필터를 빼지 마라.**
     2026-08-13 에 lifecycle 498거래를 무효 처리했다(팬텀 익절/재진입/숏 수수료
     미부과). 필터 없는 수치는 그 오염을 그대로 싣는다.

이 라우터는 **거래 경로를 건드리지 않는다.** DB 를 읽기만 하고, 좌석 목록은
`session.json` 을 읽기만 한다.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.tier_result import (
    EngineGateRun, PaperTrade, ResearchResult, Tier1LayerObservation,
)

logger = logging.getLogger(__name__)
router = APIRouter()

BACKEND = Path(__file__).resolve().parents[2]
LAYER_ORDER = ["BT", "CANON", "PA", "REAL"]


def _league_seats() -> List[Dict[str, Any]]:
    """지금 리그 좌석에 앉아 있는 세션.

    "무엇이 리그 세션인가"의 정의는 `tier_governor.is_governed` **한 곳**에만 둔다.
    2026-08-13 에 이 정의를 여기서 다시 쓰려다 251 → 136 으로 정정했다.

    좌석 배치는 **살아 있는 운영 상태**라 DB 가 아니라 `session.json` 에 있다
    (설계 §1: 세션 상태는 정본 엔진의 것이고 DB 로 옮기지 않는다). 그래서 이
    함수만 파일을 읽고, 성과 수치는 전부 DB 에서 온다.

    읽기 실패는 조용히 빈 목록이다 — 조회 API 가 500 을 내면 안 된다.
    """
    try:
        sp = str(BACKEND / "scripts")
        if sp not in sys.path:
            sys.path.insert(0, sp)
        from tier_governor import SESS_DIR, is_governed  # type: ignore
    except Exception as exc:
        logger.warning("tier_governor import 실패: %s", exc)
        return []

    seats: List[Dict[str, Any]] = []
    for sdir in sorted(glob.glob(os.path.join(SESS_DIR, "*"))):
        sj = os.path.join(sdir, "session.json")
        if not os.path.exists(sj):
            continue
        try:
            with open(sj) as f:
                meta = json.load(f)
        except Exception:
            continue
        if is_governed(meta, "binance") and meta.get("status") == "active":
            seats.append({
                "session_id": meta.get("session_id"),
                "name": meta.get("name"),
                "symbol": meta.get("symbol"),
            })
    return seats


def _iso(v) -> Optional[str]:
    return v.isoformat() if v else None


@router.get("/tier1/layers")
def tier1_layers(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """1군 4층 동기화 — 한 상장 사건에 BT/CANON/PA/REAL 을 나란히.

    1군의 존재 이유인 표다: "백테스트/페이퍼/실거래의 관계성이 성립하는가".
    `CANON↔PA` 는 체결 지연, `PA↔REAL` 은 사이징 차이로 격차가 분리된다.

    **`clean` 이 핵심이다.** 네 층이 모두 진입 1회여야 수익률 비교가 성립한다.
    한 층이라도 재진입했으면 비교 대상이 아니다.
    """
    latest = db.query(func.max(Tier1LayerObservation.observed_at)).scalar()
    if latest is None:
        return {"observed_at": None, "events": [], "clean_count": 0}

    rows = (db.query(Tier1LayerObservation)
            .filter(Tier1LayerObservation.observed_at == latest)
            .order_by(Tier1LayerObservation.listing_date.desc()).all())

    events: Dict[tuple, Dict[str, Any]] = {}
    for r in rows:
        key = (r.symbol, r.listing_date)
        ev = events.setdefault(key, {
            "symbol": r.symbol,
            "listing_date": r.listing_date.isoformat(),
            "layers": {},
        })
        ev["layers"][r.layer] = {
            "n_trades": r.n_trades,
            "entry_date": r.entry_date.isoformat() if r.entry_date else None,
            "entry_price": r.entry_price,
            "return_pct": r.return_pct,
            "pnl_usdt": r.pnl_usdt,
            "reentry": r.reentry,
        }

    out = []
    for ev in events.values():
        L = ev["layers"]
        # 네 층 모두 진입 1회 — 이때만 층간 수익률 비교가 의미를 갖는다
        ev["clean"] = (len(L) == len(LAYER_ORDER)
                       and all(L[k].get("n_trades") == 1 for k in LAYER_ORDER if k in L))
        out.append(ev)

    out.sort(key=lambda e: e["listing_date"], reverse=True)
    return {
        "observed_at": _iso(latest),
        "layer_order": LAYER_ORDER,
        "events": out,
        "clean_count": sum(1 for e in out if e["clean"]),
    }


@router.get("/tier2/seats")
def tier2_seats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """2군 좌석별 성과 — **유효 거래만**.

    좌석 목록은 `is_governed`(파일), 성과는 `paper_trade`(DB). 거래가 0건인
    좌석도 빠지지 않고 나온다 — 안 잡히는 좌석이 있으면 그게 사고다.
    """
    seats = _league_seats()
    ids = [s["session_id"] for s in seats if s.get("session_id")]

    agg: Dict[str, Dict[str, Any]] = {}
    if ids:
        rows = (db.query(
                    PaperTrade.session_id,
                    func.count(PaperTrade.id),
                    func.avg(PaperTrade.return_pct),
                    func.sum(PaperTrade.pnl_cash),
                    func.max(PaperTrade.exit_ts),
                    func.sum(case((PaperTrade.return_pct > 0, 1), else_=0)),
                )
                .filter(PaperTrade.invalid.is_(False),
                        PaperTrade.session_id.in_(ids))
                .group_by(PaperTrade.session_id).all())
        for sid, n, avg_r, sum_p, last_x, wins in rows:
            agg[sid] = {
                "n_valid": int(n or 0),
                "mean_return_pct": float(avg_r) if avg_r is not None else None,
                "sum_pnl": float(sum_p) if sum_p is not None else None,
                "win_rate": (float(wins) / n) if n else None,
                "last_exit": _iso(last_x),
            }

    out = []
    for s in seats:
        a = agg.get(s["session_id"], {"n_valid": 0, "mean_return_pct": None,
                                      "sum_pnl": None, "win_rate": None,
                                      "last_exit": None})
        out.append({**s, **a})
    out.sort(key=lambda r: (r["n_valid"], r["sum_pnl"] or 0), reverse=True)

    return {
        # ⚠ 이 숫자는 `tier=2` 행 수가 아니다. 리그 좌석에 앉은 세션만이다.
        "seat_count": len(seats),
        "valid_trades": sum(r["n_valid"] for r in out),
        "seats": out,
        "note": "좌석=tier_governor.is_governed · 성과=paper_trade WHERE invalid=false",
    }


@router.get("/gate-runs")
def gate_runs(limit: int = Query(50, ge=1, le=500),
              db: Session = Depends(get_db)) -> Dict[str, Any]:
    """정본 관문 실행 이력.

    `orders_blocked` 가 이 표의 존재 이유다 — **관문이 실제로 주문을 막은 순간**.
    수동 실행은 막을 주문이 없으므로 실패해도 false 다.
    """
    rows = (db.query(EngineGateRun)
            .order_by(EngineGateRun.ran_at.desc()).limit(limit).all())
    total = db.query(func.count(EngineGateRun.id)).scalar() or 0
    blocked = (db.query(func.count(EngineGateRun.id))
               .filter(EngineGateRun.orders_blocked.is_(True)).scalar() or 0)
    return {
        "total": total,
        "blocked_total": blocked,
        "runs": [{
            "id": r.id,
            "ran_at": _iso(r.ran_at),
            "mode": r.mode,
            "verdict": r.verdict,
            "unit": (f"{r.unit_passed}/{r.unit_total}"
                     if r.unit_total is not None else None),
            "golden": (f"{r.golden_matched}/{r.golden_mismatched}"
                       if r.golden_matched is not None else None),
            "parity": (f"{r.parity_pass}/{r.parity_fail}/{r.parity_skip}"
                       if r.parity_pass is not None else None),
            "orders_blocked": r.orders_blocked,
            "context": (r.detail or {}).get("context"),
        } for r in rows],
    }


@router.get("/research")
def research(kind: Optional[str] = None, strategy: Optional[str] = None,
             include_superseded: bool = False,
             limit: int = Query(100, ge=1, le=1000),
             db: Session = Depends(get_db)) -> Dict[str, Any]:
    """백테스트·포트폴리오 시뮬 수치.

    **폐기된 세대는 기본 제외한다.** 2026-08-14 에 숏 수익률 규약 결함으로 20행이
    무효가 됐다(`진입/청산−1` 은 상한이 없어 이익 거래가 부풀려졌다 — 251 코호트
    평균 43.41% → 5.15%, t 5.73 → 1.74). 두 세대가 섞여 나오면 어느 쪽이 유효한지
    호출자가 알 수 없다. 옛 행은 지우지 않았다 — 그때 무엇을 믿고 있었는지는
    남아야 한다. `include_superseded=true` 로 볼 수 있다.

    `git_commit` 은 **그 파일을 만든 시점의 HEAD** 다(적재 시점이 아니라).
    다만 머신별 값이다 — 민트는 별도 미러 이력을 갖는다.
    """
    q = db.query(ResearchResult)
    if kind:
        q = q.filter(ResearchResult.kind == kind)
    if strategy:
        q = q.filter(ResearchResult.strategy == strategy)
    rows = q.order_by(ResearchResult.created_at.desc()).limit(limit).all()
    if not include_superseded:
        rows = [r for r in rows if not (r.params or {}).get("superseded")]
    return {
        "count": len(rows),
        "excluded_superseded": not include_superseded,
        "results": [{
            "superseded": bool((r.params or {}).get("superseded")),
            "id": r.id,
            "kind": r.kind,
            "strategy": r.strategy,
            "variant": r.variant,
            "cohort_n": r.cohort_n,
            "metrics": r.metrics,
            "params": r.params,
            "git_commit": r.git_commit,
            "script": r.script,
            "source_file": r.source_file,
            "created_at": _iso(r.created_at),
        } for r in rows],
    }


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """한 화면 요약 — 1군 4층 / 2군 좌석 / 관문."""
    t1 = tier1_layers(db)
    t2 = tier2_seats(db)
    last_gate = (db.query(EngineGateRun)
                 .order_by(EngineGateRun.ran_at.desc()).first())
    total = db.query(func.count(PaperTrade.id)).scalar() or 0
    invalid = (db.query(func.count(PaperTrade.id))
               .filter(PaperTrade.invalid.is_(True)).scalar() or 0)
    return {
        "tier1": {
            "observed_at": t1["observed_at"],
            "events": len(t1["events"]),
            # 네 층 모두 1회 진입 — 실제로 비교 가능한 사건 수
            "clean_events": t1["clean_count"],
        },
        "tier2": {
            "seat_count": t2["seat_count"],
            "valid_trades": t2["valid_trades"],
        },
        "gate": ({
            "ran_at": _iso(last_gate.ran_at),
            "verdict": last_gate.verdict,
            "mode": last_gate.mode,
            "orders_blocked": last_gate.orders_blocked,
        } if last_gate else None),
        "trades": {"total": total, "invalid": invalid, "valid": total - invalid},
    }
