import os
from dotenv import load_dotenv

# 1. Încărcăm variabilele din fișierul .env în memoria calculatorului
# Fără linia asta, Python nu știe ce e ăla "FINNHUB_TOKEN"
load_dotenv()

# ==========================================
# CONFIGURĂRI PENTRU AI (OLLAMA)
# ==========================================

# Host-ul: Adresa serverului unde rulează "creierul"
# Dacă nu găsește nimic în .env, presupune că e site-ul oficial
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "https://ollama.com")

# Modelul: Specificăm exact ce model uriaș vrem să folosim
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud")

# Cheia: Dacă serverul cloud are parolă, o luăm de aici
OLLAMA_KEY = os.getenv("OLLAMA_KEY")

# ==========================================
# CONFIGURĂRI PENTRU ȘTIRI (FINNHUB & RSS)
# ==========================================

# Token-ul pentru Finnhub (sursa de știri financiare)
FINNHUB_TOKEN = os.getenv("FINNHUB_TOKEN")

# ==========================================
# CONFIGURĂRI PENTRU SENTIMENT INTELLIGENCE
# ==========================================

# Alpha Vantage API (free tier: 25 requests/day)
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

# FRED API (free, 120 requests/minute)
FRED_API_KEY = os.getenv("FRED_API_KEY")

# Sentiment source weights (sum to 1.0)
SENTIMENT_WEIGHTS = {
    'ollama_ai': 0.35,      # Deep article analysis
    'alphavantage': 0.25,   # Professional sentiment
    'stocktwits': 0.20,     # Retail social sentiment
    'reddit': 0.10,         # Reddit retail sentiment
    'volume_bonus': 0.10    # High activity multiplier
}

# Signal thresholds
SIGNAL_THRESHOLDS = {
    'strong_buy': {'sentiment': 0.6, 'confidence': 0.75, 'consensus': 0.7},
    'buy': {'sentiment': 0.3, 'confidence': 0.6},
    'sell': {'sentiment': -0.3, 'confidence': 0.6},
    'strong_sell': {'sentiment': -0.6, 'confidence': 0.75, 'consensus': 0.7}
}

# Rate limits per source (requests, period in seconds)
RATE_LIMITS = {
    'alphavantage': {'requests': 25, 'period': 86400},  # 25/day
    'stocktwits': {'requests': 200, 'period': 3600},    # 200/hour
    'apewisdom': {'requests': 100, 'period': 60},       # 100/min
    'finnhub': {'requests': 60, 'period': 60},          # 60/min
    'fred': {'requests': 120, 'period': 60}             # 120/min
}

# Lista centralizată de surse RSS
# Aici adăugăm sau ștergem surse. Restul programului se va adapta automat.
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

# ==========================================
# VERIFICĂRI DE SIGURANȚĂ (DEBUG)
# ==========================================
# Asta ne ajută să nu ne chinuim mai târziu dacă am uitat să punem cheia.
if not FINNHUB_TOKEN:
    print("⚠️ ATENȚIE: Nu am găsit FINNHUB_TOKEN în fișierul .env!")

if not OLLAMA_KEY and "ollama.com" in OLLAMA_HOST:
    print("⚠️ ATENȚIE: Folosești cloud-ul oficial dar nu ai setat OLLAMA_KEY!")

# ==========================================
# FRED ECONOMIC INDICATORS CONFIGURATION
# ==========================================

# 20 key economic indicators from FRED
FRED_INDICATORS = {
    # Growth & Output
    'GDPC1': {'name': 'Real GDP', 'category': 'growth', 'frequency': 'quarterly', 'direction': 'higher_better'},
    'INDPRO': {'name': 'Industrial Production', 'category': 'growth', 'frequency': 'monthly', 'direction': 'higher_better'},
    'TCU': {'name': 'Capacity Utilization', 'category': 'growth', 'frequency': 'monthly', 'direction': 'optimal_range', 'optimal': (75, 85)},

    # Labor Market
    'UNRATE': {'name': 'Unemployment Rate', 'category': 'labor', 'frequency': 'monthly', 'direction': 'lower_better'},
    'PAYEMS': {'name': 'Non-Farm Payrolls', 'category': 'labor', 'frequency': 'monthly', 'direction': 'higher_better'},
    'ICSA': {'name': 'Initial Jobless Claims', 'category': 'labor', 'frequency': 'weekly', 'direction': 'lower_better'},

    # Inflation
    'CPIAUCSL': {'name': 'CPI All Items', 'category': 'inflation', 'frequency': 'monthly', 'direction': 'optimal_range', 'optimal': (2, 3)},
    'PCEPILFE': {'name': 'Core PCE', 'category': 'inflation', 'frequency': 'monthly', 'direction': 'optimal_range', 'optimal': (1.5, 2.5)},
    'PPIACO': {'name': 'PPI', 'category': 'inflation', 'frequency': 'monthly', 'direction': 'stable'},

    # Interest Rates
    'FEDFUNDS': {'name': 'Federal Funds Rate', 'category': 'rates', 'frequency': 'daily', 'direction': 'context'},
    'DGS10': {'name': '10-Year Treasury', 'category': 'rates', 'frequency': 'daily', 'direction': 'context'},
    'DGS2': {'name': '2-Year Treasury', 'category': 'rates', 'frequency': 'daily', 'direction': 'context'},
    'T10Y2Y': {'name': 'Yield Curve (10Y-2Y)', 'category': 'rates', 'frequency': 'daily', 'direction': 'higher_better'},
    'M2SL': {'name': 'M2 Money Supply', 'category': 'rates', 'frequency': 'monthly', 'direction': 'moderate_growth'},

    # Consumer & Business
    'RSXFS': {'name': 'Retail Sales', 'category': 'consumer', 'frequency': 'monthly', 'direction': 'higher_better'},
    'UMCSENT': {'name': 'Consumer Sentiment', 'category': 'consumer', 'frequency': 'monthly', 'direction': 'higher_better'},
    'HOUST': {'name': 'Housing Starts', 'category': 'consumer', 'frequency': 'monthly', 'direction': 'higher_better'},
    'DGORDER': {'name': 'Durable Goods Orders', 'category': 'consumer', 'frequency': 'monthly', 'direction': 'higher_better'},

    # Financial Conditions
    'VIXCLS': {'name': 'VIX', 'category': 'financial', 'frequency': 'daily', 'direction': 'lower_better'},
    'SP500': {'name': 'S&P 500', 'category': 'financial', 'frequency': 'daily', 'direction': 'higher_better'},
}

# Category weights for composite Economic Health Index
CATEGORY_WEIGHTS = {
    'growth': 0.20,      # GDP, Industrial Production, Capacity
    'labor': 0.25,       # Unemployment, Payrolls, Claims (strongest economic signal)
    'inflation': 0.15,   # CPI, PCE, PPI
    'rates': 0.15,       # Fed Funds, Treasury, Yield Curve
    'consumer': 0.15,    # Retail, Sentiment, Housing, Durable Goods
    'financial': 0.10    # VIX, S&P 500 (market-driven, less fundamental)
}

# Regime classification thresholds
REGIME_THRESHOLDS = {
    'expansion': 70,     # Score >= 70
    'peak': 60,          # Score 60-70
    'contraction': 30,   # Score 30-60
    'trough': 0          # Score < 30
}