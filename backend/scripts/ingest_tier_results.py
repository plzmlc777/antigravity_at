"""파일 → DB 적재. 1군/2군 결과를 조회 가능하게 만든다.

설계: `.claude/plans/tier1_result_store_schema.md`

원칙
  · **파일이 원본이다.** 여기는 사본을 만든다. 적재가 실패해도 거래에 영향이 없다.
  · **멱등** — 몇 번 돌려도 같은 결과. UNIQUE 제약 + 존재 확인으로 중복을 막는다.
  · **무효 표시를 보존한다.** `invalid` 를 그대로 옮겨야 `WHERE invalid = false`
    한 줄로 성과를 인용할 수 있다. 이게 이 작업의 존재 이유다.

무엇을 적재하나
  paper_trade              runs/paper_sessions/*/trades.jsonl
  research_result          runs/research_track/**/*.json (키 파일만 명시 매핑)
  tier1_layer_observation  lifecycle_three_way_sync.json

사용:
  python3 -m scripts.ingest_tier_results --all
  python3 -m scripts.ingest_tier_results --trades      # 거래만
  python3 -m scripts.ingest_tier_results --dry         # 계획만
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.db.session import SessionLocal  # noqa: E402
from app.models.tier_result import (  # noqa: E402
    PaperTrade, ResearchResult, Tier1LayerObservation,
)

SESS = ROOT / "runs" / "paper_sessions"
RT = ROOT / "runs" / "research_track"

LIFECYCLE_RE = re.compile(
    r"lifecycle_(h21|earlyexit_d7|earlyexit_d14|bearskip)?_?(.+?)_(\d{4}-\d{2}-\d{2})$")


def git_commit() -> str | None:
    """현재 HEAD. 마지막 수단이다 — 아래 `commit_at` 을 먼저 써라."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
            stderr=subprocess.DEVNULL, timeout=10).decode().strip()
    except Exception:
        return None


def commit_at(when: datetime) -> str | None:
    """그 시각에 HEAD 였던 커밋 — **파일을 산출한 코드**.

    2026-08-14: 처음엔 적재 시점 HEAD 를 적었다. 그러면 이 컬럼이 "언제 적재했나"를
    답하지 사람이 물은 "**어느 코드가 낸 수치인가**"를 답하지 않는다. 결과 파일이
    며칠 전에 만들어졌으면 그 사이 커밋이 몇 개든 끼어 있다.

    파일 mtime 시점의 HEAD 를 역추적한다. 산출 스크립트를 고칠 필요가 없고 과거
    파일에도 적용된다.
    """
    try:
        out = subprocess.check_output(
            ["git", "rev-list", "-1", "--first-parent",
             f"--before={when.isoformat()}", "HEAD"],
            cwd=str(ROOT), stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        return out[:8] or None
    except Exception:
        return None


def classify(name: str, spec: dict) -> tuple[int | None, str | None, str | None]:
    """(tier, strategy, variant). 이름과 스펙에서 뽑는다."""
    if "lifecycle" in name:
        m = LIFECYCLE_RE.match(name)
        return 1, "lifecycle", (m.group(1) or "base") if m else None
    srcs = [s.get("type", "") for s in (spec.get("sources") or [])]
    for s in srcs:
        if "volume_burst" in s or "stablecoin" in s or "premium" in s:
            return 2, s.replace("bn_", ""), None
    return 2, (srcs[0].replace("bn_", "") if srcs else None), None


def _clean(o):
    """JSONB 에 넣기 전 정제 — **NaN/Infinity 를 None 으로**.

    2026-08-13: 적재가 `Token "NaN" is invalid` 로 통째로 실패했다. 파이썬 json 은
    NaN 을 그대로 뱉는데 PostgreSQL JSONB 는 받지 않는다. 거래가 1건뿐인 계열의
    t 통계가 NaN 이라 생긴다 — 값이 없는 것이지 0 이 아니므로 None 이 맞다.
    """
    import math
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def _dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def ingest_trades(db, dry: bool) -> tuple[int, int]:
    added = skipped = 0
    for d in sorted(os.listdir(SESS)):
        sf, tf = SESS / d / "session.json", SESS / d / "trades.jsonl"
        if not (sf.exists() and tf.exists()):
            continue
        try:
            j = json.loads(sf.read_text())
        except Exception:
            continue
        name = j.get("name", "")
        tier, strategy, variant = classify(name, j.get("pipeline_spec") or {})
        for row_idx, line in enumerate(tf.read_text().splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            ets, xts = _dt(t.get("entry_ts")), _dt(t.get("exit_ts"))
            side = t.get("side")
            exists = db.query(PaperTrade.id).filter(
                PaperTrade.session_id == d, PaperTrade.row_idx == row_idx).first()
            if exists:
                skipped += 1
                continue
            added += 1
            if dry:
                continue
            db.add(PaperTrade(
                session_id=d, row_idx=row_idx,
                session_name=name, symbol=j.get("symbol", ""),
                tier=tier, strategy=strategy, variant=variant,
                side=side, entry_ts=ets, exit_ts=xts,
                entry_price=t.get("entry_price"), exit_price=t.get("exit_price"),
                qty=t.get("qty"), return_pct=t.get("return_pct"),
                pnl_cash=t.get("pnl_cash"), exit_reason=t.get("exit_reason"),
                prediction_at_entry=t.get("prediction_at_entry"),
                # 무효 표시 보존 — 이게 적재의 존재 이유다
                invalid=bool(t.get("invalid", False)),
                invalid_defects=t.get("invalid_defects"),
                invalidated_on=(date.fromisoformat(t["invalidated_on"])
                                if t.get("invalidated_on") else None),
            ))
    if not dry:
        db.commit()
    return added, skipped


def ingest_research(db, dry: bool) -> tuple[int, int]:
    """키 결과 파일만 **명시 매핑**한다.

    자동 스캔하지 않는다 — 파일마다 구조가 달라서 조용히 잘못 넣느니 안 넣는 게 낫다.
    """
    added = skipped = 0
    specs = [
        (RT / "lifecycle_variant_backtest.json", "backtest", "lifecycle",
         "scripts/research/lifecycle_variant_backtest.py"),
        (RT / "lifecycle_phase" / "variant_x_sizing__metrics.json", "portfolio_sim",
         "lifecycle", "scripts/research/lifecycle_variant_x_sizing_sim.py"),
        (RT / "lifecycle_phase" / "variant_sizing_v2__metrics.json", "portfolio_sim",
         "lifecycle", "scripts/research/lifecycle_variant_sizing_v2.py"),
        (RT / "lifecycle_phase" / "leverage_sim__metrics.json", "portfolio_sim",
         "lifecycle", "scripts/research/lifecycle_leverage_sim.py"),
        (RT / "short_fee_rebacktest.json", "backtest", "short_families",
         "scripts/research/short_fee_rebacktest.py"),
    ]
    for path, kind, strategy, script in specs:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        created = datetime.fromtimestamp(path.stat().st_mtime)
        # 이 파일을 만든 시점의 HEAD — 적재 시점 HEAD 가 아니다
        gc = commit_at(created) or git_commit()
        # 변형별로 행을 나눌 수 있으면 나눈다 — 조회축이 살아난다
        rows = []
        if kind == "backtest" and isinstance(data.get("variants"), dict):
            for var, m in data["variants"].items():
                rows.append((var, {"cohort_n": data.get("n")}, m))
        elif isinstance(data.get("results"), dict):
            for key, m in data["results"].items():
                rows.append((str(key), {"cohort": data.get("cohort")}, m))
        else:
            rows.append((None, {}, data))

        for var, params, metrics in rows:
            exists = db.query(ResearchResult.id).filter(
                ResearchResult.kind == kind, ResearchResult.strategy == strategy,
                ResearchResult.variant == var,
                ResearchResult.created_at == created).first()
            if exists:
                skipped += 1
                continue
            added += 1
            if dry:
                continue
            db.add(ResearchResult(
                kind=kind, strategy=strategy, variant=var,
                cohort_n=(params.get("cohort_n") or params.get("cohort")
                          or data.get("n") or data.get("cohort")),
                params=_clean(params), metrics=_clean(metrics),
                git_commit=gc, script=script,
                source_file=str(path.relative_to(ROOT)), created_at=created))
    if not dry:
        db.commit()
    return added, skipped


def ingest_layers(db, dry: bool) -> tuple[int, int]:
    """4층 동기화 관측. `lifecycle_three_way_sync.py` 산출물을 행으로."""
    path = RT / "lifecycle_three_way_sync.json"
    if not path.exists():
        return 0, 0
    try:
        data = json.loads(path.read_text())
    except Exception:
        return 0, 0
    rows = data if isinstance(data, list) else data.get("rows", [])
    observed = datetime.fromtimestamp(path.stat().st_mtime)
    added = skipped = 0
    LAYERS = [
        ("BT", "bt_n", "bt_entry", None, "bt_ret", None),
        ("CANON", "pap_n", "pap_entry", None, "pap_ret", None),
        ("PA", "pa_n", "pa_entry", "pa_px", None, None),
        ("REAL", "real_n", "real_entry", "real_px", None, "real_pnl"),
    ]
    for r in rows:
        sym, ld = r.get("symbol"), r.get("listing")
        if not (sym and ld):
            continue
        for layer, kn, ke, kpx, kret, kpnl in LAYERS:
            n = r.get(kn)
            if n in (None, ""):
                continue
            ed = r.get(ke)
            exists = db.query(Tier1LayerObservation.id).filter(
                Tier1LayerObservation.symbol == sym,
                Tier1LayerObservation.listing_date == date.fromisoformat(ld),
                Tier1LayerObservation.layer == layer,
                Tier1LayerObservation.observed_at == observed).first()
            if exists:
                skipped += 1
                continue
            added += 1
            if dry:
                continue
            db.add(Tier1LayerObservation(
                symbol=sym, listing_date=date.fromisoformat(ld), layer=layer,
                n_trades=int(n or 0),
                entry_date=(date.fromisoformat(ed) if ed and ed != "—" else None),
                entry_price=(r.get(kpx) if kpx else None),
                return_pct=(r.get(kret) if kret else None),
                pnl_usdt=(r.get(kpnl) if kpnl else None),
                reentry=bool(n and int(n) != 1),
                observed_at=observed))
    if not dry:
        db.commit()
    return added, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="1군/2군 결과 파일 → DB 적재")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--trades", action="store_true")
    ap.add_argument("--research", action="store_true")
    ap.add_argument("--layers", action="store_true")
    ap.add_argument("--dry", action="store_true", help="계획만, 쓰지 않음")
    a = ap.parse_args()
    if not (a.all or a.trades or a.research or a.layers):
        a.all = True

    db = SessionLocal()
    try:
        print("=" * 72)
        print(f"1군/2군 결과 적재{' (DRY)' if a.dry else ''}")
        print("=" * 72)
        if a.all or a.trades:
            n, s = ingest_trades(db, a.dry)
            print(f"  paper_trade              신규 {n:>6} · 기존 {s:>6}")
        if a.all or a.research:
            n, s = ingest_research(db, a.dry)
            print(f"  research_result          신규 {n:>6} · 기존 {s:>6}")
        if a.all or a.layers:
            n, s = ingest_layers(db, a.dry)
            print(f"  tier1_layer_observation  신규 {n:>6} · 기존 {s:>6}")
        if not a.dry:
            from sqlalchemy import func
            v = db.query(func.count(PaperTrade.id)).filter(
                PaperTrade.invalid.is_(False)).scalar()
            t = db.query(func.count(PaperTrade.id)).scalar()
            print("-" * 72)
            print(f"  거래 총 {t} · **유효 {v}** (무효 {t - v})")
        print("=" * 72)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
