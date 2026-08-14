"""신상저격수 파라미터 최적화 — 범용 축 스윕, 표본 밖 분할 **필수**.

설계 근거 `.claude/plans/param_sweep_heatmap_component.md`
표준 형식 `scripts/research/sweep_format.py`

무엇이 MT5 에서 왔나
    MT5 Strategy Tester 는 최적화 UI 에 **Forward 기간을 내장**한다. 표본 밖을
    떼어놓지 않고는 최적화를 시작할 수 없다. 그게 이 스크립트가 `--split` 을
    필수 인자로 두는 이유다.

    2026-08-14 실측이 그 필요를 증명했다. 익절 20칸 격자에서 IS 최고였던
    `d7@tp50/w3`(1338%p, t 2.19)이 표본 밖에서 **-11.4%p** 로 뒤집혔고,
    IS 중위였던 `d14@tp50/w7` 이 표본 밖 1위였다. 분할이 선택 사항이었으면
    그대로 채택했을 것이다.

    반대로 **유전 알고리즘은 들이지 않는다.** 우리 격자는 수십~수백 칸이라
    전수로 충분하고, 확률적 탐색은 교훈 #87(LGBM 세션 재현 불가)과 같은 병을
    새로 들인다. 재현 가능한 전수 탐색이 낫다.

축
    sl       손절 %. **2026-08-14 에 처음 열렸다.** 그전까지 0.50 고정이라
             익절 격자에서 최악 거래가 전 칸 -50.1% 였다 — 축을 안 열면
             위험 쪽은 탐색 자체가 안 된다.
    tp       익절 %. `none` = 없음(현행)
    window   재진입 창(상장 후 일수). 개정된 패러다임 정의가 여는 자유도
    variant  base / h21 / earlyexit_d7 / earlyexit_d14 / bearskip

사용:
  python3 -m scripts.research.lifecycle_optimize \\
      --split 2026-05-13 \\
      --axis variant=base,earlyexit_d7,bearskip \\
      --axis sl=0.3,0.5,0.7 \\
      --axis tp=none,30,50 \\
      --axis window=3,7
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lc_optimize")

OUT = ROOT / "runs" / "research_track" / "lifecycle_optimize.json"

VARIANT_SPEC = {                       # 이름 → (보유일, 조기청산일, 정책)
    "base": (30, None, "baseline"),
    "h21": (21, None, "baseline"),
    "earlyexit_d7": (30, 7, "early_exit"),
    "earlyexit_d14": (30, 14, "early_exit"),
    "bearskip": (30, None, "bear_skip"),
}

# 손절 물리 하한. 진입 바 일중 상승폭 p50 이 10.5% 이므로 그 언저리 아래는
# 절반 넘는 사건에서 손절이 무력화된다. 0.20 이면 무력화 32%, 0.30 이면 20%.
# 완전히 깨끗한 값은 없다 — 0.50 에서도 8.8% 는 무력화된다.
SL_FLOOR = 0.20

# ── 위약 (교훈 #85) ────────────────────────────────────────────────────
# 신상저격수는 **사건 가설**(상장)이다. 기억의 교훈 #85:
#   "사건가설은 '사건 안 겪는 대조군' + '같은 사건 다른 시각' 두 위약 의무"
# 그런데 최적화기에는 위약이 하나도 없었다. 135칸에서 최고를 고르는 것 자체가
# 다중검정인데, "이 자산군이면 아무 날에 숏 쳐도 이만큼 나오는가"를 안 봤다.
#
# `placebo_days` 축이 그 대조군을 만든다 — 상장일을 N일 뒤로 **가짜로** 옮겨
# 같은 종목·같은 규칙을 상장 사건이 없는 시점에 적용한다.
#   0   진짜 상장일 (관측)
#   60  상장 두 달 뒤 — 같은 자산, 사건 없음
#   120 넉 달 뒤
# 위약 칸이 관측 칸과 비슷하면 **엣지는 상장이 아니라 자산군 드리프트**다.
PLACEBO_AXIS = "placebo_days"

# 두 번째 위약 — **사건 안 겪는 대조군**.
#   `placebo_days=control` 이면 같은 **날짜**에 이미 오래 상장된 종목으로
#   같은 규칙을 돌린다. 달력·시장 국면은 같고 다른 것은 "신규 상장인가"뿐이다.
#
#   +60일 위약이 "같은 종목 다른 시각"을 물었다면, 이건 "같은 시각 다른 종목"을
#   묻는다. 둘 다 관측에 근접하면 남는 설명은 **알트코인 전반의 하락 드리프트**다.
#
#   대조 종목은 **결정적으로** 고른다(정렬 후 인덱스). 무작위를 쓰면 재현이
#   깨진다 — 교훈 #87.
CONTROL_VALUE = "control"
CONTROL_MIN_AGE_DAYS = 180      # 이만큼 지난 종목만 '기성'으로 본다
# 사건당 대조 종목 수. 1개면 표본이 너무 얇아 위약 분포를 못 만든다
# (실측: 25사건 → 대조 거래 5건). 위약은 "귀무가 어떻게 생겼나"를 재는
# 것이므로 표본이 많을수록 낫다.
CONTROL_PER_EVENT = 3

DEFAULT_AXES = {
    "variant": ["base", "earlyexit_d7", "bearskip"],
    "sl": [0.3, 0.5, 0.7],
    "tp": ["none", 30, 50],
    "window": [3, 7],
}

# 짧은 별칭 → 실제 스펙 경로. 축 이름은 이제 **제한이 없다** —
# `policy.entry_threshold` 처럼 아무 kwargs 나 열 수 있고, 이 표는 편의일 뿐이다.
# (2026-08-14 첫 판은 네 개를 화이트리스트했다. 그러면 계열마다 임시 스크립트를
#  또 만들게 된다 — 오늘 손계산 6개가 그렇게 생겼다.)
AXIS_ALIAS = {
    "sl": "policy.sl_pct",
    "tp": "policy.tp_pct",
    "window": "source.entry_window_days",
}

# 별칭과 정식 경로를 **같은 축**으로 본다.
#
# 2026-08-14: `--axis policy.sl_pct=...` 를 주면 기본 축 `sl` 이 그대로 남아
# 두 축이 **같은 스펙 경로에 두 번** 쓰였다. 조합이 3배로 불어나고(120 → 360)
# `sl` 열은 뒤에 쓰인 값에 덮여 의미를 잃는다. 축 이름을 정규화해 막는다.
ALIAS_OF = {v: k for k, v in AXIS_ALIAS.items()}


def canon_axis(name: str) -> str:
    """`policy.sl_pct` → `sl`. 별칭이 없으면 그대로."""
    return ALIAS_OF.get(name, name)


def alias_value(axis: str, v):
    """별칭 축의 값 변환. `tp=30` 은 30% 를 뜻하므로 0.30 으로, `none` 은
    1.0(=tp_price 0.0, 커널이 비활성으로 읽음)으로 바꾼다."""
    if axis == "tp":
        if isinstance(v, str) and v.lower() in ("none", "off", ""):
            return 1.0
        return float(v) / 100.0
    return v


def preflight(combos: list, names: list) -> None:
    """모든 조합의 스펙이 실제로 조립되는지 먼저 확인한다. 실패 시 SystemExit."""
    from research.lifecycle_session_spawner import build_session_spec
    from research.sweep_engine import apply_all
    from app.composer_framework.pipeline_spec import build_pipeline

    for combo in combos:
        kw = dict(zip(names, combo))
        variant = kw.get("variant", "base")
        hold, early, pv = VARIANT_SPEC[variant]
        spec = build_session_spec(
            "BTCUSDT", "2026-01-01", policy_variant=pv,
            early_exit_check_day=(early or 14), baseline_hold_days=hold,
            bear_skip_btc_30d_pre_ret=0.0)
        inject = {AXIS_ALIAS.get(k, k): alias_value(k, v)
                  for k, v in kw.items() if k not in ("variant", PLACEBO_AXIS)}
        try:
            build_pipeline(apply_all(spec["pipeline_spec"], inject), {})
        except Exception as exc:
            raise SystemExit(
                f"사전 점검 실패 — 조합 {kw}\n"
                f"  {type(exc).__name__}: {exc}\n"
                f"  축 이름을 확인하라: python3 -m scripts.research.lifecycle_optimize "
                f"--split ... --list-axes")
    log.info("사전 점검 통과 — %d칸 전부 조립됨", len(combos))


def run_combo(sym: str, ld, kw: dict, bars_daily):
    """한 조합 실행. **스펙을 여기서 다시 쓰지 않는다** — CANON 세션과 같은
    `build_session_spec` 이 만든 것에 축 값만 주입한다(교훈 #88)."""
    from research.lifecycle_canon_backtest import btc_pre_ret  # noqa: E402
    from research.lifecycle_session_spawner import build_session_spec  # noqa: E402
    from research.sweep_engine import apply_all  # noqa: E402

    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import SourceContext

    variant = kw.get("variant", "base")
    hold, early, pv = VARIANT_SPEC[variant]
    pre_ret = None
    if pv == "bear_skip":
        pre_ret = btc_pre_ret(str(ld))
        if pre_ret is None:
            return []                     # 레짐 미상 — 표본 밖
    spec = build_session_spec(
        sym, str(ld), policy_variant=pv, early_exit_check_day=(early or 14),
        early_exit_vc_threshold=0.40, baseline_hold_days=hold,
        bear_skip_btc_30d_pre_ret=pre_ret, bear_skip_threshold=-0.05)

    inject = {}
    for ax, v in kw.items():
        if ax in ("variant", PLACEBO_AXIS):   # 위약은 상장일 자체를 옮긴다
            continue
        path = AXIS_ALIAS.get(ax, ax)
        if path in inject:           # 정규화가 뚫렸다면 여기서 잡는다
            raise SystemExit(f"축 충돌 — `{path}` 에 두 축이 쓰려 한다: {sorted(kw)}")
        inject[path] = alias_value(ax, v)
    ps = apply_all(spec["pipeline_spec"], inject)

    ctx = SourceContext(symbol=sym,
                        eval_freq_minutes=ps["config"]["eval_freq_minutes"],
                        ohlcv_1m=None, ohlcv_eval=bars_daily)
    bt = GenericBacktester(initial_capital=float(spec["initial_capital"]),
                           fee_rate=float(spec["fee_rate"]),
                           apply_fee_to_short=True)
    # signal_lag_bars=1 — 신상저격수 소스는 달력 규칙이라 밀어야 Day-1 종가에
    # 들어간다. 안 밀면 상장가에 들어가 t 1.64 가 -0.12 가 된다(교훈 #90)
    return bt.run_rule_based(pipeline=build_pipeline(ps, {}), ctx=ctx,
                             signal_lag_bars=1).trades


def stats(a: np.ndarray) -> dict:
    if len(a) == 0:
        return {"n_trades": 0}
    if len(a) < 2:
        return {"n_trades": int(len(a)), "total_ret": float(a.sum()),
                "mean": float(a[0]), "worst": float(a[0])}
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {
        "n_trades": int(len(a)),
        "total_ret": float(a.sum()),
        "mean": float(a.mean()),
        "med": float(np.median(a)),
        "win": float(100 * (a > 0).mean()),
        "t": float(a.mean() / se) if se else None,
        "worst": float(a.min()),
        "std": float(a.std(ddof=1)),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="신상저격수 파라미터 최적화")
    p.add_argument("--split", required=True,
                   help="표본 안/밖 분할 상장일 (필수). 이 날 **이후** 상장이 표본 밖")
    p.add_argument("--axis", action="append", default=[],
                   help="축 선언. 예 sl=0.3,0.5,0.7 · 반복 가능")
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--limit", type=int, default=0, help="앞에서 N 사건만")
    p.add_argument("--allow-thin-sl", action="store_true",
                   help="손절 물리 하한을 무시한다. **수치를 믿지 말 것** — "
                        "일봉 판정에서 좁은 손절은 진입 바에 무력화된다")
    p.add_argument("--data-days", type=int, default=0,
                   help="시뮬 데이터 구간(상장 후 일수). 기본은 코호트 창과 같다. "
                        "재진입 창+보유가 길면 늘려야 강제 마감이 안 생긴다")
    p.add_argument("--list-axes", action="store_true",
                   help="이 계열에서 스윕 가능한 축을 출력하고 종료")
    a = p.parse_args()

    from research.lifecycle_canon_backtest import (  # noqa: E402
        LISTINGS, MIN_DAILY_BARS, WINDOW_DAYS, daily_bars,
    )
    from research.sweep_format import SweepWriter  # noqa: E402

    if a.list_axes:
        from research.lifecycle_session_spawner import build_session_spec
        from research.sweep_engine import describe
        for v, (hold, early, pv) in VARIANT_SPEC.items():
            sp = build_session_spec("XUSDT", "2026-01-01", policy_variant=pv,
                                    early_exit_check_day=(early or 14),
                                    baseline_hold_days=hold,
                                    bear_skip_btc_30d_pre_ret=0.0)
            print(f"[{v}]", json.dumps(describe(sp["pipeline_spec"]),
                                       ensure_ascii=False))
        print("\n별칭:", AXIS_ALIAS)
        return 0

    axes = dict(DEFAULT_AXES)
    for spec in a.axis:
        from research.sweep_engine import parse_axis
        k, v = parse_axis(spec)
        axes[canon_axis(k)] = v      # 별칭 정규화 — 같은 경로에 두 번 쓰지 않는다
    for v in axes.get("variant", []):
        if v not in VARIANT_SPEC:
            raise SystemExit(f"모르는 변형: {v}. 가능: {sorted(VARIANT_SPEC)}")

    names = list(axes)
    combos = list(product(*(axes[k] for k in names)))
    log.info("축 %s · 조합 %d칸 · 분할 %s", {k: len(v) for k, v in axes.items()},
             len(combos), a.split)

    # ── 손절 물리 하한 ────────────────────────────────────────────────
    # 커널은 **진입한 바에서 SL/TP 를 검사하지 않는다.** 일봉 하나 안에서
    # 시가 진입과 고가 도달의 순서를 알 수 없기 때문이고, 그 선택은 보수적으로
    # 옳다(같은 바에서 검사하면 고가가 진입 앞에 온 경우까지 손절 처리해
    # 미래를 참조한다).
    #
    # 부작용은 손절 폭에 따라 달라진다. 진입 바의 (고가-시가)/시가 실측
    # (251 사건): p50 10.5% · p75 25.4% · 평균 21.0%.
    #   sl  2% → 89.2% 사건에서 무력화      sl 20% → 32.3%
    #   sl  5% → 72.1%                      sl 50% →  8.8%
    # 즉 **손절을 좁힐수록 손절이 사라진다.** 2026-08-14 에 이걸 모르고
    # sl 0.02 까지 훑어 IS t 17.55 를 얻었는데, 엣지가 아니라 위험 관리가
    # 꺼진 정도를 잰 것이었다.
    #
    # 좁은 손절을 진짜로 보려면 **1분봉 판정**이 필요하다. 일봉 스윕으로는
    # 답할 수 없는 질문이므로 여기서 막는다.
    sls = [float(v) for v in axes.get("sl", []) if isinstance(v, (int, float))]
    if sls and min(sls) < SL_FLOOR and not a.allow_thin_sl:
        raise SystemExit(
            f"손절 {min(sls):.2%} 는 물리 하한 {SL_FLOOR:.0%} 아래다.\n"
            f"  진입 바 일중 상승폭 실측: p50 10.5% · p75 25.4%\n"
            f"  → 이 폭에서는 손절이 진입 바에 이미 넘겨져 **작동하지 않는다**.\n"
            f"  일봉으로 판정하는 한 이 구간의 수치는 위험 관리가 꺼진 결과다.\n"
            f"  정말 보려면 --allow-thin-sl (수치를 믿지 말 것) 또는 1분봉 판정.")

    # ── 사전 점검 ──────────────────────────────────────────────────────
    # 오타 난 축이 사건마다 경고만 남기고 **거래 0건짜리 결과**를 만들어내면
    # 안 된다. 그건 실패가 아니라 조용한 오답이고, 교훈 #88 이 정확히 그 병이다
    # (스펙에 넣은 값이 팩토리에서 사라져 재진입 차단이 한 번도 안 돌았다).
    # 첫 조합으로 파이프라인을 실제 조립해 보고, 안 되면 **즉시 멈춘다.**
    preflight(combos, names)

    raw_pl = axes.get(PLACEBO_AXIS, [0])
    use_control = any(str(x).lower() == CONTROL_VALUE for x in raw_pl)
    placebo_offsets = sorted({int(x or 0) for x in raw_pl
                              if str(x).lower() != CONTROL_VALUE})
    if use_control:
        log.info("대조군 위약 사용 — 같은 날짜, 상장 %d일 이상 지난 종목",
                 CONTROL_MIN_AGE_DAYS)
    if placebo_offsets != [0]:
        log.info("위약 오프셋 %s일 — 0 은 진짜 상장일(관측)", placebo_offsets)

    data_days = a.data_days or WINDOW_DAYS
    if data_days > WINDOW_DAYS:
        log.info("시뮬 데이터 구간 %d일 (코호트 선별은 %d일로 고정)",
                 data_days, WINDOW_DAYS)

    listings = json.load(open(LISTINGS))
    from app.db.session import engine

    def control_symbols(sym: str, ld) -> list[str]:
        """이 사건의 대조 종목들. 같은 날짜에 이미 오래 상장돼 있던 것.

        **결정적으로** 고른다 — 정렬한 풀에서 일정 간격으로 집는다. 무작위를
        쓰면 재현이 깨진다(교훈 #87).
        """
        pool = sorted(
            k for k, m in listings.items()
            if m.get("onboard_date")
            and (ld - datetime.strptime(m["onboard_date"], "%Y-%m-%d").date()).days
            >= CONTROL_MIN_AGE_DAYS)
        if not pool:
            return []
        base = sum(ord(c) for c in sym) % len(pool)
        step = max(1, len(pool) // CONTROL_PER_EVENT)
        return [pool[(base + i * step) % len(pool)]
                for i in range(min(CONTROL_PER_EVENT, len(pool)))]

    # (조합 키) → {"IS": [수익률...], "OOS": [...]}
    bucket: dict[tuple, dict[str, list]] = {c: {"IS": [], "OOS": []} for c in combos}
    # 데이터 끝에서 강제 마감된 거래 — 많으면 그 칸의 수치는 창 길이의
    # 산물이지 전략의 결과가 아니다
    eod: dict[tuple, dict[str, int]] = {c: {"IS": 0, "OOS": 0} for c in combos}
    # 청산 사유별 횟수. **발동 0 인 축은 죽은 축**이다 — 값을 바꿔도 아무 일이
    # 일어나지 않았다는 뜻이고, 그건 탐색된 게 아니다.
    # 2026-08-14: sl 을 0.02 까지 좁히자 손절이 한 번도 안 걸렸는데 지표에
    # 없어서 안 보였다. IS t 가 3.19 → 17.55 로 오른 것이 '엣지'가 아니라
    # '손절이 꺼지는 정도'였다.
    reasons: dict[tuple, dict[str, dict]] = {
        c: {"IS": {}, "OOS": {}} for c in combos}
    n_events = {"IS": 0, "OOS": 0}
    win_lo, win_hi = None, None

    with engine.connect() as conn:
        items = sorted(listings.items())
        used = 0
        for i, (sym, meta) in enumerate(items, 1):
            od = meta.get("onboard_date")
            if not od:
                continue
            ld = datetime.strptime(od, "%Y-%m-%d").date()
            # **코호트 선별은 항상 같은 창(35일)으로 한다.** 데이터 구간을
            # 넓힌다고 표본이 달라지면 이전 실행과 비교가 깨진다 — 넓힌 건
            # 시뮬이 쓸 봉이지 선별 기준이 아니다.
            gate = daily_bars(conn, sym, ld, ld + timedelta(days=WINDOW_DAYS))
            if len(gate) < MIN_DAILY_BARS:
                continue
            used += 1
            # 위약 오프셋마다 다른 구간이 필요하다. 한 번씩만 읽어 캐시한다.
            bars_by_off: dict[object, object] = {}
            if use_control:
                ctls = []
                for cs in control_symbols(sym, ld):
                    cd = daily_bars(conn, cs, ld, ld + timedelta(days=data_days))
                    if len(cd) >= MIN_DAILY_BARS:
                        ctls.append((cd, cs))
                if ctls:
                    bars_by_off[CONTROL_VALUE] = ctls
            for off in placebo_offsets:
                a0 = ld + timedelta(days=off)
                b = a0 + timedelta(days=data_days)
                dd = gate if (off == 0 and data_days <= WINDOW_DAYS) \
                    else daily_bars(conn, sym, a0, b)
                if len(dd) >= MIN_DAILY_BARS:
                    bars_by_off[off] = dd
            side = "OOS" if od >= a.split else "IS"
            n_events[side] += 1
            win_lo = od if win_lo is None or od < win_lo else win_lo
            win_hi = od if win_hi is None or od > win_hi else win_hi

            for combo in combos:
                kw = dict(zip(names, combo))
                pv_raw = kw.get(PLACEBO_AXIS, 0)
                is_ctl = str(pv_raw).lower() == CONTROL_VALUE
                got = bars_by_off.get(CONTROL_VALUE if is_ctl else int(pv_raw or 0))
                if got is None:
                    continue           # 그 오프셋/대조군에 데이터가 모자란 사건
                # 대조군은 사건당 여러 종목이라 목록으로 돈다
                runs = (got if is_ctl
                        else [(got, sym)])
                run_ld = (ld if is_ctl
                          else ld + timedelta(days=int(pv_raw or 0)))
                trades = []
                for dl, run_sym in runs:
                    try:
                        trades += run_combo(run_sym, run_ld, kw, dl)
                    except Exception as exc:
                        log.warning("%s %s 실패: %s", run_sym, kw, exc)
                if not trades:          # bearskip 억제 또는 진입 없음 = 표본 밖
                    continue
                bucket[combo][side].extend(float(t.return_pct) * 100
                                           for t in trades)
                eod[combo][side] += sum(1 for t in trades
                                        if t.exit_reason in ("eod", "close_at_end"))
                for t in trades:
                    rc = reasons[combo][side]
                    rc[t.exit_reason] = rc.get(t.exit_reason, 0) + 1
            if a.limit and used >= a.limit:
                break
            if i % 100 == 0:
                log.info("%d/%d (사용 %d)", i, len(items), used)

    w = SweepWriter(
        script="scripts/research/lifecycle_optimize.py",
        engine="canon_kernel", root=ROOT, split_date=a.split, axes=axes,
        data_window={"start": win_lo, "end": win_hi,
                     "is_events": n_events["IS"], "oos_events": n_events["OOS"],
                     "cohort_window_days": WINDOW_DAYS, "sim_data_days": data_days},
        notes=("표본 밖 = 분할일 이후 상장. 지표는 **거래 기준**(재진입 포함). "
               "total_ret 은 거래별 수익률의 합(%p, 복리 아님)."))
    for combo in combos:
        kw = dict(zip(names, combo))
        for side in ("IS", "OOS"):
            m = stats(np.array(bucket[combo][side]))
            n = m.get("n_trades") or 0
            m["eod_exits"] = eod[combo][side]
            m["eod_pct"] = (100.0 * eod[combo][side] / n) if n else None
            rc = reasons[combo][side]
            m["sl_exits"] = rc.get("sl", 0)
            m["tp_exits"] = rc.get("tp", 0)
            m["time_exits"] = rc.get("time", 0)
            w.add(axis_values=kw, metrics=m, split=side)
    d = w.write(a.out)

    # ── 요약 ──
    print("=" * 92)
    print(f"신상저격수 최적화 — {len(combos)}칸 · 분할 {a.split} "
          f"(IS 사건 {n_events['IS']} / OOS 사건 {n_events['OOS']})")
    print("=" * 92)
    hdr = "".join(f"{k:>10}" for k in names)
    print(f"  {hdr}{'IS 거래':>8}{'IS 총%p':>10}{'IS t':>7}"
          f"{'OOS 거래':>9}{'OOS 총%p':>10}{'OOS 평균':>9}{'OOS t':>7}")
    rows = {(r["split"], tuple(r[k] for k in names)): r for r in d["results"]}
    for combo in sorted(combos, key=lambda c: -(rows.get(("IS", c), {}).get("total_ret") or 0)):
        i_, o_ = rows.get(("IS", combo), {}), rows.get(("OOS", combo), {})
        vals = "".join(f"{str(v):>10}" for v in combo)
        print(f"  {vals}{i_.get('n_trades', 0):>8}{i_.get('total_ret', 0):>10.0f}"
              f"{(i_.get('t') or 0):>7.2f}{o_.get('n_trades', 0):>9}"
              f"{o_.get('total_ret', 0):>10.1f}{(o_.get('mean') or 0):>9.2f}"
              f"{(o_.get('t') or 0):>7.2f}")
    print("-" * 92)
    print("  IS 총%p 내림차순. **IS 최고를 채택하지 마라** — 고원 판정을 거쳐라:")
    print("    python3 -m scripts.research.plateau_select --file", a.out)
    print("=" * 92)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
