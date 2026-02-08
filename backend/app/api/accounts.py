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
    is_active: bool = False
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
            is_active=acc.is_active,
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
        is_active=new_account.is_active,
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


@router.put("/{account_id}/activate")
async def activate_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 0. Block if live sessions are running
    from ..core.live_manager import LiveManager
    live_manager = LiveManager.get_instance()
    active_count = live_manager.get_active_sessions_count()

    if active_count > 0:
        session_ids = live_manager.get_active_session_ids()
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Live 세션 {active_count}개 실행 중입니다. 계정 전환 전 먼저 중지해주세요.",
                "active_sessions": session_ids
            }
        )

    # 1. Verify account ownership
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.id == account_id,
        ExchangeAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # 2. Deactivate all other accounts for this user
    db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id
    ).update({"is_active": False})

    # 3. Activate target account
    account.is_active = True
    db.commit()

    # 4. 캐시를 새 계좌 정보로 즉시 업데이트 (invalidate 대신 직접 설정)
    from ..core.account_cache import AccountCache
    from ..core.trading_env import TradingEnvironment

    try:
        decrypted_app = security.decrypt_key(account.encrypted_access_key)
        decrypted_secret = security.decrypt_key(account.encrypted_secret_key)

        new_config = {
            'app_key': decrypted_app,
            'secret_key': decrypted_secret,
            'account_no': account.account_number,
            'account_name': account.account_name,
            'environment': account.environment or TradingEnvironment.REAL.value
        }

        # 캐시에 새 값 직접 설정 (race condition 방지)
        AccountCache.get_instance().set_active_account_config(current_user.id, new_config)
    except Exception as e:
        # 복호화 실패 시 캐시 무효화 (fallback)
        AccountCache.get_instance().invalidate(current_user.id)
        print(f"[Activate] Cache update failed, invalidated instead: {e}")

    # 5. Notify LiveManager to reinitialize adapter with new account
    from ..core.live_manager import LiveManager
    live_manager = LiveManager.get_instance()
    adapter_result = await live_manager.on_account_changed(account_id=account_id)

    return {
        "status": "success",
        "message": f"Account {account.account_name} activated",
        "adapter": adapter_result
    }


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
        # If disabling, also deactivate
        if account_update.is_disabled and account.is_active:
            account.is_active = False

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
        is_active=account.is_active,
        is_disabled=account.is_disabled,
        environment=account.environment or TradingEnvironment.REAL.value,
        is_virtual=account.is_virtual,
        api_url=account.api_url,
        display_name=account.display_name
    )


class AccountPreferencesOut(BaseModel):
    """계좌별 환경설정"""
    last_selected_strategy_id: Optional[str] = None
    last_symbol: Optional[str] = None
    saved_symbols: Optional[List] = None
    symbol_compare_settings: Optional[dict] = None
    execution_mode: Optional[str] = None


class UpdateLastStrategyRequest(BaseModel):
    strategy_id: Optional[str] = None


class UpdateWatchlistRequest(BaseModel):
    """워치리스트 업데이트"""
    last_symbol: Optional[str] = None
    saved_symbols: Optional[List] = None


class UpdateSymbolCompareRequest(BaseModel):
    """종목 비교 설정 업데이트"""
    symbol_compare_settings: Optional[dict] = None


class UpdateExecutionModeRequest(BaseModel):
    """실행 모드 업데이트"""
    execution_mode: Optional[str] = None  # 'exclusive' | 'parallel'


@router.get("/preferences", response_model=AccountPreferencesOut)
def get_account_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current active account's preferences (last selected strategy, saved symbols, etc.)
    계좌 중심으로 환경설정 조회
    """
    # Get active account
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    return AccountPreferencesOut(
        last_selected_strategy_id=account.last_selected_strategy_id,
        last_symbol=account.last_symbol,
        saved_symbols=account.saved_symbols,
        symbol_compare_settings=account.symbol_compare_settings,
        execution_mode=account.execution_mode
    )


@router.put("/preferences/strategy")
def update_last_selected_strategy(
    request: UpdateLastStrategyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update last selected strategy for current active account
    계좌별로 마지막 선택 전략 저장
    """
    # Get active account
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    # Update last selected strategy
    account.last_selected_strategy_id = request.strategy_id
    db.commit()

    return {"status": "success", "last_selected_strategy_id": request.strategy_id}


@router.put("/preferences/watchlist")
def update_watchlist(
    request: UpdateWatchlistRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update watchlist (last_symbol, saved_symbols) for current active account
    계좌별로 워치리스트 저장
    """
    # Get active account
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    # Update fields if provided
    if request.last_symbol is not None:
        account.last_symbol = request.last_symbol
    if request.saved_symbols is not None:
        account.saved_symbols = request.saved_symbols

    db.commit()

    return {
        "status": "success",
        "last_symbol": account.last_symbol,
        "saved_symbols": account.saved_symbols
    }


@router.put("/preferences/symbol-compare")
def update_symbol_compare(
    request: UpdateSymbolCompareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update symbol compare settings for current active account
    계좌별로 종목 비교 설정 저장
    """
    # Get active account
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    # Update symbol compare settings
    if request.symbol_compare_settings is not None:
        account.symbol_compare_settings = request.symbol_compare_settings

    db.commit()

    return {
        "status": "success",
        "symbol_compare_settings": account.symbol_compare_settings
    }


@router.put("/preferences/execution-mode")
def update_execution_mode(
    request: UpdateExecutionModeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update execution mode for current active account
    계좌별로 실행 모드 저장
    """
    # Get active account
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    # Validate execution mode
    valid_modes = ['exclusive', 'parallel']
    if request.execution_mode and request.execution_mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid execution mode. Must be one of: {valid_modes}")

    # Update execution mode
    if request.execution_mode is not None:
        account.execution_mode = request.execution_mode

    db.commit()

    return {
        "status": "success",
        "execution_mode": account.execution_mode
    }


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

# Fallback Google models (used when API key not available) - only latest version
GOOGLE_MODELS_FALLBACK = [
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "description": "Best for complex tasks", "provider": "google"},
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "description": "Fast & versatile", "provider": "google"},
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
    Check if the current active account has an AI API key configured.
    Returns key preview (first 10 + last 3 chars) for confirmation.
    """
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    has_key = bool(account.encrypted_ai_api_key)
    key_preview = None

    if has_key:
        try:
            decrypted = security.decrypt_key(account.encrypted_ai_api_key)
            if len(decrypted) > 15:
                key_preview = f"{decrypted[:10]}...{decrypted[-3:]}"
            else:
                key_preview = f"{decrypted[:5]}..."
        except Exception:
            key_preview = "***"

    # Check Google API key
    has_google_key = bool(account.encrypted_google_api_key)
    google_key_preview = None

    if has_google_key:
        try:
            decrypted = security.decrypt_key(account.encrypted_google_api_key)
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
        ai_model=account.ai_model or DEFAULT_AI_MODEL
    )


@router.put("/ai-key")
def set_ai_key(
    request: AIKeyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Set or update AI API key for the current active account.
    Key is encrypted before storage.
    """
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    # Validate key format (basic check for Anthropic key)
    key = request.ai_api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="AI API key cannot be empty")

    if not key.startswith("sk-ant-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid Anthropic API key format. Key should start with 'sk-ant-'"
        )

    # Encrypt and store
    encrypted_key = security.encrypt_key(key)
    account.encrypted_ai_api_key = encrypted_key
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
    Remove AI API key from the current active account.
    """
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    account.encrypted_ai_api_key = None
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
    Set or update Google API key for the current active account.
    Key is encrypted before storage.
    """
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    key = request.google_api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="Google API key cannot be empty")

    # Encrypt and store
    encrypted_key = security.encrypt_key(key)
    account.encrypted_google_api_key = encrypted_key
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
    Remove Google API key from the current active account.
    """
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    account.encrypted_google_api_key = None
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

            # Find the highest version among all models
            if models:
                max_version = max(get_version(m["id"]) for m in models)
                # Filter to only include models with the highest version
                models = [m for m in models if get_version(m["id"]) == max_version]

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
    # Get user's Google API key to fetch models
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    google_models = GOOGLE_MODELS_FALLBACK

    if account and account.encrypted_google_api_key:
        try:
            google_key = security.decrypt_key(account.encrypted_google_api_key)
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
    Set default AI model for the current active account.
    """
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    # Basic validation - allow any gemini-* or claude-* model
    # (since Google models are fetched dynamically)
    model = request.ai_model
    if not (model.startswith("claude-") or model.startswith("gemini-")):
        raise HTTPException(
            status_code=400,
            detail="Invalid model. Model must start with 'claude-' or 'gemini-'"
        )

    account.ai_model = request.ai_model
    db.commit()

    return {
        "status": "success",
        "message": f"AI model set to {request.ai_model}",
        "ai_model": request.ai_model
    }
