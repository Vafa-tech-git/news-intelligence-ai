from flask import Flask, render_template, request
import sqlite3
import database
from modules import news_fetcher, web_scraper, ai_analyst

app = Flask(__name__)

# Se asigură că tabelul e creat înainte de orice cerere a utilizatorului
with app.app_context():
    database.init_db()

def get_analyzed_news(only_saved=False):
    with sqlite3.connect(database.DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        query = "SELECT * FROM news WHERE ai_summary IS NOT NULL"
        
        # Dacă vrem doar salvate, adăugăm condiția
        if only_saved:
            query += " AND is_saved = 1"
            
        query += " ORDER BY impact_score DESC, created_at DESC"
        
        c.execute(query)
        return [dict(row) for row in c.fetchall()]

@app.route('/')
def index():
    """Pagina principală. Încarcă știrile existente."""
    news_list = get_analyzed_news(only_saved=False)
    return render_template('index.html', news_list=news_list, showing_saved=False)

# --- RUTĂ NOUĂ PENTRU FILTRU "DOAR SALVATE" ---
@app.route('/saved')
def saved_news():
    news_list = get_analyzed_news(only_saved=True)
    return render_template('index.html', news_list=news_list, showing_saved=True)

# --- RUTĂ NOUĂ PENTRU BUTONUL DE SAVE ---
@app.route('/toggle-save/<int:news_id>', methods=['POST'])
def toggle_save(news_id):
    # Schimbăm starea în DB
    new_status = database.toggle_save_status(news_id)
    
    # Returnăm doar butonul actualizat (nu toată pagina)
    # Iconița se schimbă în funcție de new_status
    return render_template('save_button.html', is_saved=new_status, news_id=news_id)

@app.route('/scan-news', methods=['POST'])
def scan_news():
    """
    Aceasta este inima HTMX.
    Nu returnează o pagină întreagă, ci doar 'cartonașele' cu știri noi.
    """
    print("🚀 Am primit comanda de scanare...")
    
    # 1. Colectare (News Fetcher)
    # Aducem link-urile noi de pe Finnhub și RSS
    news_fetcher.fetch_finnhub_news()
    news_fetcher.fetch_rss_feeds()
    
    # 2. Luăm lista de știri neprocesate din DB
    unprocessed = database.get_unprocessed_news()
    
    html_response = ""
    
    # 3. Procesăm (Scraping + AI)
    # Limităm la 10 știri pe tură ca să nu dureze o veșnicie (utilizatorul așteaptă)
    count = 0
    for item in unprocessed:
        if count >= 10: 
            break
            
        print(f"   ⚙️ Procesez: {item['title']}...")
        
        # A. Extragem textul (Scraper)
        content = web_scraper.get_article_content(item['url'])
        
        if content:
            # B. Analizăm (AI)
            ai_result = ai_analyst.analyze_article(content)
            
            if ai_result:
                # C. Salvăm rezultatul
                database.update_news_analysis(
                    item['url'], 
                    content, 
                    ai_result['summary'],       # Trimitem rezumatul separat
                    ai_result['impact_score'],  # Trimitem scorul separat
                    ai_result['is_important']   # Trimitem boolean-ul separat
                )
                
                # D. Pregătim datele pentru a fi afișate
                full_news_item = {**item, **ai_result} 
                
                # E. Generăm HTML-ul pentru acest card
                html_response += render_template('news_card.html', news=full_news_item)
                count += 1

        else:
            print("   ⚠️ Nu am putut extrage conținutul. Sar peste.")

    # Luăm din nou TOATĂ lista de știri analizate, acum că avem date noi
    all_news = get_analyzed_news()

    # Generăm HTML-ul pentru toate știrile, gata sortate de SQL
    html_response = ""
    for news_item in all_news:
        html_response += render_template('news_card.html', news=news_item)
        
    if not all_news:
        return "<div class='p-4 text-gray-400 text-center'>Nicio știre nouă importantă găsită momentan.</div>"

    return html_response

@app.route('/reset-db', methods=['POST'])
def reset_db():
    with sqlite3.connect(database.DB_NAME) as conn:
        conn.execute("DELETE FROM news WHERE is_saved = 0")
    
    # După ștergere, reîncărcăm lista (vor rămâne doar cele salvate)
    all_news = get_analyzed_news()
    html_response = ""
    for news_item in all_news:
        html_response += render_template('news_card.html', news=news_item)
        
    if not all_news:
         return "<div class='p-4 text-gray-400 text-center'>Baza de date a fost curățată (elementele salvate au fost păstrate).</div>"

    return html_response

if __name__ == '__main__':
    # Pornim serverul în modul Debug (ne arată erorile în browser)
    app.run(debug=True, port=5000)