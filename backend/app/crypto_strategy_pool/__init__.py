"""Crypto Meta-Strategy MoE — Binance USDT-M Futures version of kr_strategy_pool.

24/7 시장, perpetual futures (taker/maker fee + funding) 환경에 맞춘 mirror.
KR 패키지와 1:1 대응:
  base/data_utils/multi_tf_helpers/indicators/env_encoder/meta_learner/
  meta_paper_runner/meta_strategy_registry/tournament

키 차이:
  - exit_time(EOD) 개념 제거 (24/7)
  - 매수/매도 수수료: USDT-M Futures taker 0.04% (round trip 0.08%)
  - 매도 거래세 없음
  - tick size는 Binance exchangeInfo 기반 (engine에서 처리)
  - env_encoder에서 time_sin/cos/dow_* 제거 → 24/7 무의미한 dim
"""
