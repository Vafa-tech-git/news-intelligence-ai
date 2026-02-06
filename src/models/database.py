import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_NAME = "news_intelligence.db"

def init_db():
    """Initialize database with performance indexes"""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        
        # Create main news table
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
                is_saved BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create performance indexes for optimal query performance
        logger.info("🔍 Creating performance indexes...")
        
        # Index for URL uniqueness and lookups
        c.execute('CREATE INDEX IF NOT EXISTS idx_news_url ON news(url)')
        
        # Index for sorting by creation time (most recent first)
        c.execute('CREATE INDEX IF NOT EXISTS idx_news_created_at ON news(created_at DESC)')
        
        # Index for impact score sorting (highest first)
        c.execute('CREATE INDEX IF NOT EXISTS idx_news_impact_score ON news(impact_score DESC)')
        
        # Index for saved status filtering
        c.execute('CREATE INDEX IF NOT EXISTS idx_news_is_saved ON news(is_saved)')
        
        # Composite index for main query optimization
        c.execute('CREATE INDEX IF NOT EXISTS idx_news_main_query ON news(is_saved, impact_score DESC, created_at DESC)')
        
        # Index for AI processing workflow
        c.execute('CREATE INDEX IF NOT EXISTS idx_news_ai_processing ON news(ai_summary) WHERE ai_summary IS NULL')
        
        conn.commit()
        
        logger.info("✅ Baza de date a fost inițializată cu indecși optimizați!")

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
        logger.error(f"Eroare DB: {e}")
        return None

def get_unprocessed_news(limit=20):
    """Get unprocessed news with limit for batch processing"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        # Use AI processing index and limit for better performance
        c.execute('''
            SELECT * FROM news 
            WHERE ai_summary IS NULL 
            ORDER BY created_at ASC 
            LIMIT ?
        ''', (limit,))
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
    """Toggle save status with error handling"""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT is_saved FROM news WHERE id = ?", (news_id,))
        current_status = c.fetchone()[0]
        new_status = 0 if current_status else 1
        
        c.execute("UPDATE news SET is_saved = ? WHERE id = ?", (new_status, news_id))
        conn.commit()
        return new_status

def get_analyzed_news(only_saved=False, limit=50):
    """Get analyzed news with optimized query and limit"""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        if only_saved:
            # Use composite index for saved news
            c.execute('''
                SELECT * FROM news 
                WHERE ai_summary IS NOT NULL AND is_saved = 1 
                ORDER BY impact_score DESC, created_at DESC 
                LIMIT ?
            ''', (limit,))
        else:
            # Use main composite index
            c.execute('''
                SELECT * FROM news 
                WHERE ai_summary IS NOT NULL 
                ORDER BY impact_score DESC, created_at DESC 
                LIMIT ?
            ''', (limit,))
        
        return [dict(row) for row in c.fetchall()]

def get_database_stats():
    """Get database performance statistics"""
    import os
    
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        
        stats = {}
        
        # Total news count
        c.execute("SELECT COUNT(*) FROM news")
        stats['total_news'] = c.fetchone()[0]
        
        # Analyzed news count
        c.execute("SELECT COUNT(*) FROM news WHERE ai_summary IS NOT NULL")
        stats['analyzed_news'] = c.fetchone()[0]
        
        # Saved news count
        c.execute("SELECT COUNT(*) FROM news WHERE is_saved = 1")
        stats['saved_news'] = c.fetchone()[0]
        
        # High impact news count
        c.execute("SELECT COUNT(*) FROM news WHERE impact_score >= 7")
        stats['high_impact_news'] = c.fetchone()[0]
        
        # Database size
        if os.path.exists(DB_NAME):
            stats['db_size_mb'] = os.path.getsize(DB_NAME) / (1024 * 1024)
        else:
            stats['db_size_mb'] = 0
        
        return stats

if __name__ == "__main__":
    # Reinitialize database with performance indexes
    init_db()
    
    # Show current statistics
    stats = get_database_stats()
    logger.info("\n📈 Database Statistics:")
    for key, value in stats.items():
        if key == 'db_size_mb':
            logger.info(f"   {key}: {value:.2f} MB")
        else:
            logger.info(f"   {key}: {value}")