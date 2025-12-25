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

app = FastAPI(title="Antigravity Auto Trading", lifespan=lifespan)

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
    return {"message": "Auto Trading System Backend is Running", "status": "active"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Include Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(accounts.router, prefix="/api/v1/accounts", tags=["accounts"])
app.include_router(endpoints.router, prefix="/api/v1", tags=["trading"])
app.include_router(mock_strategies.router, prefix="/api/v1/strategies", tags=["strategies"])
