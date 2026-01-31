import sqlite3

DB_NAME = "news_intelligence.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                title TEXT,
                url TEXT UNIQUE,
                published_at TEXT,
                full_content TEXT,
                ai_summary TEXT,
                impact_score INTEGER,
                is_important BOOLEAN,
                sentiment TEXT,
                is_saved BOOLEAN DEFAULT 0,  -- COLOANĂ NOUĂ PENTRU SALVARE
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    print("✅ Baza de date a fost inițializată!")

def add_news_placeholder(source, title, url, published_at):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR IGNORE INTO news (source, title, url, published_at)
                VALUES (?, ?, ?, ?)
            ''', (source, title, url, published_at))
            conn.commit()
            return c.lastrowid
    except Exception as e:
        print(f"Eroare DB: {e}")
        return None

def get_unprocessed_news():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        c.execute("SELECT * FROM news WHERE ai_summary IS NULL")
        return [dict(row) for row in c.fetchall()]

def update_news_analysis(url, content, summary, score, is_important):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE news 
            SET full_content = ?, ai_summary = ?, impact_score = ?, is_important = ?
            WHERE url = ?
        ''', (content, summary, score, is_important, url))
        conn.commit()

# --- TOGGLE SAVE ---
def toggle_save_status(news_id):
    """Schimbă statusul: dacă e salvat devine nesalvat și invers."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Verificăm starea actuală
        c.execute("SELECT is_saved FROM news WHERE id = ?", (news_id,))
        current_status = c.fetchone()[0]
        
        # O inversăm (0 devine 1, 1 devine 0)
        new_status = 0 if current_status else 1
        
        c.execute("UPDATE news SET is_saved = ? WHERE id = ?", (new_status, news_id))
        conn.commit()
        return new_status

if __name__ == "__main__":
    init_db()