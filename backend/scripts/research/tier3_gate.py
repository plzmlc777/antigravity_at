#!/usr/bin/env python3
"""3군 판정 엔진 — 성과(G1) + 실행가능성(G2).

설계 근거: .claude/plans/tier3_redesign.md (2026-08-08 대표님 지시 재설계)

기존 R-1~R-4 elite gate 를 대체한다. 관문의 층을 바꾼 것이 핵심이다 —
자금 위험이 0인 3군에서 실전급 기준(R-4 Hard Gate: 기존 24세션 중 2개만 통과)을
요구하니 79일간 배출이 0이었고, 정작 검증장인 2군은 11석이 비어 있었다.
과적합 판별은 2군 forward(alpha<0 → TERMINATE)에 위임하고, 3군은
**"실전에서 재현될 수 있는 후보인가"** 만 책임진다.

G1 — 성과 (단일 종목·단일 스펙으로 판정. 다종목 요구 폐기)
  유의성과 최근성을 **분리해서** 본다 (2026-08-09 수정, T_MIN 주석 참조):
    유의성  max(전구간 t, 최근가중 t) >= 1.5
    최근성  최근 1/3 엣지 > 0  AND  decay_ratio >= 0.3
  핵심은 decay_ratio — 과거에만 좋고 최근에 죽은 전략을 거른다.
  유의성은 두 t 중 하나만 넘으면 된다 — 고르게 유의한 알파와 최근에 되살아난
  알파는 서로 다른 지표에 잡히고, 둘 다 실재한다(대조군 실측은 T_MIN 주석).

G2 — 실행가능성 (2026-08-08 하루에 세 번 데인 지점)
  lookahead / 지연 후 마찰여유 / 실행주기 정합.
  통과·실패가 아니라 **차단**이다. 하나라도 걸리면 2군에 올리지 않는다 —
  올려도 재현이 안 되기 때문이다.

사용:
  from tier3_gate import evaluate
  verdict = evaluate(trades, spec_meta)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Sequence

import numpy as np

# ── G1 임계값 ────────────────────────────────────────────────────────
HALFLIFE_DAYS = 90.0     # 시간가중 반감기
RECENT_FRAC = 1.0 / 3.0  # "최근 구간" 비율
DECAY_RATIO_MIN = 0.30   # 최근/과거 엣지 비율
N_TRADES_MIN = 20

# 유의성 판정 (2026-08-09 대표님 승인 수정 + 대조군 검증 반영).
#
# 왜 wt_t 를 관문에서 뺐는가 —
#   반감기 90일 고정이면 가중 합이 90/ln2 ≈ 130일분으로 수렴하므로, wt_t 의
#   유효 표본은 **구간 길이와 무관하게 130일분에 상한**을 갖는다. 즉 데이터를
#   더 주면 wt_t 는 커지지 않고 최근 130일이 약하면 오히려 떨어진다.
#   표본을 늘릴수록 판정이 나빠지는 지표였다.
#
#   실측 (paradigm 251 스테이블코인 공급):
#     DOGE h3d   299일 창  n=117  raw_t 3.80  wt_t 2.574 → 통과
#     DOGE h3d   880일 창  n=375  raw_t 1.75  wt_t 0.776 → 탈락
#     132종목 동일가중 포트폴리오 h3d 880일  raw_t 2.645  wt_t 0.567 → 탈락
#   짧은 창에서 wt_t 가 크게 나온 건 그 창에서 최근 130일이 표본의 43% 를
#   차지했기 때문이고, 게이트가 의도한 방향과 정반대다.
#
#   그리고 역할이 중복이었다. "최근에 죽었나" 는 이미 recent_edge>0 과
#   decay_ratio>=0.3 두 항목이 담당한다. wt_t 는 유의성과 최근성을 한 지표에
#   섞어 놓고 그 대가로 구간길이 의존성을 얻은 셈이었다. 그래서 분리한다 —
#   유의성은 t, 최근성은 recent_edge / decay_ratio 로 나눠 담당한다.
#
# 관문은 **둘 중 하나라도** 넘으면 통과다: max(raw_t, wt_t) >= T_MIN.
#
#   처음에는 raw_t >= 2.0 단독으로 바꿨는데 **양성 대조가 탈락했다** —
#   lifecycle pump-decay(실계좌 3개월 +240.17 USDT)가 n=129, 거래당 +6.4309%,
#   raw_t **1.469** 로 falsify 됐다. 거래당 표준편차가 약 50% 인 초고분산
#   전략이라(신규상장 숏, SL +50%, 30일 보유) t 기반 2.0 기준을 구조적으로
#   넘지 못한다. tier3_redesign 이 ci_lower 를 폐기한 사유와 같은 함정이다 —
#   "고분산 전략을 구조적으로 배제. 실제로 돈 번 lifecycle 이 여기서 falsify".
#
#   그래서 두 t 를 **선택지**로 둔다. 실재하는 알파는 두 모습 중 하나다:
#     · 전 구간에 고르게 유의     → raw_t 가 잡는다 (p251 포트폴리오 2.645)
#     · 최근 레짐에서 되살아남    → wt_t 가 잡는다 (lifecycle 1.652,
#                                    과거 1/3 -17.14% / 최근 1/3 +10.75%)
#   raw_t 를 넣은 목적(구간 길이 의존성 제거)은 유지되고, wt_t 는 의무 관문이
#   아니라 대안 경로가 되므로 "표본을 늘리면 탈락" 하는 결함이 사라진다.
#
#   임계값 1.5 는 대표님이 2026-08-08 에 이미 정한 값이다(기존 WT_T_MIN,
#   "뒤에 2군 forward 가 있으니 3군에서 과하게 조일 이유가 없다").
#
#   대조군 검증 (2026-08-09):
#     양성 lifecycle    max(1.469, 1.652) = 1.652 >= 1.5  → PASS  (의도대로)
#     음성 volume_burst max(1.024, 0.573) = 1.024 <  1.5  → FAIL  (의도대로)
T_MIN = 1.5              # max(raw_t, wt_t) 기준 (유의성)

# ── G2 임계값 ────────────────────────────────────────────────────────
# 지연 후 엣지가 마찰을 넘는 배수. **비율(잔존율) 기준을 쓰지 않는다** —
# 2026-08-08 검증에서 음성 대조(volume_burst)의 잔존율이 133% 로 양성(37%)보다
# 높게 나왔다. 엣지가 애초에 0 에 가까우면 비율은 의미가 없다. 판단해야 할 것은
# "지연을 먹고도 마찰을 넘을 만큼 남는가" 라는 절대량이다.
#   양성 lifecycle    : 지연후 3.296% / 마찰 0.100% = 33배   → 통과
#   음성 volume_burst : 지연후 0.029% / 마찰 0.054% = 0.54배 → 차단
NET_HEADROOM_MIN = 3.0       # (지연 후 엣지) ÷ 왕복 마찰
CYCLE_MARGIN_MIN = 3.0       # 보유기간 ÷ 실행 사이클 주기


@dataclass
class Trade:
    """판정 입력. exit_ts 기준으로 시간가중한다."""
    entry_ts: datetime
    exit_ts: datetime
    net_ret: float  # 수수료 차감 후 수익률 (0.01 = +1%)


@dataclass
class ExecContext:
    """G2 입력. 측정값이 없으면 None → 해당 검사는 UNKNOWN(차단)."""
    lookahead_clean: Optional[bool] = None      # 섭동 검사 통과 여부
    edge_after_1bar_delay: Optional[float] = None  # 1바 지연 후 거래당 엣지
    roundtrip_friction: Optional[float] = None  # 스프레드+충격 (0.0007 = 7bp)
    hold_minutes: Optional[float] = None        # 전략 평균 보유(분)
    cycle_minutes: Optional[float] = None       # 실행 인프라 사이클 주기(분)


@dataclass
class GateResult:
    passed: bool
    blocked_by: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def _weights(exit_ts: Sequence[datetime], now: datetime, halflife: float) -> np.ndarray:
    ages = np.array([(now - t).total_seconds() / 86400.0 for t in exit_ts], dtype=float)
    ages = np.clip(ages, 0.0, None)
    return np.exp(-math.log(2.0) * ages / halflife)


def _raw_t(x: np.ndarray) -> float:
    """전체 표본 t-stat. 유의성 관문의 한쪽 경로 (T_MIN 주석 참조)."""
    if len(x) < 2:
        return float("nan")
    sd = float(np.std(x, ddof=1))
    if sd <= 0:
        return float("nan")
    return float(np.mean(x) / (sd / math.sqrt(len(x))))


def _weighted_t(x: np.ndarray, w: np.ndarray) -> float:
    """가중 평균의 t-stat. 유효표본 n_eff = (Σw)²/Σw² 로 보정한다 —
    가중을 주면 실질 표본이 줄어드는데 이를 무시하면 t 가 부풀려진다."""
    sw = w.sum()
    if sw <= 0:
        return float("nan")
    mu = float((w * x).sum() / sw)
    var = float((w * (x - mu) ** 2).sum() / sw)
    n_eff = float(sw ** 2 / (w ** 2).sum())
    if var <= 0 or n_eff <= 1:
        return float("nan")
    return mu / math.sqrt(var / n_eff)


def evaluate_g1(trades: Sequence[Trade], now: Optional[datetime] = None,
                halflife: float = HALFLIFE_DAYS) -> dict:
    now = now or datetime.utcnow()
    if not trades:
        return {"n_trades": 0, "ok": False, "fail": ["표본 없음"]}
    ts = [t.exit_ts for t in trades]
    order = np.argsort(ts)
    x = np.array([trades[i].net_ret for i in order], dtype=float)
    ts_sorted = [ts[i] for i in order]

    w = _weights(ts_sorted, now, halflife)
    wt_edge = float((w * x).sum() / w.sum()) if w.sum() > 0 else 0.0
    wt_t = _weighted_t(x, w)

    k = max(int(len(x) * RECENT_FRAC), 1)
    recent = x[-k:]
    older = x[:k]
    recent_edge = float(recent.mean())
    older_edge = float(older.mean())
    # 과거가 0 이하면 비율이 무의미 — 최근이 양수인지만 본다.
    if older_edge > 0:
        decay_ratio = recent_edge / older_edge
    else:
        decay_ratio = float("inf") if recent_edge > 0 else 0.0

    raw_tstat = _raw_t(x)

    # 유의성: 전 구간 t 와 최근가중 t 중 **하나라도** 넘으면 통과 (T_MIN 주석 참조)
    cands = [t for t in (raw_tstat, wt_t) if not math.isnan(t)]
    best_t = max(cands) if cands else float("nan")
    carried_by = ("raw_t" if cands and best_t == raw_tstat else
                  "wt_t" if cands else None)

    fails = []
    if len(x) < N_TRADES_MIN:
        fails.append(f"표본 {len(x)} < {N_TRADES_MIN}")
    if math.isnan(best_t) or not (best_t >= T_MIN):
        fails.append(f"t {best_t:.2f} < {T_MIN} "
                     f"(전구간 {raw_tstat:.2f} / 최근가중 {wt_t:.2f} 둘 다 미달)")
    if not (recent_edge > 0):
        fails.append(f"최근 1/3 엣지 {recent_edge*100:+.3f}% <= 0")
    if not (decay_ratio >= DECAY_RATIO_MIN):
        fails.append(f"decay_ratio {decay_ratio:.2f} < {DECAY_RATIO_MIN}")

    return {
        "n_trades": int(len(x)),
        "raw_edge_pct": round(float(x.mean()) * 100, 4),
        "raw_t": None if math.isnan(raw_tstat) else round(raw_tstat, 3),
        "wt_t": None if math.isnan(wt_t) else round(wt_t, 3),
        "t_used": None if math.isnan(best_t) else round(best_t, 3),
        "t_carried_by": carried_by,
        "recent_edge_pct": round(recent_edge * 100, 4),
        "older_edge_pct": round(older_edge * 100, 4),
        "decay_ratio": None if math.isinf(decay_ratio) else round(decay_ratio, 3),
        "wt_edge_pct": round(wt_edge * 100, 4),
        "ok": not fails, "fail": fails,
    }


def evaluate_g2(ctx: ExecContext, g1: dict) -> dict:
    """차단형 게이트. 측정값이 없으면 UNKNOWN 으로 차단한다 —
    '모르니까 통과'는 오늘 사고의 원인이었다."""
    blocks, notes, metrics = [], [], {}

    if ctx.lookahead_clean is None:
        blocks.append("lookahead 미측정")
    elif not ctx.lookahead_clean:
        blocks.append("lookahead 검출")

    base = g1.get("wt_edge_pct")
    if ctx.edge_after_1bar_delay is None:
        blocks.append("지연 후 엣지 미측정")
    elif ctx.roundtrip_friction is None:
        blocks.append("왕복 마찰 미측정")
    else:
        delayed = float(ctx.edge_after_1bar_delay)          # 소수 (0.01 = 1%)
        fric = float(ctx.roundtrip_friction)
        metrics["edge_after_1bar_pct"] = round(delayed * 100, 4)
        metrics["roundtrip_friction_pct"] = round(fric * 100, 4)
        if base:
            metrics["delay_retention"] = round((delayed * 100) / base, 3)  # 참고용만
        headroom = (delayed / fric) if fric > 0 else float("inf")
        metrics["net_headroom"] = round(headroom, 2)
        if delayed <= 0:
            blocks.append(f"지연 후 엣지 {delayed*100:+.4f}% <= 0")
        elif headroom < NET_HEADROOM_MIN:
            blocks.append(f"마찰 대비 여유 {headroom:.2f}x < {NET_HEADROOM_MIN}x "
                          f"(지연후 {delayed*100:.4f}% / 마찰 {fric*100:.4f}%)")

    if ctx.hold_minutes is None or ctx.cycle_minutes is None:
        blocks.append("실행주기 정합 미측정")
    else:
        margin = ctx.hold_minutes / ctx.cycle_minutes if ctx.cycle_minutes > 0 else float("inf")
        metrics["cycle_margin"] = round(margin, 2)
        if margin < CYCLE_MARGIN_MIN:
            blocks.append(f"실행주기 정합 {margin:.1f}x < {CYCLE_MARGIN_MIN}x "
                          f"(보유 {ctx.hold_minutes:.0f}분 / 사이클 {ctx.cycle_minutes:.0f}분)")

    return {"ok": not blocks, "blocked": blocks, "metrics": metrics, "notes": notes}


def evaluate(trades: Sequence[Trade], ctx: ExecContext,
             now: Optional[datetime] = None, label: str = "") -> GateResult:
    g1 = evaluate_g1(trades, now=now)
    g2 = evaluate_g2(ctx, g1)
    passed = bool(g1["ok"] and g2["ok"])
    return GateResult(
        passed=passed,
        blocked_by=(g1.get("fail", []) + g2.get("blocked", [])),
        metrics={"label": label, "G1": g1, "G2": g2},
    )


def render(r: GateResult) -> str:
    g1, g2 = r.metrics["G1"], r.metrics["G2"]
    L = []
    L.append(f"{'='*66}")
    L.append(f"3군 판정 — {r.metrics.get('label','')}")
    L.append(f"{'='*66}")
    L.append("  [G1] 성과 — 유의성(t) + 최근성(recent/decay)")
    L.append(f"    표본                {g1['n_trades']}          기준 >= {N_TRADES_MIN}")
    L.append(f"    거래당 엣지         {g1['raw_edge_pct']:+.4f}%")
    L.append(f"    t (전구간/최근가중)  {g1['raw_t']} / {g1['wt_t']}"
             f"   → 채택 {g1['t_used']} ({g1['t_carried_by']})  기준 >= {T_MIN}")
    L.append(f"    최근 1/3 엣지       {g1['recent_edge_pct']:+.4f}%   기준 > 0")
    L.append(f"    과거 1/3 엣지       {g1['older_edge_pct']:+.4f}%")
    dr = g1['decay_ratio']
    dr_s = "N/A (과거 음수·최근 양수 → 통과)" if dr is None else f"{dr}"
    L.append(f"    decay_ratio         {dr_s}   기준 >= {DECAY_RATIO_MIN}")
    L.append(f"    [진단] 시간가중 엣지 {g1['wt_edge_pct']:+.4f}%"
             f"   (반감기 {HALFLIFE_DAYS:.0f}일, 관문 아님)")
    L.append(f"    → G1 {'PASS' if g1['ok'] else 'FAIL'}")
    for f in g1.get("fail", []):
        L.append(f"       · {f}")
    L.append("  [G2] 실행가능성 (차단형)")
    for k, v in (g2.get("metrics") or {}).items():
        L.append(f"    {k:<20}{v}")
    L.append(f"    → G2 {'PASS' if g2['ok'] else 'BLOCKED'}")
    for b in g2.get("blocked", []):
        L.append(f"       · {b}")
    L.append(f"{'-'*66}")
    L.append(f"  최종: {'PASS → 2군 승격 큐 등록' if r.passed else 'FAIL'}")
    L.append(f"{'='*66}")
    return "\n".join(L)


# ─────────────────────────────────────────────────────── CLI / enqueue ───
# 판정과 큐 등록을 **코드 경로**로 강제한다. 에이전트가 "PASS" 라고 말하는 것에
# 의존하면 2026-08-08 같은 일이 반복된다 — 그날 R-4 PASS 판정은 났지만 이식된
# 스펙은 lookahead 로 성과의 95% 가 허수였다. 등록은 게이트를 통과한 경우에만,
# 그리고 판정 결과 전체를 큐 엔트리에 박아 넣어 governor 가 시드 직전에 다시
# 확인할 수 있게 한다.

def _load_trades(path: str) -> list:
    """[{"entry_ts","exit_ts","net_ret"}, ...] JSON → Trade 목록."""
    import json as _json
    raw = _json.loads(open(path).read())
    rows = raw["trades"] if isinstance(raw, dict) and "trades" in raw else raw
    out = []
    for r in rows:
        out.append(Trade(
            entry_ts=datetime.fromisoformat(str(r["entry_ts"]).replace("Z", "")),
            exit_ts=datetime.fromisoformat(str(r["exit_ts"]).replace("Z", "")),
            net_ret=float(r["net_ret"]),
        ))
    return out


def enqueue(entry: dict, queue_path: str) -> int:
    """승격 큐에 등록. 게이트 결과가 없거나 미통과면 거부한다."""
    import json as _json
    import os as _os
    gate = entry.get("gate") or {}
    if not gate.get("passed"):
        raise ValueError("게이트 미통과 항목은 큐에 등록할 수 없다")
    for k in ("name", "spec", "paradigm", "symbol"):
        if not entry.get(k):
            raise ValueError(f"큐 엔트리에 '{k}' 가 없다")
    if not _os.path.exists(_os.path.join(_os.path.dirname(_os.path.dirname(
            _os.path.dirname(_os.path.abspath(__file__)))), entry["spec"])):
        raise ValueError(f"spec 파일이 없다: {entry['spec']}")
    data = {"queue": []}
    if _os.path.exists(queue_path):
        try:
            data = _json.loads(open(queue_path).read()) or {"queue": []}
        except Exception:
            data = {"queue": []}
    q = data.setdefault("queue", [])
    if any(e.get("name") == entry["name"] for e in q):
        return len(q)  # 멱등
    entry.setdefault("enqueued_at", datetime.utcnow().isoformat(timespec="seconds"))
    q.append(entry)
    tmp = queue_path + ".tmp"
    with open(tmp, "w") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)
    _os.replace(tmp, queue_path)
    return len(q)


def main() -> int:
    import argparse
    import json as _json
    import os as _os

    ap = argparse.ArgumentParser(description="3군 판정 게이트 (G1 시간가중 + G2 실행가능성)")
    ap.add_argument("--trades", required=True, help="거래 JSON (entry_ts/exit_ts/net_ret)")
    ap.add_argument("--label", default="")
    # G2 입력 — 미지정은 UNKNOWN 으로 차단된다
    ap.add_argument("--lookahead-clean", choices=["true", "false"])
    ap.add_argument("--edge-after-1bar", type=float, help="1바 지연 후 거래당 엣지 (0.01=1%%)")
    ap.add_argument("--friction", type=float, help="왕복 마찰 (0.0007=7bp)")
    ap.add_argument("--hold-min", type=float, help="평균 보유(분)")
    ap.add_argument("--cycle-min", type=float, help="실행 사이클 주기(분)")
    ap.add_argument("--out", help="판정 결과 JSON 저장 경로")
    # 통과 시 큐 등록
    ap.add_argument("--enqueue", action="store_true")
    ap.add_argument("--name")
    ap.add_argument("--spec", help="backend 기준 상대경로")
    ap.add_argument("--paradigm")
    ap.add_argument("--symbol")
    ap.add_argument("--queue", default="configs/tier_promotion_queue.json")
    args = ap.parse_args()

    ctx = ExecContext(
        lookahead_clean=(None if args.lookahead_clean is None
                         else args.lookahead_clean == "true"),
        edge_after_1bar_delay=args.edge_after_1bar,
        roundtrip_friction=args.friction,
        hold_minutes=args.hold_min,
        cycle_minutes=args.cycle_min,
    )
    r = evaluate(_load_trades(args.trades), ctx, label=args.label or args.name or "")
    print(render(r))

    payload = {"passed": r.passed, "blocked_by": r.blocked_by, **r.metrics}
    if args.out:
        _os.makedirs(_os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            _json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"판정 저장: {args.out}")

    if args.enqueue:
        if not r.passed:
            print("게이트 미통과 — 큐 등록하지 않는다.")
            return 1
        depth = enqueue({
            "name": args.name, "spec": args.spec, "paradigm": args.paradigm,
            "symbol": args.symbol,
            "gate_score": r.metrics["G1"].get("raw_t") or 0.0,
            "gate": payload,
        }, args.queue)
        print(f"승격 큐 등록 완료 — depth {depth}")
    return 0 if r.passed else 1


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
