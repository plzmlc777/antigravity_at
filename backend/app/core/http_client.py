import httpx
import logging
import asyncio
import time
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter to prevent excessive API requests.
    Kiwoom API typically allows ~5 requests/second.
    """
    def __init__(self, max_requests: int = 5, window_seconds: float = 1.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._lock = asyncio.Lock()
        self._total_requests = 0
        self._throttled_count = 0

    async def acquire(self):
        """Wait if necessary to stay within rate limits."""
        async with self._lock:
            now = time.monotonic()

            # Remove timestamps outside the window
            while self._timestamps and self._timestamps[0] < now - self.window_seconds:
                self._timestamps.popleft()

            # If at limit, wait until oldest request exits the window
            if len(self._timestamps) >= self.max_requests:
                wait_time = self._timestamps[0] + self.window_seconds - now
                if wait_time > 0:
                    self._throttled_count += 1
                    if self._throttled_count % 10 == 1:  # Log every 10th throttle
                        logger.warning(f"[RateLimiter] Throttled {self._throttled_count} times, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    # Re-check after waiting
                    now = time.monotonic()
                    while self._timestamps and self._timestamps[0] < now - self.window_seconds:
                        self._timestamps.popleft()

            self._timestamps.append(now)
            self._total_requests += 1

    def get_stats(self) -> dict:
        return {
            "total_requests": self._total_requests,
            "throttled_count": self._throttled_count,
            "current_window": len(self._timestamps)
        }


# Global rate limiter instance (5 requests per second)
_rate_limiter = RateLimiter(max_requests=5, window_seconds=1.0)


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter


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

    async def post_with_rate_limit(self, url: str, **kwargs) -> httpx.Response:
        """
        POST request with rate limiting.
        Use this for Kiwoom API calls to prevent excessive requests.
        """
        await _rate_limiter.acquire()
        return await self.get_client().post(url, **kwargs)

    async def get_with_rate_limit(self, url: str, **kwargs) -> httpx.Response:
        """
        GET request with rate limiting.
        """
        await _rate_limiter.acquire()
        return await self.get_client().get(url, **kwargs)
