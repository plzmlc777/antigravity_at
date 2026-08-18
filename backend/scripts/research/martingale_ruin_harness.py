"""마틴게일(물타기) **파산 하네스** — 배수·스텝 격자 × 전 종목 × 전 기간.

무엇을 묻는가
    그룹 C(2026-08-11)는 마틴게일 7가설을 전부 닫았다. 그러나 그때 측정한
    것은 **손익**이었고 파산은 부수적으로 셌다 — 33종목·60일·**사이클 1회**
    (파산하면 그 종목은 거기서 끝). 그래서 다음을 모른다:

        · 파산이 **얼마나 자주** 오는가 (사이클당 비율)
        · 파산이 **언제** 오는가 (사이클 시작 후 몇 시간, 어떤 국면)
        · 파산 당시 **시장이 무엇을 하고 있었나**
        · 그 비율이 **종목마다 다른가**

    이 하네스는 파산해도 자본을 리셋하고 **계속 돈다**. 그래서 종목·설정마다
    사이클이 수백~수천 개 쌓이고, 승률과 파산률이 비율로 나온다.

⚠ 파산은 백테스트에서 **반드시 계상해야** 한다
    한도 없이 물타면 백테스트는 항상 이긴다. 그게 마틴게일의 거짓말이다.
    여기서 파산은 두 가지로 온다:
        ① 미실현 손실 >= 자본        → 강제청산 (테이커 마찰)
        ② 다음 계단 명목 > 자본×레버리지 → 못 채운다 (계단 중단, 파산 아님)
    ②를 안 넣으면 **자금 조달이 불가능한 사다리**를 공짜로 태우게 된다.

⚠ 봉 안의 순서는 모른다 — **불리한 쪽을 먼저** 본다
    1h 봉은 고가·저가 중 무엇이 먼저인지 말해주지 않는다. 파산을 재는 것이
    목적이므로 불리한 극단(롱이면 저가)을 먼저 처리한다. 같은 봉에서 물타기와
    익절이 동시에 걸리는 **모호한 봉의 비율을 반드시 출력**하고, `close_only`
    민감도판을 같이 낸다. 결론이 뒤집히면 그렇게 적는다.

설계 원칙 — `.claude` 하네스 구성 규칙 7종을 그대로 따른다
    ① 설정은 `MartingaleConfig` **한 곳**. 모듈 상수 임계값 금지
    ② `verify_reaches()` 가 **파라미터 도달을 증명**한다 (교훈 #88)
    ③ **방향은 파라미터** — 롱/숏을 가정하는 코드·문구 금지 (교훈 #91)
    ④ 출력 경로는 설정에서 **유도**
    ⑤ 손익 커널은 **한 경로**. jit 판과 참조판을 교차검증해 일치를 증명한다
    ⑥ 관측 단위는 **사이클**. 봉을 독립 표본으로 세지 않는다
    ⑦ 결과 파일에 **설정 전문**을 박는다 + 검정력 사전검사

⚠ 숏 수익률 규약 (교훈 #89)
    `(진입-청산)/진입` 을 쓴다. `진입/청산-1` 은 상한이 없어 평균만 부풀고
    중앙값·승률은 안 움직여서 **안 보인다**.

사용:
  python3 -m scripts.research.martingale_ruin_harness --selftest
  python3 -m scripts.research.martingale_ruin_harness --side long
  python3 -m scripts.research.martingale_ruin_harness --side long --null shuffle
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mart_ruin")

OUT_DIR = ROOT / "runs" / "research_track" / "martingale_ruin"

# 사이클 결과 코드
WIN, RUIN, CENSORED, STOP = 0, 1, 2, 3
# 사이클 기록 열
C_START, C_END, C_OUT, C_PNL, C_RUNGS, C_P0, C_AVG, C_PX, C_MAE, C_NOT, C_AMB = range(11)
N_COLS = 11


# ══════════════════════════════════════════════════════════════════════
#  ① 설정은 여기 **한 곳**에만 있다
# ══════════════════════════════════════════════════════════════════════
@dataclass
class MartingaleConfig:
    """모든 파라미터. 새 항목을 넣으면 ② `verify_reaches` 에도 반드시 넣어라."""
    # ── 사다리 규칙 ──────────────────────────────────────────────
    side: str = "long"            # long | short  (③ 방향은 파라미터)
    step_bp: float = 200.0        # **스텝값** — 직전 체결가에서 이만큼 불리해지면 물탄다
    multiplier: float = 2.0       # **물타기 배수** — 다음 계단 크기 = 직전 × 배수
    max_rungs: int = 10           # 최대 계단 수
    tp_ratio: float = 1.0         # 익절폭 = step_bp × 이 비율 (평단 기준)

    # ── 자본·파산 ────────────────────────────────────────────────
    capital_units: float = 30.0   # 자본 = 1계단 명목의 몇 배
    leverage: float = 5.0         # 최대 누적 명목 = 자본 × 레버리지

    # ── 손절 ────────────────────────────────────────────────────
    sl_capital: float = 1.0       # **손절** — 미실현 손실이 초기자본의 이 비율에
                                  #   닿으면 바구니 전량 청산. 1.0 이면 손절 없음
                                  #   (그때는 자본 소진 = 파산까지 간다)
    stop_fill: str = "level"      # level | extreme
    # ⚠ level : 손절가에서 체결됐다고 본다 (지정손절 이상적 체결)
    #   extreme: 그 봉의 불리한 극단에서 체결됐다고 본다 (갭 최악)
    #   실제는 둘 사이다. **둘 다 돌려 결론이 갈리는지 본다.**

    # ── 계좌 모형 ────────────────────────────────────────────────
    persist_equity: bool = False  # True = 자본이 사이클을 가로질러 누적된다
    stop_on_ruin: bool = False    # True = 파산하면 그 종목 테스트를 **종료**
    # ⚠ 이 둘을 켜면 파산률의 뜻이 바뀐다 — 사이클당 비율이 아니라
    #   **종목당 생존 여부**가 된다. 판독에서 절대 섞지 마라.
    # ⚠ capital_units 는 "1계단 명목" 단위다. 배수 2·10계단이면 누적 명목이
    #   1023 단위라 레버리지 제약이 먼저 걸린다 — 그게 현실이다.

    # ── 마찰 ────────────────────────────────────────────────────
    fee_entry_bp: float = 2.0     # 지정가 물타기 = 메이커
    fee_tp_bp: float = 2.0        # 지정가 익절 = 메이커
    fee_ruin_bp: float = 5.0      # 강제청산 = 테이커

    # ── 체결 규약 ────────────────────────────────────────────────
    intrabar: str = "strict"      # strict | adverse_first | close_only
    # ⚠ **strict 가 기본이다.** 1h 봉은 고가·저가 순서를 말해주지 않는다.
    #   같은 봉에서 물타고 그 봉 안에서 익절하면 "저가에 사서 고가에 판" 것이
    #   되어 백테스트가 공짜로 이긴다 — 첫 스모크에서 모호봉 **64.7%** ·
    #   승률 100% · ROI +686% 가 그렇게 나왔다 (교훈 #83, 체결 정직성).
    #   strict 는 물타기가 발생한 봉에서는 **익절을 다음 봉으로 미룬다.**
    reenter_gap_bars: int = 1     # 사이클 종료 후 재진입까지 대기 봉수

    # ── 진입 필터 ────────────────────────────────────────────────
    entry_filter: str = "none"    # none | rv7 | ret30 | dd30
    filter_mode: str = "low"      # low = 순위 <= 문턱일 때만 진입 / high = 그 반대
    filter_thr: float = 1.0       # 자기이력 롤링 백분위 문턱 (0~1)
    # ⚠ **양방향을 반드시 같이 돌린다.** low 만 돌리면 high 가 더 나았을
    #   가능성을 못 본다. 그리고 필터 격자를 뒤지는 순간 검정이 여러 번이 되므로
    #   **최대통계량 귀무**가 필요하다 (교훈 #95) — 필터 원형회전 위약을 쓴다.
    # ⚠ 순위는 **과거 봉만**으로 만든다. 전 구간 분위로 자르면 미래참조다.

    # ── 표본 ────────────────────────────────────────────────────
    min_bars: int = 500           # 이보다 짧은 종목은 제외
    min_cycles_judge: int = 30    # ⑦ 이보다 사이클이 적으면 **판정하지 않는다**

    def __post_init__(self):
        if self.side not in ("long", "short"):
            raise SystemExit(f"side 는 long|short — 받은 값 {self.side!r}")
        if self.multiplier < 1.0:
            raise SystemExit("배수 < 1.0 은 물타기가 아니다 (역피라미딩)")
        if self.step_bp <= 0 or self.tp_ratio <= 0:
            raise SystemExit("스텝·익절폭은 양수여야 한다")
        if self.capital_units <= 0 or self.leverage <= 0:
            raise SystemExit("자본·레버리지는 양수여야 한다")
        if self.intrabar not in ("strict", "adverse_first", "close_only"):
            raise SystemExit(
                f"intrabar 는 strict|adverse_first|close_only — {self.intrabar!r}")
        if not (0.0 < self.sl_capital <= 1.0):
            raise SystemExit(f"손절은 (0, 1.0] — 받은 값 {self.sl_capital!r}")
        if self.stop_fill not in ("level", "extreme"):
            raise SystemExit(f"stop_fill 은 level|extreme — {self.stop_fill!r}")
        if self.entry_filter not in ("none", "rv7", "ret30", "dd30", "rsi"):
            raise SystemExit(f"entry_filter 는 none|rv7|ret30|dd30|rsi — "
                             f"{self.entry_filter!r}")
        if self.filter_mode not in ("low", "high"):
            raise SystemExit(f"filter_mode 는 low|high — {self.filter_mode!r}")
        if not (0.0 < self.filter_thr <= 1.0):
            raise SystemExit(f"filter_thr 는 (0, 1.0] — {self.filter_thr!r}")
        if self.stop_on_ruin and not self.persist_equity:
            raise SystemExit(
                "stop_on_ruin 은 persist_equity 와 함께 써야 한다 — 자본이 "
                "리셋되는데 '한 번 파산하면 종료'는 뜻이 없다")

    @property
    def d(self) -> int:
        """③ 방향 부호. 롱 +1 / 숏 -1. 코드 어디에도 side 문자열 분기를 두지 않는다."""
        return 1 if self.side == "long" else -1

    @property
    def step(self) -> float:
        return self.step_bp / 1e4

    @property
    def tp(self) -> float:
        return self.step_bp * self.tp_ratio / 1e4

    def key(self) -> str:
        f = ("nofilter" if self.entry_filter == "none"
             else f"{self.entry_filter}{self.filter_mode}{self.filter_thr:g}")
        return (f"{self.side}_s{self.step_bp:g}_m{self.multiplier:g}"
                f"_c{self.capital_units:g}_r{self.max_rungs}"
                f"_sl{self.sl_capital:g}_{f}")


# ══════════════════════════════════════════════════════════════════════
#  ⑤ 손익 커널 — 참조판(순수 파이썬). jit 판과 교차검증한다
# ══════════════════════════════════════════════════════════════════════
def run_cycles_ref(o, h, l, c, gate, d, step, tp, mult, max_rungs, capital,
                   leverage, fee_in, fee_tp, fee_ruin, mode,
                   gap, sl_units, stop_extreme, persist, halt, trace=None):
    """마틴게일 사이클을 돌린다.

    두 계좌 모형을 한 커널로 다룬다:
      persist=0 — 사이클마다 자본을 리셋한다 (사이클당 파산률을 재는 판)
      persist=1 — 자본이 누적된다. halt=1 이면 파산에서 **종목 테스트 종료**

    손절: 미실현 손실이 `sl_units` 에 닿으면 바구니 전량 청산.
          `sl_units >= capital` 이면 손절 없음 = 자본 소진까지 간다.

    반환: (n_cycles, rec[n,11])
      rec 열 = 시작봉·종료봉·결과·손익(단위)·계단수·첫진입가·평단·청산가·
               최대미실현손실(자본대비)·최종명목·모호봉수

    `trace` 에 리스트를 주면 체결을 (봉, 종류, 가격, 크기) 로 적는다 —
    ② 파라미터 도달 증명에 쓴다.
    """
    n = len(c)
    rec = np.zeros((n, N_COLS), dtype=np.float64)
    nc = 0
    equity = capital

    i = 0
    while i < n:
        if persist and equity <= 0.0:
            break
        # 파산 한도는 **현재 자본**이다 — 잃고 나면 버틸 힘도 준다
        risk_cap = equity if persist else capital
        max_notional = risk_cap * leverage
        # ── 사이클 시작: 1계단 진입 (해당 봉 시가) ──────────────
        #   ⚠ 진입 게이트는 **이 봉 이전 정보로만** 만들어져 있어야 한다.
        p0 = o[i]
        if not (p0 > 0) or gate[i] == 0:
            i += 1
            continue
        px_fill = [p0]
        wt_fill = [1.0]
        notional = 1.0
        pnl = -fee_in * 1.0
        last_px = p0
        mae = 0.0
        amb = 0.0
        start_i = i
        outcome = CENSORED
        exit_px = c[-1]

        j = i
        while j < n:
            # 불리한 극단 / 유리한 극단 — ③ 방향으로만 갈린다
            if mode == 2:                      # close_only
                adverse = c[j]
                favor = c[j]
            else:
                adverse = l[j] if d > 0 else h[j]
                favor = h[j] if d > 0 else l[j]

            added_here = False
            # ── ⓐ 물타기: 직전 체결가에서 step 만큼 불리해질 때마다 ──
            while len(px_fill) < max_rungs:
                trig = last_px * (1.0 - d * step)
                hit = (adverse <= trig) if d > 0 else (adverse >= trig)
                if not hit:
                    break
                w = wt_fill[-1] * mult
                if notional + w > max_notional:
                    break                      # 자금 조달 불가 — 계단 중단
                px_fill.append(trig)
                wt_fill.append(w)
                notional += w
                pnl -= fee_in * w
                last_px = trig
                added_here = True
                if trace is not None:
                    trace.append((j, "add", trig, w))

            # ── ⓑ 파산 판정: 불리한 극단에서의 미실현 손실 ──────
            unreal = 0.0
            for k in range(len(px_fill)):
                unreal += wt_fill[k] * d * (adverse - px_fill[k]) / px_fill[k]
            loss = -unreal
            if loss > mae:
                mae = loss
            # ⚠ 순서: **작은 문턱이 먼저 닿는다.** 손절이 자본보다 얕으면
            #   손절이 먼저 걸리므로 파산은 손절이 없을 때만 일어난다.
            if sl_units < risk_cap and loss >= sl_units:
                realized = loss if stop_extreme else sl_units
                if realized > risk_cap:
                    realized = risk_cap
                pnl += -realized - fee_ruin * notional
                outcome = STOP
                exit_px = adverse
                if trace is not None:
                    trace.append((j, "stop", adverse, notional))
                break
            if loss >= risk_cap:
                # 자본 소진 — 강제청산. 손실은 자본까지로 자른다(-100%)
                pnl += -risk_cap - fee_ruin * notional
                outcome = RUIN
                exit_px = adverse
                if trace is not None:
                    trace.append((j, "ruin", adverse, notional))
                break

            # ── ⓒ 익절: 평단 + tp ────────────────────────────────
            wsum = 0.0
            wpx = 0.0
            for k in range(len(px_fill)):
                wsum += wt_fill[k]
                wpx += wt_fill[k] * px_fill[k]
            avg = wpx / wsum
            tgt = avg * (1.0 + d * tp)
            tp_hit = (favor >= tgt) if d > 0 else (favor <= tgt)
            if tp_hit and added_here:
                amb += 1.0            # 같은 봉에서 물타기+익절 — 순서를 모른다
                if mode == 0:         # strict — 익절을 다음 봉으로 미룬다
                    tp_hit = False
            if tp_hit:
                gross = 0.0
                for k in range(len(px_fill)):
                    gross += wt_fill[k] * d * (tgt - px_fill[k]) / px_fill[k]
                pnl += gross - fee_tp * notional
                outcome = WIN
                exit_px = tgt
                if trace is not None:
                    trace.append((j, "tp", tgt, notional))
                break

            j += 1

        # ── 사이클 마감 ────────────────────────────────────────
        if outcome == CENSORED:
            j = n - 1
            p = c[j]
            gross = 0.0
            for k in range(len(px_fill)):
                gross += wt_fill[k] * d * (p - px_fill[k]) / px_fill[k]
            pnl += gross - fee_ruin * notional
            exit_px = p

        wsum = 0.0
        wpx = 0.0
        for k in range(len(px_fill)):
            wsum += wt_fill[k]
            wpx += wt_fill[k] * px_fill[k]

        rec[nc, C_START] = start_i
        rec[nc, C_END] = j
        rec[nc, C_OUT] = outcome
        rec[nc, C_PNL] = pnl
        rec[nc, C_RUNGS] = len(px_fill)
        rec[nc, C_P0] = p0
        rec[nc, C_AVG] = wpx / wsum
        rec[nc, C_PX] = exit_px
        rec[nc, C_MAE] = mae / risk_cap
        rec[nc, C_NOT] = notional
        rec[nc, C_AMB] = amb
        nc += 1

        equity += pnl
        if outcome == CENSORED:
            break
        if persist and halt and outcome == RUIN:
            break                              # 한 번 파산하면 종목 종료
        i = j + gap

    return nc, rec[:nc]


# ── jit 판. 본문은 참조판과 **한 글자도 다르지 않게** 유지한다 ─────────
try:
    from numba import njit
    _HAVE_NUMBA = True
except Exception:                                   # pragma: no cover
    _HAVE_NUMBA = False
    def njit(*a, **k):
        def deco(f):
            return f
        return deco


@njit(cache=True, fastmath=False)
def run_cycles_jit(o, h, l, c, gate, d, step, tp, mult, max_rungs, capital,
                   leverage, fee_in, fee_tp, fee_ruin, mode, gap,
                   sl_units, stop_extreme, persist, halt):
    n = len(c)
    rec = np.zeros((n, 11), dtype=np.float64)
    nc = 0
    px_fill = np.zeros(max_rungs + 1, dtype=np.float64)
    wt_fill = np.zeros(max_rungs + 1, dtype=np.float64)
    equity = capital

    i = 0
    while i < n:
        if persist == 1 and equity <= 0.0:
            break
        if persist == 1:
            risk_cap = equity
        else:
            risk_cap = capital
        max_notional = risk_cap * leverage
        p0 = o[i]
        if not (p0 > 0.0) or gate[i] == 0:
            i += 1
            continue
        nf = 1
        px_fill[0] = p0
        wt_fill[0] = 1.0
        notional = 1.0
        pnl = -fee_in
        last_px = p0
        mae = 0.0
        amb = 0.0
        start_i = i
        outcome = 2
        exit_px = c[n - 1]

        j = i
        while j < n:
            if mode == 2:
                adverse = c[j]
                favor = c[j]
            else:
                if d > 0:
                    adverse = l[j]
                    favor = h[j]
                else:
                    adverse = h[j]
                    favor = l[j]

            added_here = False
            while nf < max_rungs:
                trig = last_px * (1.0 - d * step)
                if d > 0:
                    hit = adverse <= trig
                else:
                    hit = adverse >= trig
                if not hit:
                    break
                w = wt_fill[nf - 1] * mult
                if notional + w > max_notional:
                    break
                px_fill[nf] = trig
                wt_fill[nf] = w
                nf += 1
                notional += w
                pnl -= fee_in * w
                last_px = trig
                added_here = True

            unreal = 0.0
            for k in range(nf):
                unreal += wt_fill[k] * d * (adverse - px_fill[k]) / px_fill[k]
            loss = -unreal
            if loss > mae:
                mae = loss
            if sl_units < risk_cap and loss >= sl_units:
                if stop_extreme == 1:
                    realized = loss
                else:
                    realized = sl_units
                if realized > risk_cap:
                    realized = risk_cap
                pnl += -realized - fee_ruin * notional
                outcome = 3
                exit_px = adverse
                break
            if loss >= risk_cap:
                pnl += -risk_cap - fee_ruin * notional
                outcome = 1
                exit_px = adverse
                break

            wsum = 0.0
            wpx = 0.0
            for k in range(nf):
                wsum += wt_fill[k]
                wpx += wt_fill[k] * px_fill[k]
            avg = wpx / wsum
            tgt = avg * (1.0 + d * tp)
            if d > 0:
                tp_hit = favor >= tgt
            else:
                tp_hit = favor <= tgt
            if tp_hit and added_here:
                amb += 1.0
                if mode == 0:
                    tp_hit = False
            if tp_hit:
                gross = 0.0
                for k in range(nf):
                    gross += wt_fill[k] * d * (tgt - px_fill[k]) / px_fill[k]
                pnl += gross - fee_tp * notional
                outcome = 0
                exit_px = tgt
                break

            j += 1

        if outcome == 2:
            j = n - 1
            p = c[j]
            gross = 0.0
            for k in range(nf):
                gross += wt_fill[k] * d * (p - px_fill[k]) / px_fill[k]
            pnl += gross - fee_ruin * notional
            exit_px = p

        wsum = 0.0
        wpx = 0.0
        for k in range(nf):
            wsum += wt_fill[k]
            wpx += wt_fill[k] * px_fill[k]

        rec[nc, 0] = start_i
        rec[nc, 1] = j
        rec[nc, 2] = outcome
        rec[nc, 3] = pnl
        rec[nc, 4] = nf
        rec[nc, 5] = p0
        rec[nc, 6] = wpx / wsum
        rec[nc, 7] = exit_px
        rec[nc, 8] = mae / risk_cap
        rec[nc, 9] = notional
        rec[nc, 10] = amb
        nc += 1

        equity += pnl
        if outcome == 2:
            break
        if persist == 1 and halt == 1 and outcome == 1:
            break
        i = j + gap

    return nc, rec[:nc]


def run_cycles(o, h, l, c, cfg: MartingaleConfig, use_jit=True, gate=None):
    """⑤ **단 하나의 호출 경로.** 격자·위약·자기검사 전부 여기로 들어온다."""
    if gate is None:
        gate = np.ones(len(c), dtype=np.int8)
    args = (o, h, l, c, gate, cfg.d, cfg.step, cfg.tp, cfg.multiplier,
            int(cfg.max_rungs), cfg.capital_units, cfg.leverage,
            cfg.fee_entry_bp / 1e4, cfg.fee_tp_bp / 1e4, cfg.fee_ruin_bp / 1e4,
            {"strict": 0, "adverse_first": 1, "close_only": 2}[cfg.intrabar],
            int(cfg.reenter_gap_bars),
            cfg.sl_capital * cfg.capital_units,
            1 if cfg.stop_fill == "extreme" else 0,
            1 if cfg.persist_equity else 0,
            1 if cfg.stop_on_ruin else 0)
    if use_jit and _HAVE_NUMBA:
        return run_cycles_jit(*args)
    return run_cycles_ref(*args)


# ══════════════════════════════════════════════════════════════════════
#  진입 필터 — 게이트는 **과거 봉만** 본다
# ══════════════════════════════════════════════════════════════════════
FILTER_WIN_D = 180                # 자기이력 순위 롤링 창 (일)
FILTER_WARM_D = 30                # 이보다 이른 봉은 어떤 설정이든 진입 금지 (일)
RSI_PERIOD = 14                   # RSI 게이트 기간 (rsi_threshold_source 와 동일)
# ⚠ 창은 **일 단위로** 정의하고 봉 수로는 시간대마다 환산한다. 1h 에서 168봉이던
#   7일이 1m 에서는 10,080봉이다. 봉 수를 상수로 박으면 1분봉 교차검증이
#   조용히 다른 지표를 재게 된다.


def filter_ranks(g: pd.DataFrame, bph: int = 1) -> dict:
    """필터별 **과거 봉만으로** 만든 자기이력 롤링 백분위.

    ⚠ 두 군데서 미래참조가 샌다. 둘 다 막는다:
        ① 지표 자체가 현재 봉을 쓰면 안 된다  → `.shift(1)`
        ② 순위를 전 구간 분위로 매기면 안 된다 → 롤링 창 안에서만 순위

    ⚠ 무필터 대조군도 **같은 워밍업**을 적용해야 공정하다. 안 그러면 필터가
      단지 초반 구간을 뺐다는 이유로 달라 보인다.
    """
    D = 24 * bph                       # 하루치 봉 수
    c = g["close"].astype(float)
    lr = np.log(c).diff()
    raw = {
        # 7일 실현변동성 — 파산이 82~91%분위 변동성에서 났다는 단서
        "rv7": lr.rolling(7 * D).std() * math.sqrt(365 * D),
        # 30일 수익률 — 추세
        "ret30": c.pct_change(30 * D),
        # 30일 고점 대비 낙폭
        "dd30": c / c.rolling(30 * D).max() - 1.0,
    }
    out = {}
    for k, v in raw.items():
        past = v.shift(1)                                   # ① 현재 봉 배제
        out[k] = past.rolling(FILTER_WIN_D * D,
                              min_periods=FILTER_WARM_D * D
                              ).rank(pct=True)              # ② 롤링 순위

    # ── RSI 는 **절대값** 문턱이다. 순위로 바꾸면 안 된다 ──────────
    #   대표님 지시(2026-08-17): "RSI 15 하단이면 롱, 85 상단이면 숏 마틴게일".
    #   RSI 는 이미 0~100 으로 정규화된 지표라 자기이력 순위를 매기면 **다른
    #   규칙**이 된다(변동성 낮은 종목의 RSI 40 이 상위 5% 가 될 수 있다).
    #   그래서 rsi/100 을 그대로 쓴다 — `filter_thr 0.15` = RSI 15.
    #   ⚠ 그래도 `.shift(1)` 은 지킨다. 진입은 커널이 다음 봉 시가에 낸다.
    from app.composer_framework.sources.rsi_threshold_source import wilder_rsi
    out["rsi"] = (wilder_rsi(c, RSI_PERIOD) / 100.0).shift(1)
    return out


def common_warm(ranks: dict, n: int, bph: int = 1,
                used: set | None = None) -> np.ndarray:
    """모든 설정이 공유하는 유효구간.

    ⚠ 필터마다 워밍업이 다르다 (rv7 은 37일, ret30·dd30 은 60일). 각자
      자기 워밍업만 쓰면 **필터마다 표본 구간이 달라져** 비교가 무너진다.
      그래서 쓰는 필터 전체가 유효해지는 시점부터를 공통 구간으로 삼고,
      **무필터 대조군에도 똑같이** 적용한다.
    """
    ok = np.ones(n, dtype=bool)
    sel = {k: v for k, v in ranks.items() if used is None or k in used}
    if sel:
        for v in sel.values():
            ok &= ~np.isnan(v.to_numpy(float))
    else:
        ok[:min(FILTER_WARM_D * 24 * bph, n)] = False
    return ok


def build_gate(cfg: MartingaleConfig, ranks: dict, n: int,
               rotate_by: int = 0, warm_ok: np.ndarray | None = None,
               bph: int = 1) -> np.ndarray:
    """설정 → 게이트 배열. `rotate_by`>0 이면 **필터만 원형회전**한 위약."""
    if warm_ok is None:
        warm_ok = common_warm(ranks, n, bph)
    if cfg.entry_filter == "none":
        return warm_ok.astype(np.int8)     # 무필터도 같은 유효구간을 쓴다
    r = ranks[cfg.entry_filter].to_numpy(float)
    if rotate_by:
        r = np.roll(r, rotate_by % n)
    ok = (r <= cfg.filter_thr) if cfg.filter_mode == "low" else (r >= cfg.filter_thr)
    return (warm_ok & ok & ~np.isnan(r)).astype(np.int8)


# ══════════════════════════════════════════════════════════════════════
#  ② 파라미터 도달 증명 + ⑤ 두 구현 교차검증
# ══════════════════════════════════════════════════════════════════════
def verify_reaches() -> None:
    """설정값이 **실제 체결에 닿는지** 합성 경로로 증명한다.

    이게 없으면 "플래그는 있는데 판정은 하드코딩"을 못 잡는다. 이 저장소에서
    실제로 세 번 났다 (교훈 #88).
    """
    # ── ⓐ 스텝값 도달: 단조 하락 경로에서 k번째 물타기는 p0(1-step)^k 여야 ──
    for step_bp, mult in ((200.0, 2.0), (500.0, 1.5)):
        cfg = MartingaleConfig(side="long", step_bp=step_bp, multiplier=mult,
                               max_rungs=5, capital_units=1e9, leverage=1e9)
        px = 100.0 * (1.0 - np.arange(400) * 0.0005)      # 5bp/봉 단조 하락
        o = px.copy(); h = px.copy(); l = px.copy(); c = px.copy()
        trace: list = []
        run_cycles_ref(o, h, l, c, np.ones(len(c), dtype=np.int8),
                       cfg.d, cfg.step, cfg.tp, cfg.multiplier,
                       cfg.max_rungs, cfg.capital_units, cfg.leverage,
                       cfg.fee_entry_bp / 1e4, cfg.fee_tp_bp / 1e4,
                       cfg.fee_ruin_bp / 1e4, 1, cfg.reenter_gap_bars,
                       cfg.sl_capital * cfg.capital_units, 0, 0, 0,
                       trace=trace)
        adds = [t for t in trace if t[1] == "add"]
        if len(adds) < 4:
            raise SystemExit(f"물타기가 안 걸렸다 — step={step_bp}bp, 체결 {len(adds)}건")
        for k, (_, _, p, w) in enumerate(adds[:4], start=1):
            want_p = 100.0 * (1.0 - cfg.step) ** k
            want_w = mult ** k
            if abs(p / want_p - 1.0) > 1e-9:
                raise SystemExit(
                    f"**스텝값이 커널에 도달하지 않았다** — {k}계단 체결가 "
                    f"{p:.6f}, 설정대로면 {want_p:.6f} (step={step_bp}bp)")
            if abs(w / want_w - 1.0) > 1e-9:
                raise SystemExit(
                    f"**물타기 배수가 커널에 도달하지 않았다** — {k}계단 크기 "
                    f"{w:.6f}, 설정대로면 {want_w:.6f} (배수={mult})")
        log.info("✔ 도달 확인 — 스텝 %gbp / 배수 %g : 계단가·계단크기 일치",
                 step_bp, mult)

    # ── ⓑ 배수가 결과를 바꾸는가 (선언만 되고 안 쓰이는 경우 방지) ──
    rng = np.random.default_rng(7)
    r = rng.normal(0, 0.004, 8000)
    cl = 100.0 * np.exp(np.cumsum(r))
    op = np.concatenate([[100.0], cl[:-1]])
    hi = np.maximum(op, cl) * 1.001
    lo = np.minimum(op, cl) * 0.999
    base = MartingaleConfig(side="long", step_bp=200, multiplier=1.0, capital_units=30)
    hi_m = MartingaleConfig(side="long", step_bp=200, multiplier=2.0, capital_units=30)
    n1, r1 = run_cycles(op, hi, lo, cl, base)
    n2, r2 = run_cycles(op, hi, lo, cl, hi_m)
    ru1 = (r1[:, C_OUT] == RUIN).mean() if n1 else 0
    ru2 = (r2[:, C_OUT] == RUIN).mean() if n2 else 0
    if abs(ru1 - ru2) < 1e-12 and abs(r1[:, C_PNL].sum() - r2[:, C_PNL].sum()) < 1e-12:
        raise SystemExit("**배수를 바꿔도 결과가 같다** — 파라미터가 죽어 있다")
    log.info("✔ 배수 감응 확인 — 배수1.0 파산률 %.1f%% vs 배수2.0 %.1f%%",
             100 * ru1, 100 * ru2)

    # ── ⓒ ③ 방향 대조: 숏이 롱의 거울인지 (같은 경로에서 다른 결과여야) ──
    s_cfg = MartingaleConfig(side="short", step_bp=200, multiplier=2.0, capital_units=30)
    n3, r3 = run_cycles(op, hi, lo, cl, s_cfg)
    if n3 == 0:
        raise SystemExit("숏 방향에서 사이클이 0건 — 방향 파라미터가 안 닿는다")
    log.info("✔ 방향 확인 — 롱 사이클 %d건 / 숏 %d건", n2, n3)

    # ── ⓓ 체결 규약이 실제로 갈리는가 (strict 가 안 닿으면 공짜로 이긴다) ──
    strict = MartingaleConfig(side="long", step_bp=200, multiplier=2.0,
                              capital_units=30, intrabar="strict")
    loose = MartingaleConfig(side="long", step_bp=200, multiplier=2.0,
                             capital_units=30, intrabar="adverse_first")
    # ⚠ 모호봉이 실제로 생기는 경로여야 한다. 위의 좁은 봉(±0.1%)에서는
    #   200bp 스텝이 한 봉 안에 물타기+익절을 못 만들어 검사가 **공회전**한다.
    wide_h = np.maximum(op, cl) * 1.035
    wide_l = np.minimum(op, cl) * 0.965
    ns, rs = run_cycles(op, wide_h, wide_l, cl, strict)
    nl, rl = run_cycles(op, wide_h, wide_l, cl, loose)
    amb_l = float((rl[:, C_AMB] > 0).mean()) if nl else 0.0
    if amb_l < 0.02:
        raise SystemExit(
            f"자기검사 경로에 모호봉이 {100*amb_l:.2f}% 뿐 — 체결 규약을 "
            "검사하지 못한다. 합성 경로의 봉 폭을 넓혀라")
    if abs(rs[:, C_PNL].sum() - rl[:, C_PNL].sum()) < 1e-12:
        raise SystemExit(
            "**intrabar 규약이 커널에 도달하지 않았다** — 모호봉이 "
            f"{100*amb_l:.1f}% 인데 strict 와 adverse_first 손익이 같다")
    log.info("✔ 체결 규약 확인 — 모호봉 %.1f%% · strict 손익 %+.2f vs "
             "adverse_first %+.2f (단위)", 100 * amb_l,
             rs[:, C_PNL].sum(), rl[:, C_PNL].sum())

    # ── ⓔ 손절 도달: 손실이 정확히 설정한 자본 비율에서 잘리는가 ──
    for slc in (0.20, 0.50):
        cfg = MartingaleConfig(side="long", step_bp=200, multiplier=2.0,
                               capital_units=30, sl_capital=slc,
                               intrabar="adverse_first")
        ns, rs = run_cycles(op, hi, lo, cl, cfg)
        st = rs[rs[:, C_OUT] == STOP]
        if len(st) == 0:
            raise SystemExit(f"**손절이 한 번도 안 걸렸다** — sl_capital={slc}")
        # 손절 사이클 손익 ≈ -(sl × 자본) - 진입마찰 - 청산마찰
        worst = st[:, C_PNL].max()          # 손절 손익 중 가장 얕은 것
        want = -slc * cfg.capital_units
        if worst > want:
            raise SystemExit(
                f"**손절이 설정보다 얕게 잘렸다** — sl={slc} 이면 손익이 "
                f"{want:+.2f} 보다 나쁠 수 없는데 {worst:+.2f} 가 있다")
        if (rs[:, C_OUT] == RUIN).any():
            raise SystemExit(
                f"손절 {slc} 인데 파산이 났다 — 작은 문턱이 먼저 닿아야 한다")
        log.info("✔ 손절 도달 — sl=%.0f%% : 손절 %d건 · 최얕은 손익 %+.2f "
                 "(상한 %+.2f) · 파산 0건", 100 * slc, len(st), worst, want)

    # ── ⓕ 계좌 모형: 한 번 파산하면 종목이 **끝나는가** ──────────
    cfg = MartingaleConfig(side="long", step_bp=200, multiplier=2.0,
                           capital_units=3, persist_equity=True,
                           stop_on_ruin=True, intrabar="adverse_first")
    nh, rh = run_cycles(op, hi, lo, cl, cfg)
    outs = rh[:, C_OUT]
    if (outs == RUIN).any():
        first = int(np.where(outs == RUIN)[0][0])
        if first != nh - 1:
            raise SystemExit(
                f"**파산 후에도 사이클이 이어졌다** — 파산 {first}번째인데 "
                f"총 {nh}건. stop_on_ruin 이 안 닿는다")
        log.info("✔ 종목 종료 확인 — 파산이 마지막 사이클(%d/%d)이고 그 뒤가 없다",
                 first + 1, nh)
    else:
        log.info("✔ 종목 종료 확인 — 이 경로에선 파산 없이 %d사이클 생존", nh)
    cfg_np = MartingaleConfig(side="long", step_bp=200, multiplier=2.0,
                              capital_units=3, intrabar="adverse_first")
    nn, _ = run_cycles(op, hi, lo, cl, cfg_np)
    if nn <= nh:
        raise SystemExit(
            f"**자본 누적/종료가 결과를 안 바꾼다** — 리셋판 {nn}사이클 vs "
            f"누적·종료판 {nh}사이클. 파라미터가 죽어 있다")
    log.info("✔ 계좌 모형 감응 — 리셋판 %d사이클 vs 누적·종료판 %d사이클", nn, nh)

    # ── ⓖ 진입 필터: 게이트가 **닫힌 봉에서 진입하지 않는가** ────
    rng2 = np.random.default_rng(11)
    gate = (rng2.random(len(cl)) < 0.5).astype(np.int8)
    cfg = MartingaleConfig(side="long", step_bp=200, multiplier=2.0,
                           capital_units=30, intrabar="adverse_first")
    ng, rg2 = run_cycles(op, hi, lo, cl, cfg, gate=gate)
    if ng == 0:
        raise SystemExit("게이트를 절반 열었는데 사이클이 0건 — 배선이 끊겼다")
    starts = rg2[:, C_START].astype(int)
    bad = int((gate[starts] == 0).sum())
    if bad:
        raise SystemExit(
            f"**닫힌 게이트에서 {bad}건 진입했다** — 진입 필터가 안 닿는다")
    n_open, _ = run_cycles(op, hi, lo, cl, cfg)
    if ng >= n_open:
        raise SystemExit(
            f"게이트를 절반 닫았는데 사이클이 안 줄었다 ({ng} vs {n_open})")
    log.info("✔ 진입 필터 도달 — 게이트 50%%: 사이클 %d→%d · 닫힌 봉 진입 0건",
             n_open, ng)

    # ── ⓗ 필터에 미래참조가 없는가 (그 봉을 바꿔도 순위가 안 변해야) ──
    idx = pd.date_range("2023-01-01", periods=6000, freq="h")
    gsyn = pd.DataFrame({"close": 100.0 * np.exp(np.cumsum(
        np.random.default_rng(3).normal(0, 0.004, 6000)))}, index=idx)
    r0 = filter_ranks(gsyn)
    g2 = gsyn.copy()
    probe = 5000
    g2.iloc[probe, 0] *= 1.5                     # 그 봉만 50% 흔든다
    r1 = filter_ranks(g2)
    for k in r0:
        a0, a1 = r0[k].to_numpy()[probe], r1[k].to_numpy()[probe]
        if not (np.isnan(a0) and np.isnan(a1)) and abs(a0 - a1) > 1e-12:
            raise SystemExit(
                f"**필터 {k} 에 미래참조가 있다** — {probe}번 봉을 바꿨더니 "
                f"그 봉의 순위가 {a0:.6f} → {a1:.6f} 로 변했다")
    log.info("✔ 미래참조 없음 — 해당 봉을 50%% 흔들어도 그 봉의 필터 값 불변 "
             "(%s)", "·".join(r0.keys()))

    # ── ⓗ-2 RSI 게이트 — 절대 문턱이 뜻대로 열리는가 ──────────────
    #   순위가 아니라 절대값이어야 한다. RSI 15 게이트가 전체 봉의 몇 %를
    #   여는지 찍어 "사실상 안 열림"이나 "다 열림"을 바로 잡는다.
    rr = filter_ranks(gsyn)["rsi"] * 100.0
    n_lo = int((rr <= 15).sum())
    n_hi = int((rr >= 85).sum())
    if not (0 < n_lo < len(rr) * 0.2) or not (0 < n_hi < len(rr) * 0.2):
        raise SystemExit(
            f"**RSI 게이트가 이상하다** — RSI<=15 {n_lo}봉 / >=85 {n_hi}봉 "
            f"(전체 {len(rr)}). 절대값이 아니라 순위로 들어갔을 수 있다")
    if int(((rr <= 15) & (rr >= 85)).sum()):
        raise SystemExit("RSI 게이트 롱·숏 조건이 동시에 켜졌다")
    log.info("✔ RSI 게이트 확인 — RSI<=15 %d봉(%.2f%%) / >=85 %d봉(%.2f%%) · 겹침 0",
             n_lo, 100 * n_lo / len(rr), n_hi, 100 * n_hi / len(rr))

    # ── ⓘ ⑤ jit ↔ 참조판 교차검증 ────────────────────────────────
    if _HAVE_NUMBA:
        for cfg in (base, hi_m, s_cfg, strict, loose, cfg_np,
                    MartingaleConfig(side="long", step_bp=200, multiplier=2.0,
                                     capital_units=30, sl_capital=0.35),
                    MartingaleConfig(side="short", step_bp=400, multiplier=1.6,
                                     capital_units=10, sl_capital=0.5,
                                     persist_equity=True, stop_on_ruin=True)):
            na, ra = run_cycles(op, hi, lo, cl, cfg, use_jit=True)
            nb, rb = run_cycles(op, hi, lo, cl, cfg, use_jit=False)
            if na != nb or not np.allclose(ra, rb, rtol=1e-10, atol=1e-10):
                raise SystemExit(
                    f"**jit 판과 참조판이 다르다** ({cfg.key()}) — "
                    f"사이클 {na} vs {nb}. 손익 구현체가 갈라졌다")
        log.info("✔ 교차검증 — jit 판 = 참조판 (%d설정 전부 완전일치)", 8)
    log.info("✔ 자기검사 통과 — 커널을 신뢰할 수 있다")


# ══════════════════════════════════════════════════════════════════════
#  기질 적재
# ══════════════════════════════════════════════════════════════════════
def load_symbols_1m(symbols: list) -> dict:
    """1분봉은 **종목마다 따로** 읽는다 — 85종목 전 구간이면 2.5억 행이다.

    ⚠ `ohlcv` 는 45GB 다. `time_frame` 에 인덱스가 없으므로 반드시
      `symbol` 을 먼저 좁혀야 한다 (유니크 인덱스 앞자리).
    """
    from sqlalchemy import text
    from app.db.session import engine
    out = {}
    with engine.connect() as conn:
        for i, s in enumerate(symbols, 1):
            rows = conn.execute(text(
                "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                "WHERE symbol = :s AND time_frame = '1m' ORDER BY timestamp"),
                {"s": s}).fetchall()
            if not rows:
                log.warning("%s — 1분봉 없음", s)
                continue
            g = pd.DataFrame(rows, columns=["ts", "open", "high", "low",
                                            "close", "volume"])
            out[s] = g.drop_duplicates("ts").reset_index(drop=True)
            log.info("[%d/%d] %s 1m %s봉", i, len(symbols), s,
                     f"{len(out[s]):,}")
    return out


def load_panel(min_bars: int, limit: int = 0) -> dict:
    from sqlalchemy import text
    from app.db.session import engine

    log.info("ohlcv_hourly 적재 …")
    # ⚠ pandas.read_sql 은 sqlalchemy 판본에 따라 Connection 을 못 알아본다
    #   (Mint 실측 TypeError). 커서로 직접 받아 판본 의존을 없앤다.
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT symbol, ts, open, high, low, close, volume "
            "FROM ohlcv_hourly ORDER BY symbol, ts")).fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "ts", "open", "high",
                                     "low", "close", "volume"])
    out = {}
    for sym, g in df.groupby("symbol", sort=True):
        g = g.drop_duplicates("ts").sort_values("ts")
        if len(g) < min_bars:
            continue
        out[sym] = g.reset_index(drop=True)
    if limit:
        out = {k: out[k] for k in sorted(out)[:limit]}
    log.info("적재 완료 — %d종목 (>=%d봉) · 총 %s봉",
             len(out), min_bars, f"{sum(len(v) for v in out.values()):,}")
    return out


def make_null(g: pd.DataFrame, mode: str, seed: int) -> pd.DataFrame:
    """위약 경로. **봉의 모양은 보존하고 순서만 바꾼다.**

    shuffle : 봉 모양을 IID 로 섞는다 → 추세 지속성이 사라진다.
              실제 파산률이 이보다 훨씬 높으면 파산의 원인은 **추세**다.
    rotate  : 원형회전. 통계는 그대로, 위상만 바뀐다.
    """
    c = g["close"].to_numpy(float)
    r = np.diff(np.log(c), prepend=np.log(c[0]))
    hr = np.log(g["high"].to_numpy(float) / c)
    lr = np.log(g["low"].to_numpy(float) / c)
    orr = np.log(g["open"].to_numpy(float) / c)
    n = len(c)
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n) if mode == "shuffle" else np.roll(np.arange(n),
                                                              rng.integers(1, n))
    r, hr, lr, orr = r[idx], hr[idx], lr[idx], orr[idx]
    c2 = c[0] * np.exp(np.cumsum(r))
    return pd.DataFrame({
        "ts": g["ts"].to_numpy(),
        "open": c2 * np.exp(orr), "high": c2 * np.exp(hr),
        "low": c2 * np.exp(lr), "close": c2,
        "volume": g["volume"].to_numpy()})


# ══════════════════════════════════════════════════════════════════════
#  파산 당시 상황 — 사후 특징 (커널이 못 보는 것들)
# ══════════════════════════════════════════════════════════════════════
def bar_context(g: pd.DataFrame, btc_close: pd.Series | None) -> pd.DataFrame:
    c = g["close"].astype(float)
    ctx = pd.DataFrame(index=g.index)
    ctx["ret_24h"] = c.pct_change(24)
    ctx["ret_7d"] = c.pct_change(24 * 7)
    ctx["ret_30d"] = c.pct_change(24 * 30)
    lr = np.log(c).diff()
    ctx["rv_7d"] = lr.rolling(24 * 7).std() * math.sqrt(24 * 365)
    ctx["rv_30d"] = lr.rolling(24 * 30).std() * math.sqrt(24 * 365)
    ctx["dd_30d"] = c / c.rolling(24 * 30).max() - 1.0
    ctx["hour"] = pd.to_datetime(g["ts"]).dt.hour
    ctx["dow"] = pd.to_datetime(g["ts"]).dt.dayofweek
    if btc_close is not None:
        b = btc_close.reindex(pd.to_datetime(g["ts"]).to_numpy()).to_numpy(float)
        bs = pd.Series(b)
        ctx["btc_ret_7d"] = bs.pct_change(24 * 7).to_numpy()
        ctx["btc_ret_30d"] = bs.pct_change(24 * 30).to_numpy()
    return ctx


# ══════════════════════════════════════════════════════════════════════
#  집계
# ══════════════════════════════════════════════════════════════════════
def summarize(nc: int, rec: np.ndarray, cfg: MartingaleConfig) -> dict:
    if nc == 0:
        return {"n_cycles": 0}
    out = rec[:, C_OUT]
    pnl = rec[:, C_PNL]
    closed = out != CENSORED
    n_win = int((out == WIN).sum())
    n_ruin = int((out == RUIN).sum())
    n_stop = int((out == STOP).sum())
    n_cl = int(closed.sum())
    # ⚠ 손절이 생기면 승률의 분모가 바뀐다 — 익절/(익절+손절+파산).
    #   손절을 빼고 세면 "손절 많이 하는 설정" 이 승률 100% 로 보인다.
    ruined = bool(n_ruin > 0)
    dur = rec[:, C_END] - rec[:, C_START] + 1
    ruin_m = out == RUIN
    tot = float(pnl.sum())
    # 누적 손익의 최대 낙폭 — ROI 만 보면 파산 후 회복까지 좋아 보인다
    cum = np.cumsum(pnl)
    mdd = float((cum - np.maximum.accumulate(cum)).min())
    se = pnl.std(ddof=1) / math.sqrt(nc) if nc > 1 else np.nan
    return {
        "n_cycles": int(nc),
        "n_win": n_win, "n_ruin": n_ruin, "n_stop": n_stop,
        "n_censored": int((out == CENSORED).sum()),
        "win_rate": 100.0 * n_win / n_cl if n_cl else np.nan,
        "ruin_rate": 100.0 * n_ruin / n_cl if n_cl else np.nan,
        "stop_rate": 100.0 * n_stop / n_cl if n_cl else np.nan,
        # 종목 단위 — persist+halt 판에서만 뜻이 있다
        "ruined": ruined,
        "bars_alive": float(rec[-1, C_END] + 1),
        "cycles_alive": int(nc),
        "final_equity_pct": 100.0 * (cfg.capital_units + tot) / cfg.capital_units,
        "med_dur_stop_h": float(np.median(dur[out == STOP])) if n_stop else np.nan,
        "stop_pnl_mean": float(pnl[out == STOP].mean()) if n_stop else np.nan,
        "pnl_units": tot,
        "roi_pct": 100.0 * tot / cfg.capital_units,
        "mdd_pct": 100.0 * mdd / cfg.capital_units,
        "mean_pnl": float(pnl.mean()),
        "t": float(pnl.mean() / se) if se and se > 0 else np.nan,
        "med_dur_h": float(np.median(dur)),
        "med_dur_win_h": float(np.median(dur[out == WIN])) if n_win else np.nan,
        "med_dur_ruin_h": float(np.median(dur[ruin_m])) if n_ruin else np.nan,
        "mean_rungs": float(rec[:, C_RUNGS].mean()),
        "max_rungs_used": float(rec[:, C_RUNGS].max()),
        "mean_rungs_ruin": float(rec[ruin_m, C_RUNGS].mean()) if n_ruin else np.nan,
        "amb_bar_pct": 100.0 * float((rec[:, C_AMB] > 0).mean()),
        "mean_mae": float(rec[:, C_MAE].mean()),
        "win_pnl_mean": float(pnl[out == WIN].mean()) if n_win else np.nan,
        "ruin_pnl_mean": float(pnl[ruin_m].mean()) if n_ruin else np.nan,
    }


def build_grid(side: str, steps, mults, caps, sls, filters, max_rungs,
               tp_ratio, intrabar, base: dict) -> list:
    grid = []
    for s in steps:
        for m in mults:
            for cp in caps:
                for sl in sls:
                    for fname, fmode, fthr in filters:
                        grid.append(MartingaleConfig(
                            side=side, step_bp=s, multiplier=m,
                            capital_units=cp, sl_capital=sl,
                            entry_filter=fname, filter_mode=fmode,
                            filter_thr=fthr, max_rungs=max_rungs,
                            tp_ratio=tp_ratio, intrabar=intrabar, **base))
    return grid


def parse_filters(spec: str) -> list:
    """'none' 또는 'rv7:low:0.2,rv7:high:0.8' 형식.

    ⚠ 무필터 대조군은 **언제나** 앞에 붙는다 — 빼고 돌리면 비교 대상이 없다.
    """
    out = [("none", "low", 1.0)]
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok or tok == "none":
            continue
        parts = tok.split(":")
        if len(parts) != 3:
            raise SystemExit(f"필터 형식은 이름:low|high:문턱 — 받은 값 {tok!r}")
        out.append((parts[0], parts[1], float(parts[2])))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="마틴게일 파산 하네스")
    p.add_argument("--side", default="long", choices=["long", "short", "both"])
    p.add_argument("--steps", default="50,100,200,400,800")
    p.add_argument("--mults", default="1.0,1.3,1.6,2.0")
    p.add_argument("--caps", default="10,30,100")
    p.add_argument("--sls", default="1.0",
                   help="손절 — 초기자본 대비 미실현손실 비율. 1.0 = 손절 없음")
    p.add_argument("--stop-fill", default="level", choices=["level", "extreme"])
    p.add_argument("--filters", default="none",
                   help="진입 필터. 예: rv7:low:0.2,rv7:high:0.8 "
                        "(무필터 대조군은 자동으로 항상 포함)")
    p.add_argument("--tf", default="1h", choices=["1h", "1m"],
                   help="시간대. 1m 은 --symbols 로 좁혀야 한다 (45GB 테이블)")
    p.add_argument("--symbols", default="", help="쉼표 구분 (1m 교차검증용)")
    p.add_argument("--start", default="", help="구간 시작 YYYY-MM-DD (포함)")
    p.add_argument("--end", default="", help="구간 끝 YYYY-MM-DD (미포함)")
    p.add_argument("--filter-null", action="store_true",
                   help="필터만 원형회전한 위약 — 게이트 빈도는 같고 시점만 무관")
    p.add_argument("--persist-equity", action="store_true",
                   help="자본을 사이클 간 누적한다 (실계좌 모형)")
    p.add_argument("--stop-on-ruin", action="store_true",
                   help="파산하면 그 종목 테스트를 종료한다 (persist 필수)")
    p.add_argument("--max-rungs", type=int, default=10)
    p.add_argument("--tp-ratio", type=float, default=1.0)
    p.add_argument("--leverage", type=float, default=5.0)
    p.add_argument("--intrabar", default="strict",
                   choices=["strict", "adverse_first", "close_only"])
    p.add_argument("--min-bars", type=int, default=500)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--null", default="", choices=["", "shuffle", "rotate"])
    p.add_argument("--ruin-detail-per-config", type=int, default=400,
                   help="설정당 파산 상세 기록 상한 (개수 집계는 전부 남는다)")
    p.add_argument("--seed", type=int, default=20260816)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--tag", default="")
    a = p.parse_args()

    # ② 자기검사는 **언제나** 먼저 돈다
    verify_reaches()
    if a.selftest:
        return 0

    steps = [float(x) for x in a.steps.split(",")]
    mults = [float(x) for x in a.mults.split(",")]
    caps = [float(x) for x in a.caps.split(",")]
    sls = [float(x) for x in a.sls.split(",")]
    sides = ["long", "short"] if a.side == "both" else [a.side]
    base = {"leverage": a.leverage, "min_bars": a.min_bars,
            "stop_fill": a.stop_fill, "persist_equity": a.persist_equity,
            "stop_on_ruin": a.stop_on_ruin}

    bph = 1 if a.tf == "1h" else 60
    if a.tf == "1m":
        if not a.symbols:
            log.error("1분봉은 --symbols 가 필수다 — 전 종목이면 2.5억 행이다")
            return 1
        panel = load_symbols_1m([s.strip().upper()
                                 for s in a.symbols.split(",") if s.strip()])
    else:
        panel = load_panel(a.min_bars, a.limit)
        if a.symbols:
            want = {s.strip().upper() for s in a.symbols.split(",") if s.strip()}
            panel = {k: v for k, v in panel.items() if k in want}
    if not panel:
        log.error("종목이 없다 — 기질 적재를 확인하라")
        return 1

    btc = None
    if "BTCUSDT" in panel:
        b = panel["BTCUSDT"]
        btc = pd.Series(b["close"].to_numpy(float),
                        index=pd.to_datetime(b["ts"]).to_numpy())

    # ⑦ 검정력 사전검사 — 사이클이 몇 개나 나올지 먼저 본다
    tot_bars = sum(len(v) for v in panel.values())
    log.info("검정력 사전검사 — %d종목 · %s봉 · 격자 %d칸(방향 %d)",
             len(panel), f"{tot_bars:,}",
             len(steps) * len(mults) * len(caps) * len(sls), len(sides))

    filters = parse_filters(a.filters)
    used_filters = {f[0] for f in filters if f[0] != "none"}
    grids = {s: build_grid(s, steps, mults, caps, sls, filters, a.max_rungs,
                           a.tp_ratio, a.intrabar, base) for s in sides}

    ruins, per_sym, detail_n = [], [], {}
    t0 = datetime.now()
    for n_i, (sym, g) in enumerate(sorted(panel.items()), 1):
        gg = make_null(g, a.null, a.seed + n_i) if a.null else g
        gg = gg.reset_index(drop=True)
        # ⚠ 필터 순위는 **자르기 전 전 구간**에서 만든다. 구간을 먼저 자르면
        #   OOS 가 워밍업 30일을 다시 태워 IS 와 다른 표본이 된다. 순위 자체는
        #   과거 봉만 쓰므로 전 구간에서 계산해도 미래참조가 아니다.
        ranks_full = filter_ranks(gg, bph) if len(filters) > 1 else {}
        if a.start or a.end:
            tsx = pd.to_datetime(gg["ts"])
            msk = np.ones(len(gg), bool)
            if a.start:
                msk &= (tsx >= pd.Timestamp(a.start)).to_numpy()
            if a.end:
                msk &= (tsx < pd.Timestamp(a.end)).to_numpy()
            if msk.sum() < 500:
                continue
            gg = gg[msk].reset_index(drop=True)
            ranks_full = {k: v[msk].reset_index(drop=True)
                          for k, v in ranks_full.items()}
        o = gg["open"].to_numpy(float)
        h = gg["high"].to_numpy(float)
        l = gg["low"].to_numpy(float)
        c = gg["close"].to_numpy(float)
        ts = pd.to_datetime(gg["ts"]).to_numpy()
        ctx = bar_context(gg, btc) if not a.null else None
        ranks = ranks_full
        # 위약 회전량은 종목마다 다르되 재현 가능해야 한다
        rot = (a.seed * 7919 + n_i * 104729) % max(len(c) - 1, 1) if a.filter_null else 0
        warm_ok = common_warm(ranks, len(c), bph, used_filters)
        if warm_ok.sum() < 200:
            continue

        for side in sides:
            for cfg in grids[side]:
                gate = build_gate(cfg, ranks, len(c), rot, warm_ok, bph)
                nc, rec = run_cycles(o, h, l, c, cfg, gate=gate)
                s = summarize(nc, rec, cfg)
                s.update({"symbol": sym, "side": side, "step_bp": cfg.step_bp,
                          "mult": cfg.multiplier, "cap": cfg.capital_units,
                          "sl": cfg.sl_capital,
                          "filter": cfg.entry_filter,
                          "fmode": cfg.filter_mode, "fthr": cfg.filter_thr,
                          "gate_open_pct": 100.0 * float(gate.mean()),
                          "bars": len(c), "key": cfg.key()})
                per_sym.append(s)
                if nc == 0 or ctx is None:
                    continue
                # 파산 상세는 설정당 상한을 둔다 — 전 종목·전 격자면 수백만 행이
                # 된다. 균등 간격으로 솎되 **개수 자체는 위 집계에 전부** 남는다.
                idx_ruin = np.where(rec[:, C_OUT] == RUIN)[0]
                room = a.ruin_detail_per_config - detail_n.get(cfg.key(), 0)
                if room <= 0:
                    continue
                if len(idx_ruin) > room:
                    idx_ruin = idx_ruin[np.linspace(0, len(idx_ruin) - 1, room
                                                    ).astype(int)]
                detail_n[cfg.key()] = detail_n.get(cfg.key(), 0) + len(idx_ruin)
                for k in idx_ruin:
                    e = int(rec[k, C_END])
                    row = {"symbol": sym, "key": cfg.key(), "side": side,
                           "step_bp": cfg.step_bp, "mult": cfg.multiplier,
                           "cap": cfg.capital_units,
                           "ts_start": str(ts[int(rec[k, C_START])]),
                           "ts_ruin": str(ts[e]),
                           "bars": int(rec[k, C_END] - rec[k, C_START] + 1),
                           "entry_px": float(rec[k, C_P0]),
                           "avg_px": float(rec[k, C_AVG]),
                           "ruin_px": float(rec[k, C_PX]),
                           "adverse_pct": float(100 * (rec[k, C_PX] / rec[k, C_P0] - 1)),
                           "rungs": int(rec[k, C_RUNGS]),
                           "notional": float(rec[k, C_NOT])}
                    for col in ctx.columns:
                        v = ctx[col].iloc[e]
                        row[col] = None if pd.isna(v) else float(v)
                    ruins.append(row)
        if n_i % 25 == 0:
            log.info("[%d/%d] %s — %.0f초 경과", n_i, len(panel), sym,
                     (datetime.now() - t0).total_seconds())

    P = pd.DataFrame(per_sym)
    R = pd.DataFrame(ruins)

    # ⑥ 관측 단위는 사이클 — 설정별로 전 종목 사이클을 합산한다
    agg = []
    GKEY = ["side", "step_bp", "mult", "cap", "sl", "filter", "fmode", "fthr"]
    for (side, s_, m_, cp, sl_, f_, fm_, ft_), gsub in P.groupby(GKEY):
        gv = gsub[gsub.n_cycles > 0]
        if gv.empty:
            continue
        ncy = gv.n_cycles.sum()
        ncl = ncy - gv.n_censored.sum()
        rn = gv.ruined.astype(bool)
        agg.append({
            "side": side, "step_bp": s_, "mult": m_, "cap": cp, "sl": sl_,
            "filter": f_, "fmode": fm_, "fthr": ft_,
            "gate_open_pct": float(gv.gate_open_pct.median()),
            "n_sym": len(gv), "n_cycles": int(ncy), "n_closed": int(ncl),
            "win_rate": 100.0 * gv.n_win.sum() / ncl if ncl else np.nan,
            "ruin_rate": 100.0 * gv.n_ruin.sum() / ncl if ncl else np.nan,
            "stop_rate": 100.0 * gv.n_stop.sum() / ncl if ncl else np.nan,
            # ── 종목 단위 (persist+halt 판의 본판 지표) ──
            "sym_ruin_pct": 100.0 * float(rn.mean()),
            "med_bars_alive_ruined": float(gv.loc[rn, "bars_alive"].median())
                                     if rn.any() else np.nan,
            "med_cycles_alive_ruined": float(gv.loc[rn, "cycles_alive"].median())
                                       if rn.any() else np.nan,
            "med_final_equity": float(gv.final_equity_pct.median()),
            "med_final_equity_survived": float(
                gv.loc[~rn, "final_equity_pct"].median()) if (~rn).any() else np.nan,
            "roi_med": float(gv.roi_pct.median()),
            "roi_mean": float(gv.roi_pct.mean()),
            "mdd_med": float(gv.mdd_pct.median()),
            "pos_sym_pct": 100.0 * float((gv.roi_pct > 0).mean()),
            "med_dur_ruin_h": float(gv.med_dur_ruin_h.median(skipna=True)),
            "mean_rungs": float(gv.mean_rungs.mean()),
            "amb_pct": float(gv.amb_bar_pct.mean()),
            "judged": bool(ncl >= MartingaleConfig.min_cycles_judge),
        })
    A = pd.DataFrame(agg)

    tag = a.tag or (f"null_{a.null}" if a.null else "real")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # ④ 경로는 설정에서 유도한다 — 계좌 모형이 다르면 파일도 갈라져야 한다
    acct = ("persist_halt" if a.persist_equity and a.stop_on_ruin
            else "persist" if a.persist_equity else "reset")
    fl = "filtnull" if a.filter_null else ("filt" if len(filters) > 1 else "nofilt")
    span = f"_{a.start or 'beg'}_{a.end or 'end'}" if (a.start or a.end) else ""
    stem = (f"{'_'.join(sides)}_{a.tf}_{a.intrabar}_{acct}_{a.stop_fill}"
            f"_{fl}{span}_{tag}")
    A.to_csv(OUT_DIR / f"agg_{stem}.csv", index=False)
    P.to_csv(OUT_DIR / f"persym_{stem}.csv", index=False)
    if not R.empty:
        R.to_csv(OUT_DIR / f"ruins_{stem}.csv", index=False)
    with open(OUT_DIR / f"meta_{stem}.json", "w") as fh:            # ⑦ 설정 전문
        json.dump({"args": vars(a), "n_symbols": len(panel),
                   "total_bars": int(tot_bars),
                   "config_template": asdict(grids[sides[0]][0]),
                   "grid": {"steps": steps, "mults": mults, "caps": caps},
                   "generated": datetime.now().isoformat()},
                  fh, indent=2, ensure_ascii=False)

    print("\n" + "=" * 124)
    print(f"마틴게일 파산 하네스 — {len(panel)}종목 · {tot_bars:,}봉({a.tf}) · "
          f"{'위약(' + a.null + ')' if a.null else '실측'} · {a.intrabar} · "
          f"계좌 {acct} · 손절체결 {a.stop_fill}")
    print("=" * 124)
    if a.persist_equity:
        print("  ⚠ 자본이 누적되는 판이다. **파산률은 종목당 비율**이고, "
              "손절률·승률만 사이클당이다.")
    print(f"{'방향':<6}{'스텝bp':>7}{'배수':>6}{'손절':>6}  {'필터':<15}{'게이트%':>8}"
          f"{'사이클':>9}{'승률%':>7}{'종목파산%':>10}{'최종자본%':>11}"
          f"{'생존시%':>9}{'파산까지h':>10}")
    print("-" * 124)
    for _, r in A.sort_values(["side", "step_bp", "mult", "sl", "filter",
                               "fmode", "fthr"]).iterrows():
        fl_ = ("무필터" if r["filter"] == "none"
               else f"{r['filter']}·{r.fmode}·{r.fthr:g}")
        print(f"{r.side:<6}{r.step_bp:>7.0f}{r['mult']:>6.1f}"
              f"{r.sl:>6.2f}  {fl_:<15}{r.gate_open_pct:>8.1f}"
              f"{r.n_cycles:>9,}{r.win_rate:>7.1f}"
              f"{r.sym_ruin_pct:>10.1f}{r.med_final_equity:>11.1f}"
              f"{r.med_final_equity_survived:>9.1f}"
              f"{r.med_bars_alive_ruined / bph:>10.0f}")
    print("=" * 124 + "\n")
    log.info("저장: %s", OUT_DIR / f"agg_{stem}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
