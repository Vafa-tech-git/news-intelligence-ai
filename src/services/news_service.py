import requests
import feedparser
import sys
import os
import time
import logging
import concurrent.futures
from datetime import datetime
import re

# Configure logging for news fetcher module
logger = logging.getLogger(__name__)

# Import configuration and database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.config import FINNHUB_TOKEN, RSS_FEEDS, RSS_FEEDS_ROMANIA, RSS_FEEDS_GLOBAL, RSS_FEEDS_ALL
from src.core.database import get_db_connection

def fetch_single_rss_feed(source_name, feed_url):
    """Fetch articles from a single RSS feed"""
    try:
        import requests
        # Add timeout for RSS fetch
        response = requests.get(feed_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        feed = feedparser.parse(response.content)
        local_count = 0
        
        for entry in feed.entries[:5]:  # Reduced to 5 articles per source to prevent overload
            # Determine publication date
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    dt_object = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    pub_date = dt_object.strftime('%Y-%m-%d %H:%M:%S')
                except (TypeError, ValueError):
                    pub_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elif entry.get('published') or entry.get('updated'):
                pub_date = entry.get('published', entry.get('updated'))
            else:
                pub_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Determine category based on feed source
            if source_name in RSS_FEEDS_ROMANIA:
                category = 'romania'
            elif source_name in RSS_FEEDS_GLOBAL:
                category = 'global'  
            else:
                category = 'international'
            
            # Add to database with category
            is_new = add_news_placeholder(
                source=source_name,
                title=entry.title,
                url=entry.link,
                published_at=pub_date,
                category=category
            )
            
            if is_new:
                local_count += 1
        
        logger.info(f"RSS {source_name}: {local_count} new articles")
        return local_count
        
    except Exception as e:
        logger.error(f"RSS feed error for {source_name}: {type(e).__name__}")
        return 0

def fetch_rss_feeds(category=None):
    """Fetch RSS feeds using multiple threads for improved performance
    
    Args:
        category (str, optional): Filter by category ('romania', 'international', 'global', 'all')
    """
    category_filter = category or 'all'
    logger.info(f"Starting multi-threaded RSS fetching for category: {category_filter}")
    
    total_rss_count = 0
    
    # Select feeds based on category
    if category_filter == 'romania':
        feeds_to_fetch = RSS_FEEDS_ROMANIA
    elif category_filter == 'international':
        feeds_to_fetch = RSS_FEEDS
    elif category_filter == 'global':
        feeds_to_fetch = RSS_FEEDS_GLOBAL
    else:  # 'all' or None
        feeds_to_fetch = RSS_FEEDS_ALL
    
    # Use ThreadPoolExecutor for concurrent fetching
    max_workers = min(4, len(feeds_to_fetch))  # Reduced to 4 threads to prevent overload
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all feed fetching tasks
        future_to_source = {
            executor.submit(fetch_single_rss_feed, source_name, feed_url): source_name
            for source_name, feed_url in feeds_to_fetch.items()
        }
        
        # Process completed tasks as they finish
        for future in concurrent.futures.as_completed(future_to_source):
            source_name = future_to_source[future]
            try:
                count = future.result()
                total_rss_count += count
            except Exception as e:
                logger.error(f"Error processing {source_name}: {e}")
    
    logger.info(f"Multi-threaded RSS fetching complete for {category_filter}. Total new articles: {total_rss_count}")
    return total_rss_count

def fetch_finnhub_news():
    """Preia știri generale de la API-ul Finnhub"""
    logger.info("Scanning Finnhub API...")
    token = FINNHUB_TOKEN
    if not token:
        logger.warning("Missing Finnhub token in configuration")
        return 0

    url = f"https://finnhub.io/api/v1/news?category=general&token={token}"
    count = 0
    try:
        response = requests.get(url)
        data = response.json()
        
        if isinstance(data, list):
            for item in data[:30]: 
                pub_date = datetime.fromtimestamp(item['datetime']).strftime('%Y-%m-%d %H:%M:%S')
                
                # Try to get real source from Finnhub data
                real_source = item.get('source', 'Finnhub')
                
                if add_news_placeholder(real_source, item['headline'], item['url'], pub_date, 'international'):
                    count += 1
    except Exception as e:
        logger.error(f"Finnhub API error: {type(e).__name__}")
    
    return count

def add_news_placeholder(source, title, url, published_at, category='international'):
    """Add news placeholder to database with category"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO news (source, title, url, published_at, category)
                VALUES (?, ?, ?, ?, ?)
            ''', (source, title, url, published_at, category))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Database error: {e}")
        return None

def detect_financial_instruments(text):
    """Detect financial instruments using regex patterns"""
    if not text:
        return []
    
    instruments = []
    
    # Romanian stock symbols (typically 3-4 letters)
    romanian_symbols = re.findall(r'\b[A-Z]{3,4}\b', text)
    
    # Common Romanian stock symbols
    known_symbols = {
        'SNG', 'SNP', 'TLV', 'BRD', 'BCR', 'BNR', 'BVB', 'BET', 'FP', 'EL', 'TGN',
        'OTE', 'CVE', 'SNN', 'CMP', 'M', 'ARO', 'PTR', 'CC', 'VNC', 'MED'
    }
    
    # Filter for known symbols
    for symbol in romanian_symbols:
        if symbol in known_symbols:
            instruments.append(symbol)
    
    return list(set(instruments))  # Remove duplicates

if __name__ == "__main__":
    # Test multi-threaded RSS fetching
    fetch_rss_feeds()
    fetch_finnhub_news()
    logger.info("News collection process completed")
