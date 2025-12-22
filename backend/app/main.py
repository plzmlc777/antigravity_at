from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import endpoints

from .api import endpoints, auth, accounts
from .db.base import Base
from .db.session import engine

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Antigravity Auto Trading")

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
