import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time
import random
import hashlib
import logging

# Import cache manager for web content caching
try:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.utils.cache import cache_web_content, get_cached_web_content
    cache_enabled = True
except ImportError:
    cache_enabled = False
    logging.warning("Cache manager not available for web scraper")

# Configure logging
logger = logging.getLogger(__name__)

# ==========================================
# HEADER-E PENTRU DEGHIZARE
# ==========================================
# Site-urile știu când ești robot dacă nu ai un "User-Agent" (buletin de browser).
# Folosim o listă pentru a ne schimba identitatea la fiecare cerere.
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0'
]

def get_random_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/'
    }

# ==========================================
# PLANUL A: REQUESTS + BEAUTIFULSOUP
# ==========================================
def scrape_with_bs4(url):
    """Metoda rapidă. Descarcă HTML-ul static."""
    try:
        # Timeout de 10 secunde ca să nu blocăm programul dacă site-ul e picat
        response = requests.get(url, headers=get_random_headers(), timeout=10)
        
        # Dacă serverul zice "403 Forbidden", înseamnă că ne-a prins. Returnăm eșec.
        if response.status_code != 200:
            return ""
            
        return extract_text_from_html(response.text)
    except Exception as e:
        logger.debug(f"   [BS4] Eșec la {url}: {e}")
        return ""

# ==========================================
# PLANUL B: PLAYWRIGHT (BROWSER REAL)
# ==========================================
def scrape_with_playwright(url):
    logger.debug("   [Playwright] Activez browserul...")
    text = ""
    
    try:
        with sync_playwright() as p:
            # Lansăm browserul cu opțiuni anti-detecție
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            
            # --- ÎNCERCAREA 1: RAPIDĂ (Wait until domcontentloaded) ---
            try:
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                html_content = page.content()
                text = extract_text_from_html(html_content)
            except Exception as e:
                logger.debug(f"      ⚠️ Rapid a eșuat: {e}")

            # --- ÎNCERCAREA 2: LENTĂ (Dacă prima a dat text puțin) ---
            if len(text) < 200:
                logger.debug("      ➡️ Text incomplet. Trec la modul 'Heavy' (Scroll + NetworkIdle)...")
                
                # Așteptăm să se termine încărcarea rețelei (networkidle)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except:
                    pass # Continuăm chiar dacă dă timeout la networkidle

                # Simulăm scroll uman până jos pentru a încărca tot (Lazy Load)
                page.evaluate("""
                    async () => {
                        await new Promise((resolve) => {
                            var totalHeight = 0;
                            var distance = 100;
                            var timer = setInterval(() => {
                                var scrollHeight = document.body.scrollHeight;
                                window.scrollBy(0, distance);
                                totalHeight += distance;
                                
                                if(totalHeight >= scrollHeight - window.innerHeight){
                                    clearInterval(timer);
                                    resolve();
                                }
                            }, 100);
                        });
                    }
                """)
                
                # Așteptăm puțin după scroll
                time.sleep(2)
                
                # Citim din nou
                html_content = page.content()
                text = extract_text_from_html(html_content)

            browser.close()
            
    except Exception as e:
        logger.debug(f"   [Playwright] Eroare critică: {e}")
    
    return text

# ==========================================
# LOGICA DE EXTRAGERE ȘI CURĂȚARE
# ==========================================
def extract_text_from_html(html_content):
    """Această funcție curăță HTML-ul brut și scoate textul curat."""
    if not html_content:
        return ""
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. SCOATEM GUNOIUL (Elemente inutile)
    # Eliminăm scripturi JS, stiluri CSS, meniuri de navigare, subsoluri, reclame
    for junk in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        junk.decompose() # .decompose() le șterge complet din memorie
        
    # 2. EXTRAGEM TEXTUL
    # Căutăm doar tag-urile <p> (paragrafe). Acolo stă de obicei știrea.
    paragraphs = soup.find_all('p')
    
    # 3. FILTRARE
    # Păstrăm doar paragrafele care au sens (mai lungi de 50 caractere)
    # Asta elimină textele gen "Read More", "Share", "By Author"
    clean_text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 40])
    
    return clean_text

# ==========================================
# FUNCȚIA PRINCIPALĂ (MANAGERUL)
# ==========================================
def get_article_content(url):
    """Aceasta este singura funcție pe care o va apela restul aplicației cu caching."""
    
    # Step 0: Check cache first
    if cache_enabled:
        cached_content = get_cached_web_content(url)
        if cached_content and len(cached_content) > 300:
            logger.debug(f"Cache hit for URL: {url}")
            return cached_content
        logger.debug(f"Cache miss for URL: {url}")
    
    # Pasul 1: Încercăm metoda rapidă
    content = scrape_with_bs4(url)
    
    # Verificăm dacă am obținut ceva util (măcar 300 caractere)
    if content and len(content) > 300:
        # Cache the successful result
        if cache_enabled:
            cache_web_content(url, content)
        return content
        
    # Pasul 2: Dacă textul e prea scurt sau gol, încercăm metoda grea (Playwright)
    # Site-uri precum Yahoo Finance adesea necesită asta
    content = scrape_with_playwright(url)

    if content and len(content) > 300:
        # Cache the successful result
        if cache_enabled:
            cache_web_content(url, content)
        return content
    
    return content