"""고원 판정 — 최고점이 아니라 **고원 중앙**을 고른다.

왜 최고점을 고르면 안 되나
    격자에서 최고 셀을 집는 것은 정의상 과최적화다. 그 셀이 이웃 없이 홀로
    서 있으면(절벽) 파라미터가 조금만 틀려도 무너진다. 고원 중앙은 주변이
    함께 좋아서, 값을 정확히 못 맞춰도 견딘다.

    이미 이 규율로 정한 게 있다 — 실거래 사이징 20%:
        "15~20%가 MDD 플래토다. R-3 방법론(**단일 최적 대신 플래토 채택**)을
         따라 20%."  (lifecycle_live_signal_driver.py)

    설계 `.claude/plans/param_sweep_heatmap_component.md` §8 을 코드로 옮긴 것이다.
    그 문서는 §1 에서 "최적점 자동 선택 아님 (그건 과최적화 기계다)"이라고 못박았는데,
    도구를 안 만든다고 최적화를 안 하게 되는 게 아니라 **손으로 표를 보며 눈으로
    고르게 된다.** 2026-08-14 에 실제로 그랬고 OOS 에서 뒤집혔다. 그래서 규칙을
    코드로 낸다 — 다만 **자동 채택이 아니라 추천**이고, 절벽이면 경고한다.

판정 절차
    1. 표본 밖 셀은 판정에 **쓰지 않는다.** 표본 밖은 검증용이지 선택용이 아니다.
       (선택에 쓰면 그 순간 표본 밖이 아니게 된다)
    2. `|t| < T` 셀은 후보에서 뺀다 — 잡음을 고원으로 읽지 않기 위해(§7)
    3. 각 축에서 ±1 스텝 이웃을 본다. 이웃 중 **같은 부호이고 유의한 비율**이
       고원 점수다
    4. 고원 점수 × 지표값 순으로 추천. 이웃 지지가 0 이면 **절벽 경고**
    5. 추천 셀의 **표본 밖 성과를 함께 낸다** — 채택 판단은 대표님 몫이다

사용:
  python3 -m scripts.research.plateau_select --file runs/research_track/lifecycle_optimize.json
  python3 -m scripts.research.plateau_select --file ... --metric mean --min-t 2.0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _key(r, axes):
    return tuple(r[a] for a in axes)


# 축 이름 → 그 축이 살아 있는지 확인할 지표
# (그 축을 조절해도 이 값이 0 이면 아무 일도 안 일어난 것이다)
AXIS_LIVENESS = {"sl": "sl_exits", "policy.sl_pct": "sl_exits",
                 "tp": "tp_exits", "policy.tp_pct": "tp_exits"}


def dead_axes(IS: dict, axes: list, values: dict) -> list[str]:
    """**값을 바꿔도 아무 일이 안 일어난 축.**

    2026-08-14: sl 을 0.02 까지 좁혀 IS t 17.55 를 얻었는데, 커널이 진입한 바에서
    SL/TP 를 검사하지 않기 때문에(일봉에서 시가 진입과 고가 도달의 순서를 알 수
    없다) 손절이 **한 번도 발동하지 않았다.** 좁힐수록 좋아진 게 아니라
    좁힐수록 위험 관리가 꺼진 것이었다.

    고원 점수도 경계 경고도 이걸 못 잡는다 — 둘 다 지표값만 보기 때문이다.
    발동 횟수를 따로 봐야 한다.
    """
    out = []
    for ax in axes:
        key = AXIS_LIVENESS.get(ax)
        if not key or len(values.get(ax, [])) < 2:
            continue
        by_val = {}
        for k, r in IS.items():
            v = k[axes.index(ax)]
            by_val.setdefault(v, []).append(r.get(key))
        dead = [str(v) for v, xs in by_val.items()
                if all((x or 0) == 0 for x in xs)]
        if dead:
            out.append(f"{ax}: 값 {', '.join(sorted(dead))} 에서 `{key}` 가 0 "
                       f"— 그 값들은 **탐색되지 않았다**")
    return out


def edge_axes(cell, axes, values) -> list[str]:
    """추천 셀이 **끝값**에 앉아 있는 축들.

    2026-08-14 에 두 번 연속 이 함정에 빠졌다. `sl` 을 0.3~0.7 로 훑어 0.3 이
    이겼고, 범위를 0.15~0.4 로 넓히자 이번엔 0.15 가 이겼다. 최적값이 탐색
    범위의 끝에 있으면 **고원을 찾은 게 아니다** — 그 너머를 안 봤을 뿐이다.

    이때 고원 점수는 여전히 100% 로 나온다. 존재하는 이웃만 세기 때문이다.
    즉 **점수가 높다는 것이 안전을 뜻하지 않는다.** 그래서 따로 경고한다.
    """
    out = []
    for i, ax in enumerate(axes):
        vs = values[ax]
        if len(vs) < 2:
            continue                      # 축이 아니라 고정값
        try:
            pos = vs.index(cell[i])
        except ValueError:
            continue
        if pos == 0 or pos == len(vs) - 1:
            out.append(f"{ax}={cell[i]} ({'최소' if pos == 0 else '최대'}값, "
                       f"훑은 범위 {vs[0]}~{vs[-1]})")
    return out


def neighbors(cell, axes, values):
    """각 축에서 ±1 스텝. 축 값은 **선언 순서**를 이웃 순서로 본다."""
    out = []
    for i, ax in enumerate(axes):
        vs = values[ax]
        try:
            pos = vs.index(cell[i])
        except ValueError:
            continue
        for d in (-1, 1):
            j = pos + d
            if 0 <= j < len(vs):
                out.append(cell[:i] + (vs[j],) + cell[i + 1:])
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="고원 판정 — 최고점 대신 고원 중앙")
    p.add_argument("--file", required=True)
    p.add_argument("--metric", default="total_ret")
    p.add_argument("--min-t", type=float, default=2.0,
                   help="이 미만 |t| 셀은 후보에서 제외 (설계 §7)")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--record", action="store_true",
                   help="판정을 research_result 에 기록한다 (kind=plateau_verdict)")
    a = p.parse_args()

    from research.sweep_format import validate  # noqa: E402

    problems = validate(a.file)
    d = json.loads(Path(a.file).read_text())
    axes = list(d["axes"])
    values = {k: list(v) for k, v in d["axes"].items()}

    IS = {_key(r, axes): r for r in d["results"] if r["split"] == "IS"}
    OOS = {_key(r, axes): r for r in d["results"] if r["split"] == "OOS"}

    m = a.metric
    def val(r):
        return r.get(m)
    def sig(r):
        t = r.get("t")
        return t is not None and abs(t) >= a.min_t

    cand = [(k, r) for k, r in IS.items() if val(r) is not None and sig(r)]

    print("=" * 96)
    print(f"고원 판정 — {Path(a.file).name} · 지표 {m} · 유의 기준 |t| >= {a.min_t}")
    print("=" * 96)

    # ── 출처 (§9) ───────────────────────────────────────────────────────
    sp, dw = d.get("split") or {}, d.get("data_window") or {}
    print(f"  엔진 {d.get('engine')} · 커밋 {d.get('commit')} · 산출 {d.get('generated_at')}")
    print(f"  구간 {dw.get('start')} ~ {dw.get('end')} · "
          f"IS 사건 {dw.get('is_events')} / OOS 사건 {dw.get('oos_events')}")
    print(f"  분할 {sp.get('date')} · 셀 IS {sp.get('is_cells')} / OOS {sp.get('oos_cells')}")
    if problems:
        print("  ⚠ 표준 위반:")
        for x in problems:
            print(f"     · {x}")
    n_oos = dw.get("oos_events") or 0
    if n_oos < 30:
        print(f"  ⚠ **표본 밖 사건 {n_oos}건** — 30건 미만이면 채택 판단의 근거가 못 된다")
    print("-" * 96)
    print(f"  전체 {len(IS)}칸 · 유의 {len(cand)}칸 "
          f"({100*len(cand)/max(len(IS),1):.0f}%)")
    if not cand:
        print("  유의한 셀이 없다 — 이 격자로는 고를 것이 없다.")
        print("=" * 96)
        return 0

    # ── 고원 점수 ───────────────────────────────────────────────────────
    scored = []
    for k, r in cand:
        nb = neighbors(k, axes, values)
        present = [IS[n] for n in nb if n in IS]
        same = [x for x in present
                if val(x) is not None and val(x) * val(r) > 0 and sig(x)]
        score = len(same) / len(present) if present else 0.0
        scored.append({"key": k, "r": r, "score": score,
                       "n_nb": len(present), "n_same": len(same)})

    best_val = max(s["r"][m] for s in scored)
    scored.sort(key=lambda s: (-s["score"], -(s["r"][m] or 0)))

    def tfmt(t):
        """t 는 표본이 작으면 표준오차가 붕괴해 1e15 같은 값이 나온다.
        그런 값은 성과가 아니라 '읽지 말라'는 신호이므로 그대로 찍지 않는다."""
        if t is None:
            return "  —  "
        return f"{t:>7.2f}" if abs(t) < 1000 else "   ∞*  "

    hdr = "".join(f"{x:>13}" for x in axes)
    print(f"  {hdr}{'IS ' + m:>12}{'IS t':>8}{'고원':>7}{'이웃':>8}"
          f"{'OOS ' + m:>12}{'OOS t':>8}")
    for s in scored[:a.top]:
        k, r = s["key"], s["r"]
        o = OOS.get(k, {})
        flag = "  ← 절벽" if s["n_same"] == 0 else ""
        peak = "  ★최고" if r[m] == best_val else ""
        print(f"  {''.join(f'{str(v):>13}' for v in k)}"
              f"{r[m]:>12.1f}{tfmt(r.get('t')):>8}"
              f"{s['score']*100:>6.0f}%{(str(s['n_same']) + '/' + str(s['n_nb'])):>8}"
              f"{(o.get(m) or 0):>12.1f}{tfmt(o.get('t')):>8}{flag}{peak}")

    print("-" * 96)
    top = scored[0]
    ok = top["n_same"] > 0
    print(f"  **추천**: " + " · ".join(f"{ax}={v}" for ax, v in zip(axes, top["key"])))
    print(f"     고원 점수 {top['score']*100:.0f}% (이웃 {top['n_same']}/{top['n_nb']} 동일부호·유의)")
    _r = top["r"]
    if any(k in _r for k in ("sl_exits", "tp_exits", "time_exits")):
        print(f"     청산 사유: 손절 {_r.get('sl_exits', '—')} · "
              f"익절 {_r.get('tp_exits', '—')} · 시간 {_r.get('time_exits', '—')}"
              + (f" · 데이터끝 {_r['eod_exits']}" if _r.get("eod_exits") else ""))
    if not ok:
        print("     ⚠ **절벽** — 이웃 지지가 없다. 파라미터가 조금만 틀려도 무너진다")
    deads = dead_axes(IS, axes, values)
    if deads:
        print("     ⚠ **죽은 축** — 값을 바꿔도 아무 일이 일어나지 않았다:")
        for dmsg in deads:
            print(f"        · {dmsg}")
        print("        그 구간의 수치는 전략이 아니라 **기능이 꺼진 결과**다.")

    edges = edge_axes(top["key"], axes, values)
    if edges:
        print("     ⚠ **경계 최적** — 추천이 탐색 범위의 끝에 앉아 있다:")
        for e in edges:
            print(f"        · {e}")
        print("        고원을 찾은 게 아니라 **그 너머를 안 본 것**일 수 있다.")
        print("        해당 축의 범위를 넓혀 다시 돌려라. 고원 점수 100% 는")
        print("        **존재하는 이웃 안에서의** 100% 다.")
    peak_cell = max(scored, key=lambda s: s["r"][m])
    if peak_cell["key"] != top["key"]:
        print(f"     (IS 최고 셀은 "
              + " · ".join(f"{ax}={v}" for ax, v in zip(axes, peak_cell["key"]))
              + f" 이지만 고원 점수 {peak_cell['score']*100:.0f}% 로 낮아 추천에서 밀렸다)")
    o = OOS.get(top["key"], {})
    ov, ot = o.get(m), o.get("t")
    print(f"     표본 밖: {m} {('—' if ov is None else f'{ov:.1f}')} · "
          f"t {('—' if ot is None else ('∞*(표준오차 붕괴)' if abs(ot) >= 1000 else f'{ot:.2f}'))} · "
          f"거래 {o.get('n_trades')}")
    if a.record:
        _record(a, d, top, peak_cell, o, problems, len(IS), len(cand))
    print("  ∞* = 표본이 작아 표준오차가 붕괴한 칸. 성과가 아니라 읽지 말라는 신호다")
    print("  ⚠ 추천은 채택이 아니다. 표본 밖 사건이 충분히 쌓이기 전까지는 "
          "**현행 유지**가 기본이다.")
    print("=" * 96)
    return 0


def _record(a, d, top, peak, oos, problems, n_cells, n_sig) -> None:
    """판정을 DB 에 남긴다.

    왜 남기나 — 화면에 찍고 마는 도구는 "언제 무엇을 왜 추천했나"를 답하지
    못한다. 오늘 하루에만 근거 없는 수치를 세 번 만났는데(숏 규약, 복리 결함,
    진입 시점) 전부 **과거 산출물의 근거를 되짚을 수 없어서** 커진 문제였다.
    추천을 기록하지 않으면 이 도구가 같은 함정을 새로 만든다.

    ⚠ 이건 **채택 기록이 아니라 추천 기록**이다. 채택은 대표님이 한다.
    """
    try:
        from app.db.session import SessionLocal
        from app.models.tier_result import ResearchResult
    except Exception as exc:
        print(f"  (기록 실패 — {type(exc).__name__}: {exc})")
        return

    axes = list(d["axes"])
    dw, sp = d.get("data_window") or {}, d.get("split") or {}
    n_oos = dw.get("oos_events") or dw.get("oos_trades")
    pick = {ax: v for ax, v in zip(axes, top["key"])}
    metrics = {
        "metric": a.metric,
        "is_value": top["r"].get(a.metric),
        "is_t": top["r"].get("t"),
        "oos_value": oos.get(a.metric),
        "oos_t": oos.get("t"),
        "oos_trades": oos.get("n_trades"),
        "plateau_score": top["score"],
        "neighbors_same": top["n_same"],
        "neighbors_total": top["n_nb"],
        "cliff": top["n_same"] == 0,
        "cells_total": n_cells,
        "cells_significant": n_sig,
        "is_peak_cell": peak["key"] == top["key"],
        # 경계 최적이면 이 추천은 잠정이다 — 범위를 넓혀 다시 봐야 한다
        "edge_axes": edge_axes(top["key"], list(d["axes"]),
                               {k: list(v) for k, v in d["axes"].items()}),
        # 값을 바꿔도 발동 0 인 축 — 그 구간은 탐색된 적이 없다
        "dead_axes": dead_axes(IS, list(d["axes"]),
                               {k: list(v) for k, v in d["axes"].items()}),
    }
    params = {
        "pick": pick,
        "axes": {k: list(v) for k, v in d["axes"].items()},
        "min_t": a.min_t,
        "split_date": sp.get("date"),
        "data_window": dw,
        "source_commit": d.get("commit"),
        "standard_problems": problems,
        # 추천은 채택이 아니다. 이 표시가 없으면 나중에 "그때 이걸 썼다"로 읽힌다
        "adopted": False,
        "note": ("추천일 뿐 채택이 아니다. 표본 밖 사건이 충분히 쌓이기 전까지 "
                 "현행 유지가 기본이다. metrics.edge_axes 가 비어 있지 않으면 "
                 "탐색 범위의 끝에 앉은 잠정 추천이다."),
    }
    db = SessionLocal()
    try:
        from datetime import datetime
        created = datetime.utcnow()
        db.add(ResearchResult(
            kind="plateau_verdict",
            strategy=(dw.get("source") or d.get("script") or "").split("/")[-1]
                     or "unknown",
            variant="/".join(f"{k}={v}" for k, v in pick.items())[:200],
            cohort_n=(dw.get("is_events") or n_cells),
            params=params, metrics=metrics,
            git_commit=d.get("commit"),
            script="scripts/research/plateau_select.py",
            source_file=str(Path(a.file).name),
            created_at=created))
        db.commit()
        print(f"  기록됨 → research_result (kind=plateau_verdict, adopted=false)")
    except Exception as exc:
        db.rollback()
        print(f"  (기록 실패 — {type(exc).__name__}: {exc})")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
