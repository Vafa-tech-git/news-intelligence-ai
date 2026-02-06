"""
Rate Limiter Module
Token bucket algorithm for managing API rate limits across multiple sources.
"""

import time
import threading
from collections import defaultdict

class RateLimiter:
    """Thread-safe rate limiter using token bucket algorithm."""

    def __init__(self, limits=None):
        """
        Initialize rate limiter with source-specific limits.

        Args:
            limits: Dict of {source: {'requests': int, 'period': int}}
        """
        self.limits = limits or {}
        self.tokens = {}
        self.lock = threading.Lock()
        # Initialize tokens for all configured sources with full capacity
        for source, config in self.limits.items():
            self.tokens[source] = {'count': config['requests'], 'last_reset': time.time()}

    def configure(self, source, requests, period):
        """Configure rate limit for a source."""
        self.limits[source] = {'requests': requests, 'period': period}
        with self.lock:
            self.tokens[source] = {'count': requests, 'last_reset': time.time()}

    def _refill_tokens(self, source):
        """Refill tokens based on elapsed time."""
        if source not in self.limits:
            return

        limit = self.limits[source]

        # Initialize tokens if not yet created
        if source not in self.tokens:
            self.tokens[source] = {'count': limit['requests'], 'last_reset': time.time()}
            return

        token_info = self.tokens[source]

        elapsed = time.time() - token_info['last_reset']
        if elapsed >= limit['period']:
            # Full reset
            token_info['count'] = limit['requests']
            token_info['last_reset'] = time.time()
        else:
            # Partial refill (proportional)
            refill_rate = limit['requests'] / limit['period']
            new_tokens = int(elapsed * refill_rate)
            if new_tokens > 0:
                token_info['count'] = min(
                    token_info['count'] + new_tokens,
                    limit['requests']
                )
                token_info['last_reset'] = time.time()

    def can_request(self, source):
        """Check if a request can be made without consuming a token."""
        if source not in self.limits:
            return True  # No limit configured

        with self.lock:
            self._refill_tokens(source)
            return self.tokens[source]['count'] > 0

    def acquire(self, source, blocking=True, timeout=None):
        """
        Acquire a token for making a request.

        Args:
            source: The API source name
            blocking: If True, wait for token to become available
            timeout: Maximum time to wait (seconds)

        Returns:
            True if token acquired, False otherwise
        """
        if source not in self.limits:
            return True  # No limit configured

        start_time = time.time()

        while True:
            with self.lock:
                self._refill_tokens(source)
                if self.tokens[source]['count'] > 0:
                    self.tokens[source]['count'] -= 1
                    return True

            if not blocking:
                return False

            if timeout and (time.time() - start_time) >= timeout:
                return False

            # Wait a bit before retrying
            time.sleep(0.1)

    def get_wait_time(self, source):
        """Get estimated wait time until a token is available."""
        if source not in self.limits:
            return 0

        with self.lock:
            self._refill_tokens(source)
            if self.tokens[source]['count'] > 0:
                return 0

            limit = self.limits[source]
            refill_rate = limit['requests'] / limit['period']
            if refill_rate > 0:
                return 1 / refill_rate
            return limit['period']

    def get_remaining(self, source):
        """Get remaining tokens for a source."""
        if source not in self.limits:
            return float('inf')

        with self.lock:
            self._refill_tokens(source)
            return self.tokens[source]['count']

    def get_status(self):
        """Get status of all rate limiters."""
        status = {}
        with self.lock:
            for source in self.limits:
                self._refill_tokens(source)
                status[source] = {
                    'remaining': self.tokens[source]['count'],
                    'limit': self.limits[source]['requests'],
                    'period': self.limits[source]['period'],
                    'can_request': self.tokens[source]['count'] > 0
                }
        return status


# Global rate limiter instance
_rate_limiter = None

def get_rate_limiter():
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        from config import RATE_LIMITS
        _rate_limiter = RateLimiter(RATE_LIMITS)
    return _rate_limiter

def can_request(source):
    """Check if a request can be made to a source."""
    return get_rate_limiter().can_request(source)

def acquire(source, blocking=True, timeout=None):
    """Acquire a rate limit token for a source."""
    return get_rate_limiter().acquire(source, blocking, timeout)

def get_wait_time(source):
    """Get wait time until next request is allowed."""
    return get_rate_limiter().get_wait_time(source)

def get_remaining(source):
    """Get remaining requests for a source."""
    return get_rate_limiter().get_remaining(source)

def get_status():
    """Get status of all rate limiters."""
    return get_rate_limiter().get_status()
