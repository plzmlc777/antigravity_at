"""
KIS (Korean Investment Securities) Token Manager
- Singleton pattern (parallel to KiwoomTokenManager)
- OAuth2 access token: POST /oauth2/tokenP
- WebSocket approval key: POST /oauth2/Approval
- Aggressive disk caching (KIS allows ~1 token issuance per day)
"""

import logging
import json
import os
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class KISTokenManager:
    _instance = None
    CACHE_FILE = "kis_token_cache.json"

    def __init__(self):
        if KISTokenManager._instance is not None:
            raise Exception("KISTokenManager is a singleton!")
        KISTokenManager._instance = self
        self._tokens: Dict[str, Dict[str, Any]] = {}
        self._approval_keys: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    @staticmethod
    def get_instance():
        if KISTokenManager._instance is None:
            KISTokenManager()
        return KISTokenManager._instance

    def _get_cache_key(self, base_url: str, app_key: str = None) -> str:
        if app_key:
            return f"{base_url}:{app_key[:8]}"
        return base_url

    # ── Token Cache (Disk) ──

    def _load_cache(self):
        try:
            if os.path.exists(self.CACHE_FILE):
                with open(self.CACHE_FILE, "r") as f:
                    data = json.load(f)

                for url, info in data.get("tokens", {}).items():
                    expiry_str = info.get("expiry")
                    expiry = datetime.fromisoformat(expiry_str) if expiry_str else None
                    if expiry and datetime.now() < expiry:
                        self._tokens[url] = {"token": info["token"], "expiry": expiry}
                        logger.info(f"KIS: Loaded valid token for {url}")

                for url, info in data.get("approval_keys", {}).items():
                    expiry_str = info.get("expiry")
                    expiry = datetime.fromisoformat(expiry_str) if expiry_str else None
                    if expiry and datetime.now() < expiry:
                        self._approval_keys[url] = {"key": info["key"], "expiry": expiry}
        except Exception as e:
            logger.error(f"KIS: Failed to load token cache: {e}")

    def _save_cache(self):
        try:
            tokens_data = {}
            for url, info in self._tokens.items():
                tokens_data[url] = {
                    "token": info["token"],
                    "expiry": info["expiry"].isoformat() if info.get("expiry") else None,
                }
            approval_data = {}
            for url, info in self._approval_keys.items():
                approval_data[url] = {
                    "key": info["key"],
                    "expiry": info["expiry"].isoformat() if info.get("expiry") else None,
                }
            with open(self.CACHE_FILE, "w") as f:
                json.dump({"tokens": tokens_data, "approval_keys": approval_data}, f)
            logger.info("KIS: Token cache saved to disk.")
        except Exception as e:
            logger.error(f"KIS: Failed to save token cache: {e}")

    # ── Token Validity ──

    def is_token_valid(self, base_url: str = None, app_key: str = None) -> bool:
        cache_key = self._get_cache_key(base_url or "", app_key)
        info = self._tokens.get(cache_key)
        if not info:
            return False
        return bool(info.get("token") and info.get("expiry") and datetime.now() < info["expiry"])

    def get_cached_token(self, base_url: str = None, app_key: str = None) -> Optional[str]:
        cache_key = self._get_cache_key(base_url or "", app_key)
        info = self._tokens.get(cache_key)
        if info and self.is_token_valid(base_url, app_key):
            return info["token"]
        return None

    def get_remaining_seconds(self, base_url: str = None, app_key: str = None) -> int:
        cache_key = self._get_cache_key(base_url or "", app_key)
        info = self._tokens.get(cache_key)
        if not info or not info.get("expiry"):
            return 0
        remaining = (info["expiry"] - datetime.now()).total_seconds()
        return max(0, int(remaining))

    # ── Access Token ──

    async def get_token(self, app_key: str, app_secret: str, base_url: str) -> Optional[str]:
        cache_key = self._get_cache_key(base_url, app_key)

        if self.is_token_valid(base_url, app_key):
            return self._tokens[cache_key]["token"]

        logger.info(f"KIS: Fetching new access token for {cache_key}...")
        return await self._fetch_new_token(app_key, app_secret, base_url)

    async def _fetch_new_token(self, app_key: str, app_secret: str, base_url: str) -> Optional[str]:
        from .http_client import HttpClientManager

        url = f"{base_url}/oauth2/tokenP"
        cache_key = self._get_cache_key(base_url, app_key)

        payload = {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        }

        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()

            if "error_code" in data:
                logger.error(f"KIS token error: {data.get('error_description', data)}")
                return None

            token = data.get("access_token")
            if not token:
                logger.error(f"KIS: access_token missing in response: {data}")
                return None

            expires_in = int(data.get("expires_in", 86400))
            expiry = datetime.now() + timedelta(seconds=expires_in - 120)

            self._tokens[cache_key] = {"token": token, "expiry": expiry}
            self._save_cache()

            logger.info(f"KIS: Access token acquired for {cache_key}. Expires in {expires_in}s.")
            return token

        except Exception as e:
            logger.error(f"KIS: Failed to get token from {base_url}: {e}")
            return None

    # ── WebSocket Approval Key ──

    async def get_approval_key(self, app_key: str, app_secret: str, base_url: str) -> Optional[str]:
        cache_key = self._get_cache_key(base_url, app_key) + ":ws"
        info = self._approval_keys.get(cache_key)
        if info and info.get("key") and info.get("expiry") and datetime.now() < info["expiry"]:
            return info["key"]

        logger.info(f"KIS: Fetching new approval key for WebSocket...")
        return await self._fetch_approval_key(app_key, app_secret, base_url)

    async def _fetch_approval_key(self, app_key: str, app_secret: str, base_url: str) -> Optional[str]:
        from .http_client import HttpClientManager

        url = f"{base_url}/oauth2/Approval"
        cache_key = self._get_cache_key(base_url, app_key) + ":ws"

        payload = {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "secretkey": app_secret,
        }

        client = HttpClientManager.get_instance().get_client()
        try:
            response = await client.post(url, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()

            approval_key = data.get("approval_key")
            if not approval_key:
                logger.error(f"KIS: approval_key missing: {data}")
                return None

            # Approval key valid for ~24h
            expiry = datetime.now() + timedelta(hours=23)
            self._approval_keys[cache_key] = {"key": approval_key, "expiry": expiry}
            self._save_cache()

            logger.info(f"KIS: Approval key acquired for WebSocket.")
            return approval_key

        except Exception as e:
            logger.error(f"KIS: Failed to get approval key: {e}")
            return None

    def clear_all(self):
        self._tokens.clear()
        self._approval_keys.clear()
        self._save_cache()
        logger.info("KIS TokenManager: All tokens cleared")
