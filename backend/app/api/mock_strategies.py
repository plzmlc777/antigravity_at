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

from pydantic import BaseModel
class BacktestRequest(BaseModel):
    symbol: str = "TEST"
    start_hour: int = 9
    delay_minutes: int = 10
    target_percent: float = 0.02
    safety_stop_percent: float = -0.03

@router.post("/{strategy_id}/backtest")
async def run_mock_backtest(strategy_id: str, request: BacktestRequest):
    from ..core.backtest_engine import BacktestEngine
    
    # Select Strategy Class
    strategy_class = None
    config = request.dict()

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
    engine = BacktestEngine(strategy_class, config)
    # Run for 2 days to simulate more data
    result = await engine.run(symbol=request.symbol, duration_days=2) 
    
    return {
        "strategy_id": strategy_id,
        "total_return": result['total_return'],
        "win_rate": result['win_rate'],
        "max_drawdown": result['max_drawdown'],
        "chart_data": result['chart_data'],
        "logs": result['logs']
    }
