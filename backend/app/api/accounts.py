import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
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


class ConnectionTestRequest(BaseModel):
    exchange_name: str
    access_key: str
    secret_key: str
    account_number: Optional[str] = None
    environment: str = TradingEnvironment.REAL.value


@router.post("/test-connection")
async def test_account_connection(
    req: ConnectionTestRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Test exchange API connection before saving account.
    Creates a temporary adapter, attempts get_balance(), and returns result.
    """
    from ..adapters.factory import create_adapter
    from ..core.trading_env import TradingEnvironment as TE

    try:
        env = TE(req.environment)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid environment: {req.environment}")

    is_virtual = env == TE.VIRTUAL

    try:
        adapter = create_adapter(
            exchange_name=req.exchange_name,
            app_key=req.access_key,
            secret_key=req.secret_key,
            account_no=req.account_number,
            account_name="connection_test",
            is_virtual=is_virtual,
        )

        if hasattr(adapter, 'initialize'):
            await adapter.initialize()

        balance = await adapter.get_balance()

        # Extract summary info
        cash_info = balance.get("cash", {})
        holdings_count = len(balance.get("holdings", {}))

        return {
            "success": True,
            "message": "API 연결 성공",
            "details": {
                "cash": cash_info,
                "holdings_count": holdings_count,
            }
        }
    except Exception as e:
        error_msg = str(e)
        # Provide user-friendly messages for common errors
        if "-2015" in error_msg or "Invalid API-key" in error_msg:
            friendly = "API 키가 유효하지 않거나 IP 접근이 제한되어 있습니다."
        elif "Unauthorized" in error_msg or "401" in error_msg:
            friendly = "인증 실패 - API 키를 확인해주세요."
        elif "timeout" in error_msg.lower() or "connect" in error_msg.lower():
            friendly = "서버 연결 실패 - 네트워크를 확인해주세요."
        else:
            friendly = f"연결 실패: {error_msg[:200]}"

        return {
            "success": False,
            "message": friendly,
            "details": {"error": error_msg[:500]}
        }


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
    ai_model: Optional[str] = None  # Current selected model


# Available AI models (Anthropic only - AI analysis uses Claude CLI)
AI_MODELS = [
    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "description": "Fast & affordable", "provider": "anthropic"},
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "description": "Balanced (recommended)", "provider": "anthropic"},
    {"id": "claude-opus-4-5-20251101", "name": "Claude Opus 4.5", "description": "Most capable", "provider": "anthropic"},
]
DEFAULT_AI_MODEL = "claude-sonnet-4-20250514"


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

    return AIKeyStatusResponse(
        has_ai_key=has_key,
        key_preview=key_preview,
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


@router.get("/ai-models")
def get_ai_models(
    current_user: User = Depends(get_current_user)
):
    """
    Get list of available AI models (Anthropic Claude only).
    """
    return {
        "models": AI_MODELS,
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
    if not model.startswith("claude-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid model. Model must start with 'claude-'"
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
