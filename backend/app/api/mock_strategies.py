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

@router.post("/{strategy_id}/backtest")
async def run_mock_backtest(strategy_id: str):
    # Mock Backtest Calculation Delay
    time.sleep(1.0)
    
    # Generate random equity curve
    dates = []
    equity = []
    current_eq = 1000000
    for i in range(30):
        dates.append(f"2024-12-{i+1:02d}")
        change = random.uniform(-0.02, 0.03)
        current_eq *= (1 + change)
        equity.append({"date": dates[-1], "equity": int(current_eq)})
        
    return {
        "strategy_id": strategy_id,
        "total_return": f"{(current_eq/1000000 - 1) * 100:.2f}%",
        "win_rate": f"{random.randint(40, 70)}%",
        "max_drawdown": f"-{random.randint(5, 20)}%",
        "chart_data": equity
    }
