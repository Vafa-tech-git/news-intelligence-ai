import requests
import feedparser
import sys
import os
import time
import logging
import concurrent.futures
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import queue

logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.config import RSS_FEEDS, RSS_FEEDS_ROMANIA, RSS_FEEDS_ALL, FINNHUB_TOKEN
from src.core.database import get_db_connection

# Connection pool for HTTP requests
class HTTPConnectionPool:
    """Thread-safe HTTP connection pool for RSS feeds"""
    
    def __init__(self, pool_size=20):
        self.pool_size = pool_size
        self.session = requests.Session()
        
        # Configure session for reuse
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=pool_size,
            pool_maxsize=pool_size,
            max_retries=3,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Headers to avoid blocking
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; NewsAI/1.0)',
            'Accept': 'application/rss+xml, application/xml, text/xml',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache'
        })
    
    def get(self, url: str, timeout: int = 10) -> requests.Response:
        """Make HTTP GET request with connection pooling"""
        return self.session.get(url, timeout=timeout)
    
    def close(self):
        """Close the session"""
        self.session.close()

# Global connection pool
http_pool = HTTPConnectionPool()

class OptimizedRSSFetcher:
    """Optimized RSS fetcher with intelligent threading and error handling"""
    
    def __init__(self):
        self.max_workers = min(20, len(RSS_FEEDS_ALL))  # Dynamic thread count
        self.timeout = 15  # seconds
        self.retry_count = 2
        self.failed_feeds = set()  # Track failed feeds to avoid repeated attempts
        self.feed_cache = {}  # Simple in-memory cache
        self.cache_ttl = 300  # 5 minutes
        
        # Thread-safe statistics
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_articles': 0,
            'new_articles': 0,
            'processing_time': 0.0
        }
        self.stats_lock = threading.Lock()
    
    @monitor_query_performance("fetch_rss_feeds_optimized")
    def fetch_rss_feeds_optimized(self) -> int:
        """Fetch RSS feeds with optimized threading and error handling"""
        logger.info(f"Starting optimized RSS fetching with {self.max_workers} workers...")
        start_time = time.time()
        
        # Filter out recently failed feeds
        available_feeds = [
            (source, url) for source, url in RSS_FEEDS_ALL.items()
            if source not in self.failed_feeds
        ]
        
        if not available_feeds:
            logger.warning("All feeds failed recently, skipping RSS fetch")
            return 0
        
        # Use ThreadPoolExecutor with dynamic worker count
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all feed fetching tasks
            future_to_source = {
                executor.submit(self._fetch_single_rss_optimized, source, url): source
                for source, url in available_feeds
            }
            
            # Process completed tasks
            total_new_articles = 0
            for future in concurrent.futures.as_completed(future_to_source, timeout=30):
                source_name = future_to_source[future]
                
                try:
                    new_articles = future.result()
                    total_new_articles += new_articles
                    
                    # Reset failed feed status on success
                    if source_name in self.failed_feeds:
                        self.failed_feeds.remove(source_name)
                        logger.info(f"Feed {source_name} recovered from failure")
                        
                except Exception as e:
                    logger.error(f"Error processing {source_name}: {e}")
                    
                    # Mark as failed to avoid repeated attempts
                    self.failed_feeds.add(source_name)
                    
                    with self.stats_lock:
                        self.stats['failed_requests'] += 1
        
        processing_time = time.time() - start_time
        
        # Update statistics
        with self.stats_lock:
            self.stats['processing_time'] = processing_time
            self.stats['new_articles'] = total_new_articles
        
        logger.info(f"Optimized RSS fetching complete: {total_new_articles} new articles in {processing_time:.2f}s")
        return total_new_articles
    
    def _fetch_single_rss_optimized(self, source_name: str, feed_url: str) -> int:
        """Fetch single RSS feed with optimized parsing and caching"""
        # Check cache first
        cache_key = f"{source_name}:{feed_url}"
        if cache_key in self.feed_cache:
            cached_data, timestamp = self.feed_cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                logger.debug(f"Using cached RSS feed for {source_name}")
                return self._process_cached_feed(cached_data, source_name)
        
        start_time = time.time()
        local_count = 0
        
        try:
            with self.stats_lock:
                self.stats['total_requests'] += 1
            
            # Fetch with connection pooling and timeout
            response = http_pool.get(feed_url, timeout=self.timeout)
            response.raise_for_status()
            
            # Parse RSS feed
            feed = feedparser.parse(response.content)
            
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"Feed parsing warning for {source_name}: {feed.bozo_exception}")
            
            # Process entries with limits and filtering
            entries_processed = 0
            max_entries_per_feed = 15  # Increased from 10
            
            for entry in feed.entries:
                if entries_processed >= max_entries_per_feed:
                    break
                
                # Validate entry data
                if not hasattr(entry, 'title') or not hasattr(entry, 'link'):
                    continue
                
                title = entry.title.strip()
                url = entry.link.strip()
                
                if not title or not url:
                    continue
                
                # Determine publication date with fallbacks
                pub_date = self._extract_publication_date(entry)
                
                # Determine category
                category = 'romania' if source_name in RSS_FEEDS_ROMANIA else 'international'
                
                # Add to database
                is_new = db_service.add_news_placeholder(
                    source=source_name,
                    title=title,
                    url=url,
                    published_at=pub_date,
                    category=category
                )
                
                if is_new:
                    local_count += 1
                
                entries_processed += 1
            
            # Cache successful fetch
            self.feed_cache[cache_key] = (feed.entries[:max_entries_per_feed], time.time())
            
            # Cleanup old cache entries
            self._cleanup_cache()
            
            processing_time = time.time() - start_time
            logger.info(f"RSS {source_name}: {local_count} new articles in {processing_time:.2f}s")
            
            with self.stats_lock:
                self.stats['successful_requests'] += 1
                self.stats['total_articles'] += entries_processed
            
            return local_count
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching {source_name}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error fetching {source_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error processing {source_name}: {e}")
            raise
    
    def _process_cached_feed(self, cached_entries: List, source_name: str) -> int:
        """Process cached feed entries"""
        local_count = 0
        
        for entry in cached_entries:
            try:
                title = entry.title.strip()
                url = entry.link.strip()
                
                if not title or not url:
                    continue
                
                pub_date = self._extract_publication_date(entry)
                category = 'romania' if source_name in RSS_FEEDS_ROMANIA else 'international'
                
                is_new = db_service.add_news_placeholder(
                    source=source_name,
                    title=title,
                    url=url,
                    published_at=pub_date,
                    category=category
                )
                
                if is_new:
                    local_count += 1
                    
            except Exception as e:
                logger.debug(f"Error processing cached entry for {source_name}: {e}")
                continue
        
        return local_count
    
    def _extract_publication_date(self, entry) -> str:
        """Extract publication date with multiple fallbacks"""
        # Try published_parsed first
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                dt_object = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                return dt_object.strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass
        
        # Try published string
        if hasattr(entry, 'published') and entry.published:
            return entry.published
        
        # Try updated
        if hasattr(entry, 'updated') and entry.updated:
            return entry.updated
        
        # Fallback to current time
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def _cleanup_cache(self):
        """Remove expired cache entries"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self.feed_cache.items()
            if current_time - timestamp > self.cache_ttl
        ]
        
        for key in expired_keys:
            del self.feed_cache[key]
    
    @monitor_query_performance("fetch_finnhub_optimized")
    def fetch_finnhub_optimized(self) -> int:
        """Optimized Finnhub API fetching with error handling"""
        if not FINNHUB_TOKEN:
            logger.warning("Missing Finnhub token in configuration")
            return 0
        
        logger.info("Fetching from Finnhub API...")
        
        url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_TOKEN}"
        count = 0
        
        try:
            response = http_pool.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, list):
                logger.error("Finnhub API returned invalid data format")
                return 0
            
            # Process items with batching for better performance
            batch_data = []
            
            for item in data[:50]:  # Increased from 30
                try:
                    pub_date = datetime.fromtimestamp(item['datetime']).strftime('%Y-%m-%d %H:%M:%S')
                    real_source = item.get('source', 'Finnhub')
                    
                    batch_data.append({
                        'source': real_source,
                        'title': item['headline'],
                        'url': item['url'],
                        'published_at': pub_date,
                        'category': 'international'
                    })
                    
                except Exception as e:
                    logger.debug(f"Error processing Finnhub item: {e}")
                    continue
            
            # Batch insert for better performance
            if batch_data:
                count = db_service.BatchOperations.insert_news_batch(batch_data)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Finnhub API HTTP error: {e}")
        except Exception as e:
            logger.error(f"Finnhub API error: {e}")
        
        logger.info(f"Finnhub fetching complete: {count} new articles")
        return count
    
    def get_statistics(self) -> Dict:
        """Get fetching statistics"""
        with self.stats_lock:
            stats = self.stats.copy()
            stats['failed_feeds_count'] = len(self.failed_feeds)
            stats['cache_size'] = len(self.feed_cache)
            
            if stats['total_requests'] > 0:
                stats['success_rate'] = (stats['successful_requests'] / stats['total_requests']) * 100
            else:
                stats['success_rate'] = 0
            
            return stats
    
    def reset_failed_feeds(self):
        """Reset failed feeds tracking (call periodically)"""
        if self.failed_feeds:
            logger.info(f"Resetting {len(self.failed_feeds)} failed feeds")
            self.failed_feeds.clear()
    
    def close(self):
        """Cleanup resources"""
        http_pool.close()

# Global optimized fetcher instance
optimized_fetcher = OptimizedRSSFetcher()

# Backwards compatibility functions
def fetch_rss_feeds() -> int:
    """Backwards compatibility wrapper"""
    return optimized_fetcher.fetch_rss_feeds_optimized()

def fetch_finnhub_news() -> int:
    """Backwards compatibility wrapper"""
    return optimized_fetcher.fetch_finnhub_optimized()

if __name__ == "__main__":
    import logging
    logger = logging.getLogger(__name__)
    
    # Test optimized RSS fetching
    logger.info("🧪 Testing optimized RSS fetching...")
    
    rss_count = fetch_rss_feeds()
    finnhub_count = fetch_finnhub_news()
    
    stats = optimized_fetcher.get_statistics()
    logger.info(f"✅ RSS: {rss_count}, Finnhub: {finnhub_count}")
    logger.info(f"📊 Stats: {stats}")
    
    optimized_fetcher.close()
