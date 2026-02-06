import sys
import os
# Enhanced Parallel Processing Service
import json
import time
import logging
import threading
import psutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import List, Dict, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import (
    MAX_WORKER_THREADS, MIN_WORKER_THREADS, ADAPTIVE_WORKER_SCALING,
    ARTICLE_PROCESSING_TIMEOUT, SCAN_ARTICLES_LIMIT, BATCH_SIZE,
    MAX_MEMORY_USAGE_MB, MAX_CPU_USAGE_PERCENT, WORKER_SCALE_THRESHOLD
)
from src.core.database import get_db_connection, batch_update_news
from src.services.scraper_service import get_article_content
from src.services.ai_service_market_enhanced import analyze_article_with_market_data as analyze_article
from src.services.email_service import send_high_impact_alert

logger = logging.getLogger(__name__)

class AdaptiveNewsProcessor:
    """Enhanced news processor with adaptive parallel processing and resource management"""
    
    def __init__(self, max_workers=None, article_timeout=None):
        # Get system resources safely first
        self.cpu_count = 4  # Default fallback
        self.memory_mb = 4000  # Default fallback
        try:
            self.cpu_count = psutil.cpu_count(logical=False)  # Physical cores only
            self.memory_mb = psutil.virtual_memory().total // (1024 * 1024)
        except Exception as e:
            logger.warning(f"Error getting system resources: {e}")
        
        self.max_workers = max_workers or self._calculate_optimal_workers()
        self.article_timeout = article_timeout or ARTICLE_PROCESSING_TIMEOUT
        self.adaptive_scaling = ADAPTIVE_WORKER_SCALING
        
        logger.info(f"Initialized AdaptiveNewsProcessor: {self.max_workers} workers, {self.article_timeout}s timeout")
        logger.info(f"System resources: {self.cpu_count} CPUs, {self.memory_mb}MB RAM")
        
        self.stats = {
            'processed_count': 0,
            'failed_count': 0,
            'alerts_sent': 0,
            'total_time': 0.0,
            'avg_time_per_article': 0.0,
            'peak_memory_mb': 0,
            'peak_cpu_percent': 0.0,
            'worker_adjustments': 0
        }
        
        # Thread safety locks
        self.lock = Lock()
        self.results_lock = Lock()

    def _calculate_optimal_workers(self) -> int:
        """Calculate optimal worker count based on system resources"""
        try:
            # Base calculation on CPU cores
            cpu_count = getattr(self, 'cpu_count', 4)
            base_workers = min(cpu_count, MAX_WORKER_THREADS or 8)
            
            # Adjust based on available memory
            if self.memory_mb < 2000:  # Less than 2GB RAM
                memory_factor = 0.5
            elif self.memory_mb < 4000:  # Less than 4GB RAM
                memory_factor = 0.75
            else:
                memory_factor = 1.0
            
            optimal_workers = max(MIN_WORKER_THREADS or 2, int(base_workers * memory_factor))
            
            logger.info(f"Calculated optimal workers: {optimal_workers} (base: {base_workers}, memory_factor: {memory_factor})")
            return optimal_workers
            
        except Exception as e:
            logger.error(f"Error calculating optimal workers: {e}")
            return MIN_WORKER_THREADS

    def _check_system_resources(self) -> Dict:
        """Monitor system resources and return current status"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_info = psutil.virtual_memory()
            memory_used_mb = memory_info.used // (1024 * 1024)
            
            # Update peak statistics
            with self.lock:
                current_mem = self.stats.get('peak_memory_mb', 0)
                self.stats['peak_memory_mb'] = max(current_mem, memory_used_mb)
                current_cpu = self.stats.get('peak_cpu_percent', 0.0)
                self.stats['peak_cpu_percent'] = max(current_cpu, cpu_percent)
                
            return {
                'cpu_percent': cpu_percent,
                'memory_used_mb': memory_used_mb,
                'memory_percent': memory_info.percent,
                'system_overloaded': (
                    cpu_percent > MAX_CPU_USAGE_PERCENT or 
                    memory_used_mb > MAX_MEMORY_USAGE_MB
                )
            }
            
        except Exception as e:
            logger.error(f"Error checking system resources: {e}")
            return {'system_overloaded': False}

    def _adjust_workers_if_needed(self):
        """Dynamically adjust worker count based on system load"""
        if not self.adaptive_scaling:
            return
        
        try:
            resources = self._check_system_resources()
            
            if resources['system_overloaded']:
                # Reduce workers if system is overloaded
                new_workers = max(MIN_WORKER_THREADS, self.max_workers - 1)
                if new_workers != self.max_workers:
                    logger.warning(f"Reducing workers from {self.max_workers} to {new_workers} due to system load")
                    self.max_workers = new_workers
                    self.stats['worker_adjustments'] += 1
            elif (resources['cpu_percent'] < WORKER_SCALE_THRESHOLD * 100 and 
                  resources['memory_used_mb'] < MAX_MEMORY_USAGE_MB * WORKER_SCALE_THRESHOLD):
                # Increase workers if system has capacity
                new_workers = min(MAX_WORKER_THREADS, self.max_workers + 1)
                if new_workers != self.max_workers:
                    logger.info(f"Increasing workers from {self.max_workers} to {new_workers} - system has capacity")
                    self.max_workers = new_workers
                    self.stats['worker_adjustments'] += 1
                    
        except Exception as e:
            logger.error(f"Error adjusting workers: {e}")

    def process_single_article(self, item: Dict) -> Optional[Dict]:
        """Process a single article with timeout and error handling"""
        try:
            start_time = time.time()
            logger.info(f"Processing article: {item.get('title', 'Unknown')[:50]}...")
            
            # Skip system resource check to prevent "overloaded" messages
            # resources = self._check_system_resources()
            # if resources['system_overloaded']:
            #     logger.warning("System overloaded, skipping article processing")
            #     return None
            
            # Step 1: Get article content
            content = get_article_content(item['url'])
            if content is None or not isinstance(content, str):
                logger.warning(f"No content for article: {item['url']}")
                return None
                
            if not content.strip() or len(content.strip()) < 50:
                logger.warning(f"Insufficient content for article: {item['url']}")
                return None
            
            # Step 2: Get AI analysis with timeout
            ai_result = analyze_article(content)
            if ai_result is None or not isinstance(ai_result, dict):
                logger.warning(f"AI analysis failed for article: {item['url']}")
                return None
            
            # Step 3: Prepare data for database
            processing_time = time.time() - start_time
            processing_data = self._prepare_database_data(item, ai_result, content, processing_time)
            
            return {
                'item': item,
                'ai_result': ai_result,
                'processing_data': processing_data,
                'processing_time': processing_time
            }
            
        except Exception as e:
            logger.error(f"Error processing article {item.get('url', 'unknown')}: {e}")
            return None

    def _prepare_database_data(self, item: Dict, ai_result: Dict, content: str, processing_time: float) -> Tuple:
        """Prepare data for database insertion"""
        instruments = ai_result.get('instruments', [])
        if isinstance(instruments, list):
            instruments_json = json.dumps(instruments)
        else:
            instruments_json = str(instruments)
        
        return (
            content,
            ai_result.get('summary', ''), 
            ai_result.get('impact_score', 0), 
            ai_result.get('is_important', False),
            ai_result.get('sentiment', 'neutru'),
            instruments_json,
            ai_result.get('recommendation'),
            ai_result.get('confidence_score', 0.0),
            item['url']
        )

    def _send_alert_if_needed(self, item: Dict, ai_result: Dict) -> bool:
        """Send email alert for high-impact news"""
        try:
            if ai_result.get('impact_score', 0) >= 9 and ai_result.get('is_important', False):
                full_news_item = {**item, **ai_result}
                if send_high_impact_alert(full_news_item):
                    return True
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
        return False

    def process_articles_parallel(self, articles: List[Dict]) -> Tuple[List[Dict], int, List[Dict]]:
        """Process articles in parallel with resource management"""
        if not articles:
            return [], 0, []
        
        # Limit to reasonable number for first implementation
        articles_to_process = articles[:min(SCAN_ARTICLES_LIMIT, len(articles))]
        
        logger.info(f"Starting parallel processing of {len(articles_to_process)} articles with {self.max_workers} workers")
        start_time = time.time()
        
        processed_articles = []
        alerts_sent = 0
        failed_count = 0
        
        # Check and adjust workers based on system resources
        self._adjust_workers_if_needed()
        
        # Use ThreadPoolExecutor with adaptive settings
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all article processing tasks
            future_to_item = {
                executor.submit(self.process_single_article, item): item 
                for item in articles_to_process
            }
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_item, timeout=self.article_timeout * 2):
                try:
                    result = future.result(timeout=self.article_timeout)
                    if result:
                        with self.results_lock:
                            processed_articles.append(result)
                            
                            # Check if we should send alert
                            if self._send_alert_if_needed(result['item'], result['ai_result']):
                                alerts_sent += 1
                            
                            logger.info(f"Successfully processed article in {result['processing_time']:.2f}s")
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    logger.error(f"Future processing failed: {e}")
                    failed_count += 1
        
        total_time = time.time() - start_time
        avg_time = total_time / len(articles_to_process) if articles_to_process else 0
        
        # Update statistics
        with self.results_lock:
            self.stats['processed_count'] = len(processed_articles)
            self.stats['failed_count'] = failed_count
            self.stats['alerts_sent'] = alerts_sent
            self.stats['total_time'] = float(total_time)
            self.stats['avg_time_per_article'] = float(avg_time)
        
        logger.info(f"Parallel processing completed: {len(processed_articles)} processed, {failed_count} failed, {alerts_sent} alerts sent in {total_time:.2f}s")
        
        return processed_articles, alerts_sent, []  # Return empty list for failed_count compatibility

    def get_performance_stats(self) -> Dict:
        """Get current performance statistics"""
        return self.stats.copy()

    def reset_stats(self):
        """Reset performance statistics"""
        self.stats = {
            'processed_count': 0,
            'failed_count': 0,
            'alerts_sent': 0,
            'total_time': 0.0,
            'avg_time_per_article': 0.0,
            'peak_memory_mb': 0,
            'peak_cpu_percent': 0.0,
            'worker_adjustments': 0
        }

class NewsProcessor(AdaptiveNewsProcessor):
    """Legacy NewsProcessor class for backward compatibility"""
    pass
    
    def process_single_article(self, item: Dict) -> Optional[Dict]:
        """Process a single article with timeout and error handling"""
        try:
            start_time = time.time()
            logger.info(f"Processing article: {item.get('title', 'Unknown')[:50]}...")
            
            # Step 1: Get article content
            content = get_article_content(item['url'])
            if content is None or not isinstance(content, str):
                logger.warning(f"No content for article: {item['url']}")
                return None
                
            if not content.strip() or len(content.strip()) < 50:
                logger.warning(f"Insufficient content for article: {item['url']}")
                return None
            
            # Step 2: Get AI analysis with timeout
            ai_result = analyze_article(content)
            if ai_result is None or not isinstance(ai_result, dict):
                logger.warning(f"AI analysis failed for article: {item['url']}")
                return None
            
            # Step 3: Prepare data for database
            processing_time = time.time() - start_time
            processing_data = self._prepare_database_data(item, ai_result, content, processing_time)
            
            return {
                'item': item,
                'ai_result': ai_result,
                'processing_data': processing_data,
                'processing_time': processing_time
            }
            
        except Exception as e:
            logger.error(f"Error processing article {item.get('url', 'unknown')}: {e}")
            return None
    
    def _prepare_database_data(self, item: Dict, ai_result: Dict, content: str, processing_time: float) -> Tuple:
        """Prepare data for database insertion"""
        instruments = ai_result.get('instruments', [])
        if isinstance(instruments, list):
            instruments_json = json.dumps(instruments)
        else:
            instruments_json = str(instruments)
        
        return (
            content,
            ai_result.get('summary', ''), 
            ai_result.get('impact_score', 0), 
            ai_result.get('is_important', False),
            ai_result.get('sentiment', 'neutru'),
            instruments_json,
            ai_result.get('recommendation'),
            ai_result.get('confidence_score', 0.0),
            item['url']
        )
    
    def _send_alert_if_needed(self, item: Dict, ai_result: Dict) -> bool:
        """Send email alert for high-impact news"""
        try:
            if ai_result.get('impact_score', 0) >= 9 and ai_result.get('is_important', False):
                full_news_item = {**item, **ai_result}
                if send_high_impact_alert(full_news_item):
                    return True
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
        return False
    
    def process_articles_parallel(self, articles: List[Dict]) -> Tuple[List[Dict], int, List[Dict]]:
        """Process articles in parallel with resource management"""
        if not articles:
            return [], 0, []
        
        # Limit to reasonable number for first implementation
        articles_to_process = articles[:25]  # Conservative limit
        
        logger.info(f"Starting parallel processing of {len(articles_to_process)} articles with {self.max_workers} workers")
        start_time = time.time()
        
        processed_articles = []
        alerts_sent = 0
        failed_count = 0
        
        # Use ThreadPoolExecutor with conservative settings
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all article processing tasks
            future_to_item = {
                executor.submit(self.process_single_article, item): item 
                for item in articles_to_process
            }
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_item, timeout=self.article_timeout * 2):
                try:
                    result = future.result(timeout=self.article_timeout)
                    if result:
                        with self.results_lock:
                            processed_articles.append(result)
                            
                            # Check if we should send alert
                            if self._send_alert_if_needed(result['item'], result['ai_result']):
                                alerts_sent += 1
                            
                            logger.info(f"Successfully processed article in {result['processing_time']:.2f}s")
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    logger.error(f"Future processing failed: {e}")
                    failed_count += 1
        
        total_time = time.time() - start_time
        avg_time = total_time / len(articles_to_process) if articles_to_process else 0
        
        # Update statistics
        with self.results_lock:
            self.stats['processed_count'] = len(processed_articles)
            self.stats['failed_count'] = failed_count
            self.stats['alerts_sent'] = alerts_sent
            self.stats['total_time'] = float(total_time)
            self.stats['avg_time_per_article'] = float(avg_time)
        
        logger.info(f"Parallel processing completed: {len(processed_articles)} processed, {failed_count} failed, {alerts_sent} alerts sent in {total_time:.2f}s")
        
        return processed_articles, alerts_sent, []  # Return empty list for failed_count compatibility
    
    def get_performance_stats(self) -> Dict:
        """Get current performance statistics"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset performance statistics"""
        self.stats = {
            'processed_count': 0,
            'failed_count': 0,
            'alerts_sent': 0,
            'total_time': 0.0,
            'avg_time_per_article': 0.0
        }

def enhanced_scan_news(scan_limit: int = 25, category: Optional[str] = None) -> Tuple[int, int, List[Dict]]:
    """Enhanced scan function with conservative parallel processing
    
    Args:
        scan_limit (int): Maximum number of articles to process
        category (str, optional): Category to scan for ('romania', 'international', 'global', 'all')
    """
    try:
        category_filter = category or 'all'
        logger.info(f"Starting enhanced news scan with limit {scan_limit} for category: {category_filter}")
        
        # Step 1: Fetch RSS feeds first
        from src.services.news_service import fetch_rss_feeds
        rss_count = fetch_rss_feeds(category=category_filter)
        logger.info(f"Fetched {rss_count} new articles from RSS feeds for category: {category_filter}")
        
        # Get unprocessed news for specific category
        with get_db_connection() as conn:
            if category_filter == 'all':
                cursor = conn.execute('''
                    SELECT * FROM news 
                    WHERE ai_summary IS NULL 
                    ORDER BY created_at ASC 
                    LIMIT ?
                ''', (scan_limit,))
            else:
                cursor = conn.execute('''
                    SELECT * FROM news 
                    WHERE ai_summary IS NULL AND category = ?
                    ORDER BY created_at ASC 
                    LIMIT ?
                ''', (category_filter, scan_limit))
            unprocessed = [dict(row) for row in cursor.fetchall()]
        
        if not unprocessed:
            logger.info("No unprocessed articles found after RSS fetch")
            return 0, 0, []
        
        # Initialize processor with optimized settings
        processor = AdaptiveNewsProcessor(max_workers=MAX_WORKER_THREADS, article_timeout=ARTICLE_PROCESSING_TIMEOUT)
        
        # Process articles in parallel
        processed_articles, alerts_sent, failed_count = processor.process_articles_parallel(unprocessed)
        
        if not processed_articles:
            logger.warning("No articles were successfully processed")
            return 0, 0, []
        
        # Prepare data for batch database update
        articles_data = []
        html_articles = []
        
        for article_data in processed_articles:
            articles_data.append((article_data['item'], article_data['ai_result']))
            
            # Prepare HTML data for template
            full_news_item = {
                **article_data['item'], 
                **article_data['ai_result']
            }
            
            # Parse instruments for template
            if full_news_item.get('instruments'):
                try:
                    if isinstance(full_news_item['instruments'], str):
                        full_news_item['instruments'] = json.loads(full_news_item['instruments'])
                    elif not isinstance(full_news_item['instruments'], list):
                        full_news_item['instruments'] = []
                except:
                    full_news_item['instruments'] = []
            
            html_articles.append(full_news_item)
        
        # Batch update database
        updated_count = batch_update_news(articles_data)
        
        # Get performance stats
        stats = processor.get_performance_stats()
        logger.info(f"Enhanced scan completed: {updated_count} articles updated, {alerts_sent} alerts sent")
        logger.info(f"Performance stats: {stats}")
        
        return updated_count, alerts_sent, html_articles
        
    except Exception as e:
        logger.error(f"Enhanced scan failed: {e}")
        return 0, 0, []

def get_processing_status() -> Dict:
    """Get current processing status and statistics"""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total_news,
                    COUNT(CASE WHEN ai_summary IS NOT NULL THEN 1 END) as analyzed_news,
                    COUNT(CASE WHEN ai_summary IS NULL THEN 1 END) as pending_news,
                    AVG(CASE WHEN ai_summary IS NOT NULL THEN impact_score END) as avg_impact,
                    MAX(CASE WHEN ai_summary IS NOT NULL THEN created_at END) as last_analysis
                FROM news
            ''')
            
            stats = dict(cursor.fetchone())
            
            # Add processing queue info
            cursor.execute('''
                SELECT COUNT(*) as queue_size 
                FROM news 
                WHERE ai_summary IS NULL 
                AND created_at > datetime('now', '-1 day')
            ''')
            
            queue_stats = dict(cursor.fetchone())
            stats.update(queue_stats)
            
            return {
                'total_news': stats['total_news'] or 0,
                'analyzed_news': stats['analyzed_news'] or 0,
                'pending_news': stats['pending_news'] or 0,
                'average_impact': round(stats['avg_impact'] or 0, 2),
                'last_analysis': stats['last_analysis'],
                'queue_size': queue_stats['queue_size'] or 0,
                'processing_rate': 'N/A'
            }
            
    except Exception as e:
        logger.error(f"Failed to get processing status: {e}")
        return {}

# Create global processor instance
_processor = AdaptiveNewsProcessor()

def get_global_processor():
    """Get global processor instance"""
    return _processor