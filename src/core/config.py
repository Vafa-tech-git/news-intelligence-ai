# Enhanced Configuration with Global News Category
import os
from dotenv import load_dotenv

# 1. Încărcăm variabilele din fișierul .env în memoria calculatorului
load_dotenv()

# ==========================================
# CONFIGURĂRI DE MEDIU ȘI SECURITATE
# ==========================================

# Security and environment flags
HTTPS_ENABLED = os.getenv("HTTPS_ENABLED", "False").lower() == "true"
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"
CONTINUOUS_SCAN_ENABLED = os.getenv("CONTINUOUS_SCAN_ENABLED", "False").lower() == "true"
LOCAL_OLLAMA_PREFERRED = os.getenv("LOCAL_OLLAMA_PREFERRED", "True").lower() == "true"

# ==========================================
# CONFIGURĂRI PENTRU AI (OLLAMA)
# ==========================================

# Local server URL (prioritate pentru Ollama local)
OLLAMA_LOCAL_HOST = os.getenv("OLLAMA_LOCAL_HOST", "http://localhost:11434")

# Cloud fallback URL (păstrat pentru backup)
OLLAMA_CLOUD_HOST = os.getenv("OLLAMA_CLOUD_HOST", "https://ollama.com")

# Modelul: Specificăm exact ce model uriaș vrem să folosim
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud")

# Cheia: Dacă serverul cloud are parolă, o luăm de aici (pentru fallback)
OLLAMA_KEY = os.getenv("OLLAMA_KEY")

# Legacy compatibility (păstrat pentru cod vechi)
OLLAMA_HOST = OLLAMA_CLOUD_HOST  # Compatibilitate cu ai_analyst.py

# Ollama local preferences
OLLAMA_LOCAL_MODEL = os.getenv("OLLAMA_LOCAL_MODEL", "gpt-oss:120b-cloud")
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))
OLLAMA_REQUEST_TIMEOUT = int(os.getenv("OLLAMA_REQUEST_TIMEOUT", "120"))
OLLAMA_HEALTH_CHECK_INTERVAL = int(os.getenv("OLLAMA_HEALTH_CHECK_INTERVAL", "60"))

# ==========================================
# CONFIGURĂRI PENTRU ȘTIRI (FINNHUB & RSS)
# ==========================================

# Token-ul pentru Finnhub (sursa de știri financiare)
FINNHUB_TOKEN = os.getenv("FINNHUB_TOKEN")

# Lista centralizată de surse RSS Internaționale (optimizată)
RSS_FEEDS = {
    # --- GENERAL FINANCE & MARKETS ---
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "CNBC Finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "Investing.com": "https://www.investing.com/rss/news.rss",
    "WSJ Markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", # Wall Street Journal (Atenție: Paywall des)
    
    # --- TECH & BUSINESS ---
    "TechCrunch": "https://techcrunch.com/feed/",
    "The Verge Business": "https://www.theverge.com/rss/business/index.xml",
    "Quartz": "https://qz.com/feed",
    
    # --- CRYPTO & BLOCKCHAIN ---
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "CoinTelegraph": "https://cointelegraph.com/rss",
    
    # --- ECONOMY & WORLD ---
    "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "Fortune": "https://fortune.com/feed/"
}

# --- SURSE RSS ROMÂNESTI (optimizat) ---
RSS_FEEDS_ROMANIA = {
    "Ziarul Financiar": "https://www.zf.ro/rss",
    "Profit.ro": "https://www.profit.ro/rss",
    "Bursa.ro": "https://www.bursa.ro/rss.xml",
    "Wall-Street": "https://www.wall-street.ro/rss",
    "Economica.net": "https://www.economica.net/rss",
    "CursDeGuvernare": "https://cursdeguvernare.ro/rss",
    "Startup.ro": "https://startup.ro/feed/",
    "Business Magazin": "https://www.businessmagazin.ro/rss"
}

# --- SURSE RSS GLOBALE (optimizat) ---
RSS_FEEDS_GLOBAL = {
    "Reuters World": "https://www.reuters.com/world/rss.xml",
    "BBC World Service": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "CNN World": "http://rss.cnn.com/rss/edition.rss_world.xml"
}

# Surse combinate pentru funcții legacy
RSS_FEEDS_ALL = {**RSS_FEEDS, **RSS_FEEDS_ROMANIA, **RSS_FEEDS_GLOBAL}

# Category detection function
def detect_news_category(source_name, title=""):
    """Detect article category based on source and content"""
    if source_name in RSS_FEEDS_ROMANIA:
        return 'romania'
    elif source_name in RSS_FEEDS_GLOBAL:
        return 'global'
    elif source_name in RSS_FEEDS:
        return 'international'
    else:
        # Fallback to content analysis
        title_lower = title.lower()
        global_keywords = ['world', 'global', 'international', 'worldwide']
        if any(keyword in title_lower for keyword in global_keywords):
            return 'global'
        else:
            return 'international'

# ==========================================
# CONFIGURĂRI PENTRU EMAIL ALERTS (SMTP)
# ==========================================

# SMTP Server configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "True").lower() == "true"

# Email alert settings
EMAIL_ALERTS_ENABLED = os.getenv("EMAIL_ALERTS_ENABLED", "False").lower() == "true"
ALERT_HIGH_IMPACT_THRESHOLD = int(os.getenv("ALERT_HIGH_IMPACT_THRESHOLD", "9"))
ALERT_RATE_LIMIT_MINUTES = int(os.getenv("ALERT_RATE_LIMIT_MINUTES", "30"))
DEFAULT_ALERT_RECIPIENT = os.getenv("DEFAULT_ALERT_RECIPIENT")

# ==========================================
# CONFIGURĂRI PENTRU CSRF PROTECTION
# ==========================================

# Cheie secretă pentru sesiuni și CSRF protection
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# Timp de expirare pentru token CSRF (în secunde)
WTF_CSRF_TIME_LIMIT = 3600

# Enable CSRF protection for all routes
WTF_CSRF_ENABLED = True

# ==========================================
# CONFIGURĂRI PENTRU RATE LIMITING
# ==========================================

# Enable rate limiting
RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "True").lower() == "true"

# Redis connection for rate limiting storage
RATELIMIT_STORAGE_URL = os.getenv("RATELIMIT_STORAGE_URL", "redis://localhost:6379")

# Default rate limits for all endpoints
RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "200 per day, 50 per hour")

# Enable rate limit headers in responses
RATELIMIT_HEADERS_ENABLED = os.getenv("RATELIMIT_HEADERS_ENABLED", "True").lower() == "true"

# Don't swallow rate limit errors (show them to users)
RATELIMIT_SWALLOW_ERRORS = os.getenv("RATELIMIT_SWALLOW_ERRORS", "False").lower() == "true"

# ==========================================
# CONFIGURĂRI PENTRU LOGGING ȘI SECURITATE
# ==========================================

# Enable detailed security logging
SECURITY_LOG_LEVEL = os.getenv("SECURITY_LOG_LEVEL", "INFO")

# Log failed login attempts, CSRF violations, etc.
LOG_SECURITY_EVENTS = os.getenv("LOG_SECURITY_EVENTS", "True").lower() == "true"

# CSRF configuration
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "False").lower() == "true"  # HTTPS only
CSRF_COOKIE_HTTPONLY = os.getenv("CSRF_COOKIE_HTTPONLY", "True").lower() == "true"
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")

# Session security
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"  # HTTPS only
SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "True").lower() == "true"
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_PERMANENT = os.getenv("SESSION_COOKIE_PERMANENT", "False").lower() == "true"

# Security headers
SECURITY_HEADERS_ENABLED = os.getenv("SECURITY_HEADERS_ENABLED", "False").lower() == "true"

# Rate limiting security
RATELIMIT_ON_BREACH = os.getenv("RATELIMIT_ON_BREACH", "True").lower() == "true"  # Log rate limit violations

# Specific limits per endpoint
RATELIMIT_SPECIFIC = {
    "scan_news": os.getenv("RATELIMIT_SCAN_NEWS", "20 per 5 minutes, 100 per hour"),
    "toggle_save": os.getenv("RATELIMIT_TOGGLE_SAVE", "200 per hour"),
    "reset_db": os.getenv("RATELIMIT_RESET_DB", "10 per hour"),
    "filter_news": os.getenv("RATELIMIT_FILTER_NEWS", "50 per hour"),
    "set_category": os.getenv("RATELIMIT_SET_CATEGORY", "100 per hour")
}

# ==========================================
# CONFIGURĂRI PENTRU PERFORMANȚĂ
# ==========================================

# Performance optimization flags
ENABLE_PARALLEL_PROCESSING = os.getenv("ENABLE_PARALLEL_PROCESSING", "True").lower() == "true"
ENABLE_ENHANCED_CACHING = os.getenv("ENABLE_ENHANCED_CACHING", "True").lower() == "true"
ENABLE_PERFORMANCE_MONITORING = os.getenv("ENABLE_PERFORMANCE_MONITORING", "True").lower() == "true"

# Performance limits (Enhanced)
MAX_WORKER_THREADS = int(os.getenv("MAX_WORKER_THREADS", "4"))
MIN_WORKER_THREADS = int(os.getenv("MIN_WORKER_THREADS", "1"))
ADAPTIVE_WORKER_SCALING = os.getenv("ADAPTIVE_WORKER_SCALING", "False").lower() == "true"
ARTICLE_PROCESSING_TIMEOUT = int(os.getenv("ARTICLE_PROCESSING_TIMEOUT", "90"))
SCAN_ARTICLES_LIMIT = int(os.getenv("SCAN_ARTICLES_LIMIT", "25"))

# Advanced performance tuning
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "25"))
CONNECTION_POOL_SIZE = int(os.getenv("CONNECTION_POOL_SIZE", "15"))
QUERY_TIMEOUT = int(os.getenv("QUERY_TIMEOUT", "30"))
ENABLE_BATCH_PROCESSING = os.getenv("ENABLE_BATCH_PROCESSING", "True").lower() == "true"

# Memory and resource limits (Enhanced)
MAX_MEMORY_USAGE_MB = int(os.getenv("MAX_MEMORY_USAGE_MB", "1200"))
MAX_CPU_USAGE_PERCENT = int(os.getenv("MAX_CPU_USAGE_PERCENT", "95"))
ENABLE_RESOURCE_THROTTLING = os.getenv("ENABLE_RESOURCE_THROTTLING", "True").lower() == "true"
WORKER_SCALE_THRESHOLD = float(os.getenv("WORKER_SCALE_THRESHOLD", "0.9"))

# Performance monitoring thresholds
PERFORMANCE_ALERT_MEMORY_MB = int(os.getenv("PERFORMANCE_ALERT_MEMORY_MB", "300"))
PERFORMANCE_ALERT_CPU_PERCENT = int(os.getenv("PERFORMANCE_ALERT_CPU_PERCENT", "75"))
PERFORMANCE_SLOW_QUERY_SECONDS = int(os.getenv("PERFORMANCE_SLOW_QUERY_SECONDS", "2"))

# Additional performance optimization from config_v2
RSS_MAX_WORKERS = int(os.getenv("RSS_MAX_WORKERS", "20"))
RSS_TIMEOUT_SECONDS = int(os.getenv("RSS_TIMEOUT_SECONDS", "15"))
RSS_MAX_ENTRIES_PER_FEED = int(os.getenv("RSS_MAX_ENTRIES_PER_FEED", "15"))

# AI optimization enhancements
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "3"))
AI_RATE_LIMIT_DELAY = float(os.getenv("AI_RATE_LIMIT_DELAY", "1.0"))

# Resource monitoring
RESOURCE_MONITORING_ENABLED = os.getenv("RESOURCE_MONITORING_ENABLED", "True").lower() == "true"
RESOURCE_MONITOR_INTERVAL = int(os.getenv("RESOURCE_MONITOR_INTERVAL", "30"))
MAX_MEMORY_PERCENT = float(os.getenv("MAX_MEMORY_PERCENT", "80.0"))
MAX_CPU_PERCENT = float(os.getenv("MAX_CPU_PERCENT", "90.0"))
MAX_CONCURRENT_OPERATIONS = int(os.getenv("MAX_CONCURRENT_OPERATIONS", "10"))

# Emergency cleanup settings
AUTO_CLEANUP_ENABLED = os.getenv("AUTO_CLEANUP_ENABLED", "True").lower() == "true"
CLEANUP_DAYS_OLD = int(os.getenv("CLEANUP_DAYS_OLD", "30"))
EMERGENCY_CLEANUP_DAYS = int(os.getenv("EMERGENCY_CLEANUP_DAYS", "7"))

# ==========================================
# VERIFICĂRI DE SIGURANȚĂ (DEBUG)
# ==========================================

# Import logging for proper debug messages
import logging

config_logger = logging.getLogger(__name__)

# Asta ne ajută să nu ne chinuim mai târziu dacă am uitat să punem cheia.
if not FINNHUB_TOKEN:
    config_logger.warning("⚠️ ATENȚIE: Nu am găsit FINNHUB_TOKEN în fișierul .env!")

if not OLLAMA_KEY and "ollama.com" in OLLAMA_HOST:
    config_logger.warning("⚠️ ATENȚIE: Folosești cloud-ul oficial dar nu ai setat OLLAMA_KEY!")

if SECRET_KEY == "dev-secret-key-change-in-production":
    config_logger.warning("⚠️ ATENȚIE: Folosești cheie secretă de dezvoltare! Setează SECRET_KEY în .env pentru producție!")

# Performance configuration verification
if ENABLE_PARALLEL_PROCESSING:
    config_logger.info(f"✅ Parallel processing enabled with {MAX_WORKER_THREADS} workers")
if ENABLE_ENHANCED_CACHING:
    config_logger.info(f"✅ Enhanced caching enabled with {ARTICLE_PROCESSING_TIMEOUT}s timeout")
if ENABLE_PERFORMANCE_MONITORING:
    config_logger.info("✅ Performance monitoring enabled")