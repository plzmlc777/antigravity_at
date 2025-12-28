from fastapi import APIRouter
from typing import List, Dict, Any
from pydantic import BaseModel
import random
import time

router = APIRouter()

class Strategy(BaseModel):
    id: str
    name: str
    description: str
    code: str
    tags: List[str]

MOCK_STRATEGIES = [
    Strategy(
        id="time_momentum",
        name="Time Momentum (User Req)",
        description="Wait Delay -> Check % Jump -> Buy -> Trailing Stop",
        code="[Real Engine] Logic implemented in backend/strategies/time_momentum.py",
        tags=["Momentum", "Timed Entry"]
    ),
    Strategy(
        id="rsi_strategy",
        name="RSI Swing Master",
        description="Buys when RSI < 30 and Sells when RSI > 70. Classic mean reversion.",
        code="def on_data(self, data):\n    if rsi < 30:\n        order.buy()\n    elif rsi > 70:\n        order.sell()",
        tags=["Mean Reversion", "Technical"]
    ),
    Strategy(
        id="golden_cross",
        name="MA Golden Cross",
        description="Buys when 20MA crosses above 60MA. Captures strong trends.",
        code="def on_data(self, data):\n    if ma20 > ma60 and prev_ma20 <= prev_ma60:\n        order.buy()",
        tags=["Trend Following", "Moving Average"]
    ),
    Strategy(
        id="volatility_breakout",
        name="Volatility Breakout",
        description="Larry Williams' volatility breakout strategy.",
        code="def on_data(self, data):\n    if current_price > target_price:\n        order.buy()",
        tags=["Breakout", "Intraday"]
    )
]

@router.get("/list", response_model=List[Strategy])
async def list_strategies():
    return MOCK_STRATEGIES

@router.post("/generate")
async def generate_strategy_code(prompt: Dict[str, str]):
    # Mock AI Delay
    time.sleep(1.5)
    return {
        "id": f"ai_gen_{random.randint(1000, 9999)}",
        "name": "AI Generated Strategy",
        "description": f"Generated based on: {prompt.get('prompt')}",
        "code": f"# AI Generated Code for: {prompt.get('prompt')}\n\nclass MyStrategy(BaseStrategy):\n    def on_data(self, data):\n        # Logic derived from AI\n        if data.close > data.open * 1.05:\n            self.buy()",
        "tags": ["AI-Generated"]
    }

from typing import List, Dict, Any, Optional

class BacktestRequest(BaseModel):
    symbol: str = "TEST"
    interval: str = "1m"
    days: int = 365
    from_date: Optional[str] = None # Or start_date
    start_date: Optional[str] = None # Aliases
    initial_capital: int = 10000000
    config: Dict[str, Any] = {} # Nested config from frontend strategy selector

@router.post("/{strategy_id}/backtest")
async def run_mock_backtest(strategy_id: str, request: BacktestRequest):
    from ..core.backtest_engine import BacktestEngine
    
    # Select Strategy Class
    strategy_class = None
    
    # Use nested config as the strategy config
    config = request.config
    
    # Also inject root-level params into config if needed (or keep separate)
    # Strategy might need start_date? Usually not, just "on_data".
    
    if strategy_id == "time_momentum":
        from ..strategies.time_momentum import TimeMomentumStrategy
        strategy_class = TimeMomentumStrategy
    else:
        # Fallback for others (or use a Default)
        from ..strategies.base import BaseStrategy
        class MockStrategy(BaseStrategy):
             def initialize(self): pass
             def on_data(self, data): pass
        strategy_class = MockStrategy

    # Run Engine
    # Initialize engine with Strategy Class and Strategy Config
    engine = BacktestEngine(strategy_class, config)
    
    # Run
    # Pass initial_capital to run() or set it before running?
    # BacktestEngine needs to support initial_capital argument in run() or init.
    # We will pass it to run().
    
    start_date = request.start_date or request.from_date
    
    result = await engine.run(
        symbol=request.symbol, 
        interval=request.interval,
        duration_days=request.days, 
        from_date=start_date,
        initial_capital=request.initial_capital
    ) 
    
    return {
        "strategy_id": strategy_id,
        "total_return": result['total_return'],
        "win_rate": result['win_rate'],
        "max_drawdown": result['max_drawdown'],
        "total_trades": result.get('total_trades', 0),
        "avg_pnl": result.get('avg_pnl', "0%"),
        "max_profit": result.get('max_profit', "0%"),
        "max_loss": result.get('max_loss', "0%"),
        "profit_factor": result.get('profit_factor', "0.00"),
        "sharpe_ratio": result.get('sharpe_ratio', "0.00"),
        "activity_rate": result.get('activity_rate', "0%"),
        "avg_holding_time": result.get('avg_holding_time', "0m"),
        "decile_stats": result.get('decile_stats', []),
        "stability_score": result.get('stability_score', "0.00"),
        "acceleration_score": result.get('acceleration_score', "0.00"),
        "chart_data": result['chart_data'],
        "ohlcv_data": result.get('ohlcv_data', []),
        "trades": result.get('trades', []),
        "logs": result['logs']
    }
