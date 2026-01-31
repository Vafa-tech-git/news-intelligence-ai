import requests
import feedparser
import sys
import os
import time
from datetime import datetime

# ==========================================
# TRUC PENTRU IMPORTURI (PATH HACK)
# ==========================================
# Deoarece acest fișier este în folderul 'modules', el nu vede fișierele din folderul principal.
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import config
import database

# ==========================================
# FUNCȚIA 1: FINNHUB (API)
# ==========================================
def fetch_finnhub_news():
    """Preia știri generale de la API-ul Finnhub"""
    print("📡 Scanez Finnhub...")
    token = config.FINNHUB_TOKEN
    if not token:
        print("❌ Lipsă Token Finnhub în .env")
        return 0

    url = f"https://finnhub.io/api/v1/news?category=general&token={token}"
    count = 0
    try:
        response = requests.get(url)
        data = response.json()
        
        if isinstance(data, list):
            for item in data[:15]: 
                pub_date = datetime.fromtimestamp(item['datetime']).strftime('%Y-%m-%d %H:%M:%S')
                
                # Încercăm să luăm sursa reală din datele Finnhub (item['source'])
                # Dacă câmpul e gol sau nu există, folosim 'Finnhub' ca rezervă.
                real_source = item.get('source')
                if not real_source:
                    real_source = "Finnhub"
                # -----------------------------

                # Folosim real_source în loc de textul hardcodat "Finnhub"
                if database.add_news_placeholder(real_source, item['headline'], item['url'], pub_date):
                    count += 1
    except Exception as e:
        print(f"⚠️ Eroare Finnhub: {e}")
    
    return count

# ==========================================
# FUNCȚIA 2: RSS FEEDS (XML)
# ==========================================
def fetch_rss_feeds():
    """Descarcă știri din toate sursele RSS definite în config."""
    print("📡 Conectare la fluxurile RSS...")
    
    total_rss_count = 0
    
    # .items() ne dă și numele sursei (Yahoo), și link-ul
    for source_name, feed_url in config.RSS_FEEDS.items():
        try:
            # feedparser este librăria specială care "citește" formatul RSS
            feed = feedparser.parse(feed_url)
            
            local_count = 0
            for entry in feed.entries[:5]: # Luăm doar primele 5 de la fiecare sursă
                
                # Unele RSS-uri au data în 'published', altele în 'updated'. Verificăm ambele.
                # feedparser are un câmp secret numit 'published_parsed'
                # care conține data deja descifrată, indiferent de formatul sursei.
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    # O convertim în formatul nostru curat: An-Luna-Zi Ora:Min:Sec
                    dt_object = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    pub_date = dt_object.strftime('%Y-%m-%d %H:%M:%S')
                
                # PASUL 2: Dacă nu merge conversia, luăm data brută trimisă de ei
                # Căutăm câmpul 'published' sau 'updated'
                elif entry.get('published') or entry.get('updated'):
                    pub_date = entry.get('published', entry.get('updated'))
                    
                # PASUL 3: Dacă nu există nicio dată, punem data curentă (ultimul resort)
                else:
                    pub_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
                is_new = database.add_news_placeholder(
                    source=source_name,
                    title=entry.title,
                    url=entry.link,
                    published_at=pub_date
                )
                
                if is_new:
                    local_count += 1
            
            print(f"   🔹 {source_name}: {local_count} știri noi.")
            total_rss_count += local_count
            
        except Exception as e:
            print(f"⚠️ Eroare la RSS {source_name}: {e}")

# ==========================================
# MAIN (Punctul de pornire)
# ==========================================
if __name__ == "__main__":
    # Dacă rulăm fișierul direct, execută ambele funcții
    fetch_finnhub_news()
    fetch_rss_feeds()
    print("🏁 Procesul de colectare s-a încheiat.")