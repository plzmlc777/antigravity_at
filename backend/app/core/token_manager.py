import logging
import httpx
from typing import Optional
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
             self.access_token: Optional[str] = None
             self.token_expiry: Optional[datetime] = None
             
             # Force Real API for Data/Token regardless of mode (Unless user explicitly overrides differently)
             # Defaulting to openapi.kiwoom.com because Mock API lacks historical data.
             # If settings url is mockapi, we override it back to real for this manager.
             if "mockapi" in settings.HCP_KIWOOM_API_URL:
                 self.base_url = "https://openapi.kiwoom.com"
                 logger.info("Forcing Standard Open API URL for Token Manager in Mock Mode.")
             else:
                 self.base_url = settings.HCP_KIWOOM_API_URL or "https://openapi.kiwoom.com"

             # Load from disk
             self._load_cache()

    def _load_cache(self):
        try:
            import json
            import os
            if os.path.exists("token_cache.json"):
                with open("token_cache.json", "r") as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    expiry_str = data.get("token_expiry")
                    if expiry_str:
                        self.token_expiry = datetime.fromisoformat(expiry_str)
                        
                    # Check if expired
                    if self.token_expiry and datetime.now() > self.token_expiry:
                        logger.info("Cached token expired.")
                        self.access_token = None
                    elif self.access_token:
                        logger.info("Loaded valid Access Token from disk cache.")
        except Exception as e:
            logger.error(f"Failed to load token cache: {e}")

    def _save_cache(self):
        try:
            import json
            data = {
                "access_token": self.access_token,
                "token_expiry": self.token_expiry.isoformat() if self.token_expiry else None
            }
            with open("token_cache.json", "w") as f:
                json.dump(data, f)
            logger.info("Access Token saved to disk cache.")
        except Exception as e:
            logger.error(f"Failed to save token cache: {e}")

             
    @staticmethod
    def get_instance():
        if KiwoomTokenManager._instance is None:
            KiwoomTokenManager()
        return KiwoomTokenManager._instance

    def is_token_valid(self) -> bool:
        """
        Only checks if the current token is physically present and not expired.
        Does NOT trigger a network request for a new one.
        """
        if not self.access_token or not self.token_expiry:
            return False
            
        return datetime.now() < self.token_expiry

    def get_remaining_seconds(self) -> int:
        """
        Returns the number of seconds remaining until the token expires.
        Returns 0 if no token exists or if it has already expired.
        """
        if not self.access_token or not self.token_expiry:
            return 0
        
        remaining = (self.token_expiry - datetime.now()).total_seconds()
        return max(0, int(remaining))
        
    async def get_token(self, app_key: str, secret_key: str) -> Optional[str]:
        """
        Returns a valid access token.
        If existing token is valid, return it.
        Otherwise, fetch a new one.
        """
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token
            
        logger.info("Fetching new Kiwoom Access Token...")
        return await self._fetch_new_token(app_key, secret_key)
        
    async def _fetch_new_token(self, app_key: str, secret_key: str) -> Optional[str]:
        # Import inside method to avoid circular import if needed, 
        # or use the one imported at top if safe.
        # Assuming http_client.py is in same package or accessible.
        from .http_client import HttpClientManager
        
        # Determine Path based on URL (Standard vs HCP)
        # Reverting to oauth2/token as openapi.kiwoom.com/oauth2.0 failed.
        # api.kiwoom.com accepts oauth2/token.
        url = f"{self.base_url}/oauth2/token"
            
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "api-id": "au10001"
        }
        
        payload = {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "secretkey": secret_key
        }
        
        # Use Shared Client
        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            self.access_token = data.get("token")
            if not self.access_token:
                 logger.error(f"Token missing in response: {data}")
                 return None

            expires_in = int(data.get("expires_in", 86400)) # Default 24h
            
            # Set expiry with a buffer (e.g. 60 seconds earlier)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in - 60)
            
            # Save to disk
            self._save_cache()
            
            logger.info(f"Kiwoom Access Token acquired successfully. Expires in {expires_in} seconds.")
            return self.access_token
            
        except Exception as e:
            logger.error(f"Failed to get Kiwoom Token: {e}")
            return None
