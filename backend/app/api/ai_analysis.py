"""
AI Analysis API Endpoints

Provides endpoints for AI-powered optimization analysis.
"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.ai_analysis import AIAnalysisService
from app.core import security
from app.models.account import ExchangeAccount
from app.models.user import User
from app.api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# CSV output directory (same as heavy optimization)
CSV_OUTPUT_DIR = "/tmp"


def get_user_ai_config(db: Session, user_id: int) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Get decrypted AI API keys and model for the user's active account.

    Returns:
        tuple: (anthropic_api_key, google_api_key, model) - can be None if not configured
    """
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == user_id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        return None, None, None

    anthropic_key = None
    if account.encrypted_ai_api_key:
        try:
            anthropic_key = security.decrypt_key(account.encrypted_ai_api_key)
        except Exception as e:
            logger.error(f"Failed to decrypt AI key: {e}")

    google_key = None
    if account.encrypted_google_api_key:
        try:
            google_key = security.decrypt_key(account.encrypted_google_api_key)
        except Exception as e:
            logger.error(f"Failed to decrypt Google key: {e}")

    return anthropic_key, google_key, account.ai_model


class AnalysisRequest(BaseModel):
    """Request for AI analysis."""
    csv_filename: str
    strategy_id: str = "DipMartingaleStrategy"
    user_question: Optional[str] = None
    model: Optional[str] = None  # Override model (if None, uses user's default)


class AnalysisResponse(BaseModel):
    """Response from AI analysis."""
    analysis_id: str
    status: str
    total_rows: int
    symbols_count: int
    statistics: dict
    ai_response: Optional[dict] = None
    error: Optional[str] = None


class AnalysisStatusResponse(BaseModel):
    """Status of an analysis session."""
    analysis_id: str
    status: str
    created_at: str
    csv_filename: str
    total_rows: int
    ai_analysis_text: Optional[str] = None
    ai_score_formula: Optional[str] = None


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_optimization(
    request: AnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Analyze optimization results using AI.

    1. Imports CSV to temporary DB table
    2. Calculates comprehensive statistics
    3. Builds context and calls Claude API
    4. Returns analysis results
    """
    analysis_id = uuid.uuid4()

    # Get user's AI API keys and default model from database
    anthropic_key, google_key, default_model = get_user_ai_config(db, current_user.id)

    # Use request model override, or fall back to user's default
    model = request.model or default_model or "claude-sonnet-4-20250514"

    # Determine provider and select appropriate key
    from app.api.accounts import get_model_provider
    provider = get_model_provider(model)

    if provider == "google":
        if not google_key:
            raise HTTPException(
                status_code=400,
                detail="Google API key not configured. Please add your Google API key in Settings to use Gemini models."
            )
        api_key = google_key
    else:  # anthropic
        if not anthropic_key:
            raise HTTPException(
                status_code=400,
                detail="Anthropic API key not configured. Please add your Anthropic API key in Settings."
            )
        api_key = anthropic_key

    # Validate CSV file exists
    csv_path = os.path.join(CSV_OUTPUT_DIR, request.csv_filename)
    if not Path(csv_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"CSV file not found: {request.csv_filename}"
        )

    try:
        # Create analysis session record
        await db.execute(text("""
            INSERT INTO ai_analysis_sessions (id, csv_filename, strategy_id, status)
            VALUES (:id, :csv_filename, :strategy_id, 'importing')
        """), {
            "id": str(analysis_id),
            "csv_filename": request.csv_filename,
            "strategy_id": request.strategy_id
        })
        await db.commit()

        # Initialize service with user's API key, model, and provider
        service = AIAnalysisService(db, api_key=api_key, model=model, provider=provider)

        # Step 1: Import CSV to DB
        logger.info(f"[AI Analysis] Importing CSV: {request.csv_filename}")
        rows_imported = await service.import_csv_to_db(csv_path, analysis_id)

        # Update session status
        await db.execute(text("""
            UPDATE ai_analysis_sessions
            SET status = 'analyzing', total_rows = :rows
            WHERE id = :id
        """), {"id": str(analysis_id), "rows": rows_imported})
        await db.commit()

        # Step 2: Calculate statistics
        logger.info(f"[AI Analysis] Calculating statistics...")
        stats = await service.calculate_statistics(analysis_id)

        # Update symbols count
        await db.execute(text("""
            UPDATE ai_analysis_sessions
            SET symbols_count = :count
            WHERE id = :id
        """), {"id": str(analysis_id), "count": stats['overall']['symbol_count']})
        await db.commit()

        # Step 3: Build context and call AI
        logger.info(f"[AI Analysis] Calling Claude API...")
        context = service.build_ai_context(
            request.strategy_id,
            stats,
            request.user_question
        )

        ai_response = await service.call_claude_api(context)

        # Step 4: Save results
        if "error" not in ai_response:
            await db.execute(text("""
                UPDATE ai_analysis_sessions
                SET status = 'completed',
                    completed_at = NOW(),
                    ai_analysis_text = :text
                WHERE id = :id
            """), {
                "id": str(analysis_id),
                "text": ai_response.get("content", "")
            })
        else:
            await db.execute(text("""
                UPDATE ai_analysis_sessions
                SET status = 'failed', error_message = :error
                WHERE id = :id
            """), {"id": str(analysis_id), "error": ai_response.get("error")})

        await db.commit()

        return AnalysisResponse(
            analysis_id=str(analysis_id),
            status="completed" if "error" not in ai_response else "failed",
            total_rows=rows_imported,
            symbols_count=stats['overall']['symbol_count'],
            statistics=stats,
            ai_response=ai_response if "error" not in ai_response else None,
            error=ai_response.get("error")
        )

    except Exception as e:
        logger.exception(f"[AI Analysis] Error: {e}")

        # Update session with error
        await db.execute(text("""
            UPDATE ai_analysis_sessions
            SET status = 'failed', error_message = :error
            WHERE id = :id
        """), {"id": str(analysis_id), "error": str(e)})
        await db.commit()

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{analysis_id}", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    analysis_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get status of an analysis session."""
    result = await db.execute(text("""
        SELECT id, status, created_at, csv_filename, total_rows,
               ai_analysis_text, ai_score_formula
        FROM ai_analysis_sessions
        WHERE id = :id
    """), {"id": analysis_id})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Analysis session not found")

    return AnalysisStatusResponse(
        analysis_id=str(row.id),
        status=row.status,
        created_at=row.created_at.isoformat() if row.created_at else "",
        csv_filename=row.csv_filename or "",
        total_rows=row.total_rows or 0,
        ai_analysis_text=row.ai_analysis_text,
        ai_score_formula=row.ai_score_formula
    )


@router.get("/list")
async def list_analyses(
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """List recent analysis sessions."""
    result = await db.execute(text("""
        SELECT id, status, created_at, csv_filename, total_rows, symbols_count
        FROM ai_analysis_sessions
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"limit": limit})

    return [
        {
            "analysis_id": str(row.id),
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "csv_filename": row.csv_filename,
            "total_rows": row.total_rows or 0,
            "symbols_count": row.symbols_count or 0
        }
        for row in result.fetchall()
    ]


@router.delete("/cleanup")
async def cleanup_old_analyses(
    older_than_hours: int = 24,
    db: AsyncSession = Depends(get_db)
):
    """Cleanup old analysis data."""
    service = AIAnalysisService(db)
    await service.cleanup_old_analyses(older_than_hours)
    return {"message": f"Cleaned up analyses older than {older_than_hours} hours"}


@router.get("/csv-files")
async def list_csv_files():
    """List available CSV files for analysis."""
    files = []
    csv_dir = Path(CSV_OUTPUT_DIR)

    if csv_dir.exists():
        for f in csv_dir.glob("heavy_opt_*.csv"):
            stat = f.stat()
            files.append({
                "filename": f.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

    return sorted(files, key=lambda x: x['modified'], reverse=True)
