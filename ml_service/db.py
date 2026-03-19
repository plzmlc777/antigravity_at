"""Database for ML Service - SQLite, fully independent."""
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, UniqueConstraint, text
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL, DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class OHLCVHourly(Base):
    __tablename__ = "ohlcv_hourly"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uix_symbol_timestamp"),
    )


class FundingRate(Base):
    __tablename__ = "funding_rate"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    funding_rate = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uix_funding_symbol_ts"),
    )


class OpenInterest(Base):
    __tablename__ = "open_interest"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open_interest = Column(Float, nullable=False)
    open_interest_value = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uix_oi_symbol_ts"),
    )


# Create tables and enable WAL mode for concurrent read/write
Base.metadata.create_all(bind=engine)
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.commit()
