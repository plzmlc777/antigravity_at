"""RSI 진입 × 익절 × 손절 — **승률이 문턱에 따라 어떻게 변하나**.

무엇을 묻는가
    대표님 질문: "RSI 진입 조건이 달라짐에 따른 승률 변화."
    그래서 판독의 주축은 **문턱별 승률**이다. 다만 승률만 내면 거짓말이 된다 —
    익절 1% / 손절 5% 면 승률 80% 에 기대값은 음수다. 그래서 승률 옆에
    **거래당 평균**과 **손익비**를 항상 같이 낸다.

⚠ 손익 커널은 **정본 하나**만 쓴다
    `GenericBacktester.run_rule_based`. 새 백테스터를 만들지 않는다 — 그게
    이 저장소에서 손익 구현체 6개 중 4개가 오염된 경로다.

⚠ 방향은 파라미터
    롱(과매도 진입)만 돌리면 국면 효과를 규칙 효과로 읽는다. **같은 문턱의
    거울(숏, 과매수 진입)**을 항상 같이 돌린다 (교훈 #91).

⚠ 파라미터 도달을 증명한다
    `spec_sink` 로 조립된 스펙을 꺼내 설정과 대조한다. 이 저장소에서 "플래그는
    있는데 판정은 하드코딩" 이 세 번 났다 (교훈 #88).

사용:
  python3 -m scripts.research.rsi_tp_sl_harness --selftest
  python3 -m scripts.research.rsi_tp_sl_harness --side both
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rsi_grid")

OUT_DIR = ROOT / "runs" / "research_track" / "rsi_tp_sl"


# ══════════════════════════════════════════════════════════════════════
#  ① 설정은 여기 한 곳에만
# ══════════════════════════════════════════════════════════════════════
@dataclass
class RsiConfig:
    # ⚠ 신호원 축 (2026-08-22 추가)
    #   `rsi`  — RSI 문턱 (기존)
    #   `band` — 볼린저 밴드 극단. 중복도 검사에서 RSI 와 가장 안 겹친 지표
    #            (자카드 0.170 · 눈금 0.835/0.676 대비 한참 아래).
    #   손익 커널은 **하나**를 그대로 쓴다 — 신호원만 갈아끼운다. 새 백테스터를
    #   만드는 순간 손익 구현체가 또 갈라진다(이 저장소 6개 중 4개가 그렇게
    #   오염됐다).
    #   `volcap` — 거래량 항복. 중복도 검사에서 **유일하게 어느 지표와도
    #            안 뭉친 축**(최대 0.337). 파라미터가 둘이라 축이 하나 늘어난다
    #            — `entry_threshold`=거래량 z, `ret_threshold`=수익률 문턱.
    signal: str = "rsi"
    side: str = "long"           # long = 과매도 진입 / short = 과매수 진입
    period: int = 14
    entry_threshold: float = 30.0   # rsi: RSI 문턱 / band: sigma / volcap: 거래량 z
    # ⚠ volcap 전용 축. 다른 신호원에서는 쓰이지 않지만 **key·집계에는 항상**
    #   들어간다 — 축을 빠뜨리면 그 축이 통째로 뭉개진다(이 파일에서 두 번 났다).
    ret_threshold: float = -0.03
    ret_bars: int = 5
    # volcap 전용. 방아쇠(side)와 **포지션**을 가른다.
    #   reversion = 급락에 매수 / continuation = 급락에 매도
    direction: str = "reversion"
    tp_pct: float = 0.03
    sl_pct: float = 0.02
    max_hold_bars: int = 48      # 1h 봉 기준 2일
    entry_mode: str = "level"    # level | cross_back (되돌아 나올 때 진입)
    # RSI 가 이 값 아래로 다시 떨어지면 청산. 0 = 비활성.
    # 가격 손절과 달리 **봉 마감에 판정**하므로 마찰이 시간청산 수준이다.
    exit_rsi_below: float = 0.0
    # 손절을 **지정가**로 건다. 트리거 후 손절가로 되돌아와야 체결된다.
    sl_limit: bool = False
    # ── 진입 게이트 (2026-08-25) ─────────────────────────────────
    #   거래 1,725건을 **거래 단위**로 갈라 찾았다. 월로 묶으면 47개가 되고
    #   그중 11개월이 5거래 미만이라 정보를 스스로 버린다.
    #   ⚠ **상위 5일을 뺀** 표본에서 판정했다. 2025-10-10 하루가 익절의
    #     68%(341진입 310익절)라, 그 날을 표시하는 변수는 무엇이든 예측력이
    #     있어 보인다 — 빼기 전엔 `hour` 가 70.3%p 를 갈랐다.
    #   날짜 묶음 위약 p 0.001 · 앞→뒤 절반 확인 4/4 통과.
    min_atr_pct: float = 0.0     # 30분봉 ATR 하한(%). Q1(<0.98%) 익절률 6.1%
    max_drop_pct: float = 0.0    # 직전 하락 폭 상한(음수). Q1(-20%↓) 18.4%
    min_vol_mult: float = 0.0    # 거래량 배수 하한. Q5(15배↑) 20.1%
    # 방아쇠와 지정가를 **벌린다**(진입가 대비 비율). 0 = 같은 값(가장 불리).
    # 실전 스톱리밋은 stopPrice 와 price 를 따로 잡는다 — 그래야 주문이
    # 만들어지는 순간 체결 가능해지고, 슬리피지가 이 폭 안으로 갇힌다.
    sl_limit_offset: float = 0.0
    placebo: str = ""            # "" | rotate | random  (진입 대조군)
    placebo_seed: int = 0
    signal_lag_bars: int = 1     # 정본 장부 규약 — 신호 봉의 **다음 봉 시가** 체결
    eval_freq_minutes: int = 60
    # ⚠ 요율을 **반드시 넘긴다**. GenericBacktester 기본값은
    #   DEFAULT_FEE_RATE = FEE_KR_EQUITY = 1.5bp 편도 — **한국 주식** 요율이다.
    #   커널에 FEE_TAKER_BINANCE_FUTURES(5bp)가 정의돼 있는데도 기본이 아니라,
    #   안 넘기면 바이낸스 선물을 한국 주식 수수료로 계산한다.
    #   2026-08-19 발견: 이 하네스가 저장소에서 요율을 안 넘긴 유일한 곳이었다
    #   (GenericBacktester 사용처 13곳 중 12곳은 명시).
    fee_rate: float = 0.0005          # 바이낸스 선물 테이커 편도
    fee_rate_maker: float = 0.0002    # 메이커 편도 (익절 지정가)

    def __post_init__(self):
        if self.signal not in ("rsi", "band", "volcap"):
            raise SystemExit(f"signal 은 rsi|band|volcap — {self.signal!r}")
        if self.side not in ("long", "short"):
            raise SystemExit(f"side 는 long|short — {self.side!r}")
        if self.signal == "rsi" and not (0.0 < self.entry_threshold < 100.0):
            raise SystemExit(f"RSI 문턱은 (0,100) — {self.entry_threshold!r}")
        if self.signal == "band" and not (0.0 < self.entry_threshold < 10.0):
            raise SystemExit(f"밴드 sigma 는 (0,10) — {self.entry_threshold!r}")
        if self.signal == "volcap":
            if not (0.0 < self.entry_threshold < 20.0):
                raise SystemExit(f"거래량 z 는 (0,20) — {self.entry_threshold!r}")
            if not (self.ret_threshold < 0.0):
                raise SystemExit(f"수익률 문턱은 음수(롱 기준 급락) — "
                                 f"{self.ret_threshold!r}")
            if self.direction not in ("reversion", "continuation"):
                raise SystemExit(f"direction 은 reversion|continuation — "
                                 f"{self.direction!r}")
        if self.tp_pct <= 0:
            raise SystemExit("익절은 양수여야 한다")
        # ⚠ 손절 0 = **손절 없음**(커널이 `sl_price > 0` 으로 비활성 처리).
        #   음수는 여전히 거부한다 — 오타를 조용히 통과시키면 안 된다.
        #
        #   왜 손절 없음을 검정하는가 (2026-08-21)
        #   손절은 시장가로 나가고, 하필 급락 순간에 걸린다. 실측 슬리피지
        #   중앙 0bp · 평균 104bp · 최대 6,964bp. 손절 폭을 0.3~5% 로
        #   넓혀봐도 다섯 폭 전부 적자였다 — 넓히면 슬리피지 맞는 횟수는
        #   줄지만(86%→34%) 엣지가 같이 사라진다.
        #   보호용 손절을 **지정가로 거는 방법은 없다**. 시장가 아래 매도
        #   지정가는 즉시 체결되고, 스톱-리밋은 급락 때 체결이 안 돼 손실이
        #   무한대로 열린다. 슬리피지 위험을 미체결 위험으로 바꿀 뿐이다.
        #   체결이 보장되는 지정가는 **익절**뿐이다. 그래서 손절을 빼고
        #   익절 지정가 + 시간 청산만으로 돌려본다.
        if self.sl_pct < 0:
            raise SystemExit(f"손절은 0(없음) 또는 양수 — {self.sl_pct!r}")

    @property
    def feature_col(self) -> str:
        return {"rsi": "rsi_signal", "band": "band_signal",
                "volcap": "volcap_signal"}[self.signal]

    def pipeline_spec(self) -> dict:
        if self.signal == "rsi":
            src = {"type": "rsi_threshold",
                   "kwargs": {"period": self.period,
                              "entry_threshold": self.entry_threshold,
                              "side": self.side,
                              "entry_mode": self.entry_mode,
                              "min_atr_pct": self.min_atr_pct,
                              "max_drop_pct": self.max_drop_pct,
                              "min_vol_mult": self.min_vol_mult,
                              "placebo": self.placebo,
                              "placebo_seed": self.placebo_seed}}
        elif self.signal == "volcap":
            src = {"type": "volume_capitulation",
                   "kwargs": {"vol_window": self.period,
                              "vol_z_min": self.entry_threshold,
                              "ret_bars": self.ret_bars,
                              "ret_threshold": self.ret_threshold,
                              "side": self.side,
                              "direction": self.direction,
                              "entry_mode": self.entry_mode,
                              "placebo": self.placebo,
                              "placebo_seed": self.placebo_seed}}
        else:
            src = {"type": "band_extreme",
                   "kwargs": {"period": self.period,
                              "sigma": self.entry_threshold,
                              "side": self.side,
                              "entry_mode": self.entry_mode,
                              "placebo": self.placebo,
                              "placebo_seed": self.placebo_seed}}
        return {
            "sources": [src],
            "composer": {"type": "passthrough",
                         "kwargs": {"feature_col": self.feature_col}},
            "policy": {"type": "long_short_threshold",
                       "kwargs": {"entry_threshold": 0.5,
                                  "sl_pct": self.sl_pct,
                                  "tp_pct": self.tp_pct,
                                  "max_hold_bars": self.max_hold_bars,
                                  "exit_rsi_below": self.exit_rsi_below}},
        }

    def key(self) -> str:
        pl = self.placebo or "real"
        vc = (f"_r{self.ret_threshold:g}b{self.ret_bars}_{self.direction[:3]}"
              if self.signal == "volcap" else "")
        return (f"{self.signal}_{self.side}_p{self.period}"
                f"_t{self.entry_threshold:g}" + vc
                + f"_tp{self.tp_pct:g}_sl{self.sl_pct:g}_h{self.max_hold_bars}"
                + f"_{self.entry_mode}_{pl}"
                # ⚠ 2026-08-24: 손절 **방식**이 키에 없었다. 시장가 칸과
                #   지정가 칸이 같은 키를 달고 나가 원장에서 구분이 안 됐고,
                #   간격 축을 넣으면 세 칸이 조용히 한 덩어리가 된다.
                #   지정가일 때만 붙여 기존 키는 그대로 둔다.
                + (f"_sllim{self.sl_limit_offset:g}" if self.sl_limit else "")
                + (f"_g{self.min_atr_pct:g}_{-self.max_drop_pct:g}_{self.min_vol_mult:g}"
                   if (self.min_atr_pct or self.max_drop_pct or self.min_vol_mult) else "")
                + (f"_s{self.placebo_seed}" if self.placebo else ""))


# ══════════════════════════════════════════════════════════════════════
#  ② 파라미터 도달 증명
# ══════════════════════════════════════════════════════════════════════
def verify_reaches(cfg: RsiConfig) -> None:
    from app.composer_framework.pipeline_spec import build_pipeline
    pipe = build_pipeline(cfg.pipeline_spec())
    src = pipe.sources[0]
    want_name = {"rsi": "rsi_threshold", "band": "band_extreme",
                 "volcap": "volume_capitulation"}[cfg.signal]
    if getattr(src, "name", None) != want_name:
        raise SystemExit(f"신호원이 안 갈렸다 — 스펙={getattr(src,'name',None)!r} "
                         f"설정={cfg.signal!r}")
    if cfg.signal == "rsi":
        got_thr, got_per = src.entry_threshold, src.period
    elif cfg.signal == "band":
        got_thr, got_per = src.sigma, src.period
    else:
        got_thr, got_per = src.vol_z_min, src.vol_window
    checks = [("period", got_per, cfg.period),
              ("entry_threshold", got_thr, cfg.entry_threshold)]
    if cfg.signal == "volcap":
        checks += [("ret_threshold", src.ret_threshold, cfg.ret_threshold),
                   ("ret_bars", src.ret_bars, cfg.ret_bars)]
        if src.direction != cfg.direction:
            bad_dir = True
        else:
            bad_dir = False
    bad = [(k, g, w) for k, g, w in checks if abs(float(g) - float(w)) > 1e-9]
    if cfg.signal == "volcap" and bad_dir:
        bad.append(("direction", src.direction, cfg.direction))
    if src.side != cfg.side:
        bad.append(("side", src.side, cfg.side))
    if src.placebo != cfg.placebo:
        bad.append(("placebo", src.placebo, cfg.placebo))
    if getattr(src, "entry_mode", None) != cfg.entry_mode:
        bad.append(("entry_mode", getattr(src, "entry_mode", None), cfg.entry_mode))
    # 게이트도 **도달을 증명한다** — 설정에 넣고 소스가 안 받으면 조용히 꺼진다
    if cfg.signal == "rsi":
        for k in ("min_atr_pct", "max_drop_pct", "min_vol_mult"):
            g = float(getattr(src, k, 0.0) or 0.0)
            w = float(getattr(cfg, k, 0.0) or 0.0)
            if abs(g - w) > 1e-9:
                bad.append((k, g, w))
    pol = pipe.policy
    for k, want in (("sl_pct", cfg.sl_pct), ("tp_pct", cfg.tp_pct),
                    ("max_hold_bars", cfg.max_hold_bars),
                    ("exit_rsi_below", cfg.exit_rsi_below)):
        got = getattr(pol, k, None)
        if got is None or abs(float(got) - float(want)) > 1e-9:
            bad.append((k, got, want))
    if bad:
        raise SystemExit(
            "**설정이 스펙에 도달하지 않았다** — 값을 바꿔도 판정이 안 바뀐다:\n"
            + "\n".join(f"  {k}: 스펙={g!r} 설정={w!r}" for k, g, w in bad))
    log.info("✔ 도달 확인 — %s %d / 문턱 %g / %s / %s / 익절 %.1f%% / "
             "손절 %.1f%% / 보유 %d봉",
             cfg.signal, cfg.period, cfg.entry_threshold, cfg.side,
             cfg.entry_mode, 100 * cfg.tp_pct, 100 * cfg.sl_pct,
             cfg.max_hold_bars)


def aggregate(P: "pd.DataFrame") -> "pd.DataFrame":
    """종목 패널 → 격자 칸별 집계.

    ⚠ 반드시 `placebo` 로도 나눈다. 안 나누면 실측 행과 위약 행이 한 칸에
      섞여 모든 수치가 둘의 혼합이 된다 (2026-08-19 이전 산출물의 결함).

    ⚠ 이름을 값에 맞춘다. 예전 `sum_pct` 는 합계가 아니라 **종목별 합의
      중앙값**이었다. 종목 대부분이 1~4거래뿐이라 `win_rate` 중앙값도
      100/50/33/25 로 튀어 읽는 사람을 오도했다. 총손익은 `sum_pct_tot`.
    """
    need = {"n_trades", "sum_pct", "symbol", "side", "period", "thr",
            "tp", "sl"}
    P = P.copy()
    if "signal" not in P.columns:            # 구형 산출물은 전부 RSI 였다
        P["signal"] = "rsi"
    missing = need - set(P.columns)
    if missing:                         # 거래 0건으로 끝난 실행 등
        raise ValueError(f"집계에 필요한 열이 없다: {sorted(missing)}")
    if "placebo" not in P.columns:      # 구형 산출물 — key 끝에 박혀 있다
        P = P.assign(placebo=P.key.str.rsplit("_", n=1).str[-1])
    # ⚠ 격자 축을 **하나라도 빠뜨리면 그 축이 통째로 뭉개진다.**
    #   2026-08-19 에 `placebo` 가 빠져 실측과 위약이 섞였고, 2026-08-22 에
    #   `entry_mode`·`hold`·`seed` 를 새로 넣고도 **여기를 또 잊었다**
    #   (CB 8칸이 4행, HOLD 8칸이 2행으로 나왔다).
    #   그래서 이제 **있는 축은 자동으로 전부** 넣는다. 새 축을 추가해도
    #   이 자리를 고칠 필요가 없다.
    G = [c for c in ("signal", "side", "period", "thr", "retthr", "retbars",
                     "direction", "tp", "sl", "hold",
                     "entry_mode", "placebo", "seed") if c in P.columns]
    agg = (P[P.n_trades.notna()].groupby(G)
           .agg(n_sym=("symbol", "nunique"), trades=("n_trades", "sum"),
                sum_pct_tot=("sum_pct", "sum"),        # ← 총손익 (판정 주축)
                sum_pct_med=("sum_pct", "median"),     # ← 종목별 합의 중앙값
                win_rate_med=("win_rate_calc", "median"),
                avg_pct_med=("avg_pct", "median"),
                payoff_med=("payoff", "median"),
                pos_sym=("sum_pct", lambda x: 100.0 * float((x > 0).mean())))
           .reset_index())
    # 거래 가중 평균 — 종목별 중앙값과 달리 거래 수가 반영된다
    agg["avg_pct_w"] = agg.sum_pct_tot / agg.trades.replace(0, np.nan)
    return agg


def selftest() -> None:
    """RSI 계산과 문턱·방향이 실제로 신호를 바꾸는지 합성 경로로 확인."""
    from app.composer_framework.signal_source import SourceContext
    from app.composer_framework.sources.rsi_threshold_source import (
        RsiThresholdSource, wilder_rsi)

    # ⓐ 단조 상승이면 RSI 100, 단조 하락이면 0 에 붙어야 한다
    idx = pd.date_range("2024-01-01", periods=400, freq="h")
    up = pd.Series(np.linspace(100, 200, 400), index=idx)
    dn = pd.Series(np.linspace(200, 100, 400), index=idx)
    if not (wilder_rsi(up, 14).iloc[-1] > 99.9):
        raise SystemExit(f"단조 상승 RSI 가 {wilder_rsi(up,14).iloc[-1]:.2f}")
    if not (wilder_rsi(dn, 14).iloc[-1] < 0.1):
        raise SystemExit(f"단조 하락 RSI 가 {wilder_rsi(dn,14).iloc[-1]:.2f}")
    log.info("✔ RSI 계산 확인 — 단조상승 100.0 / 단조하락 0.0")

    # ⓑ 문턱을 낮추면 신호가 **줄어야** 한다 (같은 방향)
    rng = np.random.default_rng(5)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, 3000)))
    ix = pd.date_range("2024-01-01", periods=3000, freq="h")
    # ⚠ `volume` 을 넣는다 — 진입 게이트(거래량 배수)가 쓴다. 없으면
    #   게이트 자기검사가 "컬럼 없음"으로 죽는다(2026-08-25).
    bars = pd.DataFrame({"open": px, "high": px * 1.002,
                         "low": px * 0.998, "close": px,
                         "volume": rng.lognormal(10, 1.0, 3000)}, index=ix)
    ctx = SourceContext(symbol="TEST", eval_freq_minutes=60, ohlcv_eval=bars)
    cnt = {}
    for thr in (20.0, 30.0, 40.0):
        f = RsiThresholdSource(14, thr, "long").build_features(ctx)
        cnt[thr] = int((f["rsi_signal"] > 0).sum())
    if not (cnt[20.0] <= cnt[30.0] <= cnt[40.0]) or cnt[20.0] == cnt[40.0]:
        raise SystemExit(f"**문턱이 신호를 안 바꾼다** — {cnt}")
    log.info("✔ 문턱 감응 확인 — 롱 신호 봉수 20:%d ≤ 30:%d ≤ 40:%d",
             cnt[20.0], cnt[30.0], cnt[40.0])

    # ⓒ 방향 — 숏은 부호가 반대여야 하고 롱과 같은 봉에서 켜지면 안 된다
    fl = RsiThresholdSource(14, 30.0, "long").build_features(ctx)["rsi_signal"]
    fs = RsiThresholdSource(14, 30.0, "short").build_features(ctx)["rsi_signal"]
    if fs.max() > 0 or fs.min() >= 0:
        raise SystemExit("숏 신호가 음수가 아니다")
    if int(((fl != 0) & (fs != 0)).sum()) > 0:
        raise SystemExit("롱·숏 신호가 같은 봉에서 동시에 켜졌다")
    log.info("✔ 방향 확인 — 롱 %d봉 / 숏 %d봉 · 겹침 0",
             int((fl != 0).sum()), int((fs != 0).sum()))

    # ⓓ 데이터 결손은 조용한 0 이 아니라 예외여야 한다
    from app.composer_framework.signal_source import InsufficientSourceDataError
    short_ctx = SourceContext(symbol="TEST", eval_freq_minutes=60,
                              ohlcv_eval=bars.iloc[:30])
    try:
        RsiThresholdSource(14, 30.0, "long").build_features(short_ctx)
    except InsufficientSourceDataError:
        log.info("✔ 결손 처리 확인 — 봉 부족 시 조용한 0 대신 예외")
    else:
        raise SystemExit("**봉이 모자란데 예외가 안 났다** — 조용한 0 신호 위험")

    # ⓔ 위약 — **진입 횟수가 보존되고, 시점은 달라져야** 한다.
    #   횟수가 달라지면 "거래를 덜 해서 좋아진 것"과 구별이 안 된다.
    base = RsiThresholdSource(14, 30.0, "long").build_features(ctx)["rsi_signal"]
    n_base = int((base != 0).sum())
    for pl in ("rotate", "random"):
        f = RsiThresholdSource(14, 30.0, "long", placebo=pl,
                               placebo_seed=7).build_features(ctx)["rsi_signal"]
        n_pl = int((f != 0).sum())
        same = int(((base != 0) & (f != 0)).sum())
        if pl == "random" and n_pl != n_base:
            raise SystemExit(f"random 위약이 횟수를 안 지켰다 {n_base}→{n_pl}")
        if pl == "rotate" and not (0.5 * n_base <= n_pl <= n_base):
            # 앞쪽 k 개를 지우므로 조금 줄어드는 것은 정상이다
            raise SystemExit(f"rotate 위약 횟수가 이상하다 {n_base}→{n_pl}")
        if n_base and same / n_base > 0.5:
            raise SystemExit(
                f"**{pl} 위약이 실측과 {100*same/n_base:.0f}% 겹친다** — "
                f"시점이 안 흔들렸다")
        log.info("✔ 위약 %s 확인 — 진입 %d→%d봉 · 실측과 겹침 %d (%.1f%%)",
                 pl, n_base, n_pl, same, 100 * same / max(n_base, 1))

    verify_reaches(RsiConfig(side="short", period=7, entry_threshold=25,
                             tp_pct=0.05, sl_pct=0.01, max_hold_bars=12))
    verify_reaches(RsiConfig(side="long", entry_threshold=20, placebo="rotate"))
    verify_reaches(RsiConfig(side="long", entry_threshold=20,
                             entry_mode="cross_back"))
    # ⓖ 진입 모드 — level 은 구간 **안 모든 봉**, cross_back 은 **나오는 봉**.
    #    같은 값이 나오면 모드가 도달하지 않은 것이다.
    from app.composer_framework.sources.rsi_threshold_source import (
        RsiThresholdSource)
    from app.composer_framework.signal_source import SourceContext as _SC
    _n = 400
    _rng = np.random.default_rng(7)
    _px = pd.Series(100 * np.exp(np.cumsum(_rng.normal(0, 0.01, _n))),
                    index=pd.date_range("2025-01-01", periods=_n, freq="1h"))
    _bars = pd.DataFrame({"open": _px, "high": _px * 1.001,
                          "low": _px * 0.999, "close": _px, "volume": 1.0})
    _ctx = _SC(symbol="T", eval_freq_minutes=60, ohlcv_eval=_bars)
    _lv = RsiThresholdSource(period=14, entry_threshold=35, side="long",
                             entry_mode="level").build_features(_ctx)
    _cb = RsiThresholdSource(period=14, entry_threshold=35, side="long",
                             entry_mode="cross_back").build_features(_ctx)
    _nl = int((_lv.rsi_signal > 0).sum())
    _nc = int((_cb.rsi_signal > 0).sum())
    if _nl == 0 or _nc == 0:
        raise SystemExit(f"모드 검사 표본 부족 — level {_nl} / cross_back {_nc}")
    if _nc >= _nl:
        raise SystemExit(f"cross_back 이 level 보다 적어야 한다 — {_nc} vs {_nl}")
    # 발화 시점이 **겹치면 안 된다**: level 은 구간 안, cross_back 은 구간 밖
    _both = int(((_lv.rsi_signal > 0) & (_cb.rsi_signal > 0)).sum())
    if _both:
        raise SystemExit(f"두 모드가 같은 봉에서 발화했다 — {_both}봉")
    # cross_back 발화 봉의 **직전 봉**은 반드시 level 발화 봉이어야 한다
    _prev_ok = ((_cb.rsi_signal > 0) &
                (_lv.rsi_signal > 0).shift(1).fillna(False))
    if int(_prev_ok.sum()) != _nc:
        raise SystemExit("cross_back 발화 직전 봉이 구간 안이 아니다")
    log.info("✔ 진입 모드 확인 — level %d봉 / cross_back %d봉 · 겹침 0 · "
             "cross_back 은 항상 구간 직후", _nl, _nc)
    # ⓕ 집계가 **위약을 분리**하는지. 안 하면 실측 칸에 위약 행이 섞여
    #    모든 수치가 둘의 혼합이 된다 — 2026-08-19 이전 산출물의 결함이다.
    P = pd.DataFrame({
        "symbol": ["A", "B", "A", "B"],
        "side": "long", "period": 14, "thr": 8.0, "tp": 0.08, "sl": 0.03,
        "placebo": ["real", "real", "rotate", "rotate"],
        "n_trades": [2, 3, 2, 3],
        "sum_pct": [10.0, 30.0, -4.0, -6.0],
        "win_rate_calc": [50.0, 100.0, 0.0, 0.0],
        "avg_pct": [5.0, 10.0, -2.0, -2.0], "payoff": [1.0, 2.0, 0.5, 0.5],
        "key": ["k_real", "k_real", "k_rotate", "k_rotate"]})
    A = aggregate(P)
    if len(A) != 2 or set(A.placebo) != {"real", "rotate"}:
        raise SystemExit(f"집계가 위약을 안 나눈다 — {A}")
    r = A[A.placebo == "real"].iloc[0]
    if abs(r.sum_pct_tot - 40.0) > 1e-9:            # 합계이지 중앙값이 아니다
        raise SystemExit(f"sum_pct_tot 가 합계가 아니다 — {r.sum_pct_tot}")
    if abs(r.sum_pct_med - 20.0) > 1e-9:
        raise SystemExit(f"sum_pct_med 가 중앙값이 아니다 — {r.sum_pct_med}")
    if abs(r.avg_pct_w - 40.0 / 5) > 1e-9:          # 거래 가중 평균
        raise SystemExit(f"avg_pct_w 틀림 — {r.avg_pct_w}")
    # placebo 열이 없는 구형 산출물은 key 끝에서 되살린다
    A2 = aggregate(P.drop(columns=["placebo"]))
    if set(A2.placebo) != {"real", "rotate"}:
        raise SystemExit(f"구형 산출물에서 위약 복원 실패 — {set(A2.placebo)}")
    # 새 축(entry_mode·hold·seed)이 뭉개지지 않는지. 예전엔 조용히 합쳐졌다.
    P2 = pd.DataFrame({
        "symbol": ["A", "A", "A", "A"], "n_trades": [1, 1, 1, 1],
        "sum_pct": [10.0, 20.0, 30.0, 40.0], "win_rate_calc": [100.0] * 4,
        "avg_pct": [1.0] * 4, "payoff": [1.5] * 4,
        "side": ["long"] * 4, "period": [14] * 4,
        "thr": [10] * 4, "tp": [0.05] * 4, "sl": [0.0] * 4,
        "hold": [24, 288, 24, 288],
        "entry_mode": ["level", "level", "cross_back", "cross_back"],
        "placebo": ["real"] * 4, "seed": [1] * 4,
        "key": ["k1", "k2", "k3", "k4"]})
    A2 = aggregate(P2)
    if len(A2) != 4:
        raise SystemExit(f"집계가 축을 뭉갰다 — 4칸인데 {len(A2)}행 "
                         f"(entry_mode/hold 가 묶음 키에 없다)")
    P3 = P2.assign(placebo=["real", "real", "rotate", "rotate"],
                   seed=[1, 1, 7, 9], hold=288, entry_mode="level")
    if len(aggregate(P3)) != 3:
        raise SystemExit("씨앗이 뭉개졌다 — 최대통계량 귀무분포가 가짜가 된다")
    log.info("✔ 집계 확인 — 위약·모드·보유·씨앗 전부 분리 · 총손익은 합계 · "
             "구형 파일은 key 로 복원")

    # ⓖ 요율 **도달 증명** — 넘긴 값이 커널까지 가는지. 안 가면 조용히
    #    DEFAULT_FEE_RATE(한국 주식 1.5bp) 로 계산된다. 2026-08-19 실제 사고.
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.kernel import (FEE_MAKER_BINANCE_FUTURES,
                                               FEE_TAKER_BINANCE_FUTURES)
    c0 = RsiConfig()
    bt = _bt(c0)
    kc = bt._kernel_config()
    if abs(kc.fee_rate - c0.fee_rate) > 1e-12:
        raise SystemExit(f"테이커가 커널에 안 갔다 — {kc.fee_rate} vs {c0.fee_rate}")
    # ⚠ 2026-08-20 실제 결함. `fee_rate_maker` 는 RsiConfig 에 **선언만**
    #   돼 있고 백테스터로 넘어가지 않았다. 커널은 익절을 메이커로 표시
    #   (`exit_maker=(forced[1]=="tp")`)하는데 maker 요율이 None 이라
    #   테이커로 떨어졌다 — 익절마다 3bp, 페이퍼와 어긋났다.
    #   교훈 #88: 필드를 만든 것과 그 필드가 도달하는 것은 다른 사건이다.
    if kc.fee_rate_maker is None or abs(kc.fee_rate_maker - c0.fee_rate_maker) > 1e-12:
        raise SystemExit(f"메이커가 커널에 안 갔다 — {kc.fee_rate_maker} vs "
                         f"{c0.fee_rate_maker} (익절이 테이커로 계산된다)")
    if abs(c0.fee_rate - FEE_TAKER_BINANCE_FUTURES) > 1e-12:
        raise SystemExit(f"설정 요율이 바이낸스 테이커가 아니다 — {c0.fee_rate}")
    if abs(c0.fee_rate_maker - FEE_MAKER_BINANCE_FUTURES) > 1e-12:
        raise SystemExit(f"설정 요율이 바이낸스 메이커가 아니다 — {c0.fee_rate_maker}")
    # 요율을 아예 안 주면 **거절**되어야 한다(예전엔 조용히 한국 주식 1.5bp).
    try:
        GenericBacktester()
    except ValueError:
        pass
    else:
        raise SystemExit("요율 미지정이 거절되지 않는다 — 기본값 강제가 풀렸다")
    # ⓟ **RSI 청산이 실제로 발화하는가.** 도달 확인은 값이 갔는지만 본다 —
    #    동작은 따로 재야 한다(교훈 #88).
    from app.composer_framework.policy import (LongShortThresholdPolicy,
                                               PolicyContext as _PC)
    _pol = LongShortThresholdPolicy(entry_threshold=0.5, sl_pct=0.0, tp_pct=0.05,
                                    max_hold_bars=288, exit_rsi_below=10.0)
    # ⚠ 이름 주의 — 이 자기검사는 `_ctx` 를 이미 SourceContext 로 쓰고 있다.
    #   같은 이름을 쓰면 뒤 항목이 조용히 깨진다(실제로 겪었다).
    def _rsictx(rsi, held=5):
        return _PC(timestamp=None, prediction=0.0, in_position=True, side="long",
                   entry_price=100.0, bars_held=held, open_price=100.0,
                   high_price=100.0, low_price=100.0, close_price=100.0,
                   # ⚠ 운영에서 정책이 받는 건 **Series** 다. dict 로 시험하면
                   #   `features or {}` 같은 결함을 못 잡는다(실제로 놓쳤다).
                   features=pd.Series({"rsi_value": rsi}))
    if _pol.decide(_rsictx(9.9)).kind != "exit":
        raise SystemExit("RSI 9.9 인데 청산 안 한다 — 규칙이 동작하지 않는다")
    if _pol.decide(_rsictx(10.1)).kind == "exit":
        raise SystemExit("RSI 10.1 인데 청산한다 — 문턱이 틀렸다")
    if _pol.decide(_rsictx(float("nan"))).kind == "exit":
        raise SystemExit("RSI 가 NaN 인데 청산한다 — 워밍업에서 조용히 나간다")
    _off = LongShortThresholdPolicy(entry_threshold=0.5, sl_pct=0.0, tp_pct=0.05,
                                    max_hold_bars=288)
    if _off.decide(_rsictx(0.1)).kind == "exit":
        raise SystemExit("비활성(0)인데 청산한다 — 기존 동작이 바뀐다")
    if _pol.decide(_rsictx(50.0, held=288)).note != "time":
        raise SystemExit("보유상한이 RSI 청산에 가려졌다")
    # 빈 Series·None 도 죽지 않아야 한다
    for _empty in (pd.Series(dtype=float), None):
        _c = _PC(timestamp=None, prediction=0.0, in_position=True, side="long",
                 entry_price=100.0, bars_held=5, open_price=100.0,
                 high_price=100.0, low_price=100.0, close_price=100.0,
                 features=_empty if _empty is not None else {})
        if _pol.decide(_c).kind == "exit":
            raise SystemExit("피처가 비었는데 청산한다")
    log.info("✔ RSI 청산 확인 — 9.9 청산 / 10.1 유지 / NaN 유지 / 0=비활성 / "
             "보유상한 우선 / 빈 피처 안전 (**Series 로 시험**)")

    # 지정가 손절이 **커널까지** 가는가 (교훈 #88 — 필드와 도달은 다른 사건)
    _kl = _bt(RsiConfig(sl_limit=True))._kernel_config()
    if not _kl.sl_limit:
        raise SystemExit("sl_limit 이 커널에 안 갔다 — 지정가 손절이 무시된다")
    if _bt(RsiConfig())._kernel_config().sl_limit:
        raise SystemExit("기본값이 지정가 손절이다 — 기존 동작이 바뀐다")
    log.info("✔ 지정가 손절 도달 확인 — 커널 sl_limit=True / 기본 False")

    # ⚠ 클래스만 고치고 경로를 안 보면 한 번도 안 돈다(교훈 #88).
    #   설정 → 백테스터 → 커널까지 **값 자체**가 닿았는지 본다.
    _ko = _bt(RsiConfig(sl_limit=True, sl_limit_offset=0.003))._kernel_config()
    if abs(getattr(_ko, "sl_limit_offset", 0.0) - 0.003) > 1e-12:
        raise SystemExit("sl_limit_offset 이 커널에 안 갔다 — 띠가 무시된다")
    if _bt(RsiConfig(sl_limit=True))._kernel_config().sl_limit_offset != 0.0:
        raise SystemExit("sl_limit_offset 기본값이 0 이 아니다")
    from app.composer_framework.kernel import _sl_floor as _flr
    if abs(_flr(99.5, 100.0, "long", _ko) - 99.2) > 1e-9:
        raise SystemExit("띠 산술이 틀렸다 — 롱 하한이 진입가×offset 만큼 아래여야")
    if abs(_flr(100.5, 100.0, "short", _ko) - 100.8) > 1e-9:
        raise SystemExit("띠 산술이 틀렸다 — 숏 상한")
    log.info("✔ 지정가 손절 **띠** 도달 확인 — offset 0.003 / 롱 99.5→99.2 "
             "· 숏 100.5→100.8 · 기본 0.0")

    # ⚠ 서로 다른 칸이 **같은 키**를 달면 원장에서 구분이 안 된다. 축을 늘릴
    #   때마다 조용히 섞이므로 여기서 막는다 (2026-08-24: 간격 축 3칸이
    #   한 덩어리가 될 뻔했다).
    _probe = [RsiConfig(sl_limit=True, sl_limit_offset=o)
              for o in (0.0, 0.001, 0.003, 0.005)]
    _probe.append(RsiConfig())                      # 시장가
    _keys = [c.key() for c in _probe]
    if len(set(_keys)) != len(_keys):
        raise SystemExit(f"칸이 다른데 키가 같다 — 원장에서 섞인다: {_keys}")
    log.info("✔ 키 유일성 확인 — 시장가·지정가 간격 4종이 서로 다른 키")

    # ⚠ 게이트는 **신호를 줄여야** 한다. 설정만 받고 안 걸면 조용히 꺼진 것과
    #   같다 — 그러면 게이트 격자가 전부 같은 결과를 낸다(교훈 #88).
    _b = RsiThresholdSource(14, 30.0, "long").build_features(ctx)["rsi_signal"]
    _n0 = int((_b != 0).sum())
    _g = {}
    for _lab, _kw in (("atr", dict(min_atr_pct=1.5)),
                      ("drop", dict(max_drop_pct=-8.0)),
                      ("vol", dict(min_vol_mult=5.0))):
        _f = RsiThresholdSource(14, 30.0, "long", **_kw).build_features(ctx)["rsi_signal"]
        _g[_lab] = int((_f != 0).sum())
        if _g[_lab] > _n0:
            raise SystemExit(f"게이트 {_lab} 가 신호를 **늘렸다** — {_g[_lab]} > {_n0}")
    if min(_g.values()) >= _n0:
        raise SystemExit(f"게이트가 신호를 하나도 안 줄였다 — 기본 {_n0} / {_g}")
    _all = RsiThresholdSource(14, 30.0, "long", min_atr_pct=1.5,
                              max_drop_pct=-8.0, min_vol_mult=5.0
                              ).build_features(ctx)["rsi_signal"]
    _na = int((_all != 0).sum())
    if _na > min(_g.values()):
        raise SystemExit(f"셋을 모두 걸었는데 각각보다 신호가 많다 — {_na} > {min(_g.values())}")
    log.info("✔ 게이트 감응 확인 — 기본 %d → atr %d / drop %d / vol %d / 셋 모두 %d",
             _n0, _g["atr"], _g["drop"], _g["vol"], _na)
    _s = RsiThresholdSource(14, 30.0, "long", min_atr_pct=1.5)
    if abs(_s.min_atr_pct - 1.5) > 1e-9 or _s.gated is not True:
        raise SystemExit("게이트 인자가 소스에 안 실렸다")
    if RsiThresholdSource(14, 30.0, "long").gated is not False:
        raise SystemExit("게이트 기본값이 꺼짐이 아니다")
    log.info("✔ 게이트 기본 꺼짐 확인")

    log.info("✔ 요율 도달 확인 — 테이커 %.1fbp / 메이커 %.1fbp 편도 "
             "(익절은 메이커, 손절·시간은 테이커)",
             1e4 * kc.fee_rate, 1e4 * kc.fee_rate_maker)

    # ⓘ **볼린저 신호원** — 새 축이 들어왔으니 여기도 같은 관문을 통과해야
    #    한다. 소스만 만들고 하네스 자기검사를 안 늘리면, 그 소스는
    #    검증 없이 격자를 돈다.
    from app.composer_framework.sources.band_extreme_source import (
        BandExtremeSource, band_z)
    _bz = band_z(_px, 20)
    if not (abs(float(_bz.dropna().mean())) < 0.5):
        raise SystemExit(f"z 평균이 0 근처가 아니다 — {_bz.dropna().mean():.3f}")
    _cnt = {}
    for _sg in (1.5, 2.0, 3.0):
        _f = BandExtremeSource(20, _sg, "long",
                               entry_mode="level").build_features(_ctx)
        _cnt[_sg] = int((_f["band_signal"] > 0).sum())
    if not (_cnt[3.0] <= _cnt[2.0] <= _cnt[1.5]) or _cnt[3.0] == _cnt[1.5]:
        raise SystemExit(f"**sigma 가 신호를 안 바꾼다** — {_cnt}")
    log.info("✔ 밴드 sigma 감응 — 3.0:%d ≤ 2.0:%d ≤ 1.5:%d",
             _cnt[3.0], _cnt[2.0], _cnt[1.5])
    _bl = BandExtremeSource(20, 2.0, "long").build_features(_ctx)["band_signal"]
    _bs = BandExtremeSource(20, 2.0, "short").build_features(_ctx)["band_signal"]
    if _bs.max() > 0 or _bs.min() >= 0:
        raise SystemExit("밴드 숏 신호가 음수가 아니다")
    if int(((_bl != 0) & (_bs != 0)).sum()):
        raise SystemExit("밴드 롱·숏이 같은 봉에서 켜졌다")
    _blv = BandExtremeSource(20, 2.0, "long",
                             entry_mode="level").build_features(_ctx)["band_signal"]
    if not (int((_bl > 0).sum()) < int((_blv > 0).sum())):
        raise SystemExit("밴드 cross_back 이 level 보다 적지 않다")
    if int(((_bl > 0) & (_blv > 0)).sum()):
        raise SystemExit("밴드 두 모드가 같은 봉에서 발화했다")
    if int(((_bl > 0) & (_blv > 0).shift(1).fillna(False)).sum()) != int((_bl > 0).sum()):
        raise SystemExit("밴드 cross_back 직전 봉이 밴드 밖이 아니다")
    log.info("✔ 밴드 방향·모드 확인 — 롱 %d / 숏 %d · 겹침 0 · "
             "cross_back %d < level %d",
             int((_bl != 0).sum()), int((_bs != 0).sum()),
             int((_bl > 0).sum()), int((_blv > 0).sum()))
    verify_reaches(RsiConfig(signal="band", side="short", period=20,
                             entry_threshold=2.5, tp_pct=0.08, sl_pct=0.0,
                             max_hold_bars=288, entry_mode="cross_back"))
    # 두 신호원이 **같은 커널·같은 요율**을 쓰는지
    _cb = RsiConfig(signal="band", entry_threshold=2.0, sl_pct=0.0)
    if _bt(_cb)._kernel_config().fee_rate_maker != \
       _bt(RsiConfig(signal="rsi"))._kernel_config().fee_rate_maker:
        raise SystemExit("신호원마다 요율이 갈렸다")
    log.info("✔ 신호원 교체 확인 — 커널·요율 동일, 신호만 갈림")

    # ⓙ **거래량 항복** — 가격만으로는 성립 안 하는 첫 신호원이라 관문이 하나
    #    더 있다: volume 열이 없으면 조용한 0이 아니라 예외여야 한다.
    from app.composer_framework.sources.volume_capitulation_source import (
        VolumeCapitulationSource, volume_z)
    _n2 = 3000
    _r2 = np.random.default_rng(3)
    _ret = _r2.normal(0, 0.004, _n2)
    _vol = _r2.lognormal(10, 0.4, _n2)
    for _c0 in _r2.choice(np.arange(400, _n2 - 40), size=25, replace=False):
        _L = int(_r2.integers(4, 10))
        _ret[_c0:_c0 + _L] -= _r2.uniform(0.008, 0.025, _L)
        _vol[_c0:_c0 + _L] *= _r2.uniform(10, 40)
        _ret[_c0 + _L:_c0 + _L + 5] += _r2.uniform(0.004, 0.015, 5)
    _p2 = pd.Series(100 * np.exp(np.cumsum(_ret)),
                    index=pd.date_range("2025-01-01", periods=_n2, freq="5min"))
    _b2 = pd.DataFrame({"open": _p2, "high": _p2 * 1.001, "low": _p2 * 0.999,
                        "close": _p2, "volume": _vol})
    _ctx2 = _SC(symbol="V", eval_freq_minutes=5, ohlcv_eval=_b2)
    _vz = volume_z(_b2["volume"], 96)
    if not (abs(float(_vz.dropna().mean())) < 0.5):
        raise SystemExit(f"거래량 z 평균이 0 근처가 아니다 — {_vz.dropna().mean():.3f}")
    _c2 = {}
    for _z in (2.0, 3.0, 4.0):
        _f2 = VolumeCapitulationSource(96, _z, 5, -0.03, "long",
                                       entry_mode="level").build_features(_ctx2)
        _c2[_z] = int((_f2["volcap_signal"] > 0).sum())
    if not (_c2[4.0] <= _c2[3.0] <= _c2[2.0]) or _c2[4.0] == _c2[2.0]:
        raise SystemExit(f"**거래량 z 가 신호를 안 바꾼다** — {_c2}")
    _c3 = {}
    for _rt in (-0.01, -0.03, -0.06):
        _f3 = VolumeCapitulationSource(96, 2.0, 5, _rt, "long",
                                       entry_mode="level").build_features(_ctx2)
        _c3[_rt] = int((_f3["volcap_signal"] > 0).sum())
    if not (_c3[-0.06] <= _c3[-0.03] <= _c3[-0.01]) or _c3[-0.06] == _c3[-0.01]:
        raise SystemExit(f"**수익률 문턱이 신호를 안 바꾼다** — {_c3}")
    log.info("✔ 항복 감응 — 거래량z 4.0:%d ≤ 3.0:%d ≤ 2.0:%d · "
             "급락 6%%:%d ≤ 3%%:%d ≤ 1%%:%d",
             _c2[4.0], _c2[3.0], _c2[2.0],
             _c3[-0.06], _c3[-0.03], _c3[-0.01])
    _vl = VolumeCapitulationSource(96, 2.0, 5, -0.03, "long").build_features(_ctx2)["volcap_signal"]
    _vs = VolumeCapitulationSource(96, 2.0, 5, -0.03, "short").build_features(_ctx2)["volcap_signal"]
    if _vs.max() > 0 or int(((_vl != 0) & (_vs != 0)).sum()):
        raise SystemExit("항복 롱·숏이 어긋났다")
    log.info("✔ 항복 방향 확인 — 롱 %d / 숏 %d · 겹침 0",
             int((_vl != 0).sum()), int((_vs != 0).sum()))
    # 거래량 열이 없으면 **조용한 0 이 아니라 예외**
    try:
        VolumeCapitulationSource().build_features(
            _SC(symbol="V", eval_freq_minutes=5,
                ohlcv_eval=_b2.drop(columns=["volume"])))
    except InsufficientSourceDataError:
        log.info("✔ 항복 결손 처리 — volume 없으면 조용한 0 대신 예외")
    else:
        raise SystemExit("**volume 이 없는데 예외가 안 났다** — 조용한 0 위험")
    # 부호 실수 방어 — 롱 기준 양수 문턱은 거부되어야 한다
    try:
        VolumeCapitulationSource(96, 3.0, 5, +0.03)
    except ValueError:
        log.info("✔ 항복 부호 방어 — 양수 급락문턱 거부")
    else:
        raise SystemExit("양수 ret_threshold 가 통과했다 — 급등 진입이 된다")
    # 방아쇠는 같고 **포지션만** 뒤집혀야 한다 — 발화 봉이 같고 부호가 반대.
    _vr = VolumeCapitulationSource(96, 2.0, 5, -0.03, "long",
                                   direction="reversion").build_features(_ctx2)["volcap_signal"]
    _vc = VolumeCapitulationSource(96, 2.0, 5, -0.03, "long",
                                   direction="continuation").build_features(_ctx2)["volcap_signal"]
    if not np.array_equal((_vr != 0).to_numpy(), (_vc != 0).to_numpy()):
        raise SystemExit("**방아쇠가 같이 바뀌었다** — direction 은 포지션만 "
                         "뒤집어야 한다")
    if not ((_vr + _vc).abs().sum() == 0):
        raise SystemExit("continuation 부호가 반대가 아니다")
    log.info("✔ 방아쇠/포지션 분리 확인 — 발화 봉 동일(%d) · 부호만 반대",
             int((_vr != 0).sum()))
    verify_reaches(RsiConfig(signal="volcap", side="short", period=96,
                             entry_threshold=3.5, ret_threshold=-0.05,
                             ret_bars=24, direction="continuation",
                             tp_pct=0.08, sl_pct=0.0,
                             max_hold_bars=288, entry_mode="cross_back"))

    log.info("✔ 자기검사 통과")


# ══════════════════════════════════════════════════════════════════════
#  기질
# ══════════════════════════════════════════════════════════════════════
TF_TABLE = {"1h": "ohlcv_hourly", "15m": "ohlcv_15m", "5m": "ohlcv_5m"}
TF_MIN = {"1h": 60, "30m": 30, "15m": 15, "5m": 5, "1m": 1}
TF_RULE = {"1h": "1h", "30m": "30min", "15m": "15min",
           "5m": "5min", "1m": "1min"}


def load_1m_resampled(sym: str, tf: str, min_bars: int,
                      start: str = "", end: str = "") -> pd.DataFrame | None:
    """`ohlcv_1m` 에서 **한 종목만** 읽어 목표 시간대로 만다.

    ⚠ 전 종목을 한 번에 올리면 1.99억 행 = 11GB 를 넘고, 워커 7개가 포크되면
      감당이 안 된다. 그래서 **워커가 자기 종목만** 읽는다. 부모는 종목 이름만
      들고 있으므로 직렬화 비용도 없다.
    ⚠ 파생은 아카이브 원본과 일치함을 확인했다 (2026-08-17 실측: 1분→1시간
      744봉 완전일치).
    ⚠ 2026-08-20 결함 — 이 함수에 `start`/`end` 가 **아예 없어서**
      `--start/--end` 가 `--source 1m` 경로에서 조용히 무시됐다. 그런데
      산출물 파일명에는 창이 박혀 나갔다(`_2025-08-17_2026-08-17`). 실측:
      1년을 요청했는데 진입이 2024-08-18 부터 나왔고 **632거래(9.8%) ·
      149종목**이 창 밖이었다 — 복구로 2년치가 된 바로 그 종목들.
      종목마다 노출 기간이 달라지면 종목 간 비교가 통째로 기운다.
    """
    from sqlalchemy import text
    from app.db.session import engine
    q = ("SELECT ts, open, high, low, close, volume FROM ohlcv_1m "
         "WHERE symbol = :s")
    prm: dict = {"s": sym}
    if start:
        q += " AND ts >= :a"; prm["a"] = start
    if end:
        q += " AND ts < :b"; prm["b"] = end
    with engine.connect() as conn:
        rows = conn.execute(text(q + " ORDER BY ts"), prm).fetchall()
    if not rows:
        return None
    b = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close",
                                    "volume"])
    b["ts"] = pd.to_datetime(b["ts"])
    b = b.drop_duplicates("ts").set_index("ts")
    if tf != "1m":
        b = b.resample(TF_RULE[tf]).agg({"open": "first", "high": "max",
                                         "low": "min", "close": "last",
                                         "volume": "sum"}).dropna()
    return b if len(b) >= min_bars else None


def load_panel(min_bars: int, limit: int = 0, symbols: str = "",
               start: str = "", end: str = "", tf: str = "1h") -> dict:
    from sqlalchemy import text
    from app.db.session import engine
    table = TF_TABLE[tf]
    log.info("%s 적재 …", table)
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT symbol, ts, open, high, low, close, volume FROM "
            f"{table} ORDER BY symbol, ts")).fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "ts", "open", "high", "low",
                                     "close", "volume"])
    want = {s.strip().upper() for s in symbols.split(",") if s.strip()}
    out = {}
    for sym, g in df.groupby("symbol", sort=True):
        if want and sym not in want:
            continue
        g = g.drop_duplicates("ts").sort_values("ts")
        if len(g) < min_bars:
            continue
        b = g[["ts", "open", "high", "low", "close", "volume"]].copy()
        b["ts"] = pd.to_datetime(b["ts"])
        # ⚠ 구간을 자른 뒤 RSI 워밍업이 다시 필요하다. 소스가 `period*5` 봉을
        #   요구하므로 시작 **이전** 여유분을 남겨 자르고, 진입은 커널이 알아서
        #   워밍업 이후부터 낸다. 구간을 칼같이 자르면 앞 70봉이 죽는다.
        if start:
            lo = pd.Timestamp(start) - pd.Timedelta(minutes=200 * TF_MIN[tf])
            b = b[b["ts"] >= lo]
        if end:
            b = b[b["ts"] < pd.Timestamp(end)]
        if len(b) < min_bars:
            continue
        out[sym] = b.set_index("ts")
    if limit:
        out = {k: out[k] for k in sorted(out)[:limit]}
    log.info("적재 완료 — %d종목 · 총 %s봉", len(out),
             f"{sum(len(v) for v in out.values()):,}")
    return out


def run_symbol(cfgs: list, sym: str, bars: pd.DataFrame,
               dump_trades: bool = False) -> list:
    """한 종목을 워커로 **한 번만** 보내고 그 안에서 설정을 전부 돈다."""
    return [run_one(c, sym, bars, dump_trades) for c in cfgs]


def run_symbol_from_1m(cfgs: list, sym: str, tf: str, min_bars: int,
                       dump_trades: bool = False,
                       start: str = "", end: str = "") -> list:
    """워커가 **자기 종목만** `ohlcv_1m` 에서 읽어 파생한 뒤 설정을 전부 돈다.

    부모는 종목 이름만 들고 있으므로 메모리도 직렬화 비용도 없다.
    """
    bars = load_1m_resampled(sym, tf, min_bars, start, end)
    if bars is None:
        return [{"symbol": sym, "error": "1m 데이터 부족"} for _ in cfgs]
    return [run_one(c, sym, bars, dump_trades) for c in cfgs]


def run_one(cfg: RsiConfig, sym: str, bars: pd.DataFrame,
            dump_trades: bool = False) -> dict:
    """⑤ 정본 커널 **단일 경로**."""
    from app.composer_framework.backtester import GenericBacktester
    from app.composer_framework.pipeline_spec import build_pipeline
    from app.composer_framework.signal_source import (
        InsufficientSourceDataError, SourceContext)

    pipe = build_pipeline(cfg.pipeline_spec())
    ctx = SourceContext(symbol=sym, eval_freq_minutes=cfg.eval_freq_minutes,
                        ohlcv_eval=bars)
    try:
        kpi = _bt(cfg).run_rule_based(
            pipeline=pipe, ctx=ctx, signal_lag_bars=cfg.signal_lag_bars)
    except InsufficientSourceDataError as e:
        return {"symbol": sym, "error": str(e)}
    tr = getattr(kpi, "trades", None)
    d = {"symbol": sym}
    for f in ("total_trades", "win_rate", "total_return_pct", "sharpe",
              "max_drawdown_pct", "avg_trade_pct", "profit_factor"):
        d[f] = getattr(kpi, f, np.nan)
    if tr is not None and len(tr):
        t = pd.DataFrame(tr) if not isinstance(tr, pd.DataFrame) else tr
        col = next((c for c in ("pnl_pct", "return_pct", "pct", "ret")
                    if c in t.columns), None)
        if col:
            r = t[col].astype(float)
            # 정책이 % 로 주는지 소수로 주는지 판본마다 다르다 — 크기로 가른다
            if r.abs().median() > 1.0:
                r = r / 100.0
            w, l = r[r > 0], r[r < 0]
            d.update({
                "n_trades": int(len(r)),
                "win_rate_calc": 100.0 * float((r > 0).mean()),
                "avg_pct": 100.0 * float(r.mean()),
                "med_pct": 100.0 * float(r.median()),
                "avg_win": 100.0 * float(w.mean()) if len(w) else np.nan,
                "avg_loss": 100.0 * float(l.mean()) if len(l) else np.nan,
                "payoff": float(w.mean() / abs(l.mean()))
                          if len(w) and len(l) and l.mean() != 0 else np.nan,
                "sum_pct": 100.0 * float(r.sum()),
            })
            # ⚠ 상위 거래 절삭 검정(교훈 #81)은 **거래별** 손익이 있어야 한다.
            #   집계만 저장하면 "상위 10건이 전부였는가"를 영영 못 묻는다.
            if dump_trades:
                d["trades_pct"] = ",".join(f"{x:.6f}" for x in (100.0 * r))
                # ⚠ 포트폴리오는 **언제** 자본이 묶이는지를 알아야 한다.
                #   손익만 있으면 동시 포지션 수도 유휴 자본도 못 센다.
                keep = [c for c in ("entry_ts", "exit_ts", "entry_price",
                                    "exit_price", "exit_reason") if c in t.columns]
                tt = t[keep].copy()
                tt["ret_pct"] = 100.0 * r.to_numpy()
                tt["symbol"] = sym
                d["_trades"] = tt.to_dict("records")
    return d


def _bt(cfg):
    """백테스터 생성은 **여기 한 곳**. 요율이 갈라지지 않게.

    ⚠ 예전엔 호출부마다 `GenericBacktester(fee_rate=...)` 를 직접 만들었고
      `fee_rate_maker` 를 아무도 안 넘겼다. 커널은 익절을 메이커로 표시하는데
      요율이 None 이라 테이커로 떨어져 **페이퍼와 익절마다 3bp 어긋났다**.
      정본의 목적이 백테·페이퍼·실거래가 같은 회계를 쓰는 것인데,
      생성 지점이 여럿이면 그게 조용히 깨진다.
    """
    from app.composer_framework.backtester import GenericBacktester
    return GenericBacktester(fee_rate=cfg.fee_rate,
                             fee_rate_maker=cfg.fee_rate_maker,
                             sl_limit=cfg.sl_limit,
                             sl_limit_offset=cfg.sl_limit_offset)


def check_window(TR, a, where: str = "본실행") -> None:
    """거래가 요청한 창 안에 있는지. **예비비행과 본실행이 같은 검사를 쓴다.**

    ⚠ 2026-08-20~21 — 이 검사가 없었으면 창 밖 거래 632건이 든 결과를
      그대로 보고했다. 있었더니 92분 재실행을 거부했다(고친 곳이 직렬
      경로뿐이라 병렬이 우회했다). **검사는 맞았고 순서가 틀렸다** —
      고친 직후 몇 종목으로 먼저 봤어야 했다. 그래서 `--preflight` 가 있다.
    """
    if not (a.start or a.end) or "entry_ts" not in TR.columns:
        return
    et = pd.to_datetime(TR["entry_ts"], utc=True, errors="coerce")
    bad = 0
    if a.start:
        bad += int((et < pd.Timestamp(a.start, tz="UTC")).sum())
    if a.end:
        bad += int((et >= pd.Timestamp(a.end, tz="UTC")).sum())
    if bad:
        # ⚠ 저장만 막으면 몇 시간치 진단 근거까지 잃는다(실측: 92분).
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        bad_path = OUT_DIR / f"INVALID_window_{a.tag or 'run'}.csv"
        TR.to_csv(bad_path, index=False)
        raise SystemExit(
            f"[{where}] 창 밖 거래 {bad:,}/{len(TR):,}건 — 구간 인자가 적재까지 "
            f"도달하지 않았다. 요청 {a.start}~{a.end} 인데 진입이 "
            f"{et.min()}~{et.max()} 다. 정상 산출물은 저장하지 않았다. "
            f"진단용: {bad_path}")
    log.info("✔ 창 확인(%s) — 거래 %s건 전부 %s ~ %s 안",
             where, f"{len(TR):,}", a.start or "beg", a.end or "end")


_PARTIAL_STATE: dict = {}   # 실행 1회 = 파일 1쌍


def _partial(rows, a, trade_rows=None, _st: dict | None = None) -> None:
    """부분 저장 — **증분 추가**. 끝에 한 번에 쓰면 중간에 죽을 때 전부 잃는다.

    ⚠ 거래 원장도 같이 남긴다 (2026-08-23). 부분 파일에 종목별 집계만 있으면
      **슬롯 판독을 중간에 못 한다** — 슬롯은 진입·청산 **시각**이 있어야
      계산되는데 `trades_pct` 에는 수익률만 있다.

    ⚠ 2026-08-24: 체크포인트마다 누적분 **전체**를 다시 쓰고 있었다. 비용이
      O(n²) 다. 15만 행에서 3.37초/회 (증분이면 0.06초). 377종목 216칸에서는
      전체의 0.4% 라 무해했지만 격자를 키우면 제곱으로 커진다. 이제 새로 생긴
      행만 이어붙인다. 두 가지가 필수다 —
        · 첫 기록에서 기존 파일을 **지운다**. 안 그러면 이전 실행에 이어붙는다.
        · 컬럼을 **고정한다**. 오류 행은 `error` 키가 있어 정상 행과 열이
          달라, 청크마다 DataFrame 을 새로 만들면 순서가 어긋난다.
    """
    if _st is None:
        _st = _PARTIAL_STATE
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for name, buf in (("partial", rows), ("partialtrades", trade_rows or [])):
            done = _st.get(f"{name}_n", 0)
            if not buf or len(buf) <= done:
                continue
            path = OUT_DIR / f"{name}_{a.tag or 'run'}.csv"
            df = pd.DataFrame(buf[done:])
            cols = _st.get(f"{name}_cols")
            if cols is None:
                cols = list(df.columns)
                _st[f"{name}_cols"] = cols
                path.unlink(missing_ok=True)     # 이전 실행 잔재에 이어붙이면 안 된다
            elif set(df.columns) - set(cols):
                # 새 컬럼(대개 `error`)이 나타났다. 이어붙이기로는 담을 수 없으니
                # **이때 한 번만** 전체를 다시 쓴다. 드문 일이라 총비용은 O(n) 이다.
                cols = cols + [c for c in df.columns if c not in cols]
                _st[f"{name}_cols"] = cols
                log.info("부분 저장 — 컬럼 확장 %s, 전체 재기록 1회",
                         sorted(set(df.columns) - set(cols[:len(cols)])) or "…")
                pd.DataFrame(buf).reindex(columns=cols).to_csv(
                    path, index=False)
                _st[f"{name}_n"] = len(buf)
                continue
            df.reindex(columns=cols).to_csv(
                path, mode="a", header=(done == 0), index=False)
            _st[f"{name}_n"] = len(buf)
    except Exception as e:                       # 저장 실패가 실행을 죽이면 안 된다
        log.warning("부분 저장 실패: %s", e)


def main() -> int:
    p = argparse.ArgumentParser(description="RSI × 익절 × 손절 격자")
    p.add_argument("--signal", default="rsi",
                   help="rsi | band | volcap (쉼표로 여러 개). "
                        "--thresholds 의 뜻이 신호원마다 다르다 — rsi=RSI 문턱, "
                        "band=sigma, volcap=거래량 z")
    p.add_argument("--ret-thresholds", default="-0.03",
                   help="volcap 전용. 급락 문턱(음수). 쉼표로 격자")
    p.add_argument("--ret-bars", default="5",
                   help="volcap 전용. 수익률을 재는 봉 수. 쉼표로 격자")
    p.add_argument("--directions", default="reversion",
                   help="volcap 전용. reversion(급락에 매수) | "
                        "continuation(급락에 매도) | 둘 다(쉼표)")
    p.add_argument("--side", default="both", choices=["long", "short", "both"])
    p.add_argument("--periods", default="14")
    p.add_argument("--thresholds", default="15,20,25,30,35,40,45,50")
    p.add_argument("--tps", default="0.01,0.02,0.03,0.05")
    p.add_argument("--sls", default="0.01,0.02,0.03,0.05")
    p.add_argument("--hold", default="48",
                   help="보유 상한(봉). 쉼표로 격자. 손절이 없으면 이게 유일한 "
                        "손실 제어 수단이자 **자본 회전 속도**를 정한다 — "
                        "실측: 지는 포지션이 슬롯 점유시간의 83.6%%를 먹는다")
    p.add_argument("--min-bars", type=int, default=8760)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--symbols", default="")
    p.add_argument("--source", default="table", choices=["table", "1m"],
                   help="1m = ohlcv_1m 에서 메모리 파생 (새 테이블 안 만듦)")
    p.add_argument("--tf", default="1h",
                   choices=["1h", "30m", "15m", "5m", "1m"],
                   help="시간대. 보유상한(--hold)은 **봉 수**이니 같이 바꿔라")
    p.add_argument("--start", default="", help="구간 시작 YYYY-MM-DD (포함)")
    p.add_argument("--end", default="", help="구간 끝 YYYY-MM-DD (미포함)")
    p.add_argument("--gate-atr", default="0",
                   help="30분봉 ATR 하한 %% (쉼표). 0=끔. 실측 0.98 미만이 손익분기 미달")
    p.add_argument("--gate-drop", default="0",
                   help="직전 하락 폭 상한 %% (음수, 쉼표). 0=끔. -12 면 12%% 이상 폭락만")
    p.add_argument("--gate-vol", default="0",
                   help="거래량 배수 하한 (쉼표). 0=끔. 실측 15배 이상이 익절률 20.1%%")
    p.add_argument("--sl-limit-offsets", default="0",
                   help="지정가 손절의 방아쇠↔지정가 간격(진입가 대비, 쉼표). "
                        "0=같은 값(가장 불리) · 0.003=0.3%p 아래까지 받아준다. "
                        "0 보다 크면 그 칸은 자동으로 지정가 손절이 된다")
    p.add_argument("--sl-limit", action="store_true",
                   help="손절을 **지정가**로 건다(STOP 주문). 트리거 후 손절가로 "
                        "되돌아와야 체결 — 슬리피지 0, 대신 미체결 위험")
    p.add_argument("--exit-rsi-below", default="0",
                   help="RSI 가 이 값 아래로 다시 떨어지면 청산(쉼표로 격자). "
                        "0=비활성. 가격 손절과 달리 봉 마감 판정이라 마찰이 "
                        "시간청산 수준(실측 8.6bp)이다")
    p.add_argument("--entry-modes", default="level",
                   help="level | cross_back | 둘 다(쉼표). cross_back 은 과열 "
                        "구간을 **되돌아 나오는 봉**에서만 진입한다 — 급락 "
                        "한복판을 피한다")
    p.add_argument("--placebos", default="real",
                   help="real,rotate,random — 진입 대조군 축")
    p.add_argument("--seed", default="20260816",
                   help="위약 씨앗. 쉼표로 여러 개를 주면 **같은 격자를 씨앗마다** "
                        "돈다 — 최대통계량 귀무분포용(교훈 #95). 칸별 위약은 "
                        "이미 선택된 칸이라 통과한다")
    p.add_argument("--dump-trades", action="store_true",
                   help="거래별 손익을 실어 저장 (상위 절삭 검정용)")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--preflight", type=int, default=3,
                   help="본 실행 전에 N종목만 먼저 돌려 산출물 검사를 전부 "
                        "통과하는지 본다(기본 3, 0이면 생략). 1분이면 끝난다")
    p.add_argument("--tag", default="")
    a = p.parse_args()

    selftest()
    if a.selftest:
        return 0

    sides = ["long", "short"] if a.side == "both" else [a.side]
    placebos = [x.strip() for x in a.placebos.split(",")]
    placebos = ["" if x in ("real", "none", "") else x for x in placebos]
    modes = [m.strip() for m in a.entry_modes.split(",") if m.strip()]
    seeds = [x.strip() for x in str(a.seed).split(",") if x.strip()]
    xrs = [x.strip() for x in str(a.exit_rsi_below).split(",") if x.strip()]
    sl_offsets = [x.strip() for x in str(a.sl_limit_offsets).split(",") if x.strip()]
    g_atr = [x.strip() for x in str(a.gate_atr).split(",") if x.strip()]
    g_drop = [x.strip() for x in str(a.gate_drop).split(",") if x.strip()]
    g_vol = [x.strip() for x in str(a.gate_vol).split(",") if x.strip()]
    signals = [x.strip() for x in a.signal.split(",") if x.strip()]
    grid = [RsiConfig(signal=sg, side=s, period=int(pp),
                      entry_threshold=float(t),
                      ret_threshold=float(rt), ret_bars=int(rb),
                      direction=dr,
                      tp_pct=float(tp), sl_pct=float(sl),
                      max_hold_bars=int(hd),
                      entry_mode=em, exit_rsi_below=float(xr),
                      sl_limit=bool(a.sl_limit) or float(so) > 0,
                      sl_limit_offset=float(so),
                      min_atr_pct=float(ga), max_drop_pct=float(gd),
                      min_vol_mult=float(gv),
                      placebo=pl, placebo_seed=int(sd),
                      eval_freq_minutes=TF_MIN[a.tf])
            for sg in signals
            for rt in (a.ret_thresholds.split(",") if sg == "volcap" else ["-0.03"])
            for rb in (a.ret_bars.split(",") if sg == "volcap" else ["5"])
            for dr in (a.directions.split(",") if sg == "volcap" else ["reversion"])
            for s in sides
            for pp in a.periods.split(",")
            for t in a.thresholds.split(",")
            for tp in a.tps.split(",")
            for sl in a.sls.split(",")
            for so in sl_offsets
            for ga in g_atr
            for gd in g_drop
            for gv in g_vol
            for hd in a.hold.split(",")
            for em in modes
            for xr in xrs
            for pl in placebos
            # 실측은 씨앗과 무관하므로 한 번만. 위약만 씨앗마다 돈다.
            for sd in (seeds if pl else seeds[:1])]
    verify_reaches(grid[0])
    log.info("격자 %d칸", len(grid))

    if a.source == "1m":
        # 종목 목록만 확보한다 — 봉은 워커가 읽는다
        syms = [x.strip().upper() for x in a.symbols.split(",") if x.strip()]
        if not syms:
            syms = [x.strip().upper() for x in
                    (ROOT / "configs" / "rsi_paper_universe.txt").read_text().split()
                    if x.strip()]
        if a.limit:
            syms = sorted(syms)[:a.limit]
        panel = {s_: None for s_ in sorted(syms)}
        log.info("파생 모드 — ohlcv_1m → %s · %d종목 (워커가 종목별 적재)",
                 a.tf, len(panel))
    else:
        panel = load_panel(a.min_bars, a.limit, a.symbols, a.start, a.end, a.tf)
    if not panel:
        log.error("종목이 없다")
        return 1

    # 한 실행이 3.5초라 격자 전체는 순차로 몇 시간이다. 코어로 나눈다.
    # ⚠ 병렬화가 결과를 바꾸면 안 된다 — 각 작업은 완전히 독립이고 공유 상태가
    #   없다. 순차판과 대조하는 `--check-parallel` 을 둔다.
    jobs = sorted(panel)                      # 작업 = 종목
    log.info("작업 %d종목 × 설정 %d = %d실행 · 워커 %d",
             len(jobs), len(grid), len(jobs) * len(grid), a.workers)
    rows, t0 = [], datetime.now()

    trade_rows: list = []

    def tag(cfg, r):
        for tr in r.pop("_trades", []):
            tr.update({"key": cfg.key(), "signal": cfg.signal,
                       "side": cfg.side, "thr": cfg.entry_threshold,
                       "retthr": cfg.ret_threshold, "retbars": cfg.ret_bars,
                  "direction": cfg.direction,
                       "direction": cfg.direction,
                       "tp": cfg.tp_pct, "sl": cfg.sl_pct,
                       "entry_mode": cfg.entry_mode, "xr": cfg.exit_rsi_below,
                       # ⚠ 축은 **컬럼으로** 싣는다. key 문자열 파싱에 기대면
                       #   축이 늘 때마다 판독기가 조용히 틀린다(hold 가 그랬다).
                       "hold": cfg.max_hold_bars,
                       "sllim": cfg.sl_limit, "sloff": cfg.sl_limit_offset,
                       "gatr": cfg.min_atr_pct, "gdrop": cfg.max_drop_pct,
                       "gvol": cfg.min_vol_mult,
                       "placebo": cfg.placebo or "real"})
            trade_rows.append(tr)
        # ⚠ placebo 를 빼면 아래 집계가 **실측과 위약을 한 그룹에 섞는다**.
        #   거래 행(위)엔 붙는데 여기만 빠져 있었다 — 2026-08-19 발견.
        r.update({"signal": cfg.signal, "side": cfg.side, "period": cfg.period,
                  "retthr": cfg.ret_threshold, "retbars": cfg.ret_bars,
                  "direction": cfg.direction,
                  "thr": cfg.entry_threshold, "tp": cfg.tp_pct,
                  "sl": cfg.sl_pct, "hold": cfg.max_hold_bars,
                  "entry_mode": cfg.entry_mode, "xr": cfg.exit_rsi_below,
                  "sllim": cfg.sl_limit, "sloff": cfg.sl_limit_offset,
                  "seed": cfg.placebo_seed,
                  "placebo": cfg.placebo or "real", "key": cfg.key()})
        return r

    def _collect(res):
        for cfg, r in zip(grid, res):
            rows.append(tag(cfg, r))

    # ⚠ 2026-08-21 — 경로가 둘이라 하나만 고쳤다가 92분을 잃었다.
    #   `_dispatch` 에는 start/end 를 넣었는데 **병렬 경로는 `_dispatch` 를
    #   거치지 않고** `run_symbol_from_1m` 을 직접 submit 했다. 인자 목록이
    #   따로 적혀 있어 새 인자가 안 갔고, 창 밖 거래 1,116건이 나왔다.
    #   교훈 #88 그대로다 — 클래스(함수)만 고치지 말고 **경로**를 검증하라.
    #   이제 직렬·병렬이 **같은 인자 묶음**을 쓴다. 갈라질 자리를 없앤다.
    def _args(sym) -> tuple:
        if a.source == "1m":
            return (run_symbol_from_1m,
                    (grid, sym, a.tf, a.min_bars, a.dump_trades, a.start, a.end))
        return (run_symbol, (grid, sym, panel[sym], a.dump_trades))

    def _dispatch(sym):
        fn, args = _args(sym)
        return fn(*args)

    def _run(syms: list) -> None:
        """종목 묶음을 실행해 `rows`/`trade_rows` 에 쌓는다.

        ⚠ 예비비행이 **직렬로만** 검사하면 방금 그 결함(병렬 경로가 인자를
          버림)을 똑같이 놓친다. 그래서 예비비행도 본실행과 **같은 실행
          방식**을 쓴다 — 워커 수까지 같다.
        """
        if a.workers <= 1:
            for i, sym in enumerate(syms, 1):
                _collect(_dispatch(sym))
                if i % 5 == 0:
                    log.info("[%d/%d종목] %.0f초", i, len(syms),
                             (datetime.now() - t0).total_seconds())
                    _partial(rows, a, trade_rows)
            return
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            fut = {}
            for s_ in syms:
                fn, args = _args(s_)          # 직렬과 **같은** 인자 묶음
                fut[ex.submit(fn, *args)] = s_
            for i, f in enumerate(as_completed(fut), 1):
                _collect(f.result())
                if i % 5 == 0:
                    log.info("[%d/%d종목] %.0f초", i, len(syms),
                             (datetime.now() - t0).total_seconds())
                    _partial(rows, a, trade_rows)

    # ⚠ **예비비행**. 코드를 고친 뒤 전체를 먼저 돌렸다가 92분을 잃었다
    #   (2026-08-21). 있는 방법을 안 썼다 — 몇 종목이면 1분이다.
    #   이제 규율이 아니라 도구가 강제한다. 본실행 전에 N종목을 돌려
    #   **본실행과 같은 경로·같은 검사**를 통과하는지 본다.
    if a.preflight > 0 and len(jobs) > a.preflight:
        pre_rows: list = []
        saved_trades = len(trade_rows)
        t_pre = datetime.now()
        log.info("예비비행 — %d종목으로 경로·창 검사 먼저", a.preflight)
        saved_rows = len(rows)
        _run(jobs[:a.preflight])              # 본실행과 같은 실행 방식
        pre_rows = rows[saved_rows:]
        pre_tr = trade_rows[saved_trades:]
        if pre_tr:
            check_window(pd.DataFrame(pre_tr), a, where="예비비행")
        elif a.dump_trades:
            log.warning("예비비행에서 거래가 0건 — 창 검사를 못 했다. "
                        "--preflight 를 늘리거나 종목을 바꿔라")
        errs = [r for r in pre_rows if r.get("error")]
        if len(errs) == len(pre_rows):
            raise SystemExit(f"예비비행 {len(pre_rows)}건 전부 실패 — "
                             f"{errs[0].get('error')}")
        log.info("✔ 예비비행 통과 %.0f초 (워커 %d, 본실행과 동일) — "
                 "본실행 %d종목 착수",
                 (datetime.now() - t_pre).total_seconds(), a.workers, len(jobs))
        del trade_rows[saved_trades:]          # 본실행에서 다시 돈다
        del rows[saved_rows:]

    _run(jobs)

    P = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    span = f"_{a.start or 'beg'}_{a.end or 'end'}" if (a.start or a.end) else ""
    holds = [h.strip() for h in a.hold.split(",") if h.strip()]
    hlab = holds[0] if len(holds) == 1 else f"{len(holds)}holds"
    stem = f"{'_'.join(sides)}_{a.tf}{'from1m' if a.source=='1m' else ''}_h{hlab}{span}" + (f"_{a.tag}" if a.tag else "")
    P.to_csv(OUT_DIR / f"persym_{stem}.csv", index=False)
    if trade_rows:
        TR = pd.DataFrame(trade_rows)
        # ⚠ 파일명이 창을 주장하면 거래도 그 창 안에 있어야 한다.
        #   2026-08-20: `--start/--end` 가 1m 경로에서 무시됐는데 파일명엔
        #   창이 박혀 나갔다. 632거래(9.8%)가 창 밖이었고, 산출물만 보면
        #   알 길이 없었다. 이제 **조용히 지나가지 못한다**.
        check_window(TR, a)
        TR.to_csv(OUT_DIR / f"trades_{stem}.csv", index=False)
        log.info("거래 덤프 %s행 저장", f"{len(trade_rows):,}")

    agg = aggregate(P)
    agg.to_csv(OUT_DIR / f"agg_{stem}.csv", index=False)
    with open(OUT_DIR / f"meta_{stem}.json", "w") as fh:
        json.dump({"args": vars(a), "n_symbols": len(panel),
                   "grid": len(grid), "config_template": asdict(grid[0]),
                   "generated": datetime.now().isoformat()},
                  fh, indent=2, ensure_ascii=False)
    log.info("저장: %s", OUT_DIR / f"agg_{stem}.csv")
    print(f"\n격자 {len(agg)}칸 · 종목 {len(panel)} · 총 거래 "
          f"{int(agg.trades.sum()):,} — 판독은 rsi_tp_sl_report 로")
    return 0


if __name__ == "__main__":
    sys.exit(main())
