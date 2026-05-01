"""
Universal Meta-Strategy components — market-agnostic layer.

KR(주식) + Crypto(USDT-M Futures) 모두에서 공유하는 모듈을 모은다.
원칙:
  - feature engineering은 시장 미시구조의 보편적 상태만 인코딩 (OHLCV에서 도출)
  - 시장 특수성은 feature가 아니라 데이터 정제(calendar) layer에서 처리
  - 모델/학습/safety gate architecture는 동일

이 패키지는 점진적으로 확장될 예정:
  - Phase A: env_encoder.py (10 universal features)
  - Phase B: indicators.py + multi_tf_helpers.py + base.py (전략 코드 통합)
  - Phase C: meta_learner.py (모델 architecture 통합)
  - Phase D: portfolio_runner.py (멀티 종목 동시 최적화)
"""
