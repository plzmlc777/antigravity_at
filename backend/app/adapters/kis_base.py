"""
KIS (Korean Investment Securities) Base Adapter
- Credential holding and token management
- KIS-specific auth headers (appkey/appsecret in every request)
- Hashkey generation for POST (order) requests
"""

import logging
from typing import Optional, Dict

from ..core.kis_token_manager import KISTokenManager

logger = logging.getLogger(__name__)


class KISBaseAdapter:
    """
    Base class for KIS REST and WebSocket adapters.
    Centralizes credential holding and KIS-specific auth logic.
    """

    def __init__(self, app_key: str = None, app_secret: str = None,
                 cano: str = None, acnt_prdt_cd: str = "01"):
        self.app_key = app_key
        self.app_secret = app_secret
        self.cano = cano                    # Account number first 8 digits
        self.acnt_prdt_cd = acnt_prdt_cd    # Product code 2 digits (default "01")
        self.access_token: Optional[str] = None
        self.base_url: Optional[str] = None  # Set by subclass
        self._common_headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "custtype": "P",
        }

    async def _ensure_token(self):
        """Fetch/refresh access token using KISTokenManager."""
        mgr = KISTokenManager.get_instance()

        if mgr.is_token_valid(self.base_url, self.app_key):
            self.access_token = mgr.get_cached_token(self.base_url, self.app_key)
            return

        if not self.app_key or not self.app_secret:
            logger.error("KIS: App Key or App Secret missing. Cannot ensure token.")
            return

        self.access_token = await mgr.get_token(
            self.app_key, self.app_secret, self.base_url
        )

        if not self.access_token:
            logger.error(f"KIS: Failed to acquire token for {self.base_url}")

    def _get_auth_headers(self, tr_id: str) -> Dict[str, str]:
        """
        KIS auth headers: appkey + appsecret in EVERY request.
        Different from Kiwoom which uses api-id.
        """
        if not self.access_token:
            return {}

        return {
            **self._common_headers,
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    async def _get_hashkey(self, body: dict) -> Optional[str]:
        """
        Generate hashkey for POST requests (orders).
        KIS requires this for tamper prevention on order APIs.
        POST /uapi/hashkey with the order body.
        """
        from ..core.http_client import HttpClientManager

        url = f"{self.base_url}/uapi/hashkey"
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, headers=headers, json=body, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("HASH")
        except Exception as e:
            logger.error(f"KIS: Failed to get hashkey: {e}")
            return None

    def check_token_validity(self) -> bool:
        """Check if current token is valid without attempting a refresh."""
        return KISTokenManager.get_instance().is_token_valid(self.base_url, self.app_key)
