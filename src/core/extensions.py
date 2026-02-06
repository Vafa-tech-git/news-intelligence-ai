# Enhanced Security Extensions Configuration
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
from flask import request, session
import logging
from logging.handlers import RotatingFileHandler
import redis
import bleach
import hashlib
import time
from datetime import datetime, timedelta
import re

# Global extensions
csrf = CSRFProtect()
limiter = None
talisman = Talisman()
security_logger = None

# Security utilities
class SecurityUtils:
    """Enhanced security utilities for input validation and sanitization"""
    
    @staticmethod
    def sanitize_html(content: str, allowed_tags: list = None, allowed_attributes: dict = None) -> str:
        """Sanitize HTML content to prevent XSS attacks"""
        if allowed_tags is None:
            allowed_tags = ['b', 'i', 'em', 'strong', 'p', 'br', 'a']
        if allowed_attributes is None:
            allowed_attributes = {'a': ['href', 'title']}
        
        try:
            tags = allowed_tags or ['b', 'i', 'em', 'strong', 'p', 'br', 'a']
            attributes = allowed_attributes or {'a': ['href', 'title']}
            return bleach.clean(
                content,
                tags=tags,
                attributes=attributes,
                strip=True
            )
        except Exception as e:
            if security_logger:
                security_logger.error(f"HTML sanitization error: {e}")
            return ""
    
    @staticmethod
    def validate_text_input(text: str, max_length: int = 10000, min_length: int = 1) -> tuple[bool, str]:
        """Validate text input for length and malicious content"""
        if not isinstance(text, str):
            return False, "Invalid input type"
        
        if len(text) < min_length or len(text) > max_length:
            return False, f"Text length must be between {min_length} and {max_length} characters"
        
        # Check for common attack patterns
        suspicious_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'expression\s*\(',
            r'url\s*\(',
            r'@import',
            r'binding\s*:',
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if security_logger:
                    security_logger.warning(f"Suspicious pattern detected: {pattern}")
                return False, "Invalid content detected"
        
        return True, ""
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL to prevent SSRF attacks"""
        if not isinstance(url, str):
            return False
        
        # Basic URL validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'(?:\d{1,3}\.){3}\d{1,3})'  # IP address
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(url):
            return False
        
        # Prevent localhost and private IP access in production
        forbidden_patterns = [
            'localhost',
            '127.0.0.1',
            '0.0.0.0',
            '::1',
            '192.168.',
            '10.',
            '172.16.',
            '169.254.'
        ]
        
        for pattern in forbidden_patterns:
            if pattern in url:
                if security_logger:
                    security_logger.warning(f"Blocked potentially dangerous URL: {url}")
                return False
        
        return True
    
    @staticmethod
    def hash_sensitive_data(data: str, salt: str = "news_ai_security_salt") -> str:
        """Hash sensitive data for logging purposes"""
        if salt is None:
            salt = "news_ai_security_salt"
        
        return hashlib.sha256((data + salt).encode()).hexdigest()[:16]
    
    @staticmethod
    def log_security_event(event_type: str, details: dict, severity: str = "INFO"):
        """Log security events with structured data"""
        timestamp = datetime.utcnow().isoformat()
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        user_agent = request.headers.get('User-Agent', 'Unknown')[:200]
        
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        user_agent = request.headers.get('User-Agent', 'Unknown')[:200]
        
        log_data = {
            'timestamp': timestamp,
            'event_type': event_type,
            'ip_address': SecurityUtils.hash_sensitive_data(ip_address),
            'user_agent': user_agent,
            'severity': severity,
            **details
        }
        
        if security_logger:
            if severity == "CRITICAL":
                security_logger.critical(f"SECURITY: {event_type} - {log_data}")
            elif severity == "WARNING":
                security_logger.warning(f"SECURITY: {event_type} - {log_data}")
            else:
                security_logger.info(f"SECURITY: {event_type} - {log_data}")

# Rate limiting utilities
class RateLimitTracker:
    """Enhanced rate limiting with sliding window"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.memory_store = {}  # Fallback to memory
    
    def is_rate_limited(self, key: str, limit: int, window_seconds: int) -> tuple[bool, dict]:
        """Check if rate limit is exceeded with sliding window"""
        current_time = time.time()
        window_start = current_time - window_seconds
        
        if self.redis_client:
            try:
                # Use Redis for distributed rate limiting
                pipe = self.redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                pipe.zadd(key, {str(current_time): current_time})
                pipe.expire(key, window_seconds)
                results = pipe.execute()
                
                count = results[1]
                self.redis_client.expire(key, window_seconds)
                
                return count >= limit, {
                    'current': count,
                    'limit': limit,
                    'remaining': max(0, limit - count),
                    'reset_time': current_time + window_seconds
                }
            except Exception as e:
                if security_logger:
                    security_logger.error(f"Redis rate limiting failed: {e}")
        
        # Fallback to memory-based rate limiting
        if key not in self.memory_store:
            self.memory_store[key] = []
        
        # Remove old entries
        self.memory_store[key] = [t for t in self.memory_store[key] if t > window_start]
        
        # Check limit
        count = len(self.memory_store[key])
        if count >= limit:
            return True, {
                'current': count,
                'limit': limit,
                'remaining': 0,
                'reset_time': current_time + window_seconds
            }
        
        # Add current request
        self.memory_store[key].append(current_time)
        
        return False, {
            'current': count + 1,
            'limit': limit,
            'remaining': limit - count - 1,
            'reset_time': current_time + window_seconds
        }

# Security middleware
class SecurityMiddleware:
    """Enhanced security middleware for Flask applications"""
    
    def __init__(self, app):
        self.app = app
        self.init_security_headers()
        self.init_input_validation()
    
    def init_security_headers(self):
        """Initialize comprehensive security headers"""
        @self.app.after_request
        def add_security_headers(response):
            # Content Security Policy
            csp = {
                'default-src': ["'self'"],
                'script-src': [
                    "'self'",
                    "'unsafe-inline'",  # For Tailwind CSS
                    'https://cdn.tailwindcss.com',
                    'https://unpkg.com'
                ],
                'style-src': [
                    "'self'",
                    "'unsafe-inline'",
                    'https://cdn.tailwindcss.com',
                    'https://fonts.googleapis.com'
                ],
                'img-src': ["'self'", 'data:', 'https:'],
                'font-src': ["'self'", 'https://fonts.gstatic.com'],
                'connect-src': ["'self'", 'https://ollama.com'],
                'object-src': ["'none'"],
                'media-src': ["'self'"],
                'frame-src': ["'none'"],
                'base-uri': ["'self'"],
                'form-action': ["'self'"]
            }
            
            csp_string = '; '.join([f"{k} {' '.join(v)}" for k, v in csp.items()])
            
            # Set headers
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response.headers['Content-Security-Policy'] = csp_string
            response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
            
            return response
    
    def init_input_validation(self):
        """Initialize input validation middleware"""
        @self.app.before_request
        def validate_input():
            # Validate all form data
            if request.method in ['POST', 'PUT', 'PATCH']:
                for key, value in request.form.items():
                    is_valid, error_msg = SecurityUtils.validate_text_input(value)
                    if not is_valid:
                        SecurityUtils.log_security_event(
                            "INVALID_INPUT",
                            {'field': key, 'error': error_msg},
                            "WARNING"
                        )
                        return {"error": "Invalid input detected"}, 400
            
            # Validate JSON data
            if request.is_json and request.get_json():
                data = request.get_json()
                self._validate_dict_recursively(data)
    
    def _validate_dict_recursively(self, data: dict, path: str = ""):
        """Recursively validate dictionary data"""
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            
            if isinstance(value, str):
                is_valid, error_msg = SecurityUtils.validate_text_input(value)
                if not is_valid:
                    SecurityUtils.log_security_event(
                        "INVALID_JSON_INPUT",
                        {'path': current_path, 'error': error_msg},
                        "WARNING"
                    )
            elif isinstance(value, dict):
                self._validate_dict_recursively(value, current_path)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, (str, dict)):
                        item_path = f"{current_path}[{i}]"
                        if isinstance(item, str):
                            is_valid, error_msg = SecurityUtils.validate_text_input(item)
                            if not is_valid:
                                SecurityUtils.log_security_event(
                                    "INVALID_LIST_INPUT",
                                    {'path': item_path, 'error': error_msg},
                                    "WARNING"
                                )
                        elif isinstance(item, dict):
                            self._validate_dict_recursively(item, item_path)

# Global security utilities instance
security_utils = SecurityUtils()
rate_limit_tracker = None

def init_extensions(app):
    """Initialize Flask extensions"""
    global csrf, limiter, talisman, security_logger
    
    # CSRF Protection
    csrf.init_app(app)
    
    # Security logging
    security_logger = logging.getLogger('security')
    security_handler = RotatingFileHandler('logs/security.log', maxBytes=10240, backupCount=5)
    security_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    security_handler.setLevel(logging.INFO)
    security_logger.addHandler(security_handler)
    
    # Rate Limiting
    try:
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=[app.config.get('RATELIMIT_DEFAULT', '200 per day, 50 per hour')],
            storage_uri=app.config.get('RATELIMIT_STORAGE_URL', 'memory://'),
            headers_enabled=app.config.get('RATELIMIT_HEADERS_ENABLED', True),
            swallow_errors=app.config.get('RATELIMIT_SWALLOW_ERRORS', True),
            on_breach=lambda limit: security_logger.warning(f"Rate limit breached! Limit: {limit}") if security_logger else None
        )
        app.logger.info(f"Rate limiting configured with storage: {app.config.get('RATELIMIT_STORAGE_URL', 'memory://')}")
    except Exception as e:
        app.logger.error(f"Rate limiting fallback to memory: {e}")
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            storage_uri="memory://",
            headers_enabled=True,
            swallow_errors=True
        )
    
    # Initialize rate limit tracker
    global rate_limit_tracker
    rate_limit_tracker = RateLimitTracker(redis_client=redis.Redis.from_url(app.config.get('RATELIMIT_STORAGE_URL', 'redis://localhost:6379')) if 'redis://' in app.config.get('RATELIMIT_STORAGE_URL', '') else None)
    
    # Enhanced Security Headers (configurable)
    if app.config.get('SECURITY_HEADERS_ENABLED', False):
        security_middleware = SecurityMiddleware(app)
        
        talisman.init_app(app,
            force_https=app.config.get('HTTPS_ENABLED', False),
            strict_transport_security=app.config.get('HTTPS_ENABLED', False),
            content_security_policy={
                'default-src': "'self'",
                'script-src': [
                    "'self'",
                    "'unsafe-inline'",  # For Tailwind CSS
                    'https://cdn.tailwindcss.com',
                    'https://unpkg.com'
                ],
                'style-src': [
                    "'self'",
                    "'unsafe-inline'",
                    'https://cdn.tailwindcss.com',
                    'https://fonts.googleapis.com'
                ],
                'img-src': ["'self'", 'data:', 'https:'],
                'font-src': ["'self'", 'https://fonts.gstatic.com'],
                'connect-src': ["'self'", 'https://ollama.com'],
                'object-src': ["'none'"],
                'media-src': ["'self'"],
                'frame-src': ["'none'"],
                'base-uri': ["'self'"],
                'form-action': ["'self'"]
            },
            referrer_policy='strict-origin-when-cross-origin',
            feature_policy={
                'geolocation': "'none'",
                'camera': "'none'",
                'microphone': "'none'"
            }
        )
    
    return csrf, limiter, talisman, security_logger