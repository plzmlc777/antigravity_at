import logging
from typing import Optional, Dict
from ..core.token_manager import KiwoomTokenManager

logger = logging.getLogger(__name__)

class KiwoomBaseAdapter:
    """
    Base class for Kiwoom REST and WebSocket adapters.
    Centralizes credential holding and token management.
    """
    def __init__(self, app_key: str = None, secret_key: str = None):
        self.app_key = app_key
        self.secret_key = secret_key
        self.access_token: Optional[str] = None
        self._common_headers = {
            "Content-Type": "application/json;charset=UTF-8"
        }
        
    async def _ensure_token(self):
        """
        Fetch Access Token using TokenManager (Singleton).
        This method will trigger a renewal if the token is expired.
        """
        mgr = KiwoomTokenManager.get_instance()
        
        # If we already have a valid token in the manager, use it even if keys are missing from this instance.
        if mgr.is_token_valid():
            self.access_token = mgr.access_token
            return

        if not self.app_key or not self.secret_key:
            logger.error("App Key or Secret Key missing. Cannot ensure token.")
            return

        self.access_token = await mgr.get_token(
            self.app_key, self.secret_key
        )
        
        if not self.access_token:
             logger.error("Failed to acquire token from TokenManager")

    def _get_auth_headers(self, tr_id: str) -> Dict[str, str]:
        """
        Standard helper to generate headers with Authorization and api-id.
        """
        if not self.access_token:
            return {}
            
        return {
            **self._common_headers,
            "Authorization": f"Bearer {self.access_token}",
            "api-id": tr_id
        }
        
    def check_token_validity(self) -> bool:
        """
        Check if current token is valid without attempting a refresh.
        """
        return KiwoomTokenManager.get_instance().is_token_valid()
