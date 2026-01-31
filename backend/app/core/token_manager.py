import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from .config import settings

logger = logging.getLogger(__name__)

class KiwoomTokenManager:
    _instance = None

    def __init__(self):
        if KiwoomTokenManager._instance is not None:
             raise Exception("This class is a singleton!")
        else:
             KiwoomTokenManager._instance = self
             # Store tokens per API URL (supports both real and virtual servers)
             self._tokens: Dict[str, Dict[str, Any]] = {}  # {base_url: {"token": str, "expiry": datetime}}
             self.default_base_url = settings.HCP_KIWOOM_API_URL or "https://api.kiwoom.com"

             # Legacy single token support (for backward compatibility)
             self.access_token: Optional[str] = None
             self.token_expiry: Optional[datetime] = None

             # Load from disk
             self._load_cache()

    def _load_cache(self):
        try:
            import json
            import os
            if os.path.exists("token_cache.json"):
                with open("token_cache.json", "r") as f:
                    data = json.load(f)

                    # New format: multiple tokens
                    if "tokens" in data:
                        for url, token_data in data["tokens"].items():
                            expiry_str = token_data.get("expiry")
                            expiry = datetime.fromisoformat(expiry_str) if expiry_str else None
                            if expiry and datetime.now() < expiry:
                                self._tokens[url] = {
                                    "token": token_data.get("token"),
                                    "expiry": expiry
                                }
                                logger.info(f"Loaded valid token for {url}")
                            else:
                                logger.info(f"Cached token for {url} expired.")
                    else:
                        # Legacy format: single token
                        self.access_token = data.get("access_token")
                        expiry_str = data.get("token_expiry")
                        if expiry_str:
                            self.token_expiry = datetime.fromisoformat(expiry_str)

                        if self.token_expiry and datetime.now() > self.token_expiry:
                            logger.info("Cached token expired.")
                            self.access_token = None
                        elif self.access_token:
                            # Migrate to new format
                            self._tokens[self.default_base_url] = {
                                "token": self.access_token,
                                "expiry": self.token_expiry
                            }
                            logger.info("Loaded and migrated legacy token to new format.")
        except Exception as e:
            logger.error(f"Failed to load token cache: {e}")

    def _save_cache(self):
        try:
            import json
            # Save in new multi-token format
            tokens_data = {}
            for url, token_info in self._tokens.items():
                tokens_data[url] = {
                    "token": token_info.get("token"),
                    "expiry": token_info.get("expiry").isoformat() if token_info.get("expiry") else None
                }
            data = {"tokens": tokens_data}
            with open("token_cache.json", "w") as f:
                json.dump(data, f)
            logger.info("Access Tokens saved to disk cache.")
        except Exception as e:
            logger.error(f"Failed to save token cache: {e}")

    @staticmethod
    def get_instance():
        if KiwoomTokenManager._instance is None:
            KiwoomTokenManager()
        return KiwoomTokenManager._instance

    def is_token_valid(self, base_url: str = None) -> bool:
        """
        Check if token for the given base_url is valid.
        Falls back to default_base_url if not specified.
        """
        url = base_url or self.default_base_url
        token_info = self._tokens.get(url)
        if not token_info:
            return False
        token = token_info.get("token")
        expiry = token_info.get("expiry")
        if not token or not expiry:
            return False
        return datetime.now() < expiry

    def get_cached_token(self, base_url: str = None) -> Optional[str]:
        """
        Get cached token for the given base_url without fetching a new one.
        """
        url = base_url or self.default_base_url
        token_info = self._tokens.get(url)
        if token_info and self.is_token_valid(url):
            return token_info.get("token")
        return None

    def get_remaining_seconds(self, base_url: str = None) -> int:
        """
        Returns the number of seconds remaining until the token expires.
        """
        url = base_url or self.default_base_url
        token_info = self._tokens.get(url)
        if not token_info:
            return 0
        expiry = token_info.get("expiry")
        if not expiry:
            return 0
        remaining = (expiry - datetime.now()).total_seconds()
        return max(0, int(remaining))

    async def get_token(self, app_key: str, secret_key: str, base_url: str = None) -> Optional[str]:
        """
        Returns a valid access token for the given base_url.
        If existing token is valid, return it.
        Otherwise, fetch a new one.
        """
        url = base_url or self.default_base_url

        # Check if we have a valid cached token
        if self.is_token_valid(url):
            token = self._tokens[url].get("token")
            # Also update legacy fields for backward compatibility
            self.access_token = token
            self.token_expiry = self._tokens[url].get("expiry")
            return token

        logger.info(f"Fetching new Kiwoom Access Token for {url}...")
        return await self._fetch_new_token(app_key, secret_key, url)

    async def _fetch_new_token(self, app_key: str, secret_key: str, base_url: str) -> Optional[str]:
        from .http_client import HttpClientManager

        url = f"{base_url}/oauth2/token"

        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "api-id": "au10001"
        }

        payload = {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "secretkey": secret_key
        }

        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            token = data.get("token")
            if not token:
                 logger.error(f"Token missing in response: {data}")
                 return None

            expires_in = int(data.get("expires_in", 86400))  # Default 24h
            expiry = datetime.now() + timedelta(seconds=expires_in - 60)

            # Store in multi-token cache
            self._tokens[base_url] = {
                "token": token,
                "expiry": expiry
            }

            # Update legacy fields for backward compatibility
            self.access_token = token
            self.token_expiry = expiry

            # Save to disk
            self._save_cache()

            logger.info(f"Kiwoom Access Token acquired for {base_url}. Expires in {expires_in} seconds.")
            return token

        except Exception as e:
            logger.error(f"Failed to get Kiwoom Token from {base_url}: {e}")
            return None
