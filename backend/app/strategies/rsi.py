from .base import BaseStrategy
from typing import Dict, Any, List

class RSIStrategy(BaseStrategy):

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "interval", "type": "select", "label": "Interval",
             "default": "1m",
             "options": ["1m", "3m", "5m", "10m", "15m", "30m", "60m", "1d"],
             "description": "Chart candle interval",
             "show_in_table": False, "defaultOptRange": "1m, 5m, 15m, 60m"},
            {"name": "period", "type": "number", "label": "RSI Period",
             "default": 14, "min": 2, "max": 50, "step": 1,
             "description": "Lookback period for RSI calculation",
             "show_in_table": True, "defaultOptRange": "7, 14, 21"},
            {"name": "buy_threshold", "type": "number", "label": "Oversold Level",
             "default": 30, "min": 10, "max": 40, "step": 1,
             "description": "RSI level to trigger buy",
             "show_in_table": True, "defaultOptRange": "20, 25, 30"},
            {"name": "sell_threshold", "type": "number", "label": "Overbought Level",
             "default": 70, "min": 60, "max": 90, "step": 1,
             "description": "RSI level to trigger sell",
             "show_in_table": True, "defaultOptRange": "65, 70, 80"},
        ]
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.period = config.get('period', 14)
        self.buy_threshold = config.get('buy_threshold', 30)
        self.sell_threshold = config.get('sell_threshold', 70)

    @property
    def name(self) -> str:
        return "RSI Strategy"

    def calculate_rsi(self, prices: List[float]) -> float:
        if len(prices) < self.period + 1:
            return 50.0 # Not enough data

        deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]

        avg_gain = sum(gains) / self.period if gains else 0
        avg_loss = sum(losses) / self.period if losses else 0
        
        # Simple Moving Average for first period (can be improved to Wilder's)
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_signals(self, market_data: Dict[str, Any]) -> str:
        """
        Expects market_data to contain 'price_history' (List of floats).
        """
        prices = market_data.get('price_history', [])
        if not prices:
            return 'hold'

        current_rsi = self.calculate_rsi(prices)
        
        # Store latest RSI for UI/Logs (hacky way to return extra info, 
        # normally we'd return a complex object)
        self.last_rsi = current_rsi 

        if current_rsi <= self.buy_threshold:
            return 'buy'
        elif current_rsi >= self.sell_threshold:
            return 'sell'
        
        return 'hold'
