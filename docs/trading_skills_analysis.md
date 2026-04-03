# Trading Skills 분석 보고서

> 작성일: 2026-04-02 (최종 업데이트: 2026-04-02)
> 목적: 외부 트레이딩 스킬 분석 → 우리 전략 스킬화 참고

---

## 우리 프로젝트 바이낸스 API 사용 현황

> 이 프로젝트는 키움 API (한국 주식) 외에 **바이낸스 API를 적극 사용** 중.
> 아래 스킬 평가 시 바이낸스 관련 스킬의 활용도가 높음.

| 어댑터 파일 | 기능 |
|------------|------|
| `backend/app/adapters/binance_base.py` | HMAC-SHA256 서명, 시간 동기화, Rate Limiting, exchangeInfo 캐싱 |
| `backend/app/adapters/binance_spot.py` | 현물 매매 (Market/Limit 주문, 잔고, 시세) |
| `backend/app/adapters/binance_futures.py` | USDM 선물 (레버리지 1-125x, Long/Short, 펀딩비율) |
| `backend/app/adapters/binance_websocket.py` | 실시간 틱 데이터 WebSocket |
| `backend/app/services/binance_market_data.py` | 시장 데이터 서비스 |
| `backend/app/api/binance_data.py` | 바이낸스 데이터 API 엔드포인트 |

---

## 설치 명령어 및 분석 요약

### #1. backtesting-trading-strategies (jeremylongshore)

```bash
npx skills add https://github.com/jeremylongshore/claude-code-plugins-plus-skills --skill backtesting-trading-strategies
```

| 항목 | 내용 |
|------|------|
| **저장소** | `jeremylongshore/claude-code-plugins-plus-skills` |
| **유형** | 백테스팅 프레임워크 (코드 포함) |
| **구조** | commands(4) + config + scripts(5) + references(3) + tests |
| **내장 전략** | SMA/EMA 교차, RSI 반전, MACD, 볼린저, 돌파, 평균회귀, 모멘텀 (8개) |
| **지표** | Sharpe, Sortino, Calmar, MDD, VaR, CVaR, Win Rate, Profit Factor |
| **데이터** | yfinance/CoinGecko |
| **명령어** | `/backtest-strategy`, `/compare-strategies`, `/optimize-parameters`, `/walk-forward` |
| **활용도** | ★★★☆☆ |

**평가**: 가장 구조가 풍부함 (5개 하위폴더). 실제 Python 스크립트 포함. Walk-Forward 검증 로직, 성과지표 계산 코드 참고 가치. 데이터소스만 키움으로 교체하면 응용 가능.

---

### #2. trading-signal (Binance Web3)

```bash
npx skills add https://github.com/binance/binance-skills-hub --skill trading-signal
```

| 항목 | 내용 |
|------|------|
| **저장소** | `binance/binance-skills-hub` (binance-web3) |
| **유형** | API 레퍼런스 (SKILL.md 단독) |
| **기능** | 스마트머니 온체인 시그널 조회 |
| **API** | `POST web3.binance.com/.../signal/smart-money/ai` |
| **인증** | 불필요 (공개) |
| **체인** | BSC, Solana |
| **데이터** | 매수/매도 방향, 가격, maxGain, exitRate, 토큰 태그 |
| **활용도** | ★★★★☆ (바이낸스 사용으로 상향) |

**평가**: SKILL.md 하나로 API 스펙을 완전히 정의. 코드 없이 Claude가 API를 직접 호출하도록 가이드. **API 레퍼런스형 스킬의 모범 포맷**. 키움 API 스킬 만들 때 이 형식 참고.

**바이낸스 사용 프로젝트 추가 평가**: 인증 불필요한 공개 API로 스마트머니 온체인 매매 방향 조회 가능. 우리 AI 종목 선정 파이프라인의 **보조 시그널**로 통합 가능. BSC/Solana 체인의 전문 투자자 움직임을 실시간 참고할 수 있음.

---

### #3. us-stock-analysis (TraderMonty)

```bash
npx skills add https://github.com/tradermonty/claude-trading-skills --skill us-stock-analysis
```

| 항목 | 내용 |
|------|------|
| **저장소** | `tradermonty/claude-trading-skills` |
| **유형** | 분석 가이드 + 리포트 템플릿 |
| **구조** | SKILL.md + references(4): financial-metrics, fundamental-analysis, report-template, technical-analysis |
| **분석 유형** | 펀더멘탈, 기술적, 종합, 비교 분석 |
| **데이터** | WebSearch/WebFetch로 실시간 수집 |
| **출력** | 마크다운 분석 보고서 |
| **활용도** | ★★★★☆ |

**평가**: 외부 API 의존 없이 웹 검색만으로 동작. 분석 프레임워크와 리포트 템플릿 체계적. 미국 주식 용어를 한국 주식으로 바꾸면 종목 분석 보고서 생성에 즉시 활용 가능. AI 종목 선정 파이프라인 FIND 단계 참고.

---

### #4. derivatives-trading-usds-futures (Binance)

```bash
npx skills add https://github.com/binance/binance-skills-hub --skill derivatives-trading-usds-futures
```

| 항목 | 내용 |
|------|------|
| **저장소** | `binance/binance-skills-hub` |
| **유형** | API 레퍼런스 (전체 스펙) |
| **규모** | 23KB, 70+ 엔드포인트 |
| **기능** | USDS 선물 전체: 주문/포지션/계정/마켓데이터 |
| **인증** | HMAC/RSA/Ed25519 |
| **환경** | 테스트넷/메인넷 |
| **활용도** | ★★★★★ (바이낸스 사용으로 상향) |

**평가**: 우리 프로젝트가 이미 `binance_futures.py`에서 USDM 선물 API를 사용 중. 이 스킬은 해당 API의 **70+ 엔드포인트 전체 레퍼런스**를 제공. 아직 구현하지 않은 엔드포인트 발견, 인증 방식(HMAC/RSA/Ed25519) 검증, 테스트넷/메인넷 전환 가이드로 직접적으로 유용.

---

### #5. risk-management (0xhubed/agent-trading-arena)

```bash
npx skills add https://github.com/0xhubed/agent-trading-arena --skill risk-management
```

| 항목 | 내용 |
|------|------|
| **저장소** | `0xhubed/agent-trading-arena` |
| **유형** | 데이터 기반 리스크 규칙집 (자동 생성) |
| **패턴** | 40개 활성 패턴, 13,385개 샘플 |
| **핵심 규칙** | 거래 빈도 ↔ 성과 역상관, 포지션당 25% 한도, 시장 레짐별 빈도 조절 |
| **형식** | 규칙 + 성공률 + 샘플 수 + 신뢰도 테이블 |
| **활용도** | ★★★★☆ |

**주요 발견**:
- 횡보장에서 거래 많을수록 손실 (3~6회 = $0, 150~225회 = -$325~-$581)
- 진입 전 리스크 검증 단계가 있는 전략이 +$1,349 수익
- 포지션당 2% 리스크 + 2:1 보상비율은 실제로는 35% 성공률 (통념과 반대)

**평가**: AI 에이전트 경쟁에서 실제 데이터로 자동 생성된 규칙집. 시장 무관 범용. 마틴게일 전략 포지션 사이징 검증에 유용.

---

### #6. margin-trading (Binance)

```bash
npx skills add https://github.com/binance/binance-skills-hub --skill margin-trading
```

| 항목 | 내용 |
|------|------|
| **저장소** | `binance/binance-skills-hub` |
| **유형** | API 레퍼런스 |
| **규모** | 60+ 엔드포인트 |
| **기능** | 마진 계좌, 대출, 상환, OCO/OTO/OTOCO 주문 |
| **인증** | HMAC SHA256/RSA/Ed25519 |
| **활용도** | ★★★☆☆ (바이낸스 사용으로 상향) |

**평가**: 바이낸스 마진 API 레퍼런스. 현재 마진 트레이딩은 미사용이지만, 바이낸스 인프라를 이미 갖추고 있어 향후 마진 기능 확장 시 즉시 참고 가능.

---

### #7. trading-analysis (gracefullight/stock-checker)

```bash
npx skills add https://github.com/gracefullight/stock-checker --skill trading-analysis
```

| 항목 | 내용 |
|------|------|
| **저장소** | `gracefullight/stock-checker` |
| **상태** | **존재하지 않음** |
| **활용도** | N/A |

**평가**: 해당 저장소에 `trading-analysis` 스킬 없음. `.claude/skills/` 안에 14개 스킬이 있지만 모두 일반 개발 워크플로우 (brainstorm, commit, debug 등).

---

### #8. trading-strategies (agentmc15/polymarket-trader)

```bash
npx skills add https://github.com/agentmc15/polymarket-trader --skill trading-strategies
```

| 항목 | 내용 |
|------|------|
| **저장소** | `agentmc15/polymarket-trader` |
| **유형** | 전략 프레임워크 (코드 가이드) |
| **위치** | `.claude/skills/trading-strategies/` |
| **전략** | Arbitrage, CopyTrading, Momentum, MeanReversion |
| **구조** | BaseStrategy 추상 클래스 + Backtester + RiskManager |
| **리스크** | Kelly Criterion, 포지션 사이징, Stop-Loss |
| **대상** | Polymarket (예측 시장) |
| **활용도** | ★★★☆☆ |

**평가**: BaseStrategy 패턴 + Backtester + RiskManager 구조가 우리 아키텍처와 매우 유사. Kelly Criterion 포지션 사이징 포함. 전략 프레임워크 스킬화 참고 모델.

---

### #9. trading-plan-generator (jamesrochabrun)

```bash
npx skills add https://github.com/jamesrochabrun/skills --skill trading-plan-generator
```

| 항목 | 내용 |
|------|------|
| **저장소** | `jamesrochabrun/skills` |
| **유형** | 트레이딩 플랜 생성 가이드 |
| **리스크 규칙** | 1% 룰, 2R 최소 룰, 일일 손실 한도 |
| **포지션 사이징** | Fixed Dollar, Fixed Percentage, Kelly Criterion 공식 포함 |
| **트레이딩 스타일** | 데이트레이딩, 스윙, 포지션 별 가이드 |
| **체크리스트** | 진입 전 7항목, 청산 조건, 일일 리뷰 |
| **활용도** | ★★★☆☆ |

**평가**: 코드 없이 순수 트레이딩 플랜 작성 가이드. 체계적인 체크리스트와 공식. 시장 무관 범용. 포지션 사이징 공식과 리스크 관리 룰 참고.

---

### #10. trading-wisdom (0xhubed/agent-trading-arena) -- 설치됨

```bash
npx skills add https://github.com/0xhubed/agent-trading-arena --skill trading-wisdom
```

| 항목 | 내용 |
|------|------|
| **저장소** | `0xhubed/agent-trading-arena` |
| **유형** | AI 경쟁 학습 지혜 (자동 생성) |
| **패턴** | 206개 활성 패턴, 41,088개 샘플 |
| **설치 경로** | `.agents/skills/trading-wisdom/` → `.claude/skills/trading-wisdom/` (심링크) |
| **보안 평가** | Gen: Low Risk, Socket: 0 alerts, Snyk: Low Risk |
| **활용도** | ★★★★★ |

**핵심 인사이트**:
1. **과매매 = 손실**: 거래 0회 = $0, 23회 = -$28, 243회 = -$229
2. **시장 레짐 판단이 최우선**: 완만한 강세장에서 모든 능동적 전략 손실
3. **높은 확신도 =/= 높은 정확도**: 0.85~0.90 확신도 방향성 트레이드 빈번하게 오류
4. **선제적 손절이 유일한 확실한 패턴**: 0.85~0.95 확신도로 빠르게 청산
5. **자산 분산 > 단일 종목 집중**: 단일 종목 집착 에이전트 최악의 성과

**스킬 설계 패턴 학습**:
- 데이터 출처: AI 경쟁 실전 데이터 (자동 생성)
- 신뢰도 체계: 4단계 (90%+, 70-90%, 60-70%, <60%)
- 구조: 승리/회피 명확 분리 (DO/DON'T)
- 갱신: Observer Agent가 자동 업데이트
- 코드 없음: 순수 마크다운 지식 참조형

---

### #11. market-news-analyst (TraderMonty)

```bash
npx skills add https://github.com/tradermonty/claude-trading-skills --skill market-news-analyst
```

| 항목 | 내용 |
|------|------|
| **저장소** | `tradermonty/claude-trading-skills` |
| **유형** | 뉴스 분석 워크플로우 |
| **구조** | SKILL.md + references(4): market_event_patterns, geopolitical_commodity_correlations, corporate_news_impact, trusted_news_sources |
| **워크플로우** | 6단계: 뉴스 수집 → 지식베이스 참조 → 임팩트 평가 → 시장 반응 분석 → 상관관계 평가 → 리포트 생성 |
| **임팩트 공식** | 가격 영향 x 영향 범위 x 미래 전망 = 점수 |
| **데이터** | WebSearch/WebFetch (API 키 불필요) |
| **활용도** | ★★★★☆ |

**평가**: 체계적인 뉴스 분석 프레임워크. references에 이벤트 패턴, 지정학 상관관계 등 지식베이스 구축. 미국 시장 기준이나 프레임워크 자체는 범용. AI 종목 선정 파이프라인에서 뉴스 기반 필터링에 활용 가능.

---

## 종합 순위 (우리 프로젝트 활용도)

| 순위 | # | 스킬 | 활용도 | 설치 상태 | 핵심 가치 |
|:----:|:-:|------|:------:|:---------:|----------|
| 1 | 10 | **trading-wisdom** | ★★★★★ | ✅ 설치됨 | 실전 데이터 기반 트레이딩 교훈, 과매매 방지 |
| 2 | 4 | **derivatives-futures** | ★★★★★ | ✅ 설치됨 | 우리 binance_futures.py의 전체 API 레퍼런스 (70+ 엔드포인트) |
| 3 | 5 | **risk-management** | ★★★★ | ✅ 설치됨 | 데이터 기반 리스크 규칙 40개 (거래빈도 역상관, 25% 포지션 상한) |
| 4 | 2 | **trading-signal** | ★★★★ | ✅ 설치됨 | 스마트머니 온체인 시그널 (밈코인 한정, 필터링 불가) |
| 5 | 3 | **us-stock-analysis** | ★★★★ | 미설치 | 종목 분석 보고서 프레임워크 |
| 6 | 11 | **market-news-analyst** | ★★★★ | ✅ 설치됨 | 뉴스 임팩트 스코어링 + 6단계 분석 워크플로우 |
| 7 | 1 | **backtesting** | ★★★★ | ✅ 설치됨 | **가장 풍부한 구조** (5폴더/15파일), Walk-Forward, 슬래시 명령어 |
| 8 | 8 | **trading-strategies** | ★★★★ | ✅ 설치됨 | Signal 객체 + RiskManager 분리 패턴, Kelly Criterion |
| 9 | 6 | **margin-trading** | ★★★ | 미설치 | 향후 마진 기능 확장 시 참고 |
| 10 | 9 | **trading-plan-generator** | ★★★ | 미설치 | 포지션 사이징/리스크 체크리스트 |
| - | 7 | **trading-analysis** | N/A | X | 존재하지 않음 |

> **참고**: #2, #4, #6은 우리 프로젝트가 바이낸스 API(현물+선물)를 사용 중이므로 활용도 상향 조정됨.
> **참고**: #1, #8은 상세 분석 후 스킬 설계 패턴의 가치가 높아 활용도 상향됨.

---

## 설치된 스킬 요약 (8개)

| # | 스킬 | 설치 경로 | 파일 수 | 핵심 기능 |
|:-:|------|----------|:-------:|----------|
| 10 | trading-wisdom | `.agents/skills/trading-wisdom/` | 1 | 206패턴/41K샘플, AI 경쟁 학습 지혜 |
| 4 | derivatives-futures | `.agents/skills/derivatives-trading-usds-futures/` | 3 | 70+ 바이낸스 선물 API 엔드포인트 |
| 5 | risk-management | `.agents/skills/risk-management/` | 1 | 40패턴/13K샘플, 리스크 규칙집 |
| 2 | trading-signal | `.agents/skills/trading-signal/` | 1 | 스마트머니 온체인 시그널 API |
| 11 | market-news-analyst | `.agents/skills/market-news-analyst/` | 5 | 뉴스 분석 6단계 워크플로우 + 4개 references |
| 1 | backtesting | `.agents/skills/backtesting-trading-strategies/` | **15** | 8전략, 13지표, Grid Search, Walk-Forward |
| 8 | trading-strategies | `.agents/skills/trading-strategies/` | 1 | BaseStrategy + Signal + RiskManager + Backtester |

---

## 스킬 유형별 분류

### A. 지식/지혜형 (코드 없음, 마크다운 참조)
- #10 trading-wisdom, #5 risk-management, #9 trading-plan-generator
- **특징**: Observer Agent가 자동 생성, 신뢰도 체계(4단계), DO/DON'T 분리

### B. 분석 워크플로우형 (단계별 프로세스 정의)
- #3 us-stock-analysis, #11 market-news-analyst
- **특징**: WebSearch 기반 (API 키 불필요), 임팩트 스코어링 공식, 마크다운 리포트 출력
- **한계**: 상황 인식까지만 — 방향 예측/시그널 생성 안 함

### C. 코드 프레임워크형 (실행 가능한 스크립트 포함)
- #1 backtesting-trading-strategies, #8 trading-strategies
- **특징**: 실행 가능한 Python, Signal 객체 분리, 슬래시 명령어, 5폴더 구조

### D. API 레퍼런스형 (외부 API 스펙 정의)
- #2 trading-signal, #4 derivatives-futures, #6 margin-trading
- **특징**: SKILL.md 하나로 API 스펙 완전 정의, Claude가 직접 API 호출 가능
- **우리 프로젝트가 바이낸스 API를 사용 중이므로 D 유형 스킬들의 실용성이 높음**

---

## 스킬 상세 분석 결과

### #2 trading-signal — 분석 완료
- **API**: `POST web3.binance.com/.../signal/smart-money/ai` (인증 불필요)
- **체인**: BSC(56), Solana(CT_501)
- **한계**: 종목 필터링 불가, 밈코인 위주, CEX 선물과 무관
- **실제 테스트**: BSC/Solana 시그널 조회 완료 — 대부분 Pumpfun 밈코인
- **활용**: 우리 CEX 선물 트레이딩에는 직접 사용 어려움, API 레퍼런스형 스킬 포맷 참고용

### #5 risk-management — 분석 완료
- **핵심 규칙**: 거래빈도 ↔ 성과 역상관(95%), 진입 전 리스크 검증 시 +$1,349(92%)
- **통념 깨진 발견**: 2% risk + 2:1 reward = 실제 35% 성공률 (실패 패턴!)
- **활용**: 우리 전략 파라미터 검증, LiveContext 리스크 검증 강화 근거

### #11 market-news-analyst — 분석 + 실전 테스트 완료
- **임팩트 공식**: `가격영향(1~10) × 파급범위(1~3x) × 전망보정(0.75~1.5x)`
- **references 4개**: 이벤트 패턴, 지정학-원자재 상관관계, 기업 뉴스 영향, 뉴스 소스
- **실전 테스트 결과** (2026-04-02):
  - 미-이란 전쟁 종전 기대 (Score: 30.0) — S&P +0.7%, WTI +9%
  - 금 $4,800 돌파, BTC $68.5K (Fear Index 8)
  - 지정학-원자재 상관관계 테이블이 실제 시장과 정확히 일치
  - **한계**: 상황 인식까지만 — "올라? 내려?" 방향 예측 안 함

### #8 trading-strategies — 분석 완료
- **구조**: BaseStrategy + Signal 객체 + RiskManager (독립 클래스)
- **Signal 패턴**: `type(BUY/SELL/HOLD)`, `confidence(0-1)`, `metadata(판단 근거)`
- **4개 전략**: Arbitrage, CopyTrading, Momentum, MeanReversion
- **핵심 발견**:
  1. Signal 객체 분리 — 시그널 생성과 실행을 분리, 스킬 간 조합 가능
  2. RiskManager 독립 — validate_signal() + Kelly Criterion
  3. Confidence 기반 필터 — 60% 미만 자동 스킵
- **우리 프로젝트와의 차이**: 우리는 on_data()에서 직접 buy/sell 호출, Signal 객체 없음

### #1 backtesting-trading-strategies — 분석 완료
- **구조**: 5폴더/15파일 — 분석한 모든 스킬 중 가장 풍부
- **내장 전략 8개**: SMA, EMA, RSI, MACD, Bollinger, Breakout, MeanReversion, Momentum
- **성과지표 13개**: Sharpe, Sortino, Calmar, VaR, CVaR, Ulcer Index 등
- **슬래시 명령어 4개**: /backtest-strategy, /compare-strategies, /optimize-parameters, /walk-forward
- **핵심 발견**:
  1. **5폴더 구조** (commands/config/scripts/references/tests) — 스킬 디렉토리 모범 사례
  2. **Walk-Forward 검증** — 우리에게 없는 오버피팅 탐지 기능
  3. **슬래시 명령어** — 스킬 UX 패턴, 사용자가 한 줄로 복잡한 작업 실행

---

## 우리 전략 스킬화 시 참고 포인트

### 디렉토리 구조 (#1 backtesting 참고)
```
our-strategy-skill/
├── SKILL.md                ← 메인 가이드 + 트리거 키워드
├── commands/               ← 슬래시 명령어 (/generate-signal, /validate 등)
├── config/                 ← settings.yaml (파라미터 분리)
├── scripts/                ← 실행 가능한 Python
├── references/             ← 지식베이스 (패턴, 규칙, 이벤트)
└── tests/                  ← 테스트 코드
```

### Signal 객체 표준화 (#8 trading-strategies 참고)
```python
@dataclass
class Signal:
    type: SignalType       # BUY / SELL / HOLD
    confidence: float      # 0-1 신뢰도
    metadata: dict         # 판단 근거 (스킬 간 데이터 전달)
```
- 시그널 생성과 실행을 분리 → 스킬 간 조합 가능
- confidence 기반 필터링 → 저신뢰 시그널 자동 스킵

### RiskManager 독립 분리 (#8 + #5 조합)
```python
class RiskManager:
    def validate_signal(signal, portfolio) -> (bool, reason)
    def calculate_kelly_size(win_prob, win_amount, loss_amount) -> float
```
- #5 risk-management 규칙을 RiskManager에 내장
- 전략과 리스크 관리를 분리 → 독립 교체 가능

### 스킬 파이프라인 조합
```
외부 스킬: market-news-analyst  → 상황 인식 (매크로 레짐)
자체 스킬: signal-generator     → 방향 판단 + 시그널 생성
외부 스킬: risk-management      → 리스크 검증
자체 스킬: order-executor       → 주문 실행
```
- 각 단계가 독립 스킬 → 교체/업그레이드 용이
- Signal 객체로 스킬 간 데이터 표준화

### 비즈니스 모델
```
무료 공개    → 상황 인식 스킬 (market-news-analyst 수준)
무료 공개    → 보조 지표 스킬 (사용자 유입)
유료 판매    → 방향 판단 + 시그널 생성 스킬 (private repo)
프리미엄     → 고적중률 시그널 + 자동 실행 연동
```

### 현재 마켓플레이스 공백
- **매매 시그널을 직접 생성하는 스킬은 마켓플레이스에 없음**
- 상황 인식(#11), 리스크 규칙(#5), API 매뉴얼(#4)까지만 존재
- **방향 판단 + 시그널 생성 = 우리가 직접 만들어야 할 핵심 영역**

### 추가 참고
1. **포맷**: #2 Binance의 API 레퍼런스형이 키움 API 스킬에 적합
2. **지식 추출**: #10의 자동 생성 패턴 (Observer Agent) → 우리 라이브 결과에서 자동 추출 가능
3. **분석 프레임워크**: #11의 references 폴더 패턴 → 전략별 분석 기준 문서화
4. **신뢰도 체계**: #10의 4단계 신뢰도 → 패턴별 검증 수준 부여
5. **Walk-Forward**: #1의 오버피팅 탐지 → 우리 백테스트 엔진에 도입 가치
