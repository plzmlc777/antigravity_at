import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class AccountCache:
    _instance = None
    
    def __init__(self):
        if AccountCache._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            AccountCache._instance = self
            self._cache: Dict[str, Any] = {} # Key: "user_id_active", Value: Adapter Config

    @staticmethod
    def get_instance():
        if AccountCache._instance is None:
            AccountCache()
        return AccountCache._instance

    def get_active_account_config(self, user_id: int) -> Optional[Dict[str, Any]]:
        return self._cache.get(f"active_{user_id}")

    def set_active_account_config(self, user_id: int, config: Dict[str, Any]):
        self._cache[f"active_{user_id}"] = config
        logger.info(f"Account cache set for user {user_id}")

    def invalidate(self, user_id: int):
        key = f"active_{user_id}"
        if key in self._cache:
            del self._cache[key]
            logger.info(f"Account cache invalidated for user {user_id}")
