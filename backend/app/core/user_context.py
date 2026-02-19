"""
UserAccountContext - Unified User and Account Context Management

This module provides a centralized way to manage user authentication and
active account context across the application. It replaces scattered patterns
of querying ExchangeAccount and decrypting credentials.

Usage:
    from ..core.user_context import UserAccountContext, get_user_context

    @router.get("/some-endpoint")
    async def some_endpoint(ctx: UserAccountContext = Depends(get_user_context)):
        # Access user info
        user_id = ctx.user_id
        user_email = ctx.user.email

        # Access active account (None if no active account)
        if ctx.account:
            account_id = ctx.account_id
            account_name = ctx.account.account_name

        # Direct credential access (None-safe)
        app_key = ctx.app_key
        secret_key = ctx.secret_key
        account_no = ctx.account_no
        api_url = ctx.api_url

        # Token management (delegates to TokenManager)
        if ctx.is_token_valid():
            token = ctx.get_cached_token()
            remaining = ctx.get_token_remaining_seconds()
        else:
            token = await ctx.ensure_token()
"""

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.user import User
from ..models.account import ExchangeAccount

if TYPE_CHECKING:
    from ..core.exchange_interface import ExchangeInterface


@dataclass
class AccountCredentials:
    """Decrypted account credentials"""
    app_key: str
    secret_key: str
    account_no: Optional[str] = None
    account_name: Optional[str] = None
    environment: str = "real"


@dataclass
class UserAccountContext:
    """
    Unified context containing user and active account information.

    This is the single source of truth for user-account relationship
    throughout the request lifecycle.
    """
    user: User
    account: Optional[ExchangeAccount] = None
    _db: Session = field(repr=False, default=None)
    _credentials: Optional[AccountCredentials] = field(repr=False, default=None)
    _credentials_loaded: bool = field(repr=False, default=False)

    @property
    def user_id(self) -> int:
        """Get user ID"""
        return self.user.id

    @property
    def user_email(self) -> str:
        """Get user email"""
        return self.user.email

    @property
    def account_id(self) -> Optional[int]:
        """Get active account ID (None if no active account)"""
        return self.account.id if self.account else None

    @property
    def account_name(self) -> Optional[str]:
        """Get active account name"""
        return self.account.account_name if self.account else None

    @property
    def has_active_account(self) -> bool:
        """Check if user has an active account"""
        return self.account is not None

    @property
    def environment(self) -> str:
        """Get trading environment ('real', 'virtual', 'paper')"""
        if self.account:
            return self.account.environment or "real"
        return "real"

    @property
    def is_virtual(self) -> bool:
        """Check if active account is virtual trading"""
        return self.account.is_virtual if self.account else False

    @property
    def is_paper(self) -> bool:
        """Check if active account is paper trading"""
        return self.account.is_paper if self.account else False

    @property
    def is_simulation(self) -> bool:
        """Check if active account is any kind of simulation"""
        return self.account.is_simulation if self.account else False

    def get_credentials(self) -> Optional[AccountCredentials]:
        """
        Get decrypted account credentials (lazy loaded).
        Returns None if no active account.
        """
        if self._credentials_loaded:
            return self._credentials

        self._credentials_loaded = True

        if not self.account:
            return None

        try:
            from ..core import security

            decrypted_app = security.decrypt_key(self.account.encrypted_access_key)
            decrypted_secret = security.decrypt_key(self.account.encrypted_secret_key)

            self._credentials = AccountCredentials(
                app_key=decrypted_app,
                secret_key=decrypted_secret,
                account_no=self.account.account_number,
                account_name=self.account.account_name,
                environment=self.account.environment or "real"
            )
            return self._credentials
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error decrypting credentials: {e}")
            return None

    # ==========================================
    # Direct Credential Properties (None-safe)
    # ==========================================

    @property
    def app_key(self) -> Optional[str]:
        """Get decrypted app key (None if no account or decryption fails)"""
        creds = self.get_credentials()
        return creds.app_key if creds else None

    @property
    def secret_key(self) -> Optional[str]:
        """Get decrypted secret key (None if no account or decryption fails)"""
        creds = self.get_credentials()
        return creds.secret_key if creds else None

    @property
    def account_no(self) -> Optional[str]:
        """Get account number"""
        creds = self.get_credentials()
        return creds.account_no if creds else None

    @property
    def api_url(self) -> str:
        """Get API URL for current account (defaults to settings if no account)"""
        from .config import settings
        if self.account and self.account.api_url:
            return self.account.api_url
        return settings.HCP_KIWOOM_API_URL or "https://api.kiwoom.com"

    # ==========================================
    # Token Management (delegates to TokenManager)
    # ==========================================

    def _get_token_cache_key(self) -> Optional[tuple]:
        """Get cache key components (api_url, app_key) for token lookup"""
        if not self.app_key:
            return None
        return (self.api_url, self.app_key)

    def is_token_valid(self) -> bool:
        """Check if current account's token is valid"""
        from .token_manager import KiwoomTokenManager
        if not self.app_key:
            return False
        mgr = KiwoomTokenManager.get_instance()
        return mgr.is_token_valid(self.api_url, self.app_key)

    def get_token_remaining_seconds(self) -> int:
        """Get seconds until token expires (0 if no valid token)"""
        from .token_manager import KiwoomTokenManager
        if not self.app_key:
            return 0
        mgr = KiwoomTokenManager.get_instance()
        return mgr.get_remaining_seconds(self.api_url, self.app_key)

    def get_cached_token(self) -> Optional[str]:
        """Get cached token without fetching a new one"""
        from .token_manager import KiwoomTokenManager
        if not self.app_key:
            return None
        mgr = KiwoomTokenManager.get_instance()
        return mgr.get_cached_token(self.api_url, self.app_key)

    async def ensure_token(self) -> Optional[str]:
        """
        Ensure a valid token exists. Fetches new one if expired.
        Returns the token or None if credentials are missing.
        """
        from .token_manager import KiwoomTokenManager
        if not self.app_key or not self.secret_key:
            return None
        mgr = KiwoomTokenManager.get_instance()
        return await mgr.get_token(self.app_key, self.secret_key, self.api_url)

    def get_exchange_adapter(self) -> "ExchangeInterface":
        """
        Get exchange adapter for this user's active account.
        Uses cached credentials when available.
        """
        from ..adapters.factory import create_adapter
        from ..core.account_cache import AccountCache
        from ..core.trading_env import TradingEnvironment, get_api_url_for_exchange, env_from_string

        cache = AccountCache.get_instance()

        # Check cache first
        cached_config = cache.get_active_account_config(self.user_id)

        if cached_config:
            exchange_name = cached_config.get('exchange_name', 'Kiwoom')
            env = env_from_string(cached_config.get('environment', 'real'))
            api_url = get_api_url_for_exchange(exchange_name, env)
            is_virtual = env == TradingEnvironment.VIRTUAL

            return create_adapter(
                exchange_name=exchange_name,
                app_key=cached_config['app_key'],
                secret_key=cached_config['secret_key'],
                account_no=cached_config['account_no'],
                account_name=cached_config['account_name'],
                api_url=api_url,
                is_virtual=is_virtual,
            )

        # Use credentials from this context
        creds = self.get_credentials()

        if creds and self.account:
            exchange_name = self.account.exchange_name or "Kiwoom"
            # Cache the config for future use
            config = {
                'exchange_name': exchange_name,
                'app_key': creds.app_key,
                'secret_key': creds.secret_key,
                'account_no': creds.account_no,
                'account_name': creds.account_name,
                'environment': creds.environment,
            }
            cache.set_active_account_config(self.user_id, config)

            return create_adapter(
                exchange_name=exchange_name,
                app_key=creds.app_key,
                secret_key=creds.secret_key,
                account_no=creds.account_no,
                account_name=creds.account_name,
                api_url=self.account.api_url,
                is_virtual=self.account.is_virtual,
            )

        # Fallback to .env defaults
        from ..adapters.kiwoom_real import KiwoomRealAdapter
        return KiwoomRealAdapter()

    def require_account(self) -> ExchangeAccount:
        """
        Require an active account. Raises HTTPException if none exists.
        Use this in endpoints that require an active account.
        """
        if not self.account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="활성화된 계좌가 없습니다. 계좌를 먼저 설정해주세요."
            )
        return self.account

    def require_credentials(self) -> AccountCredentials:
        """
        Require decrypted credentials. Raises HTTPException if unavailable.
        """
        self.require_account()
        creds = self.get_credentials()
        if not creds:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="계좌 인증 정보를 복호화할 수 없습니다."
            )
        return creds


# ==========================================
# FastAPI Dependency Functions
# ==========================================

async def get_user_context(
    db: Session = Depends(get_db),
    token: str = Depends(None)  # Will be replaced by oauth2_scheme
) -> UserAccountContext:
    """
    Primary dependency for getting user and account context.

    Usage:
        @router.get("/endpoint")
        async def endpoint(ctx: UserAccountContext = Depends(get_user_context)):
            user_id = ctx.user_id
            account_id = ctx.account_id
    """
    from .auth_deps import get_current_user_from_token

    # Get current user (handles authentication)
    user = await get_current_user_from_token(token, db)

    # Get active account for this user
    active_account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == user.id,
        ExchangeAccount.is_active == True
    ).first()

    return UserAccountContext(
        user=user,
        account=active_account,
        _db=db
    )


def create_get_user_context_dependency():
    """
    Factory function to create the dependency with proper oauth2 setup.
    This allows the dependency to work with the existing auth system.
    """
    from ..api.auth import oauth2_scheme, get_current_user

    async def _get_user_context(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ) -> UserAccountContext:
        """Get user context using existing auth dependency"""
        active_account = db.query(ExchangeAccount).filter(
            ExchangeAccount.user_id == current_user.id,
            ExchangeAccount.is_active == True
        ).first()

        return UserAccountContext(
            user=current_user,
            account=active_account,
            _db=db
        )

    return _get_user_context


# Create the actual dependency using the factory
# This is what endpoints should import and use
get_user_context = create_get_user_context_dependency()


# ==========================================
# Helper Functions for Backward Compatibility
# ==========================================

def get_active_account_for_user(db: Session, user_id: int) -> Optional[ExchangeAccount]:
    """
    Helper to get active account for a user.
    Use UserAccountContext dependency when possible instead.
    """
    return db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == user_id,
        ExchangeAccount.is_active == True
    ).first()


def get_account_id_for_user(db: Session, user_id: int) -> Optional[int]:
    """
    Helper to get active account ID for a user.
    Use ctx.account_id when possible instead.
    """
    account = get_active_account_for_user(db, user_id)
    return account.id if account else None
