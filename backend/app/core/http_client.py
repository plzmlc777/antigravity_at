import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class HttpClientManager:
    _instance = None
    
    def __init__(self):
        if HttpClientManager._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            HttpClientManager._instance = self
            self.client: Optional[httpx.AsyncClient] = None

    @staticmethod
    def get_instance():
        if HttpClientManager._instance is None:
            HttpClientManager()
        return HttpClientManager._instance

    async def start(self):
        """
        Initialize the AsyncClient. Should be called on app startup.
        """
        if self.client is None or self.client.is_closed:
            # high timeout for financial API
            self.client = httpx.AsyncClient(timeout=30.0) 
            logger.info("Global HTTP Client started.")

    async def stop(self):
        """
        Close the AsyncClient. Should be called on app shutdown.
        """
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            logger.info("Global HTTP Client closed.")

    def get_client(self) -> httpx.AsyncClient:
        if self.client is None or self.client.is_closed:
            # Fallback for safety, though start() should be called explicitly
            logger.warning("Global HTTP Client accessed before start. Initializing...")
            self.client = httpx.AsyncClient(timeout=10.0)
            
        return self.client
