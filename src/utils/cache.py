import redis
import json
import hashlib
import logging
from datetime import timedelta
from functools import wraps
from src.core.config import RATELIMIT_STORAGE_URL

# Configure logging for cache manager
logger = logging.getLogger(__name__)

class CacheManager:
    """Redis-based caching system for News AI Intelligence"""
    
    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.redis_client.ping()
            self.enabled = True
            logger.info("Redis cache manager initialized successfully")
        except Exception as e:
            self.enabled = False
            self.redis_client = None
            logger.warning(f"Redis cache unavailable, using fallback: {e}")
    
    def _get_cache_key(self, prefix, identifier):
        """Generate cache key with prefix and identifier"""
        if isinstance(identifier, (dict, list)):
            # Hash complex objects for consistent keys
            identifier = hashlib.md5(json.dumps(identifier, sort_keys=True).encode()).hexdigest()
        return f"news_ai:{prefix}:{identifier}"
    
    def get(self, prefix, identifier):
        """Get cached data"""
        if not self.enabled:
            return None
            
        try:
            key = self._get_cache_key(prefix, identifier)
            cached_data = self.redis_client.get(key)
            
            if cached_data:
                try:
                    return json.loads(cached_data)
                except json.JSONDecodeError:
                    return cached_data
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def set(self, prefix, identifier, data, ttl_seconds=3600):
        """Set cache data with TTL"""
        if not self.enabled:
            return False
            
        try:
            key = self._get_cache_key(prefix, identifier)
            
            if isinstance(data, (dict, list)):
                serialized_data = json.dumps(data)
            else:
                serialized_data = str(data)
            
            return self.redis_client.setex(key, ttl_seconds, serialized_data)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def delete(self, prefix, identifier):
        """Delete cached data"""
        if not self.enabled:
            return False
            
        try:
            key = self._get_cache_key(prefix, identifier)
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    def clear_pattern(self, pattern):
        """Clear cache by pattern"""
        if not self.enabled:
            return False
            
        try:
            keys = self.redis_client.keys(f"news_ai:{pattern}:*")
            if keys:
                return bool(self.redis_client.delete(*keys))
            return True
        except Exception as e:
            logger.error(f"Cache clear pattern error: {e}")
            return False
    
    def get_stats(self):
        """Get cache statistics"""
        if not self.enabled:
            return {"enabled": False}
            
        try:
            info = self.redis_client.info()
            return {
                "enabled": True,
                "used_memory_mb": info.get('used_memory', 0) / (1024 * 1024),
                "connected_clients": info.get('connected_clients', 0),
                "total_commands_processed": info.get('total_commands_processed', 0),
                "keyspace_hits": info.get('keyspace_hits', 0),
                "keyspace_misses": info.get('keyspace_misses', 0),
                "hit_rate": (
                    info.get('keyspace_hits', 0) / 
                    max(1, info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0))
                ) * 100
            }
        except Exception as e:
            logger.error(f"Cache stats error: {e}")
            return {"enabled": False, "error": str(e)}

# Global cache instance
cache_manager = CacheManager()

# Decorators for easy caching
def cached(prefix, ttl=3600):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_identifier = f"{func.__name__}:{hashlib.md5(str(args + tuple(sorted(kwargs.items()))).encode()).hexdigest()}"
            
            # Try to get from cache
            cached_result = cache_manager.get(prefix, cache_identifier)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(prefix, cache_identifier, result, ttl)
            logger.debug(f"Cache set for {func.__name__}")
            
            return result
        return wrapper
    return decorator

# Specific cache functions for News AI
def cache_ai_analysis(text_hash, analysis_result, ttl_hours=24):
    """Cache AI analysis results"""
    ttl_seconds = ttl_hours * 3600
    return cache_manager.set('ai_analysis', text_hash, analysis_result, ttl_seconds)

def get_cached_ai_analysis(text_hash):
    """Get cached AI analysis"""
    return cache_manager.get('ai_analysis', text_hash)

def cache_web_content(url, content, ttl_hours=6):
    """Cache web scraped content"""
    ttl_seconds = ttl_hours * 3600
    return cache_manager.set('web_content', url, content, ttl_seconds)

def get_cached_web_content(url):
    """Get cached web content"""
    return cache_manager.get('web_content', url)

def cache_rss_feed(source, feed_data, ttl_minutes=30):
    """Cache RSS feed data"""
    ttl_seconds = ttl_minutes * 60
    return cache_manager.set('rss_feed', source, feed_data, ttl_seconds)

def get_cached_rss_feed(source):
    """Get cached RSS feed"""
    return cache_manager.get('rss_feed', source)

def cache_finnhub_news(news_data, ttl_minutes=15):
    """Cache Finnhub news data"""
    ttl_seconds = ttl_minutes * 60
    return cache_manager.set('finnhub_news', 'latest', news_data, ttl_seconds)

def get_cached_finnhub_news():
    """Get cached Finnhub news"""
    return cache_manager.get('finnhub_news', 'latest')

def invalidate_news_cache():
    """Invalidate all news-related cache"""
    patterns = ['ai_analysis', 'web_content', 'rss_feed', 'finnhub_news']
    for pattern in patterns:
        cache_manager.clear_pattern(pattern)
    logger.info("News cache invalidated")

if __name__ == "__main__":
    # Test cache functionality
    logger.info("🧪 Testing cache functionality...")
    
    # Test basic operations
    cache_manager.set('test', 'key1', {'data': 'value1'}, 60)
    result = cache_manager.get('test', 'key1')
    logger.info(f"✅ Basic test: {result}")
    
    # Test cache stats
    stats = cache_manager.get_stats()
    logger.info(f"📊 Cache stats: {stats}")