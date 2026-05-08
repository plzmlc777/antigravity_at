from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..core.config import settings

# PostgreSQL database URL
# Constructed from settings or .env
SQLALCHEMY_DATABASE_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}/{settings.POSTGRES_DB}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=30,
    max_overflow=50,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_scope(commit: bool = False):
    """Context manager for background/non-FastAPI code paths.

    Usage:
        with db_scope() as db:                # read-only
            rows = db.query(Foo).all()

        with db_scope(commit=True) as db:     # write — auto-commit on success
            db.add(Foo(...))
                                              # rollback on exception, always close

    Replaces the manual `db = SessionLocal(); try/finally db.close()` pattern.
    Connection lifecycle is guaranteed by the context manager — leak impossible.
    """
    db = SessionLocal()
    try:
        yield db
        if commit:
            db.commit()
    except Exception:
        if commit:
            db.rollback()
        raise
    finally:
        db.close()
