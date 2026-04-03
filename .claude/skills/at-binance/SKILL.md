# at-binance: Binance Trading Skill

Binance 거래소 전용 트레이딩 스킬. 백테스트, 파라미터 최적화, 라이브 트레이딩을 지원.
기존 API 엔진과 병행 운영 가능.

## Commands

### /binance-backtest
바이낸스 종목 백테스트 실행.
```bash
python scripts/backtest_binance.py --symbol BTCUSDT --strategy dip_martingale \
    --interval 1h --days 90 --leverage 5
```

### /binance-optimize
파라미터 그리드 서치 최적화.
```bash
python scripts/optimize_binance.py --symbol ETHUSDT --strategy dip_martingale \
    --interval 4h --days 180 --leverage 3 \
    --param "dip_threshold=1.0,2.0,3.0" \
    --param "trailing_start_percent=1.0,2.0,3.0"
```

### /binance-live
라이브 트레이딩 세션 관리.
```bash
python scripts/live_binance.py --action start --symbol BTCUSDT --strategy dip_martingale
python scripts/live_binance.py --action status
python scripts/live_binance.py --action stop --session-id <id>
```

## Architecture

```
at-binance/
├── SKILL.md              # This file
├── scripts/
│   ├── backtest_binance.py   # Binance backtest wrapper
│   ├── optimize_binance.py   # Parameter optimization
│   └── live_binance.py       # Live trading via API
└── references/
    ├── binance_futures.md    # Futures trading reference
    └── exchange_rules.md     # Qty/price rules reference
```

## Supported Exchanges
- **Binance Spot**: `exchange_name=Binance`
- **Binance Futures (USDM)**: `exchange_name=BinanceFutures`

## Key Differences from Korean Stocks
| Feature | Kiwoom | Binance Spot | Binance Futures |
|---------|--------|-------------|-----------------|
| Qty Type | int | float | float |
| Min Qty | 1 | 0.00001 | 0.001 |
| Min Notional | - | $5 | $5 |
| Leverage | N/A | N/A | 1-125x |
| Short | N/A | N/A | Yes |
| 24h Market | No | Yes | Yes |
