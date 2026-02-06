import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available - caching disabled")

from src.core.config import RATELIMIT_STORAGE_URL

logger = logging.getLogger(__name__)

def check_redis_connection():
    """Check if Redis is available and working"""
    if not REDIS_AVAILABLE:
        return False, "Redis not installed"
    
    try:
        # Extract Redis URL components
        import urllib.parse
        parsed = urllib.parse.urlparse(RATELIMIT_STORAGE_URL)
        
        # Connect to Redis
        r = redis.Redis(
            host=parsed.hostname or 'localhost',
            port=parsed.port or 6379,
            db=int(parsed.path.lstrip('/') or 0),
            socket_connect_timeout=5,
            socket_timeout=5
        )
        
        # Test connection
        r.ping()
        
        # Test basic operations
        test_key = "cache_test_key"
        r.set(test_key, "test_value", ex=10)
        retrieved = r.get(test_key)
        r.delete(test_key)
        
        if retrieved.decode() == "test_value":
            logger.info("Redis connection successful - caching is active")
            return True, "Redis working properly"
        else:
            return False, "Redis read/write test failed"
            
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return False, f"Redis error: {e}"

def get_cache_status():
    """Get comprehensive cache status"""
    status = {
        'redis_available': REDIS_AVAILABLE,
        'connection_status': 'unknown',
        'cache_type': 'redis' if REDIS_AVAILABLE else 'none',
        'recommendations': []
    }
    
    if REDIS_AVAILABLE:
        is_connected, message = check_redis_connection()
        status['connection_status'] = 'connected' if is_connected else 'disconnected'
        status['connection_message'] = message
        
        if not is_connected:
            status['recommendations'].extend([
                "Check if Redis server is running",
                "Verify Redis configuration in RATELIMIT_STORAGE_URL",
                "Install Redis: apt-get install redis-server"
            ])
    else:
        status['recommendations'].extend([
            "Install Redis for better performance: pip install redis",
            "Start Redis server: redis-server"
        ])
    
    return status

def enable_fallback_caching():
    """Enable in-memory fallback caching when Redis is unavailable"""
    cache_data = {}
    
    def get(key):
        return cache_data.get(key)
    
    def set(key, value, timeout=3600):
        cache_data[key] = value
        # Simple cleanup after timeout (in production, use proper TTL)
    
    def delete(key):
        cache_data.pop(key, None)
    
    logger.info("Using in-memory fallback caching")
    return {'get': get, 'set': set, 'delete': delete, 'type': 'memory'}

# Initialize cache system
if REDIS_AVAILABLE:
    is_connected, _ = check_redis_connection()
    if is_connected:
        logger.info("Redis caching initialized successfully")
    else:
        logger.warning("Redis unavailable, using fallback caching")
        cache = enable_fallback_caching()
else:
    logger.warning("Redis not available, using fallback caching")
    cache = enable_fallback_caching()
