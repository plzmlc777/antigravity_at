from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import endpoints, auth, accounts, mock_strategies
from .db.base import Base
from .db.session import engine
from .core.bot_manager import bot_manager
from .core.condition_watcher import condition_watcher
from .models.bot import TradingBotModel # Register Model
from .models.ohlcv import OHLCV # Register Model
from .core.http_client import HttpClientManager # New Import

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Logic
    logger.info("Starting up...")
    
    # Create Tables
    Base.metadata.create_all(bind=engine)
    
    # Start Services
    await HttpClientManager.get_instance().start() # Global Client
    bot_manager.initialize() # Load bots after DB creation
    await condition_watcher.start()
    
    yield
    
    # Shutdown Logic
    logger.info("Shutting down...")
    await HttpClientManager.get_instance().stop() # Close Global Client
    # await bot_manager.stop_all() # Ensure bots are stopped
    await condition_watcher.stop() # Stop watcher

app = FastAPI(title="AutoTrading Agent API", version="0.9.0.1", description="Backend API for AI-driven Auto Trading System", lifespan=lifespan)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Welcome to AutoTrading Agent API v0.9.0.2", "version": "0.9.0.2", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# --- Debug: Validation Error Logging ---
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import json

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # Log the full details to the backend console
    error_details = exc.errors()
    body = await request.body()
    
    logger.error(f"⚠️  [422 Validation Error] URL: {request.url}")
    try:
        logger.error(f"⚠️  Body: {body.decode('utf-8')}")
    except:
        logger.error(f"⚠️  Body: <binary>")
    
    logger.error(f"⚠️  Details: {json.dumps(error_details, indent=2)}")
    
    return JSONResponse(
        status_code=422,
        content={"detail": error_details, "body": str(body)},
    )
# ---------------------------------------

# Include Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(accounts.router, prefix="/api/v1/accounts", tags=["accounts"])
app.include_router(endpoints.router, prefix="/api/v1", tags=["trading"])
from .models.strategy_result import StrategyAnalysisResult # Register Model
from .api import market_data, admin, strategy_results
app.include_router(market_data.router, prefix="/api/v1/market-data", tags=["market-data"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(mock_strategies.router, prefix="/api/v1/strategies", tags=["strategies"])
app.include_router(strategy_results.router, prefix="/api/v1/strategy-results", tags=["strategy-results"])
from .api import strategy_configs
app.include_router(strategy_configs.router, prefix="/api/v1/strategy-configs", tags=["strategy-configs"])
