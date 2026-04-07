# Strategy Candidates Queue (Track B)

> AI 자율 개발한 Binance Futures 전략 후보 보관소.
> **이곳의 어떤 파일도 자동으로 실거래에 배포되지 않는다.** 신서버(~2026-04-21) 도착 후 사람이 검토하여 페이퍼 → 실거래 단계적으로 승급.

## 목적

`project_return_target.md` 의 12%/월 KPI 달성을 위해, GCP가 Binance에 접근하지 못하는 동안에도 로컬에서 Binance Futures 전략을 미리 발굴해두는 큐.

## 워크플로우

```
[자율 개발]                       [사람 검토]               [신서버 배포]
strategy-evolver  →  candidate    →  approved  →  paper  →  real
                     (.md 파일)        (수동 태그)
```

1. `scripts/binance_strategy_dev_run.sh BTCUSDT dip_martingale novel`
2. strategy-evolver 가 변이 생성 + 백테스트 + walk-forward + risk-manager 평가
3. 통과한 후보가 `<timestamp>_<symbol>_<base>_<mode>.md` 로 저장
4. 사람이 주기적으로 검토 → `_APPROVED.md` 또는 `_REJECTED.md` 로 rename
5. 신서버 도착 후 APPROVED 만 페이퍼 세션으로 배포

## 채택 기준 (사람이 검토할 때 체크)

- [ ] Walk-Forward `overfit_ratio ≤ 0.30`
- [ ] 백테스트 기간 ≥ 180일
- [ ] 월 환산 수익률 ≥ 12% (수수료/슬리피지 반영 후)
- [ ] Max Drawdown ≤ 25% (12%/월 잠재력 대비 합리적 손실 한도)
- [ ] risk-manager `approved: true`
- [ ] 레버리지 ≤ 10x (margin_type=ISOLATED)
- [ ] 백테스트 기간 외 out-of-sample 1개월 검증 통과

## 금지 사항

- ❌ 이 디렉터리의 파일을 자동으로 production 배포하지 말 것
- ❌ GCP 환경에서 binance API 호출 금지 (US IP 차단)
- ❌ 12%/월 미달 후보를 "괜찮아 보임" 정도로 승인하지 말 것
- ❌ Walk-Forward 검증 없는 후보는 즉시 폐기

## 정리 정책

`scripts/binance_strategy_dev_run.sh` 가 60일 이상 된 파일을 자동 삭제. APPROVED 마킹된 파일은 별도 디렉터리(`approved/`)로 옮겨 보호 권장.
