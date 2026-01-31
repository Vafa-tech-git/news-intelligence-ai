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