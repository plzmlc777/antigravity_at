"""횡단면 선별 하네스 — **공통 앵커 격자**. 설정은 한 곳, 하드코딩은 없다.

왜 다시 짓는가
    기존 `short_universe_scan` / `short_trait_scan` 은 앵커를 **종목마다 자기
    첫 봉 + 90일**에서 시작했다. 그래서 "횡단면 오분위"가 실은 시점이 섞인
    풀링이었다 — 실측 **앵커 1,154개 · 앵커당 종목 중앙 2개**.

        · 구간 **수준**이 국면과 교란된다 (IS 는 다섯 구간 전부 ≤0,
          OOS 는 전부 >0 — 그건 선별이 아니라 2025 하락/2026 반등이다)
        · 구간 **차등**을 깨끗이 보려면 같은 앵커 안에서 비교해야 하는데
          Q1·Q4 에 각 3종목 이상 있는 앵커가 OOS **6개**뿐이었다

    즉 그 하네스는 규칙 검정에는 쓸 수 있어도 **선별 검정에는 검정력이 없다.**

설계 원칙 — 반복된 결함의 원인을 규칙으로 막는다
    이번 세션에만 하드코딩 결함이 여섯 건 나왔다. 매번 하네스를 즉석에서
    짜기 때문이다. 그래서 이 파일은 다음을 **강제**한다:

    ① **설정은 `HarnessConfig` 한 곳**에만 있다. 모듈 상수 임계값 금지.
       (전례: `MIN_ANCHORS = 4` 가 상수로 박혀 표준오차가 붕괴해 t 1.3e18)
    ② **모든 파라미터는 도달을 증명한다.** `verify_reaches()` 가 조립된
       스펙에서 실제 값을 읽어 대조한다. 안 맞으면 **즉시 멈춘다.**
       (전례: `--max-age-days` 가 선언만 되고 `age > 14` 하드코딩이 이겼다.
        `entry_start_hours` 가 팩토리에서 버려졌다 — 교훈 #88)
    ③ **방향은 처음부터 파라미터.** `side` 를 가정하는 코드·문구 금지.
       (전례: 롱 실행인데 헤더가 "숏 스캔"으로 찍혔다)
    ④ **출력 경로는 설정에서 유도**한다. 손으로 주지 않는다.
       (전례: 롱 실행이 숏 기준선 json 을 조용히 덮었다)
    ⑤ **커널 호출은 한 경로**(`universe_rule_strategy.run_side`)만 쓴다.
       (전례: 손익 구현체 6개 중 4개 오염 — canon 통일 이전)
    ⑥ **관측 단위는 앵커**다. 같은 앵커의 종목 수백 개를 독립 표본으로 세지
       않는다. 앵커별 스프레드 → 그 앵커들로 t.
    ⑦ **결과 파일에 설정 전문을 박는다.** 재현 못 하는 수치는 수치가 아니다.

무엇이 달라지나 — 공통 앵커 격자
    앵커를 **달력에서** 뽑는다: `start` 부터 `stride` 일 간격. 모든 종목이
    같은 날짜에 평가되므로

        · 오분위가 **진짜 횡단면**이 된다 (같은 날, 같은 국면)
        · 국면이 **자동으로 상쇄**된다 — Q5−Q1 은 같은 날 안의 차이다
        · 앵커당 종목이 100개 이상이 된다 (기존 중앙 2개)

    그리고 판정 통계는 **앵커별 Q5−Q1 스프레드**의 t 다. 이게 선별 질문의
    올바른 관측 단위다.

⚠ 자격은 **앵커 시점 정보로만** 판정한다
    직전 `adv_window` 일 거래대금 중앙값과 앵커 **이전** 봉 수만 본다.
    전 구간 거래대금으로 거르면 끝까지 살아남은 종목만 남는다(생존 편향).

⚠ 성질도 **앵커 이전** 봉으로만 계산한다. 앵커 당일 봉은 안 쓴다.

사용:
  python3 -m scripts.research.xsection_harness --side long --trait ret_30d
  python3 -m scripts.research.xsection_harness --side short --trait all
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("xsec")

OUT_DIR = ROOT / "runs" / "research_track" / "xsection"


# ══════════════════════════════════════════════════════════════════════
#  ① 설정은 여기 **한 곳**에만 있다
# ══════════════════════════════════════════════════════════════════════
@dataclass
class HarnessConfig:
    """모든 파라미터. 모듈 상수로 임계값을 두지 않는다.

    새 파라미터를 넣을 때는 반드시 ② `verify_reaches` 에도 넣어라 —
    "선언은 됐는데 아무 데도 안 닿는" 결함이 이 저장소에서만 세 번 났다.
    """
    # 거래 규칙
    side: str = "long"                 # long | short
    sl: float = 0.20                   # 손절
    tp: float = 0.30                   # 익절 (>=1.0 이면 없음)
    hold: int = 30                     # 보유 일수
    signal_lag_bars: int = 1           # 정본 장부 규약

    # 앵커 격자 — **공통**
    start: str = "2023-01-01"
    end: str = ""                      # 빈 값이면 데이터 끝
    stride: int = 30                   # 앵커 간격(일). hold 미만이면 겹친다
    split: str = "2026-02-01"          # 표본 안/밖

    # 자격 (앵커 시점 정보로만)
    min_adv: float = 1_000_000.0       # 직전 창 거래대금 중앙값 하한
    adv_window: int = 30
    min_history: int = 90              # 앵커 이전 최소 봉 수 (성질 계산용)
    # ⚠ 기본값끼리 모순되면 `__post_init__` 이 잡는다 — 실제로 첫 실행에서
    #   20 으로 뒀다가 `min_per_bin 5 × n_bins 5 = 25 > 20` 으로 걸렸다.
    #   기질 복구 후 자격 종목이 ~224개이므로 50 은 넉넉하다.
    min_symbols_per_anchor: int = 50   # 이보다 적으면 그 앵커는 버린다

    # 판정
    n_bins: int = 5
    min_per_bin: int = 5               # 구간당 최소 종목 (앵커별)
    min_anchors: int = 10              # 이보다 적으면 **판정하지 않는다**

    trait: str = "all"
    limit_symbols: int = 0             # 0 = 전부 (디버그용)
    # ⚠ **최대통계량 귀무** — 성질 13종 × 방향이면 검정이 26회다. 26칸에서
    #   고른 최고 t 는 26번 뽑기의 최댓값이지 한 번 뽑기의 값이 아니다.
    #   귀무는 **같은 격자를 전부 다시 훑은** 최고 |t| 다(교훈 #95).
    #   섞는 방식: 앵커 **안에서** 성질을 뒤섞는다 — 앵커 구조와 그 날의
    #   수익 분포는 보존하고 종목별 성질↔수익 연결만 깬다.
    shuffle_null: int = 0              # 0 = 안 함. 200 권장

    def __post_init__(self):
        if self.side not in ("long", "short"):
            raise SystemExit(f"side={self.side!r} — long|short 만 된다")
        if self.stride < self.hold:
            raise SystemExit(
                f"앵커 간격 {self.stride}일 < 보유 {self.hold}일 — **창이 겹친다**.\n"
                f"  겹치는 창으로 상관·지속성을 재면 가짜가 나온다"
                f" (실측 r +0.470 → 비겹침 +0.001).")
        if self.n_bins < 2:
            raise SystemExit("n_bins 는 2 이상")
        if self.min_per_bin * self.n_bins > self.min_symbols_per_anchor:
            raise SystemExit(
                f"min_per_bin({self.min_per_bin}) × n_bins({self.n_bins}) 가 "
                f"min_symbols_per_anchor({self.min_symbols_per_anchor}) 보다 크다 "
                f"— 어떤 앵커도 통과 못 한다")

    # ④ 출력 경로는 **설정에서 유도**한다 — 손으로 주지 않으므로 충돌이 없다
    @property
    def out_path(self) -> Path:
        tag = (f"{self.side}_sl{int(self.sl*100)}_tp{int(self.tp*100)}"
               f"_h{self.hold}_s{self.stride}_{self.trait}")
        return OUT_DIR / f"xsection_{tag}.json"


# ══════════════════════════════════════════════════════════════════════
#  ② 파라미터가 실제로 **도달하는지** 증명한다
# ══════════════════════════════════════════════════════════════════════
def verify_reaches(cfg: HarnessConfig, sample_symbol: str,
                   bars: pd.DataFrame, anchor) -> None:
    """조립된 파이프라인 스펙에서 값을 **읽어** 설정과 대조한다.

    이게 없으면 "플래그는 있는데 판정은 하드코딩"을 못 잡는다. 이 저장소에서
    실제로 세 번 났다 — `entry_start_hours`(팩토리가 버림) ·
    `--max-age-days`(`age > 14` 하드코딩) · `long_threshold`(정책이 안 받음,
    롱 거래 0건). 전부 **로그는 정상**이었다.
    """
    from research.universe_rule_strategy import run_side
    sink: dict = {}
    run_side(sample_symbol, anchor, bars, cfg.sl, cfg.tp, cfg.hold,
             cfg.side, spec_sink=sink)
    pol = (sink.get("policy") or {}).get("kwargs") or {}
    comp = (sink.get("composer") or {}).get("kwargs") or {}
    checks = [
        ("sl_pct", pol.get("sl_pct"), cfg.sl),
        ("tp_pct", pol.get("tp_pct"), (1.0 if cfg.tp >= 1.0 else cfg.tp)),
        ("max_hold_bars", pol.get("max_hold_bars"), cfg.hold),
    ]
    bad = [(k, got, want) for k, got, want in checks
           if got is None or abs(float(got) - float(want)) > 1e-9]
    if bad:
        raise SystemExit(
            "**설정이 스펙에 도달하지 않았다** — 값을 바꿔도 판정이 안 바뀐다:\n"
            + "\n".join(f"  {k}: 스펙={got!r} 설정={want!r}" for k, got, want in bad))
    # ③ 방향도 확인한다 — 롱인데 컴포저 scale 이 안 뒤집혔으면 숏을 돈다
    scale = comp.get("scale")
    if cfg.side == "long" and (scale is None or float(scale) >= 0):
        raise SystemExit(
            f"side=long 인데 composer.scale={scale!r} — 소스가 -1.0(숏)을 내므로 "
            f"scale 이 음수여야 롱이 된다. **숏을 롱이라 부르며 돌 뻔했다**")
    if cfg.side == "short" and scale is not None and float(scale) < 0:
        raise SystemExit(f"side=short 인데 composer.scale={scale!r} 로 뒤집혀 있다")
    log.info("✔ 파라미터 도달 확인 — sl=%.2f tp=%.2f hold=%d side=%s scale=%s",
             cfg.sl, cfg.tp, cfg.hold, cfg.side, scale)


# ══════════════════════════════════════════════════════════════════════
#  기질 적재 — 한 번만 읽고 메모리에서 자른다
# ══════════════════════════════════════════════════════════════════════
def load_panel(conn):
    """일봉 패널 + 펀딩 패널. 한 번만 읽고 메모리에서 자른다.

    ⚠ 펀딩은 2026-08-15 에 26종목 → **354종목 · 116만 행**으로 늘렸다.
      그 전에는 성질로 쓸 수 없었다.
    """
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT symbol, date, open, high, low, close, volume FROM ohlcv_daily "
        "WHERE is_partial = false ORDER BY date, symbol")).fetchall()
    d = pd.DataFrame(r, columns=["symbol", "ts", "open", "high", "low",
                                 "close", "volume"])
    d["ts"] = pd.to_datetime(d["ts"])
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    close = d.pivot(index="ts", columns="symbol", values="close").sort_index()
    dvol = (d.assign(x=d["close"] * d["volume"])
             .pivot(index="ts", columns="symbol", values="x").sort_index())
    f = conn.execute(text(
        "SELECT symbol, date_trunc('day', funding_time) dd, sum(funding_rate) fr "
        "FROM binance_funding_rate GROUP BY symbol, dd")).fetchall()
    fu = pd.DataFrame(f, columns=["symbol", "ts", "fr"])
    fu["ts"] = pd.to_datetime(fu["ts"])
    fu["fr"] = pd.to_numeric(fu["fr"], errors="coerce")
    fund = (fu.pivot(index="ts", columns="symbol", values="fr").sort_index()
            .reindex(index=close.index).fillna(0.0))
    return close, dvol, fund


# ⚠ 성질을 늘리면 **검정 횟수가 늘어난다.** 13성질 × 2방향 = 26회다.
#   그래서 `--shuffle-null` 최대통계량 귀무가 **필수**다 — 26칸에서 고른
#   최고 t 는 26번 뽑기의 최댓값이지 한 번 뽑기의 값이 아니다(교훈 #95).
TRAITS = (
    # 변동성·수익 계열 (기존)
    "rv_30d", "ret_30d", "ret_7d", "dd_from_high", "log_dollar_vol",
    # 펀딩 — 2026-08-15 에 354종목으로 늘려 처음 쓸 수 있게 된 축
    "funding_sum_30d", "funding_z_30d",
    # 구조·미시 계열
    "age_days", "turnover_ratio", "beta_btc_60d", "skew_30d",
    "downside_ratio", "amihud",
)
BENCH = "BTCUSDT"


def traits_before(close: pd.DataFrame, dvol: pd.DataFrame,
                  fund: pd.DataFrame, anchor: pd.Timestamp) -> pd.DataFrame:
    """앵커 **이전** 봉으로만 계산한 성질 표 (index=symbol).

    ⚠ 앵커 당일 봉은 쓰지 않는다 — `index < anchor`. 당일을 넣으면 진입가
      정보가 성질에 새어든다.
    """
    hist = close.loc[close.index < anchor]
    dv = dvol.loc[dvol.index < anchor]
    fd = fund.loc[fund.index < anchor]
    if len(hist) < 61:
        return pd.DataFrame()
    ret = hist.pct_change()
    r30 = ret.tail(30)
    dvol30 = dv.tail(30).median().replace(0, np.nan)
    down = r30.where(r30 < 0)
    f30 = fd.tail(30)
    f_mu, f_sd = f30.mean(), f30.std()
    # BTC 대비 베타 — 60일. 벤치가 없으면 NaN
    beta = pd.Series(np.nan, index=hist.columns)
    if BENCH in hist.columns:
        b = ret[BENCH].tail(60)
        r60 = ret.tail(60)
        var = float(b.var())
        if var and var == var:
            beta = r60.apply(lambda c: c.cov(b) / var)
    out = pd.DataFrame({
        "rv_30d": r30.std() * 100,
        "ret_30d": (hist.iloc[-1] / hist.iloc[-31] - 1) * 100,
        "ret_7d": (hist.iloc[-1] / hist.iloc[-8] - 1) * 100,
        "dd_from_high": (hist.iloc[-1] / hist.tail(90).max() - 1) * 100,
        "log_dollar_vol": np.log10(dvol30),
        # 펀딩 — 양수면 롱이 숏에게 지급한다(숏이 받는다)
        "funding_sum_30d": f30.sum() * 100,
        "funding_z_30d": ((fd.tail(3).sum() - f_mu * 3)
                          / (f_sd.replace(0, np.nan) * np.sqrt(3))),
        # 상장 이후 경과 — 완전한 일봉 수로 근사한다
        "age_days": hist.notna().sum().astype(float),
        # 최근 거래 활황도 — 7일 대비 60일
        "turnover_ratio": (dv.tail(7).mean()
                           / dv.tail(60).mean().replace(0, np.nan)),
        "beta_btc_60d": beta,
        "skew_30d": r30.skew(),
        # 하방 변동성 비중 — 같은 변동성이라도 아래로 치우쳤는지
        "downside_ratio": (down.std() / r30.std().replace(0, np.nan)),
        # Amihud 비유동성 — 거래대금당 가격 충격
        "amihud": (r30.abs().mean() / dvol30) * 1e9,
    })
    return out


# ══════════════════════════════════════════════════════════════════════
#  판정 — ⑥ 관측 단위는 **앵커**
# ══════════════════════════════════════════════════════════════════════
def judge(rows: pd.DataFrame, cfg: HarnessConfig, trait: str) -> dict:
    """앵커별로 오분위를 **그 앵커 안에서** 나누고, Q_top − Q_bot 스프레드를
    앵커 하나당 관측 하나로 삼는다. 국면은 같은 날 안에서 상쇄된다."""
    spreads, per_bin = [], {k: [] for k in range(1, cfg.n_bins + 1)}
    for an, g in rows.groupby("anchor"):
        g = g.dropna(subset=[trait, "ret"])
        if len(g) < cfg.min_symbols_per_anchor:
            continue
        # 같은 앵커 안에서 순위 → 오분위. 경계를 표본 안에서 잡을 필요가 없다
        # (같은 날 안의 상대 순위라 국면이 들어오지 않는다).
        q = pd.qcut(g[trait].rank(method="first"), cfg.n_bins,
                    labels=list(range(1, cfg.n_bins + 1)))
        g = g.assign(q=q)
        sizes = g.groupby("q", observed=True).size()
        if sizes.min() < cfg.min_per_bin or len(sizes) < cfg.n_bins:
            continue
        means = g.groupby("q", observed=True)["ret"].mean()
        for k in range(1, cfg.n_bins + 1):
            per_bin[k].append(float(means.get(k, np.nan)))
        spreads.append({"anchor": str(an.date()),
                        "spread": float(means[cfg.n_bins] - means[1]),
                        "n": int(len(g))})
    if len(spreads) < cfg.min_anchors:
        return {"trait": trait, "n_anchors": len(spreads),
                "verdict": f"앵커 {len(spreads)}개 < 최소 {cfg.min_anchors}개 "
                           f"— **판정하지 않는다**"}
    sp = pd.DataFrame(spreads)
    sp["split"] = np.where(pd.to_datetime(sp["anchor"]) < pd.Timestamp(cfg.split),
                           "IS", "OOS")
    out = {"trait": trait, "n_anchors": len(sp), "bins": {}, "splits": {},
           # ⑦ 앵커별 원값을 남긴다 — 나중에 "이 스프레드가 시장 방향으로
           #    설명되는가" 같은 후속 검정을 재실행 없이 할 수 있어야 한다.
           "per_anchor": sp.to_dict("records")}
    for k in range(1, cfg.n_bins + 1):
        v = np.array([x for x in per_bin[k] if x == x])
        out["bins"][k] = {"n": int(len(v)), "mean": float(v.mean())}
    for name, g in sp.groupby("split"):
        v = g["spread"].values
        se = v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else np.nan
        out["splits"][name] = {
            "n_anchors": int(len(v)), "mean": float(v.mean()),
            "med": float(np.median(v)),
            "t": float(v.mean() / se) if se and se == se else None,
            "pos_frac": float((v > 0).mean()),
        }
    a = out["splits"].get("IS", {}); b = out["splits"].get("OOS", {})
    same_sign = (a.get("mean", 0) * b.get("mean", 0) > 0) if a and b else False
    out["survives"] = bool(
        same_sign and b.get("n_anchors", 0) >= cfg.min_anchors
        and abs(b.get("t") or 0) >= 2.0)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="횡단면 선별 하네스 (공통 앵커 격자)")
    for f_ in HarnessConfig.__dataclass_fields__.values():
        arg = "--" + f_.name.replace("_", "-")
        if f_.type is bool:
            p.add_argument(arg, action="store_true")
        else:
            p.add_argument(arg, type=type(f_.default), default=f_.default)
    a = p.parse_args()
    cfg = HarnessConfig(**{k: getattr(a, k)
                           for k in HarnessConfig.__dataclass_fields__})

    from app.db.session import engine
    with engine.connect() as conn:
        close, dvol, fund = load_panel(conn)
    end = pd.Timestamp(cfg.end) if cfg.end else close.index[-1]
    start = pd.Timestamp(cfg.start)

    # 공통 앵커 격자 — **달력에서** 뽑는다. 종목마다 다르지 않다.
    anchors = pd.date_range(start, end - pd.Timedelta(days=cfg.hold + 2),
                            freq=f"{cfg.stride}D")
    log.info("앵커 %d개 (%s ~ %s · %d일 간격) · 종목 후보 %d",
             len(anchors), anchors[0].date(), anchors[-1].date(),
             cfg.stride, close.shape[1])

    # ⚠ **검정력을 먼저 확인한다.** 표본 밖 앵커가 몇 개인지는 데이터를 돌리기
    #   전에 알 수 있다. 돌리고 나서야 "OOS 5개였네" 하면, 그 5개로 나온 t 를
    #   보고 분할을 옮기고 싶어진다 — 그게 사후 조정이다.
    #   실측: split 2026-02-01 · stride 30 이면 OOS 앵커가 **5개**뿐이었고
    #   그 5개에서 log_dollar_vol 숏이 t **+5.02** 를 냈다(100% 양수).
    n_is = int((anchors < pd.Timestamp(cfg.split)).sum())
    n_oos = int(len(anchors) - n_is)
    if min(n_is, n_oos) < cfg.min_anchors:
        latest = (anchors[-1] - pd.Timedelta(days=cfg.stride * cfg.min_anchors))
        earliest = (anchors[0] + pd.Timedelta(days=cfg.stride * cfg.min_anchors))
        raise SystemExit(
            f"**검정력 부족** — IS 앵커 {n_is}개 / OOS 앵커 {n_oos}개 "
            f"(최소 {cfg.min_anchors}개씩 필요)\n"
            f"  분할을 {earliest.date()} ~ {latest.date()} 사이로 두거나, "
            f"`--start` 를 앞당기거나, `--stride` 를 줄여라.\n"
            f"  ⚠ **결과를 보고 분할을 고르지 마라** — 이 검사는 그래서 "
            f"데이터를 돌리기 전에 있다.")
    log.info("검정력 — IS 앵커 %d개 / OOS 앵커 %d개 (최소 %d)",
             n_is, n_oos, cfg.min_anchors)

    # ② 도달 검증 — 실제 데이터로 한 번 돌려 스펙을 읽어본다
    probe_sym = close.notna().sum().idxmax()
    probe_anchor = anchors[len(anchors) // 2]
    seg = close[[probe_sym]].loc[probe_anchor:probe_anchor
                                 + pd.Timedelta(days=cfg.hold + 5)]
    from sqlalchemy import text
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT date, open, high, low, close, volume FROM ohlcv_daily "
            "WHERE symbol=:s AND date>=:a AND date<=:b AND is_partial=false "
            "ORDER BY date"),
            {"s": probe_sym, "a": probe_anchor.date(),
             "b": (probe_anchor + pd.Timedelta(days=cfg.hold + 5)).date()}
        ).fetchall()
    pb = pd.DataFrame(r, columns=["ts", "open", "high", "low", "close", "volume"])
    pb["ts"] = pd.to_datetime(pb["ts"])
    pb = pb.set_index("ts").astype(float)
    verify_reaches(cfg, probe_sym, pb, probe_anchor.date())

    # ── 앵커 격자 순회 ────────────────────────────────────────────────
    from research.universe_rule_strategy import run_side
    adv = dvol.rolling(cfg.adv_window, min_periods=max(5, cfg.adv_window // 2)
                       ).median().shift(1)
    hist_n = close.notna().cumsum().shift(1)
    recs = []
    with engine.connect() as conn:
        for ai, an in enumerate(anchors, 1):
            if an not in adv.index:
                idx = adv.index.searchsorted(an)
                if idx >= len(adv.index):
                    continue
                an_key = adv.index[idx]
            else:
                an_key = an
            elig = adv.loc[an_key][adv.loc[an_key] >= cfg.min_adv].index
            elig = [s for s in elig
                    if hist_n.loc[an_key, s] >= cfg.min_history]
            if cfg.limit_symbols:
                elig = elig[:cfg.limit_symbols]
            if len(elig) < cfg.min_symbols_per_anchor:
                continue
            tr = traits_before(close[elig], dvol[elig], fund.reindex(columns=elig).fillna(0.0), an)
            if tr.empty:
                continue
            rows = conn.execute(text(
                "SELECT symbol, date, open, high, low, close, volume "
                "FROM ohlcv_daily WHERE symbol = ANY(:s) AND date >= :a "
                "AND date <= :b AND is_partial = false ORDER BY symbol, date"),
                {"s": list(elig), "a": an.date(),
                 "b": (an + pd.Timedelta(days=cfg.hold + 5)).date()}).fetchall()
            seg_df = pd.DataFrame(rows, columns=["symbol", "ts", "open", "high",
                                                 "low", "close", "volume"])
            if seg_df.empty:
                continue
            seg_df["ts"] = pd.to_datetime(seg_df["ts"])
            for sym, g in seg_df.groupby("symbol"):
                bars = g.set_index("ts")[["open", "high", "low", "close",
                                          "volume"]].astype(float)
                if len(bars) < cfg.hold - 2:
                    continue
                try:
                    trades = run_side(sym, an.date(), bars, cfg.sl, cfg.tp,
                                      cfg.hold, cfg.side)
                except Exception:
                    continue
                for t in (trades or []):
                    rec = {"anchor": an, "symbol": sym,
                           "ret": float(t.return_pct) * 100}
                    rec.update({k: float(tr.loc[sym, k]) if sym in tr.index
                                and tr.loc[sym, k] == tr.loc[sym, k] else np.nan
                                for k in TRAITS})
                    recs.append(rec)
            if ai % 10 == 0:
                log.info("앵커 %d/%d · 표본 %d", ai, len(anchors), len(recs))

    if not recs:
        raise SystemExit("표본이 없다 — 자격 조건을 확인하라")
    df = pd.DataFrame(recs)
    per_anchor = df.groupby("anchor").size()
    log.info("표본 %d · 앵커 %d개 · **앵커당 종목 중앙 %d개**",
             len(df), df["anchor"].nunique(), int(per_anchor.median()))

    traits = list(TRAITS) if cfg.trait == "all" else [cfg.trait]
    print("=" * 100)
    print(f"  **횡단면 선별 — 공통 앵커 격자** · {cfg.side.upper()} · 손절 "
          f"{cfg.sl:.0%} · 익절 {'없음' if cfg.tp>=1 else f'{cfg.tp:.0%}'} · "
          f"보유 {cfg.hold}일")
    print(f"  앵커 {df['anchor'].nunique()}개 · 앵커당 종목 중앙 "
          f"**{int(per_anchor.median())}개** · 분할 {cfg.split}")
    print(f"  ⚠ 관측 단위는 **앵커**다 — 같은 날 종목 수백 개를 독립 표본으로 "
          f"세지 않는다")
    print("=" * 100)
    print(f"\n  {'성질':>16}{'앵커':>6} | {'IS n':>6}{'IS 스프%p':>10}{'IS t':>7}"
          f"{'IS 양수':>8} | {'OOS n':>7}{'OOS 스프%p':>11}{'OOS t':>7}"
          f"{'OOS 양수':>9} | {'통과':>5}")
    out = {"config": asdict(cfg), "n_samples": int(len(df)),
           "n_anchors": int(df["anchor"].nunique()),
           "median_symbols_per_anchor": int(per_anchor.median()),
           "results": {}}
    for tr_ in traits:
        r = judge(df, cfg, tr_)
        out["results"][tr_] = r
        if "verdict" in r:
            print(f"  {tr_:>16}{r['n_anchors']:>6} | {r['verdict']}")
            continue
        i_, o_ = r["splits"].get("IS", {}), r["splits"].get("OOS", {})
        print(f"  {tr_:>16}{r['n_anchors']:>6} | "
              f"{i_.get('n_anchors',0):>6}{i_.get('mean',np.nan):>+10.2f}"
              f"{(i_.get('t') or 0):>+7.2f}{i_.get('pos_frac',0)*100:>7.0f}% | "
              f"{o_.get('n_anchors',0):>7}{o_.get('mean',np.nan):>+11.2f}"
              f"{(o_.get('t') or 0):>+7.2f}{o_.get('pos_frac',0)*100:>8.0f}% | "
              f"{'○' if r['survives'] else '✗':>5}")

    # ── 최대통계량 귀무 (교훈 #95) ────────────────────────────────────
    if cfg.shuffle_null:
        # ⚠ 귀무는 **사전 확정한 통과 규칙과 같은 통계량**으로 만들어야 한다.
        #   OOS t 하나만 쓰면 "IS·OOS 부호 일치 + 둘 다 유의"라는 실제 기준보다
        #   느슨한 귀무가 되어, 그 기준을 통과한 칸을 과소평가한다.
        #   결합 통계량 = 부호가 일치할 때 min(|IS t|, |OOS t|), 아니면 0.
        def joint_stat(res: dict) -> float:
            i_ = (res.get("splits", {}) or {}).get("IS") or {}
            o_ = (res.get("splits", {}) or {}).get("OOS") or {}
            ti, to = i_.get("t"), o_.get("t")
            if ti is None or to is None:
                return 0.0
            if float(i_.get("mean", 0)) * float(o_.get("mean", 0)) <= 0:
                return 0.0                     # 부호 불일치 = 탈락
            return min(abs(float(ti)), abs(float(to)))

        obs_oos = max((abs((r.get("splits", {}).get("OOS", {}) or {}).get("t") or 0)
                       for r in out["results"].values()), default=0.0)
        obs_max = max((joint_stat(r) for r in out["results"].values()), default=0.0)
        obs_best = max(out["results"].items(),
                       key=lambda kv: joint_stat(kv[1]))[0]
        rng = np.random.default_rng(20260816)
        null = []
        for _ in range(cfg.shuffle_null):
            sh = df.copy()
            # 앵커 안에서 성질만 뒤섞는다 — 그 날의 수익 분포는 그대로다
            for tr_ in traits:
                sh[tr_] = sh.groupby("anchor")[tr_].transform(
                    lambda v: rng.permutation(v.values))
            m = mo = 0.0
            for tr_ in traits:
                rr = judge(sh, cfg, tr_)
                m = max(m, joint_stat(rr))
                mo = max(mo, abs((rr.get("splits", {}).get("OOS", {}) or {})
                                 .get("t") or 0))
            null.append((m, mo))
        null_j = np.array([x[0] for x in null])
        null_o = np.array([x[1] for x in null])
        null = null_j
        null = np.array(null)
        p_max = float((null >= obs_max).mean())
        p_oos = float((null_o >= obs_oos).mean())
        out["max_stat"] = {
            "joint": {"obs": obs_max, "best_trait": obs_best, "p": p_max,
                      "null_med": float(np.median(null_j)),
                      "null_p95": float(np.percentile(null_j, 95))},
            "oos_only": {"obs": obs_oos, "p": p_oos,
                         "null_med": float(np.median(null_o)),
                         "null_p95": float(np.percentile(null_o, 95))}}
        print(f"\n  **최대통계량 귀무** — 앵커 안 성질 뒤섞기 "
              f"{cfg.shuffle_null}회 × {len(traits)}성질 전부 재판정")
        print(f"     ① OOS t 만        관측 **{obs_oos:.2f}** · 귀무 중앙 "
              f"{np.median(null_o):.2f} · p95 {np.percentile(null_o,95):.2f}"
              f" → p {p_oos:.3f}")
        print(f"     ② **결합**(부호일치 & min(|IS t|,|OOS t|)) — 사전 확정 "
              f"규칙과 같은 통계량")
        print(f"        관측 **{obs_max:.2f}** ({obs_best}) · 귀무 중앙 "
              f"{np.median(null_j):.2f} · p95 {np.percentile(null_j,95):.2f}"
              f" → **p {p_max:.3f}**")

    print("\n" + "=" * 100)
    print("  통과 조건 — IS·OOS 부호 일치 + OOS |t| >= 2.0 + 앵커 "
          f">= {cfg.min_anchors}")
    print("  스프레드 = 같은 앵커 안에서 Q{top} 평균 − Q1 평균. 국면은 상쇄된다."
          .replace("{top}", str(cfg.n_bins)))
    cfg.out_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2,
                                       default=str))
    print(f"  → {cfg.out_path}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
