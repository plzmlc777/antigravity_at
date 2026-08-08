#!/usr/bin/env python3
"""3군 판정 엔진 — 시간가중 성과(G1) + 실행가능성(G2).

설계 근거: .claude/plans/tier3_redesign.md (2026-08-08 대표님 지시 재설계)

기존 R-1~R-4 elite gate 를 대체한다. 관문의 층을 바꾼 것이 핵심이다 —
자금 위험이 0인 3군에서 실전급 기준(R-4 Hard Gate: 기존 24세션 중 2개만 통과)을
요구하니 79일간 배출이 0이었고, 정작 검증장인 2군은 11석이 비어 있었다.
과적합 판별은 2군 forward(alpha<0 → TERMINATE)에 위임하고, 3군은
**"실전에서 재현될 수 있는 후보인가"** 만 책임진다.

G1 — 시간가중 성과 (단일 종목·단일 스펙으로 판정. 다종목 요구 폐기)
  과거 균등가중 대신 최근에 가중한다: w_i = exp(-ln2 · age_i / H), H=반감기.
  핵심은 decay_ratio — 과거에만 좋고 최근에 죽은 전략을 거른다.

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
WT_T_MIN = 1.5           # 시간가중 t-stat (기존 2.0 에서 완화 — 뒤에 2군 forward 가 있다)
RECENT_FRAC = 1.0 / 3.0  # "최근 구간" 비율
DECAY_RATIO_MIN = 0.30   # 최근/과거 엣지 비율
N_TRADES_MIN = 20

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

    fails = []
    if len(x) < N_TRADES_MIN:
        fails.append(f"표본 {len(x)} < {N_TRADES_MIN}")
    if not (wt_edge > 0):
        fails.append(f"시간가중 엣지 {wt_edge*100:+.3f}% <= 0")
    if not (wt_t >= WT_T_MIN) or math.isnan(wt_t):
        fails.append(f"시간가중 t {wt_t:.2f} < {WT_T_MIN}")
    if not (recent_edge > 0):
        fails.append(f"최근 1/3 엣지 {recent_edge*100:+.3f}% <= 0")
    if not (decay_ratio >= DECAY_RATIO_MIN):
        fails.append(f"decay_ratio {decay_ratio:.2f} < {DECAY_RATIO_MIN}")

    return {
        "n_trades": int(len(x)),
        "wt_edge_pct": round(wt_edge * 100, 4),
        "wt_t": None if math.isnan(wt_t) else round(wt_t, 3),
        "recent_edge_pct": round(recent_edge * 100, 4),
        "older_edge_pct": round(older_edge * 100, 4),
        "decay_ratio": None if math.isinf(decay_ratio) else round(decay_ratio, 3),
        "raw_edge_pct": round(float(x.mean()) * 100, 4),
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
    L.append("  [G1] 시간가중 성과")
    L.append(f"    표본                {g1['n_trades']}")
    L.append(f"    단순 엣지           {g1['raw_edge_pct']:+.4f}%")
    L.append(f"    시간가중 엣지       {g1['wt_edge_pct']:+.4f}%   (반감기 {HALFLIFE_DAYS:.0f}일)")
    L.append(f"    시간가중 t          {g1['wt_t']}          기준 >= {WT_T_MIN}")
    L.append(f"    최근 1/3 엣지       {g1['recent_edge_pct']:+.4f}%   기준 > 0")
    L.append(f"    과거 1/3 엣지       {g1['older_edge_pct']:+.4f}%")
    dr = g1['decay_ratio']
    dr_s = "N/A (과거 음수·최근 양수 → 통과)" if dr is None else f"{dr}"
    L.append(f"    decay_ratio         {dr_s}   기준 >= {DECAY_RATIO_MIN}")
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
