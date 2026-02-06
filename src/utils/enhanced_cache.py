# Enhanced Redis Caching Layer
import redis
import json
import time
import hashlib
import pickle
import logging
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timedelta
from functools import wraps
import threading

from src.core.config import (
    RATELIMIT_STORAGE_URL, ENABLE_ENHANCED_CACHING,
    ARTICLE_PROCESSING_TIMEOUT, BATCH_SIZE
)

logger = logging.getLogger(__name__)

class AdvancedCacheManager:
    """Enhanced Redis cache manager with advanced features"""
    
    def __init__(self, redis_url: str = None, default_ttl: int = 3600):
        self.default_ttl = default_ttl
        self.redis_client = None
        self.fallback_cache = {}
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'errors': 0,
            'fallback_hits': 0
        }
        self.lock = threading.Lock()
        
        try:
            if redis_url and 'redis://' in redis_url:
                self.redis_client = redis.from_url(
                    redis_url,
                    decode_responses=False,  # Keep binary data
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                # Test connection
                self.redis_client.ping()
                logger.info(f"Connected to Redis at {redis_url}")
            else:
                logger.warning("Redis not configured, using in-memory fallback")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}, using memory fallback")
            self.redis_client = None
    
    def _get_fallback_key(self, prefix: str, identifier: str) -> str:
        """Generate fallback cache key"""
        return f"{prefix}:{identifier}"
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value for storage"""
        try:
            if isinstance(value, (str, int, float, bool, type(None))):
                return json.dumps(value).encode('utf-8')
            else:
                return pickle.dumps(value)
        except Exception as e:
            logger.error(f"Serialization error: {e}")
            return json.dumps(None).encode('utf-8')
    
    def _deserialize_value(self, value: bytes) -> Any:
        """Deserialize value from storage"""
        try:
            if value is None:
                return None
            
            # Try JSON first (faster)
            try:
                return json.loads(value.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Fallback to pickle
                return pickle.loads(value)
        except Exception as e:
            logger.error(f"Deserialization error: {e}")
            return None
    
    def get(self, prefix: str, identifier: str) -> Optional[Any]:
        """Get value from cache"""
        key = f"{prefix}:{identifier}"
        
        try:
            if self.redis_client:
                value = self.redis_client.get(key)
                if value is not None:
                    with self.lock:
                        self.cache_stats['hits'] += 1
                    return self._deserialize_value(value)
                else:
                    with self.lock:
                        self.cache_stats['misses'] += 1
                    return None
            else:
                # Fallback to memory
                fallback_key = self._get_fallback_key(prefix, identifier)
                if fallback_key in self.fallback_cache:
                    cache_item = self.fallback_cache[fallback_key]
                    if time.time() < cache_item['expires']:
                        with self.lock:
                            self.cache_stats['fallback_hits'] += 1
                        return cache_item['value']
                    else:
                        # Expired, remove it
                        del self.fallback_cache[fallback_key]
                        with self.lock:
                            self.cache_stats['misses'] += 1
                        return None
                else:
                    with self.lock:
                        self.cache_stats['misses'] += 1
                    return None
                    
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            with self.lock:
                self.cache_stats['errors'] += 1
            return None
    
    def set(self, prefix: str, identifier: str, value: Any, ttl: int = None) -> bool:
        """Set value in cache"""
        key = f"{prefix}:{identifier}"
        ttl = ttl or self.default_ttl
        
        try:
            serialized_value = self._serialize_value(value)
            
            if self.redis_client:
                result = self.redis_client.setex(key, ttl, serialized_value)
                if result:
                    with self.lock:
                        self.cache_stats['sets'] += 1
                return bool(result)
            else:
                # Fallback to memory with TTL
                fallback_key = self._get_fallback_key(prefix, identifier)
                self.fallback_cache[fallback_key] = {
                    'value': value,
                    'expires': time.time() + ttl
                }
                
                # Cleanup old entries periodically
                if len(self.fallback_cache) > 1000:  # Limit memory usage
                    current_time = time.time()
                    expired_keys = [
                        k for k, v in self.fallback_cache.items()
                        if current_time >= v['expires']
                    ]
                    for expired_key in expired_keys:
                        del self.fallback_cache[expired_key]
                
                with self.lock:
                    self.cache_stats['sets'] += 1
                return True
                
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            with self.lock:
                self.cache_stats['errors'] += 1
            return False
    
    def delete(self, prefix: str, identifier: str) -> bool:
        """Delete value from cache"""
        key = f"{prefix}:{identifier}"
        
        try:
            if self.redis_client:
                result = self.redis_client.delete(key)
                if result:
                    with self.lock:
                        self.cache_stats['deletes'] += 1
                return bool(result)
            else:
                fallback_key = self._get_fallback_key(prefix, identifier)
                if fallback_key in self.fallback_cache:
                    del self.fallback_cache[fallback_key]
                    with self.lock:
                        self.cache_stats['deletes'] += 1
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            with self.lock:
                self.cache_stats['errors'] += 1
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern"""
        try:
            if self.redis_client:
                keys = self.redis_client.keys(f"*{pattern}*")
                if keys:
                    deleted = self.redis_client.delete(*keys)
                    with self.lock:
                        self.cache_stats['deletes'] += deleted
                    return deleted
                return 0
            else:
                # Fallback: filter memory cache
                pattern_lower = pattern.lower()
                keys_to_delete = [
                    k for k in self.fallback_cache.keys()
                    if pattern_lower in k.lower()
                ]
                for key in keys_to_delete:
                    del self.fallback_cache[key]
                with self.lock:
                    self.cache_stats['deletes'] += len(keys_to_delete)
                return len(keys_to_delete)
                
        except Exception as e:
            logger.error(f"Cache clear pattern error: {e}")
            with self.lock:
                self.cache_stats['errors'] += 1
            return 0
    
    def get_with_fallback(self, prefix: str, identifier: str, fallback_func, 
                         ttl: int = None, *args, **kwargs) -> Any:
        """Get from cache with fallback function"""
        result = self.get(prefix, identifier)
        if result is not None:
            return result
        
        # Cache miss, call fallback function
        try:
            result = fallback_func(*args, **kwargs)
            if result is not None:
                self.set(prefix, identifier, result, ttl)
            return result
        except Exception as e:
            logger.error(f"Fallback function error: {e}")
            return None
    
    def invalidate_pattern_with_delay(self, pattern: str, delay_seconds: int = 0):
        """Invalidate cache pattern with optional delay"""
        if delay_seconds > 0:
            def delayed_invalidate():
                time.sleep(delay_seconds)
                self.clear_pattern(pattern)
            
            thread = threading.Thread(target=delayed_invalidate)
            thread.daemon = True
            thread.start()
        else:
            self.clear_pattern(pattern)
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        with self.lock:
            stats = self.cache_stats.copy()
            total_requests = stats['hits'] + stats['misses']
            stats['hit_rate'] = (stats['hits'] / total_requests) if total_requests > 0 else 0
            stats['total_requests'] = total_requests
            return stats
    
    def reset_stats(self):
        """Reset cache statistics"""
        with self.lock:
            self.cache_stats = {
                'hits': 0,
                'misses': 0,
                'sets': 0,
                'deletes': 0,
                'errors': 0,
                'fallback_hits': 0
            }
    
    def health_check(self) -> Dict:
        """Perform health check on cache system"""
        health_info = {
            'redis_connected': False,
            'memory_cache_size': len(self.fallback_cache),
            'stats': self.get_stats(),
            'status': 'healthy'
        }
        
        if self.redis_client:
            try:
                self.redis_client.ping()
                health_info['redis_connected'] = True
            except Exception as e:
                logger.error(f"Redis health check failed: {e}")
                health_info['status'] = 'degraded'
        
        return health_info

# Global cache manager instance
_cache_manager = None

def get_cache_manager() -> AdvancedCacheManager:
    """Get or create global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        redis_url = RATELIMIT_STORAGE_URL if 'redis://' in RATELIMIT_STORAGE_URL else None
        _cache_manager = AdvancedCacheManager(redis_url)
    return _cache_manager

def cached(prefix: str, ttl: int = None, key_generator=None):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not ENABLE_ENHANCED_CACHING:
                return func(*args, **kwargs)
            
            cache_manager = get_cache_manager()
            
            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                # Default key generation
                key_parts = [str(arg) for arg in args]
                key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
                key_string = ":".join(key_parts)
                cache_key = hashlib.md5(key_string.encode()).hexdigest()
            
            # Try to get from cache
            result = cache_manager.get(prefix, cache_key)
            if result is not None:
                return result
            
            # Cache miss, call function
            try:
                result = func(*args, **kwargs)
                if result is not None:
                    cache_manager.set(prefix, cache_key, result, ttl)
                return result
            except Exception as e:
                logger.error(f"Cacheable function error: {e}")
                raise
        
        return wrapper
    return decorator

# Specialized cache functions
def cache_ai_analysis(content: str, analysis_result: Dict, ttl: int = 86400):
    """Cache AI analysis result"""
    cache_manager = get_cache_manager()
    content_hash = hashlib.md5(content.encode()).hexdigest()
    return cache_manager.set('ai_analysis', content_hash, analysis_result, ttl)

def get_cached_ai_analysis(content: str) -> Optional[Dict]:
    """Get cached AI analysis result"""
    cache_manager = get_cache_manager()
    content_hash = hashlib.md5(content.encode()).hexdigest()
    return cache_manager.get('ai_analysis', content_hash)

def cache_rss_feed(feed_url: str, feed_data: List[Dict], ttl: int = 300):
    """Cache RSS feed data"""
    cache_manager = get_cache_manager()
    url_hash = hashlib.md5(feed_url.encode()).hexdigest()
    return cache_manager.set('rss_feed', url_hash, feed_data, ttl)

def get_cached_rss_feed(feed_url: str) -> Optional[List[Dict]]:
    """Get cached RSS feed data"""
    cache_manager = get_cache_manager()
    url_hash = hashlib.md5(feed_url.encode()).hexdigest()
    return cache_manager.get('rss_feed', url_hash)

def cache_article_content(url: str, content: str, ttl: int = 3600):
    """Cache article content"""
    cache_manager = get_cache_manager()
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return cache_manager.set('article_content', url_hash, content, ttl)

def get_cached_article_content(url: str) -> Optional[str]:
    """Get cached article content"""
    cache_manager = get_cache_manager()
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return cache_manager.get('article_content', url_hash)

def cache_market_data(symbols: List[str], market_data: Dict, ttl: int = 300):
    """Cache market data"""
    cache_manager = get_cache_manager()
    symbols_key = ",".join(sorted(symbols))
    symbols_hash = hashlib.md5(symbols_key.encode()).hexdigest()
    return cache_manager.set('market_data', symbols_hash, market_data, ttl)

def get_cached_market_data(symbols: List[str]) -> Optional[Dict]:
    """Get cached market data"""
    cache_manager = get_cache_manager()
    symbols_key = ",".join(sorted(symbols))
    symbols_hash = hashlib.md5(symbols_key.encode()).hexdigest()
    return cache_manager.get('market_data', symbols_hash)

# Cache warming functions
def warm_popular_cache():
    """Warm cache with popular data"""
    logger.info("Starting cache warming")
    cache_manager = get_cache_manager()
    
    # This could pre-load popular RSS feeds, market data, etc.
    # Implementation depends on application usage patterns
    
    logger.info("Cache warming completed")

def cleanup_expired_cache():
    """Clean up expired cache entries"""
    cache_manager = get_cache_manager()
    stats_before = cache_manager.get_stats()
    
    # Clear old RSS feeds
    cleared_feeds = cache_manager.clear_pattern('rss_feed')
    
    # Clear old market data
    cleared_market = cache_manager.clear_pattern('market_data')
    
    stats_after = cache_manager.get_stats()
    
    logger.info(f"Cache cleanup completed: {cleared_feeds} feeds, {cleared_market} market data entries cleared")
    logger.info(f"Cache stats: {stats_after}")

# Periodic maintenance
def schedule_cache_maintenance():
    """Schedule periodic cache maintenance"""
    import threading
    import time
    
    def maintenance_loop():
        while True:
            try:
                # Run cleanup every hour
                time.sleep(3600)
                cleanup_expired_cache()
            except Exception as e:
                logger.error(f"Cache maintenance error: {e}")
    
    maintenance_thread = threading.Thread(target=maintenance_loop)
    maintenance_thread.daemon = True
    maintenance_thread.start()
    
    logger.info("Cache maintenance scheduled")