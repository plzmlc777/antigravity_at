---
name: at-strategy
description: |
  전략 지식 베이스 + AI 파라미터 추천 스킬.
  시장 데이터를 분석하여 종목 특성에 맞는 전략과 파라미터를 추천하고,
  기본 파라미터 대비 성과를 비교 검증한다.
  "전략 추천해줘", "파라미터 최적화", "이 종목에 맞는 설정", "A/B 테스트" 등의 요청 시 사용.
allowed-tools: Read, Write, Edit, Bash(python:*), Bash(curl:*)
version: 0.1.0
author: Antigravity Auto Trading
tags: [strategy, recommendation, ab-test, knowledge-base]
---

# AT-Strategy: 전략 지식 기반 AI 추천 스킬

## Overview

기존 전략 코드를 변경하지 않고, AI가 **지식 베이스를 참조하여 파라미터를 추천**하는 스킬.
코드는 실행자, AI는 설계자 역할을 분담한다.

## 병행 테스트 원칙

> 기본 파라미터(baseline)와 AI 추천 파라미터를 동일 조건으로 백테스트하여 비교한다.
> AI 추천이 baseline을 이기는 경우에만 채택한다.

## 디렉토리 구조

```
at-strategy/
├── SKILL.md                     ← 이 파일
├── references/
│   ├── dip_martingale.md        ← Dip Martingale 전략 지식
│   ├── market_regime.md         ← 시장 국면 판단 기준 (향후)
│   └── param_effects.md         ← 파라미터 영향도 가이드 (향후)
└── scripts/
    ├── analyze_symbol.py        ← 종목 특성 분석 (변동성, 패턴)
    └── ab_test.py               ← baseline vs AI 추천 비교 테스트
```

## 사용법

### 1. 종목 분석
```bash
cd .claude/skills/at-strategy/scripts
python3 analyze_symbol.py --symbol 005930 --interval 1d --days 180
```

### 2. AI 추천 + A/B 테스트
```bash
python3 ab_test.py --symbol 005930 --strategy dip_martingale --interval 1d --days 365
```

### 3. AI 전체 흐름 (대화형)
1. `analyze_symbol.py`로 종목 특성 파악
2. AI가 `references/dip_martingale.md` 읽고 파라미터 추천
3. `ab_test.py`로 baseline vs 추천 비교
4. 결과 해석 + 추가 조정

## 지식 베이스 활용 규칙

1. **추천 전 반드시** `references/` 파일을 읽을 것
2. **데이터 기반 판단**: `analyze_symbol.py` 결과를 근거로 추천
3. **추천 이유 명시**: "이 종목의 일변동성이 2.3%이므로 dip_percent=1.5 추천" 형태
4. **비교 검증 필수**: 추천 후 반드시 `ab_test.py`로 비교

## When to Pivot

- 전략 자체가 적합하지 않으면 → 다른 전략 추천 (references/ 참조)
- 데이터가 부족하면 → at-backtest 스킬로 데이터 수집 먼저
- 새 전략이 필요하면 → strategy-builder 에이전트 호출
