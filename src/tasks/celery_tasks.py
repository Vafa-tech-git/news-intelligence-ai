# Enhanced Celery Tasks for Modular Architecture with Continuous Scanning
from celery import Celery
import redis
import logging
from datetime import datetime, timedelta

# Import enhanced caching
from src.utils.enhanced_cache import get_cache_manager

# Configure logging for background tasks
logger = logging.getLogger(__name__)

# Initialize Celery with Redis broker and backend
celery_app = Celery(
    'news_ai_tasks',
    broker='redis://localhost:6379/1',
    backend='redis://localhost:6379/2',
    include=['src.tasks.celery_tasks']
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    result_expires=3600,
    task_reject_on_worker_lost=True,
    task_ignore_result=False,
)

@celery_app.task(bind=True, max_retries=3)
def process_news_article(self, news_id, url):
    """Background task to process a single news article"""
    try:
        logger.info(f"Processing article ID {news_id}: {url}")
        
        # Import services here to avoid circular imports
        from src.services.scraper_service import get_article_content
        from src.services.ai_service_market_enhanced import analyze_article_with_market_data as analyze_article
        from src.core.database import get_db_connection
        
        # Get article content
        content = get_article_content(url)
        
        if content and len(content) > 80:
            # Analyze with AI
            ai_result = analyze_article(content)
            
            if ai_result:
                # Update database
                with get_db_connection() as conn:
                    conn.execute('''
                        UPDATE news 
                        SET full_content = ?, ai_summary = ?, impact_score = ?, is_important = ?
                        WHERE url = ?
                    ''', (content, ai_result['summary'], ai_result['impact_score'], ai_result['is_important'], url))
                    conn.commit()
                
                logger.info(f"Successfully processed article {news_id}")
                return {"status": "success", "news_id": news_id}
        
        return {"status": "failed", "reason": "insufficient_content"}
        
    except Exception as e:
        logger.error(f"Error processing article {news_id}: {e}")
        raise self.retry(countdown=60 * (2 ** self.request.retries))

@celery_app.task
def fetch_news_sources():
    """Background task to fetch news from all sources"""
    try:
        logger.info("Starting news fetch cycle")
        
        # Import news fetch functions
        from src.services.news_service import fetch_finnhub_news, fetch_rss_feeds
        
        # Fetch from sources
        finnhub_count = fetch_finnhub_news()
        logger.info(f"Fetched {finnhub_count} articles from Finnhub")
        
        fetch_rss_feeds()
        logger.info("RSS feeds fetched")
        
        return {
            "status": "success",
            "finnhub_count": finnhub_count,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in news fetch cycle: {e}")
        return {"status": "error", "error": str(e)}

@celery_app.task
def cleanup_old_data():
    """Maintenance task to clean up old data"""
    try:
        logger.info("Starting cleanup cycle")
        
        # Clean up old news
        from src.core.database import get_db_connection
        
        with get_db_connection() as conn:
            cursor = conn.execute(f'''
                DELETE FROM news 
                WHERE is_saved = 0 
                AND created_at < date('now', '-7 days')
            ''')
            deleted_count = cursor.rowcount
            conn.commit()
            
            # Vacuum database
            conn.execute("VACUUM")
            conn.commit()
        
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in cleanup cycle: {e}")
        return {"status": "error", "error": str(e)}

@celery_app.task
def health_check():
    """Health check task"""
    try:
        from src.core.database import get_database_stats
        
        # Check Redis connection
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        redis_client.ping()
        
        # Check database
        stats = get_database_stats()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "redis": "connected",
            "database_stats": stats
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Periodic tasks
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'fetch-news-every-15-min': {
        'task': 'src.tasks.celery_tasks.fetch_news_sources',
        'schedule': crontab(minute='*/15'),
    },
    'cleanup-old-data-daily': {
        'task': 'src.tasks.celery_tasks.cleanup_old_data',
        'schedule': crontab(hour=2, minute=0),
    },
    'health-check-hourly': {
        'task': 'src.tasks.celery_tasks.health_check',
        'schedule': crontab(minute=0),
    },
    'check-continuous-scan': {
        'task': 'src.tasks.celery_tasks.check_and_run_continuous_scan',
        'schedule': crontab(minute='*/5'),  # Check every 5 minutes
    },
}

if __name__ == "__main__":
    logger.info("🧪 Testing Celery configuration...")
    
    # Test health check
    result = health_check.delay()
    logger.info(f"✅ Health check task queued: {result.id}")
    
    logger.info("📋 Available tasks:")
    logger.info("   - fetch_news_sources")
    logger.info("   - process_news_article")
    logger.info("   - cleanup_old_data")
    logger.info("   - health_check")