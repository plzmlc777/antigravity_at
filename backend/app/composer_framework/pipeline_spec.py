"""Serializable Pipeline configuration.

A Pipeline must be reconstructable from a JSON-friendly spec:
  {
    "sources": [
      {"type": "market_state", "kwargs": {}},
      {"type": "regime", "kwargs": {"daily_preset": true}},
      {"type": "pattern", "kwargs": {"pattern_lookback_bars": 5}},
      {"type": "kr_flow", "kwargs": {"symbol": "122630"}},
    ],
    "composer": {"type": "lgbm", "kwargs": {}},
    "policy": {"type": "long_only_threshold", "kwargs": {
        "entry_threshold": 0.005, "sl_pct": 0.04, "tp_pct": 0.10,
        "max_hold_bars": 5
    }},
    "config": {"eval_freq_minutes": 1440, "forward_bars": 5}
  }

Sources that need RUN-TIME data (e.g. PatternSource needs signals_df,
KRInvestorFlowSource needs flow_df) get those injected via `runtime_data`
at build time — not stored in the spec.
"""
from __future__ import annotations

from typing import Any, Callable

import joblib
import pandas as pd

from .composer import Composer
from .pipeline import Pipeline, PipelineConfig
from .policy import (
    FundingReversalPolicy,
    LifecycleDecayEarlyExitPolicy,
    LongOnlyThresholdPolicy,
    LongShortThresholdPolicy,
    TradingPolicy,
)
from .signal_source import SignalSource


# ─────────────────────────────────────────────────── registries ───
# Each entry is (factory_function) that takes (kwargs, runtime_data) and
# returns the instance. runtime_data is a dict of arbitrary Python objects
# the factory may need (signals_df, flow_df, metrics_df, ohlcv_1m, etc.).

SOURCE_FACTORIES: dict[str, Callable[[dict, dict], SignalSource]] = {}
COMPOSER_FACTORIES: dict[str, Callable[[dict], Composer]] = {}
POLICY_FACTORIES: dict[str, Callable[[dict], TradingPolicy]] = {}


def register_source(type_name: str):
    def _wrap(fn):
        SOURCE_FACTORIES[type_name] = fn
        return fn
    return _wrap


def register_composer(type_name: str):
    def _wrap(fn):
        COMPOSER_FACTORIES[type_name] = fn
        return fn
    return _wrap


def register_policy(type_name: str):
    def _wrap(fn):
        POLICY_FACTORIES[type_name] = fn
        return fn
    return _wrap


# ─────────────────────────────────────────────────── default registry entries ───


@register_source("market_state")
def _build_market_state(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import MarketStateSource
    return MarketStateSource()


@register_source("regime")
def _build_regime(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import RegimeSource
    return RegimeSource(daily_preset=bool(kwargs.get("daily_preset", True)))


@register_source("pattern")
def _build_pattern(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import PatternSource
    signals_df = runtime.get("signals_df")
    if signals_df is None:
        raise KeyError("runtime_data['signals_df'] required for pattern source")
    return PatternSource(
        signals_df=signals_df,
        pattern_lookback_bars=int(kwargs.get("pattern_lookback_bars", 5)),
    )


@register_source("kr_flow")
def _build_kr_flow(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import KRInvestorFlowSource
    flow_df = runtime.get("flow_df")
    if flow_df is not None:
        return KRInvestorFlowSource(flow_df=flow_df)
    sym = kwargs.get("symbol") or runtime.get("symbol")
    if not sym:
        raise KeyError("kr_flow source needs flow_df or symbol")
    return KRInvestorFlowSource(symbol=sym)


@register_source("binance_micro")
def _build_binance_micro(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceMicrostructureSource
    metrics = runtime.get("binance_metrics_5m")
    if metrics is None:
        raise KeyError("runtime_data['binance_metrics_5m'] required for binance_micro")
    return BinanceMicrostructureSource(metrics_5m=metrics)


@register_source("bn_funding_oi")
def _build_bn_funding_oi(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceFundingOISource
    funding = runtime.get("binance_funding_df")
    oi = runtime.get("binance_oi_df")
    if funding is None and oi is None:
        raise KeyError("runtime_data needs binance_funding_df and/or binance_oi_df for bn_funding_oi")
    return BinanceFundingOISource(funding_df=funding, oi_df=oi)


@register_source("bn_smart_money")
def _build_bn_smart_money(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceSmartMoneySource
    metrics = runtime.get("binance_metrics_5m")
    if metrics is None:
        raise KeyError("runtime_data['binance_metrics_5m'] required for bn_smart_money")
    return BinanceSmartMoneySource(metrics_5m=metrics)


@register_source("bn_taker_flow")
def _build_bn_taker_flow(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceTakerFlowSource
    metrics = runtime.get("binance_metrics_5m")
    if metrics is None:
        raise KeyError("runtime_data['binance_metrics_5m'] required for bn_taker_flow")
    return BinanceTakerFlowSource(metrics_5m=metrics)


@register_source("bn_book_depth")
def _build_bn_book_depth(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceBookDepthSource
    bd = runtime.get("book_depth_daily")
    if bd is None:
        raise KeyError("runtime_data['book_depth_daily'] required for bn_book_depth")
    return BinanceBookDepthSource(bd_daily=bd)


@register_source("bn_premium")
def _build_bn_premium(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinancePremiumSource
    premium = runtime.get("premium_df")
    if premium is None:
        raise KeyError("runtime_data['premium_df'] required for bn_premium")
    return BinancePremiumSource(premium_df=premium)


@register_source("bn_event_detector")
def _build_bn_event_detector(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceEventDetectorSource
    metrics = runtime.get("binance_metrics_5m")
    if metrics is None:
        raise KeyError("runtime_data['binance_metrics_5m'] required for bn_event_detector")
    return BinanceEventDetectorSource(metrics_5m=metrics)


@register_source("bn_mtf_alignment")
def _build_bn_mtf_alignment(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceMTFAlignmentSource
    return BinanceMTFAlignmentSource()


@register_source("bn_cascade_reversal")
def _build_bn_cascade_reversal(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceCascadeReversalSource
    metrics = runtime.get("binance_metrics_5m")
    if metrics is None:
        raise KeyError("runtime_data['binance_metrics_5m'] required for bn_cascade_reversal")
    return BinanceCascadeReversalSource(metrics_5m=metrics)


@register_source("bn_cross_eth")
def _build_bn_cross_eth(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceCrossETHSource
    eth = runtime.get("eth_ohlcv_eval")
    if eth is None:
        raise KeyError("runtime_data['eth_ohlcv_eval'] required for bn_cross_eth")
    return BinanceCrossETHSource(eth_ohlcv_eval=eth)


@register_source("bn_oi_dynamics")
def _build_bn_oi_dynamics(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceOIDynamicsSource
    metrics = runtime.get("binance_metrics_5m")
    if metrics is None:
        raise KeyError("runtime_data['binance_metrics_5m'] required for bn_oi_dynamics")
    return BinanceOIDynamicsSource(metrics_5m=metrics)


@register_source("bn_funding_zscore")
def _build_bn_funding_zscore(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceFundingZScoreSource
    funding = runtime.get("binance_funding_df")
    if funding is None:
        raise KeyError("runtime_data['binance_funding_df'] required for bn_funding_zscore")
    return BinanceFundingZScoreSource(
        funding_df=funding,
        lookback=int(kwargs.get("lookback", 30)),
    )


@register_source("bn_autocorr_regime")
def _build_bn_autocorr_regime(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceAutocorrRegimeSource
    return BinanceAutocorrRegimeSource(**(kwargs or {}))


@register_source("bn_funding_dispersion")
def _build_bn_funding_dispersion(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceFundingDispersionSource
    universe_df = runtime.get("binance_funding_universe_df")
    if universe_df is None:
        raise KeyError("runtime_data['binance_funding_universe_df'] required for bn_funding_dispersion")
    target = kwargs.get("target_symbol") or runtime.get("symbol")
    if not target:
        raise KeyError("bn_funding_dispersion needs target_symbol in kwargs or runtime['symbol']")
    return BinanceFundingDispersionSource(
        funding_universe_df=universe_df,
        target_symbol=target,
        entry_z=float(kwargs.get("entry_z", 0.8)),
    )


@register_source("bn_cross_lead_lag")
def _build_bn_cross_lead_lag(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceCrossLeaderLagSource
    leader = runtime.get("leader_ohlcv_eval")
    if leader is None:
        raise KeyError("runtime_data['leader_ohlcv_eval'] required for bn_cross_lead_lag")
    return BinanceCrossLeaderLagSource(
        leader_ohlcv_eval=leader,
        lead_lookback=int(kwargs.get("lead_lookback", 1)),
        lead_thresh=float(kwargs.get("lead_thresh", 0.005)),
        follow_ratio=float(kwargs.get("follow_ratio", 0.5)),
    )


@register_source("bn_oi_price_decoupling")
def _build_bn_oi_price_decoupling(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceOIPriceDecouplingSource
    metrics = runtime.get("binance_metrics_5m")
    if metrics is None:
        raise KeyError("runtime_data['binance_metrics_5m'] required for bn_oi_price_decoupling")
    return BinanceOIPriceDecouplingSource(
        metrics_5m=metrics,
        mode=str(kwargs.get("mode", "confirm")),
        zwin=int(kwargs.get("zwin", 288)),
        entry_z=float(kwargs.get("entry_z", 2.0)),
    )


@register_source("bn_premium_velocity_zscore")
def _build_bn_premium_velocity_zscore(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinancePremiumVelocityZScoreSource
    premium = runtime.get("premium_df")
    if premium is None:
        raise KeyError("runtime_data['premium_df'] required for bn_premium_velocity_zscore")
    return BinancePremiumVelocityZScoreSource(
        premium_df=premium,
        zwin=int(kwargs.get("zwin", 30)),
        entry_z=float(kwargs.get("entry_z", 1.0)),
    )


@register_source("bn_wick_reversal_multibar")
def _build_bn_wick_reversal_multibar(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceWickReversalMultibarSource
    return BinanceWickReversalMultibarSource(
        n_bars=int(kwargs.get("n_bars", 2)),
        wick_thresh=float(kwargs.get("wick_thresh", 0.35)),
        prior_lookback=int(kwargs.get("prior_lookback", 12)),
        prior_move_pct=float(kwargs.get("prior_move_pct", 0.03)),
    )


@register_source("rsi_threshold")
def _build_rsi_threshold(kwargs: dict, runtime: dict) -> SignalSource:
    """⚠ 인자를 하나라도 버리면 격자를 돌려도 판정이 안 바뀐다 (교훈 #88).
    세 인자 전부 넘기고, 하네스가 `spec_sink` 로 도달을 확인한다."""
    from .sources import RsiThresholdSource
    return RsiThresholdSource(
        period=int(kwargs.get("period", 14)),
        entry_threshold=float(kwargs.get("entry_threshold", 30.0)),
        side=str(kwargs.get("side", "long")),
        placebo=str(kwargs.get("placebo", "")),
        placebo_seed=int(kwargs.get("placebo_seed", 0)),
    )


def _lifecycle_window_kwargs(kwargs: dict) -> dict:
    """상장 창 인자(listing_date / max_age_days / entry_window_days)를 전달한다.

    ⚠ 2026-08-13 발견 — 이 팩토리들이 해당 인자를 **통째로 버리고 있었다.**
    2026-08-12 에 소스 클래스에 넣은 재진입 차단이 실제 경로에서는 한 번도
    동작하지 않았다. 클래스 단위로는 "진입 신호 4일 켜짐, 41일 0.0" 으로
    검증까지 했는데, `build_pipeline` 을 지나면 `listing_date=None` 이라
    조건문이 통째로 건너뛰어졌다. 스펙에는 값이 멀쩡히 적혀 있었다.

    그 사이 GRVTUSDT 는 상장 11일차에 **세 번째 진입**을 했다. 패러다임은
    "상장 Day-1 종가 숏 한 번" 이다.

    교훈: 소스 클래스만 고치고 검증하면 안 된다. **스펙 → build_pipeline →
    인스턴스** 경로로 값이 도달하는지까지 봐야 한다.
    """
    out: dict = {}
    if kwargs.get("listing_date"):
        out["listing_date"] = str(kwargs["listing_date"])
    if kwargs.get("max_age_days") is not None:
        out["max_age_days"] = int(kwargs["max_age_days"])
    if kwargs.get("entry_window_days") is not None:
        out["entry_window_days"] = int(kwargs["entry_window_days"])
    # ⚠ 2026-08-15 — 위 경고를 읽고도 **같은 실수를 반복했다.**
    #   소스에 `entry_start_hours` 를 넣고 클래스 단위로 검증까지 했는데
    #   (0 → 진입신호 10봉 / 24 → 1봉), 여기에 안 넣어서 실제 세션에서는
    #   내내 무시됐다. 스펙에는 24 가 멀쩡히 적혀 있었다.
    #   **새 소스 인자를 추가하면 이 헬퍼도 같이 고쳐야 한다.**
    if kwargs.get("entry_start_hours") is not None:
        out["entry_start_hours"] = int(kwargs["entry_start_hours"])
    return out


@register_source("bn_lifecycle_decay")
def _build_bn_lifecycle_decay(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceLifecycleDecaySource
    return BinanceLifecycleDecaySource(**_lifecycle_window_kwargs(kwargs))


@register_source("bn_lifecycle_decay_early_exit")
def _build_bn_lifecycle_decay_early_exit(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceLifecycleDecayEarlyExitSource
    return BinanceLifecycleDecayEarlyExitSource(
        check_day=int(kwargs.get("check_day", 14)),
        vol_cliff_hi_threshold=float(kwargs.get("vol_cliff_hi_threshold", 0.40)),
        **_lifecycle_window_kwargs(kwargs),
    )


@register_source("bn_lifecycle_decay_bear_skip")
def _build_bn_lifecycle_decay_bear_skip(kwargs: dict, runtime: dict) -> SignalSource:
    from .sources import BinanceLifecycleDecayBearSkipSource
    return BinanceLifecycleDecayBearSkipSource(
        btc_30d_pre_ret=float(kwargs["btc_30d_pre_ret"]),
        bear_threshold=float(kwargs.get("bear_threshold", -0.05)),
        **_lifecycle_window_kwargs(kwargs),
    )


@register_source("bn_stablecoin_supply_flow")
def _build_bn_stablecoin_supply_flow(kwargs: dict, runtime: dict) -> SignalSource:
    """paradigm 251 — 3군 게이트 PASS 2026-08-09. USDT+USDC 7일 순증감 z (DefiLlama).

    substrate 는 외부 무료 API 라 OHLCV 주입이 필요 없다. 캐시가 낡고 네트워크가
    막히면 InsufficientSourceDataError 로 실패한다 — 조용한 0 신호를 내지 않는다.
    """
    from .sources import BinanceStablecoinSupplyFlowSource
    return BinanceStablecoinSupplyFlowSource(
        cache_path=kwargs.get("cache_path"),
        z_thresh=float(kwargs.get("z_thresh", 1.0)),
        refresh_hours=float(kwargs.get("refresh_hours", 12.0)),
        allow_network=bool(kwargs.get("allow_network", True)),
    )


@register_source("us_daily")
def _build_us_daily(kwargs: dict, runtime: dict) -> SignalSource:
    """미국 ETF 일봉 파생 피처 (갭·52주 위치·거래량 z·연속일).

    이 일봉의 갭은 통상적 야간 갭이 아니라 오버나이트(Blue Ocean) 종료가 대비
    정규장 시가 괴리다 — us_daily_source docstring 참조."""
    from .sources import USDailySource
    return USDailySource(
        z_lookback=int(kwargs.get("z_lookback", 60)),
        high_low_window=int(kwargs.get("high_low_window", 252)),
    )


@register_source("us_rs")
def _build_us_rs(kwargs: dict, runtime: dict) -> SignalSource:
    """벤치마크(기본 SPY) 대비 상대강도. 벤치마크 일봉은 runtime 에서 받는다."""
    from .sources import USRelativeStrengthSource
    return USRelativeStrengthSource(
        benchmark_df=runtime.get("leader_ohlcv_eval"),
        benchmark_symbol=str(kwargs.get("benchmark_symbol", "SPY")),
        z_lookback=int(kwargs.get("z_lookback", 60)),
        beta_window=int(kwargs.get("beta_window", 60)),
    )


@register_composer("lgbm")
def _build_lgbm(kwargs: dict) -> Composer:
    from .composers import LGBMComposerAdapter
    from app.pattern_ml.lgbm_composer import LGBMComposerConfig
    cfg = LGBMComposerConfig(**kwargs) if kwargs else None
    return LGBMComposerAdapter(cfg)


@register_composer("xgb")
def _build_xgb(kwargs: dict) -> Composer:
    from .composers import XGBComposerAdapter
    return XGBComposerAdapter(**(kwargs or {}))


@register_composer("negation_passthrough")
def _build_negation_passthrough(kwargs: dict) -> Composer:
    from .composers import NegationPassthroughComposer
    return NegationPassthroughComposer(**(kwargs or {}))


@register_composer("passthrough")
def _build_passthrough(kwargs: dict) -> Composer:
    from .composers import PassthroughComposer
    return PassthroughComposer(**(kwargs or {}))


@register_policy("long_only_threshold")
def _build_long_only(kwargs: dict) -> TradingPolicy:
    return LongOnlyThresholdPolicy(**kwargs) if kwargs else LongOnlyThresholdPolicy()


@register_policy("long_short_threshold")
def _build_long_short(kwargs: dict) -> TradingPolicy:
    return LongShortThresholdPolicy(**kwargs) if kwargs else LongShortThresholdPolicy()


@register_policy("funding_reversal")
def _build_funding_reversal(kwargs: dict) -> TradingPolicy:
    return FundingReversalPolicy(**kwargs) if kwargs else FundingReversalPolicy()


@register_policy("lifecycle_decay_early_exit")
def _build_lifecycle_decay_early_exit(kwargs: dict) -> TradingPolicy:
    return LifecycleDecayEarlyExitPolicy(**kwargs) if kwargs else LifecycleDecayEarlyExitPolicy()


# ─────────────────────────────────────────────────── public API ───


def build_pipeline(spec: dict, runtime_data: dict | None = None) -> Pipeline:
    """Construct Pipeline from a JSON-friendly spec.

    runtime_data is a dict of arbitrary objects the source factories need.
    Example keys:
      signals_df: pd.DataFrame from PatternScanner
      flow_df: pd.DataFrame from fetch_investor_flow
      binance_metrics_5m: pd.DataFrame
      symbol: str (used as fallback for kr_flow if flow_df not provided)
    """
    runtime = runtime_data or {}

    sources = []
    for src_spec in spec.get("sources", []):
        type_name = src_spec["type"]
        if type_name not in SOURCE_FACTORIES:
            raise KeyError(f"Unknown source type: {type_name!r}. "
                           f"Registered: {list(SOURCE_FACTORIES)}")
        sources.append(SOURCE_FACTORIES[type_name](src_spec.get("kwargs", {}), runtime))
    if not sources:
        raise ValueError("Pipeline spec must include at least one source")

    composer_spec = spec.get("composer") or {"type": "lgbm", "kwargs": {}}
    if composer_spec["type"] not in COMPOSER_FACTORIES:
        raise KeyError(f"Unknown composer type: {composer_spec['type']!r}")
    composer = COMPOSER_FACTORIES[composer_spec["type"]](composer_spec.get("kwargs", {}))

    policy_spec = spec.get("policy") or {"type": "long_only_threshold", "kwargs": {}}
    if policy_spec["type"] not in POLICY_FACTORIES:
        raise KeyError(f"Unknown policy type: {policy_spec['type']!r}")
    policy = POLICY_FACTORIES[policy_spec["type"]](policy_spec.get("kwargs", {}))

    cfg_dict = spec.get("config", {})
    config = PipelineConfig(**cfg_dict) if cfg_dict else PipelineConfig()

    return Pipeline(sources=sources, composer=composer, policy=policy, config=config)


def validate_spec(spec: dict) -> list[str]:
    """Return list of human-readable validation errors. Empty list = OK."""
    errors = []
    if not isinstance(spec, dict):
        return ["spec must be a dict"]
    sources = spec.get("sources", [])
    if not sources:
        errors.append("spec.sources must be non-empty list")
    for i, s in enumerate(sources):
        if "type" not in s:
            errors.append(f"sources[{i}].type missing")
        elif s["type"] not in SOURCE_FACTORIES:
            errors.append(f"sources[{i}].type {s['type']!r} not registered")
    composer = spec.get("composer", {})
    if composer and composer.get("type") not in COMPOSER_FACTORIES:
        errors.append(f"composer.type {composer.get('type')!r} not registered")
    policy = spec.get("policy", {})
    if policy and policy.get("type") not in POLICY_FACTORIES:
        errors.append(f"policy.type {policy.get('type')!r} not registered")
    return errors
