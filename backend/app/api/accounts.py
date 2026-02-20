import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import httpx
from ..db.session import get_db
from ..models.account import ExchangeAccount
from ..models.user import User
from ..core import security
from ..core.trading_env import TradingEnvironment, get_env_config
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class AccountCreate(BaseModel):
    exchange_name: str
    account_name: str
    access_key: str
    secret_key: str
    account_number: Optional[str] = None
    environment: str = TradingEnvironment.REAL.value  # "real", "virtual", "paper"


class AccountOut(BaseModel):
    id: int
    exchange_name: str
    account_name: str
    account_number: Optional[str] = None
    is_disabled: bool = False
    environment: str  # "real", "virtual", "paper"
    # Computed properties for backward compatibility
    is_virtual: bool = False
    api_url: Optional[str] = None
    display_name: str = ""

    class Config:
        from_attributes = True


class AccountUpdate(BaseModel):
    account_name: Optional[str] = None
    is_disabled: Optional[bool] = None


@router.get("/", response_model=List[AccountOut])
def get_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    accounts = db.query(ExchangeAccount).filter(ExchangeAccount.user_id == current_user.id).all()
    # Convert to response with computed properties
    result = []
    for acc in accounts:
        result.append(AccountOut(
            id=acc.id,
            exchange_name=acc.exchange_name,
            account_name=acc.account_name,
            account_number=acc.account_number,
            is_disabled=acc.is_disabled,
            environment=acc.environment or TradingEnvironment.REAL.value,
            is_virtual=acc.is_virtual,
            api_url=acc.api_url,
            display_name=acc.display_name
        ))
    return result


@router.post("/", response_model=AccountOut)
def create_account(
    account_in: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Validate environment value
    try:
        env = TradingEnvironment(account_in.environment)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid environment: {account_in.environment}")

    # Encrypt keys
    encrypted_access = security.encrypt_key(account_in.access_key)
    encrypted_secret = security.encrypt_key(account_in.secret_key)

    new_account = ExchangeAccount(
        user_id=current_user.id,
        exchange_name=account_in.exchange_name,
        account_name=account_in.account_name,
        encrypted_access_key=encrypted_access,
        encrypted_secret_key=encrypted_secret,
        account_number=account_in.account_number,
        environment=env.value
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)

    return AccountOut(
        id=new_account.id,
        exchange_name=new_account.exchange_name,
        account_name=new_account.account_name,
        account_number=new_account.account_number,
        is_disabled=new_account.is_disabled,
        environment=new_account.environment,
        is_virtual=new_account.is_virtual,
        api_url=new_account.api_url,
        display_name=new_account.display_name
    )


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Block if live sessions are running
    from ..core.live_manager import LiveManager
    live_manager = LiveManager.get_instance()
    active_count = live_manager.get_active_sessions_count()

    if active_count > 0:
        session_ids = live_manager.get_active_session_ids()
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Live 세션 {active_count}개 실행 중입니다. 계정 삭제 전 먼저 중지해주세요.",
                "active_sessions": session_ids
            }
        )

    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.id == account_id,
        ExchangeAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    db.delete(account)
    db.commit()

    # Invalidate Cache
    from ..core.account_cache import AccountCache
    AccountCache.get_instance().invalidate(current_user.id)

    return {"status": "success"}


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int,
    account_update: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.id == account_id,
        ExchangeAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Update fields if provided
    if account_update.account_name is not None:
        account.account_name = account_update.account_name

    if account_update.is_disabled is not None:
        account.is_disabled = account_update.is_disabled

    db.commit()
    db.refresh(account)

    # Invalidate Cache
    from ..core.account_cache import AccountCache
    AccountCache.get_instance().invalidate(current_user.id)

    return AccountOut(
        id=account.id,
        exchange_name=account.exchange_name,
        account_name=account.account_name,
        account_number=account.account_number,
        is_disabled=account.is_disabled,
        environment=account.environment or TradingEnvironment.REAL.value,
        is_virtual=account.is_virtual,
        api_url=account.api_url,
        display_name=account.display_name
    )


class AccountPreferencesOut(BaseModel):
    """사용자 환경설정"""
    last_selected_strategy_id: Optional[str] = None
    last_selected_profile_id: Optional[str] = None
    last_symbol: Optional[str] = None
    saved_symbols: Optional[List] = None
    # NOTE: symbol_compare_settings, execution_mode moved to strategy_profiles (Profile-Centric Architecture)


class UpdateLastStrategyRequest(BaseModel):
    strategy_id: Optional[str] = None


class UpdateLastProfileRequest(BaseModel):
    profile_id: Optional[str] = None


class UpdateWatchlistRequest(BaseModel):
    """워치리스트 업데이트"""
    last_symbol: Optional[str] = None
    saved_symbols: Optional[List] = None


@router.get("/preferences", response_model=AccountPreferencesOut)
def get_account_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get user preferences (last selected strategy, saved symbols, etc.)
    사용자 계정 기준으로 환경설정 조회
    """
    user = db.merge(current_user)

    return AccountPreferencesOut(
        last_selected_strategy_id=user.last_selected_strategy_id,
        last_selected_profile_id=user.last_selected_profile_id,
        last_symbol=user.last_symbol,
        saved_symbols=user.saved_symbols
    )


@router.put("/preferences/strategy")
def update_last_selected_strategy(
    request: UpdateLastStrategyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update last selected strategy for user.
    """
    user = db.merge(current_user)
    user.last_selected_strategy_id = request.strategy_id
    db.commit()

    return {"status": "success", "last_selected_strategy_id": request.strategy_id}


@router.put("/preferences/profile")
def update_last_selected_profile(
    request: UpdateLastProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update last selected profile for user.
    """
    user = db.merge(current_user)
    user.last_selected_profile_id = request.profile_id
    db.commit()

    return {"status": "success", "last_selected_profile_id": request.profile_id}


@router.put("/preferences/watchlist")
def update_watchlist(
    request: UpdateWatchlistRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update watchlist (last_symbol, saved_symbols) for user.
    """
    user = db.merge(current_user)

    if request.last_symbol is not None:
        user.last_symbol = request.last_symbol
    if request.saved_symbols is not None:
        user.saved_symbols = request.saved_symbols

    db.commit()

    return {
        "status": "success",
        "last_symbol": user.last_symbol,
        "saved_symbols": user.saved_symbols
    }


# NOTE: symbol_compare_settings, execution_mode endpoints removed
# These are now managed at the profile level (strategy_profiles table)
# See: /api/v1/live/profiles endpoints


# ========================================
# AI API Key Management
# ========================================

class AIKeyRequest(BaseModel):
    """AI API 키 설정"""
    ai_api_key: str


class AIKeyStatusResponse(BaseModel):
    """AI API 키 상태"""
    has_ai_key: bool
    key_preview: Optional[str] = None  # e.g., "sk-ant-...xxx"
    has_google_key: bool = False
    google_key_preview: Optional[str] = None  # e.g., "AIza...xxx"
    ai_model: Optional[str] = None  # Current selected model


class GoogleKeyRequest(BaseModel):
    """Google API 키 설정"""
    google_api_key: str


# Available AI models (Anthropic - static, Google - fetched dynamically)
ANTHROPIC_MODELS = [
    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "description": "Fast & affordable", "provider": "anthropic"},
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "description": "Balanced (recommended)", "provider": "anthropic"},
    {"id": "claude-opus-4-5-20251101", "name": "Claude Opus 4.5", "description": "Most capable", "provider": "anthropic"},
]

# Fallback Google models (used when API key not available) - latest + previous version
GOOGLE_MODELS_FALLBACK = [
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "description": "Best for complex tasks", "provider": "google"},
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "description": "Fast & versatile", "provider": "google"},
    {"id": "gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "description": "Fast & versatile (Previous)", "provider": "google"},
]

# Combined list for validation (will be updated dynamically)
AI_MODELS = ANTHROPIC_MODELS + GOOGLE_MODELS_FALLBACK
DEFAULT_AI_MODEL = "claude-sonnet-4-20250514"

# Google models API endpoint
GOOGLE_MODELS_API = "https://generativelanguage.googleapis.com/v1beta/models"


def get_model_provider(model_id: str) -> str:
    """Get provider for a model ID."""
    # Dynamic detection based on model name prefix
    if model_id.startswith("gemini-"):
        return "google"
    elif model_id.startswith("claude-"):
        return "anthropic"

    # Fallback to static list lookup
    for m in AI_MODELS:
        if m["id"] == model_id:
            return m.get("provider", "anthropic")
    return "anthropic"  # default


class AIModelRequest(BaseModel):
    """AI 모델 설정"""
    ai_model: str


@router.get("/ai-key/status", response_model=AIKeyStatusResponse)
def get_ai_key_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if the user has AI API keys configured.
    Returns key preview (first 10 + last 3 chars) for confirmation.
    """
    user = db.merge(current_user)

    has_key = bool(user.encrypted_ai_api_key)
    key_preview = None

    if has_key:
        try:
            decrypted = security.decrypt_key(user.encrypted_ai_api_key)
            if len(decrypted) > 15:
                key_preview = f"{decrypted[:10]}...{decrypted[-3:]}"
            else:
                key_preview = f"{decrypted[:5]}..."
        except Exception:
            key_preview = "***"

    has_google_key = bool(user.encrypted_google_api_key)
    google_key_preview = None

    if has_google_key:
        try:
            decrypted = security.decrypt_key(user.encrypted_google_api_key)
            if len(decrypted) > 15:
                google_key_preview = f"{decrypted[:10]}...{decrypted[-3:]}"
            else:
                google_key_preview = f"{decrypted[:5]}..."
        except Exception:
            google_key_preview = "***"

    return AIKeyStatusResponse(
        has_ai_key=has_key,
        key_preview=key_preview,
        has_google_key=has_google_key,
        google_key_preview=google_key_preview,
        ai_model=user.ai_model or DEFAULT_AI_MODEL
    )


@router.put("/ai-key")
def set_ai_key(
    request: AIKeyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Set or update AI API key for the user.
    Key is encrypted before storage.
    """
    user = db.merge(current_user)

    key = request.ai_api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="AI API key cannot be empty")

    if not key.startswith("sk-ant-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid Anthropic API key format. Key should start with 'sk-ant-'"
        )

    encrypted_key = security.encrypt_key(key)
    user.encrypted_ai_api_key = encrypted_key
    db.commit()

    return {
        "status": "success",
        "message": "AI API key saved successfully",
        "key_preview": f"{key[:10]}...{key[-3:]}"
    }


@router.delete("/ai-key")
def delete_ai_key(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Remove AI API key from the user.
    """
    user = db.merge(current_user)
    user.encrypted_ai_api_key = None
    db.commit()

    return {
        "status": "success",
        "message": "AI API key removed"
    }


@router.put("/google-key")
def set_google_key(
    request: GoogleKeyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Set or update Google API key for the user.
    Key is encrypted before storage.
    """
    user = db.merge(current_user)

    key = request.google_api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="Google API key cannot be empty")

    # Encrypt and store
    encrypted_key = security.encrypt_key(key)
    user.encrypted_google_api_key = encrypted_key
    db.commit()

    return {
        "status": "success",
        "message": "Google API key saved successfully",
        "key_preview": f"{key[:10]}...{key[-3:]}" if len(key) > 13 else f"{key[:5]}..."
    }


@router.delete("/google-key")
def delete_google_key(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Remove Google API key from the user.
    """
    user = db.merge(current_user)
    user.encrypted_google_api_key = None
    db.commit()

    return {
        "status": "success",
        "message": "Google API key removed"
    }


async def fetch_google_models(api_key: str) -> List[dict]:
    """Fetch available Google Gemini models from API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{GOOGLE_MODELS_API}?key={api_key}"
            )

            if response.status_code != 200:
                logger.warning(f"Failed to fetch Google models: {response.status_code}")
                return GOOGLE_MODELS_FALLBACK

            data = response.json()
            models = []

            for model in data.get("models", []):
                name = model.get("name", "")
                # Extract model ID from "models/gemini-xxx" format
                model_id = name.replace("models/", "") if name.startswith("models/") else name

                # Only include models that support generateContent
                supported_methods = model.get("supportedGenerationMethods", [])
                if "generateContent" not in supported_methods:
                    continue

                # Skip non-gemini models and special-purpose models
                mid_lower = model_id.lower()
                if not mid_lower.startswith("gemini"):
                    continue
                # Only skip truly unusable models (TTS, robotics, image-only, computer-use)
                if any(skip in mid_lower for skip in ["tts", "robotics", "computer-use", "banana"]):
                    continue

                display_name = model.get("displayName", model_id)

                # Determine tier based on model name
                if "flash-lite" in mid_lower:
                    tier = "Cost-effective"
                elif "flash" in mid_lower:
                    tier = "Fast & versatile"
                elif "pro" in mid_lower:
                    tier = "Best for complex tasks"
                else:
                    tier = "Gemini model"

                # Add preview tag if applicable
                if "preview" in mid_lower:
                    tier += " (Preview)"

                models.append({
                    "id": model_id,
                    "name": display_name,
                    "description": tier,
                    "provider": "google"
                })

            # Helper function to extract version from model ID
            def get_version(mid: str) -> int:
                mid = mid.lower()
                if "-3-" in mid or mid.startswith("gemini-3"):
                    return 40
                elif "2.5" in mid:
                    return 30
                elif "2.0" in mid:
                    return 20
                elif "1.5" in mid:
                    return 10
                return 0

            # Find the top 2 versions among all models (latest + previous)
            if models:
                all_versions = sorted(set(get_version(m["id"]) for m in models), reverse=True)
                # Keep top 2 versions (e.g., gemini-3 and gemini-2.5)
                top_versions = set(all_versions[:2])
                models = [m for m in models if get_version(m["id"]) in top_versions]

            # Sort: pro before flash, stable before preview
            def sort_key(m):
                mid = m["id"].lower()
                # Type score (pro > flash > flash-lite)
                type_score = 0
                if "pro" in mid:
                    type_score = 3
                elif "flash-lite" in mid:
                    type_score = 1
                elif "flash" in mid:
                    type_score = 2
                # Preview penalty
                preview_penalty = 1 if "preview" in mid else 0
                # Experimental/latest penalty
                exp_penalty = 1 if ("exp" in mid or "latest" in mid) else 0
                return (-type_score, preview_penalty, exp_penalty, mid)

            models.sort(key=sort_key)

            # Limit to reasonable number
            return models[:10] if models else GOOGLE_MODELS_FALLBACK

    except Exception as e:
        logger.error(f"Error fetching Google models: {e}")
        return GOOGLE_MODELS_FALLBACK


@router.get("/ai-models")
async def get_ai_models(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of available AI models.
    Fetches Google models dynamically if Google API key is configured.
    """
    user = db.merge(current_user)

    google_models = GOOGLE_MODELS_FALLBACK

    if user.encrypted_google_api_key:
        try:
            google_key = security.decrypt_key(user.encrypted_google_api_key)
            google_models = await fetch_google_models(google_key)
        except Exception as e:
            logger.error(f"Failed to decrypt Google key for model fetch: {e}")

    all_models = ANTHROPIC_MODELS + google_models

    return {
        "models": all_models,
        "default": DEFAULT_AI_MODEL
    }


@router.put("/ai-model")
def set_ai_model(
    request: AIModelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Set default AI model for the user.
    """
    user = db.merge(current_user)

    model = request.ai_model
    if not (model.startswith("claude-") or model.startswith("gemini-")):
        raise HTTPException(
            status_code=400,
            detail="Invalid model. Model must start with 'claude-' or 'gemini-'"
        )

    user.ai_model = request.ai_model
    db.commit()

    return {
        "status": "success",
        "message": f"AI model set to {request.ai_model}",
        "ai_model": request.ai_model
    }


# ========================================
# Telegram Notification Settings
# ========================================

class TelegramSettingsRequest(BaseModel):
    """텔레그램 설정"""
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    enabled: bool = False
    notify_trades: bool = True
    notify_ai_eval: bool = True
    notify_errors: bool = True


class TelegramSettingsResponse(BaseModel):
    """텔레그램 설정 상태"""
    enabled: bool = False
    has_bot_token: bool = False
    token_preview: Optional[str] = None
    chat_id: Optional[str] = None
    notify_trades: bool = True
    notify_ai_eval: bool = True
    notify_errors: bool = True


@router.get("/{account_id}/telegram", response_model=TelegramSettingsResponse)
def get_telegram_settings(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get Telegram notification settings for a specific account.
    """
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.id == account_id,
        ExchangeAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    has_token = bool(account.encrypted_telegram_bot_token)
    token_preview = None

    if has_token:
        try:
            decrypted = security.decrypt_key(account.encrypted_telegram_bot_token)
            if len(decrypted) > 15:
                token_preview = f"{decrypted[:10]}...{decrypted[-4:]}"
            else:
                token_preview = f"{decrypted[:5]}..."
        except Exception:
            pass

    return TelegramSettingsResponse(
        enabled=account.telegram_enabled or False,
        has_bot_token=has_token,
        token_preview=token_preview,
        chat_id=account.telegram_chat_id,
        notify_trades=account.telegram_notify_trades if account.telegram_notify_trades is not None else True,
        notify_ai_eval=account.telegram_notify_ai_eval if account.telegram_notify_ai_eval is not None else True,
        notify_errors=account.telegram_notify_errors if account.telegram_notify_errors is not None else True
    )


@router.put("/{account_id}/telegram")
def update_telegram_settings(
    account_id: int,
    request: TelegramSettingsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update Telegram notification settings for a specific account.
    """
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.id == account_id,
        ExchangeAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Update bot token if provided
    if request.bot_token:
        account.encrypted_telegram_bot_token = security.encrypt_key(request.bot_token)

    # Update other settings
    if request.chat_id is not None:
        account.telegram_chat_id = request.chat_id

    account.telegram_enabled = request.enabled
    account.telegram_notify_trades = request.notify_trades
    account.telegram_notify_ai_eval = request.notify_ai_eval
    account.telegram_notify_errors = request.notify_errors

    db.commit()

    return {
        "status": "success",
        "message": "Telegram settings updated",
        "settings": {
            "enabled": account.telegram_enabled,
            "has_bot_token": bool(account.encrypted_telegram_bot_token),
            "chat_id": account.telegram_chat_id,
            "notify_trades": account.telegram_notify_trades,
            "notify_ai_eval": account.telegram_notify_ai_eval,
            "notify_errors": account.telegram_notify_errors
        }
    }


@router.post("/{account_id}/telegram/test")
async def test_telegram_connection(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Test Telegram bot connection for a specific account.
    """
    from ..core.telegram_service import test_telegram_connection as test_connection

    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.id == account_id,
        ExchangeAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if not account.encrypted_telegram_bot_token:
        raise HTTPException(status_code=400, detail="Bot token not configured")

    if not account.telegram_chat_id:
        raise HTTPException(status_code=400, detail="Chat ID not configured")

    try:
        bot_token = security.decrypt_key(account.encrypted_telegram_bot_token)
        result = await test_connection(bot_token, account.telegram_chat_id)
        return result
    except Exception as e:
        return {"success": False, "message": f"Test failed: {str(e)}"}
