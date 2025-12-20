from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import endpoints

app = FastAPI(
    title="Auto Trading System API",
    description="Backend for Auto Trading System (Kiwoom/Binance)",
    version="0.1.0"
)

# CORS Configuration
origins = [
    "http://localhost:5173",  # React Frontend (Vite default port)
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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

app.include_router(endpoints.router, prefix="/api/v1", tags=["trading"])
