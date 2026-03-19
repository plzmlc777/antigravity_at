"""ML Service Configuration - Fully Independent."""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Data storage (SQLite - independent from main backend)
DATA_DIR = os.environ.get("ML_DATA_DIR", "/mnt/data/ml")
SQLITE_DB_PATH = os.path.join(DATA_DIR, "ohlcv.db")
DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH}"

# Model storage
MODEL_DIR = os.environ.get("ML_MODEL_DIR", "/mnt/data/ml/models")

# Binance Futures API (public, no auth needed)
BINANCE_FUTURES_BASE = "https://fapi.binance.com"

# Collector settings
COLLECT_INTERVAL_MINUTES = int(os.environ.get("ML_COLLECT_INTERVAL", "5"))
COLLECT_SYMBOLS = [s.strip() for s in os.environ.get(
    "ML_SYMBOLS",
    "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,DOGEUSDT,AVAXUSDT,XRPUSDT,SUIUSDT"
).split(",") if s.strip()]
COLLECT_INITIAL_DAYS = int(os.environ.get("ML_INITIAL_DAYS", "730"))

# Server
ML_PORT = int(os.environ.get("ML_PORT", "8002"))
