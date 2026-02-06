# Enhanced Database Factory with Connection Pooling and Performance
import sqlite3
import os
import threading
import time
import logging
import json
from contextlib import contextmanager
from pathlib import Path

# Database configuration
DB_NAME = "news_intelligence.db"
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), DB_NAME)

logger = logging.getLogger(__name__)

# Connection pool for better concurrency
class ConnectionPool:
    def __init__(self, max_connections=10):
        self.max_connections = max_connections
        self.pool = []
        self.semaphore = threading.Semaphore(max_connections)
        self.lock = threading.Lock()
        self.created_connections = 0
        
    def get_connection(self):
        """Get connection from pool or create new one"""
        self.semaphore.acquire()
        try:
            with self.lock:
                if self.pool:
                    conn = self.pool.pop()
                    return self._prepare_connection(conn)
                else:
                    return self._create_new_connection()
        finally:
            self.semaphore.release()
    
    def _create_new_connection(self):
        """Create new database connection with optimizations"""
        self.created_connections += 1
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn = self._prepare_connection(conn)
        return conn
    
    def _prepare_connection(self, conn):
        """Prepare connection with performance optimizations"""
        # Enable WAL mode for better concurrency
        conn.execute('PRAGMA journal_mode=WAL')
        # Optimize for concurrent access
        conn.execute('PRAGMA synchronous=NORMAL')
        # Enable foreign key constraints
        conn.execute('PRAGMA foreign_keys=ON')
        # Optimize memory usage
        conn.execute('PRAGMA cache_size=10000')
        conn.execute('PRAGMA temp_store=MEMORY')
        # Set row factory for consistent results
        conn.row_factory = sqlite3.Row
        return conn
    
    def return_connection(self, conn):
        """Return connection to pool"""
        try:
            with self.lock:
                if len(self.pool) < self.max_connections:
                    self.pool.append(conn)
                else:
                    conn.close()
        except Exception as e:
            logger.error(f"Error returning connection to pool: {e}")
            try:
                conn.close()
            except:
                pass
    
    def close_all(self):
        """Close all connections in pool"""
        with self.lock:
            for conn in self.pool:
                try:
                    conn.close()
                except:
                    pass
            self.pool.clear()

# Global connection pool
_connection_pool = None

def get_connection_pool():
    """Get or create global connection pool"""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool(max_connections=10)
    return _connection_pool

@contextmanager
def get_db_connection():
    """Context manager for database connections with pooling"""
    pool = get_connection_pool()
    conn = pool.get_connection()
    try:
        yield conn
        # Commit on successful completion
        if not conn.in_transaction:
            conn.commit()
    except Exception:
        # Rollback on error
        if not conn.in_transaction:
            conn.rollback()
        raise
    finally:
        # Return connection to pool
        pool.return_connection(conn)

def init_database():
    """Initialize database with enhanced schema and indexes"""
    logger.info("Initializing enhanced database schema...")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create enhanced news table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                published_at TEXT NOT NULL,
                full_content TEXT,
                ai_summary TEXT,
                impact_score INTEGER DEFAULT 0,
                is_important BOOLEAN DEFAULT FALSE,
                sentiment TEXT DEFAULT 'neutru',
                is_saved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                category TEXT DEFAULT 'international',
                instruments TEXT DEFAULT '[]',
                recommendation TEXT,
                confidence_score REAL DEFAULT 0.0
            )
        ''')
        
        # Create email alerts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER NOT NULL,
                recipient_email TEXT NOT NULL,
                alert_type TEXT DEFAULT 'high_impact',
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                FOREIGN KEY (news_id) REFERENCES news (id) ON DELETE CASCADE
            )
        ''')
        
        # Performance indexes with composite keys
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_url ON news(url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_category ON news(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_created_at ON news(created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_impact_score ON news(impact_score DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_is_saved ON news(is_saved)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_recommendation ON news(recommendation)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_instruments ON news(instruments)')
        
        # Composite indexes for common query patterns
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_main_query ON news(is_saved, impact_score DESC, created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_category_filter ON news(category, impact_score DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_composite_filter ON news(category, impact_score DESC, recommendation)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_ai_processing ON news(ai_summary) WHERE ai_summary IS NULL')
        
        # Email alerts indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_alerts_news_id ON email_alerts(news_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_alerts_status ON email_alerts(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_alerts_sent_at ON email_alerts(sent_at DESC)')
        
        # Performance optimizations
        cursor.execute('PRAGMA optimize')
        conn.commit()
        
        logger.info("✅ Enhanced database schema initialized successfully")
        return True

def get_database_stats():
    """Get comprehensive database statistics"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Basic counts
            cursor.execute("SELECT COUNT(*) FROM news")
            stats['total_news'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM news WHERE ai_summary IS NOT NULL")
            stats['analyzed_news'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM news WHERE is_saved = 1")
            stats['saved_news'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM news WHERE impact_score >= 7")
            stats['high_impact_news'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM news WHERE category = 'romania'")
            stats['romanian_news'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM news WHERE category = 'international'")
            stats['international_news'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM email_alerts")
            stats['total_alerts'] = cursor.fetchone()[0]
            
            # Average metrics
            cursor.execute("SELECT AVG(impact_score) FROM news WHERE ai_summary IS NOT NULL")
            avg_score = cursor.fetchone()[0]
            stats['average_impact_score'] = round(avg_score or 0, 2)
            
            # Database size
            if os.path.exists(DB_PATH):
                stats['db_size_mb'] = os.path.getsize(DB_PATH) / (1024 * 1024)
            else:
                stats['db_size_mb'] = 0
            
            # Connection pool stats
            pool = get_connection_pool()
            stats['active_connections'] = pool.max_connections - pool.semaphore._value
            stats['pooled_connections'] = len(pool.pool)
            stats['created_connections'] = pool.created_connections
            
            return stats
            
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        return {}

def batch_update_news(articles_data):
    """Batch update multiple news articles efficiently"""
    if not articles_data:
        return 0
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Use executemany for batch operation
            update_data = []
            for item, ai_result in articles_data:
                instruments_json = ai_result.get('instruments', [])
                if isinstance(instruments_json, list):
                    instruments_json = json.dumps(instruments_json)
                elif not isinstance(instruments_json, str):
                    instruments_json = str(instruments_json)
                
                update_data.append((
                    ai_result.get('content'),
                    ai_result['summary'], 
                    ai_result['impact_score'], 
                    ai_result['is_important'],
                    ai_result.get('sentiment', 'neutru'),
                    instruments_json,
                    ai_result.get('recommendation'),
                    ai_result.get('confidence_score', 0.0),
                    item['url']
                ))
            
            cursor.executemany('''
                UPDATE news 
                SET full_content = ?, ai_summary = ?, impact_score = ?, 
                    is_important = ?, sentiment = ?, instruments = ?,
                    recommendation = ?, confidence_score = ?
                WHERE url = ?
            ''', update_data)
            
            updated_count = cursor.rowcount
            conn.commit()
            
            logger.info(f"Batch updated {updated_count} articles successfully")
            return updated_count
            
    except Exception as e:
        logger.error(f"Batch update failed: {e}")
        return 0

def cleanup_old_data(days_to_keep=30):
    """Clean up old data to maintain performance"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Delete old unprocessed news
            cursor.execute('''
                DELETE FROM news 
                WHERE ai_summary IS NULL 
                AND created_at < datetime('now', '-{} days')
            '''.format(days_to_keep))
            
            # Delete old email alerts
            cursor.execute('''
                DELETE FROM email_alerts 
                WHERE sent_at < datetime('now', '-{} days')
            '''.format(days_to_keep))
            
            deleted_news = cursor.rowcount
            deleted_alerts = cursor.rowcount
            conn.commit()
            
            logger.info(f"Cleanup completed: {deleted_news} old news, {deleted_alerts} old alerts")
            return deleted_news + deleted_alerts
            
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return 0

def close_database():
    """Close database connections properly"""
    global _connection_pool
    if _connection_pool:
        _connection_pool.close_all()
        _connection_pool = None
    logger.info("Database connections closed")