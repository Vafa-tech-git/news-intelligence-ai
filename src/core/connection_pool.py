import sqlite3
import threading
import queue
import time
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

class ConnectionPool:
    """SQLite connection pool for better performance"""
    
    def __init__(self, max_connections=10, database_path="news_intelligence.db"):
        self.max_connections = max_connections
        self.database_path = database_path
        self._pool = queue.Queue(maxsize=max_connections)
        self._lock = threading.Lock()
        self._created_connections = 0
        
        # Initialize pool with some connections
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize the connection pool with a few connections"""
        initial_size = min(3, self.max_connections)
        for _ in range(initial_size):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)
    
    def _create_connection(self):
        """Create a new database connection with optimizations"""
        try:
            conn = sqlite3.connect(
                self.database_path,
                check_same_thread=False,
                timeout=30.0,
                isolation_level=None  # Autocommit mode for better performance
            )
            
            # Performance optimizations
            conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
            conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety/performance
            conn.execute("PRAGMA cache_size=10000")   # 10MB cache
            conn.execute("PRAGMA temp_store=MEMORY")   # Store temp tables in memory
            conn.execute("PRAGMA mmap_size=268435456") # 256MB memory-mapped I/O
            conn.row_factory = sqlite3.Row
            
            with self._lock:
                self._created_connections += 1
            
            return conn
            
        except Exception as e:
            logger.error(f"Failed to create connection: {e}")
            return None
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool"""
        conn = None
        try:
            # Try to get connection from pool
            try:
                conn = self._pool.get(timeout=5.0)
            except queue.Empty:
                # Pool exhausted, create new connection if under limit
                with self._lock:
                    if self._created_connections < self.max_connections:
                        conn = self._create_connection()
                    else:
                        # Wait for connection to become available
                        conn = self._pool.get(timeout=10.0)
            
            if not conn:
                raise Exception("Failed to get database connection")
            
            yield conn
            
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise e
        finally:
            if conn:
                try:
                    # Check if connection is still valid
                    conn.execute("SELECT 1")
                    self._pool.put(conn, timeout=1.0)
                except (queue.Full, sqlite3.Error):
                    # Connection is bad or pool is full, close it
                    try:
                        conn.close()
                        with self._lock:
                            self._created_connections -= 1
                    except:
                        pass
    
    def get_stats(self):
        """Get pool statistics"""
        with self._lock:
            return {
                'pool_size': self._pool.qsize(),
                'created_connections': self._created_connections,
                'max_connections': self.max_connections
            }
    
    def close_all(self):
        """Close all connections in the pool"""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except queue.Empty:
                break
        with self._lock:
            self._created_connections = 0

# Global connection pool instance
connection_pool = ConnectionPool()

def get_db_connection():
    """Get a database connection from the pool"""
    return connection_pool.get_connection()

# Prepared statements for common queries
class PreparedStatements:
    """Prepared statements for optimal database performance"""
    
    def __init__(self):
        self._statements = {}
        self._initialize_statements()
    
    def _initialize_statements(self):
        """Initialize prepared statements"""
        with connection_pool.get_connection() as conn:
            # Insert news statement
            self._statements['insert_news'] = conn.compile('''
                INSERT OR IGNORE INTO news (source, title, url, published_at, category)
                VALUES (?, ?, ?, ?, ?)
            ''')
            
            # Update news analysis statement
            self._statements['update_analysis'] = conn.compile('''
                UPDATE news 
                SET full_content = ?, ai_summary = ?, impact_score = ?, 
                    is_important = ?, sentiment = ?
                WHERE url = ?
            ''')
            
            # Get unprocessed news statement
            self._statements['get_unprocessed'] = conn.compile('''
                SELECT id, url, title, source, published_at 
                FROM news 
                WHERE ai_summary IS NULL 
                ORDER BY created_at ASC 
                LIMIT ?
            ''')
            
            # Get analyzed news statement
            self._statements['get_analyzed'] = conn.compile('''
                SELECT id, title, url, source, ai_summary, impact_score, 
                       is_important, sentiment, published_at, is_saved
                FROM news 
                WHERE ai_summary IS NOT NULL 
                ORDER BY impact_score DESC, created_at DESC 
                LIMIT ?
            ''')
            
            # Toggle save statement
            self._statements['toggle_save'] = conn.compile('''
                UPDATE news SET is_saved = ? WHERE id = ?
            ''')
    
    def get_statement(self, name):
        """Get a prepared statement by name"""
        return self._statements.get(name)

# Global prepared statements
prepared = PreparedStatements()

# Batch operations
class BatchOperations:
    """Optimized batch database operations"""
    
    @staticmethod
    def insert_news_batch(news_items):
        """Insert multiple news items in a single transaction"""
        if not news_items:
            return 0
        
        with connection_pool.get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                
                stmt = prepared.get_statement('insert_news')
                count = 0
                
                for item in news_items:
                    stmt.execute((
                        item.get('source'),
                        item.get('title'),
                        item.get('url'),
                        item.get('published_at'),
                        item.get('category', 'international')
                    ))
                    if stmt.lastrowid:
                        count += 1
                
                conn.commit()
                return count
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Batch insert error: {e}")
                return 0
    
    @staticmethod
    def update_analysis_batch(updates):
        """Update multiple analyses in a single transaction"""
        if not updates:
            return 0
        
        with connection_pool.get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                
                stmt = prepared.get_statement('update_analysis')
                
                update_data = [
                    (
                        update.get('full_content'),
                        update.get('ai_summary'),
                        update.get('impact_score'),
                        update.get('is_important'),
                        update.get('sentiment'),
                        update.get('url')
                    )
                    for update in updates
                    if update.get('url')
                ]
                
                if update_data:
                    conn.executemany(stmt, update_data)
                    conn.commit()
                    return len(update_data)
                
                return 0
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Batch update error: {e}")
                return 0

if __name__ == "__main__":
    import logging
    logger = logging.getLogger(__name__)
    
    # Test connection pool
    logger.info("🧪 Testing connection pool...")
    
    stats = connection_pool.get_stats()
    logger.info(f"📊 Pool stats: {stats}")
    
    # Test prepared statements
    logger.info("✅ Prepared statements initialized")
