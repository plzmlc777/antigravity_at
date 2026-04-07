"""
Target Assets loader — reads target_assets.json

Usage:
    from app.core.target_assets import BINANCE_TARGET_ASSETS, BINANCE_SYMBOLS
"""

import json
from pathlib import Path
from typing import List, Dict, Any

_JSON_PATH = Path(__file__).parent / "target_assets.json"
_data = json.loads(_JSON_PATH.read_text(encoding="utf-8"))

BINANCE_TARGET_ASSETS: List[Dict[str, Any]] = _data.get("symbols", [])
BINANCE_SYMBOLS: List[str] = [a["code"] for a in BINANCE_TARGET_ASSETS]
