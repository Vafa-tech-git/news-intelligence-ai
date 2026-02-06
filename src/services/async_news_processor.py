import asyncio
import concurrent.futures
import time
from typing import List, Dict, Optional
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ProcessingResult:
    url: str
    success: bool
    content: Optional[str] = None
    analysis: Optional[Dict] = None
    error: Optional[str] = None
    processing_time: float = 0.0

class AsyncNewsProcessor:
    """High-performance async news processor with parallel execution"""
    
    def __init__(self, max_workers_content=5, max_workers_ai=3):
        self.max_workers_content = max_workers_content
        self.max_workers_ai = max_workers_ai
        self.timeout_content = 15  # seconds
        self.timeout_ai = 60      # seconds
    
    async def process_news_batch(self, news_items: List[Dict]) -> List[ProcessingResult]:
        """Process news items in parallel with optimized resource usage"""
        logger.info(f"Starting parallel processing of {len(news_items)} items")
        start_time = time.time()
        
        # Phase 1: Parallel content extraction
        content_results = await self._extract_content_batch(news_items)
        
        # Phase 2: Filter successful content and analyze in parallel
        valid_items = [
            (item, result.content) 
            for item, result in zip(news_items, content_results) 
            if result.success and result.content
        ]
        
        analysis_results = await self._analyze_content_batch(valid_items)
        
        # Phase 3: Combine results
        final_results = []
        for i, (item, content_result) in enumerate(zip(news_items, content_results)):
            if not content_result.success:
                final_results.append(content_result)
            else:
                analysis_result = analysis_results.get(i)
                final_results.append(ProcessingResult(
                    url=item['url'],
                    success=analysis_result is not None,
                    content=content_result.content,
                    analysis=analysis_result,
                    processing_time=content_result.processing_time
                ))
        
        total_time = time.time() - start_time
        successful = sum(1 for r in final_results if r.success)
        logger.info(f"Batch processing complete: {successful}/{len(news_items)} successful in {total_time:.2f}s")
        
        return final_results
    
    async def _extract_content_batch(self, news_items: List[Dict]) -> List[ProcessingResult]:
        """Extract content from multiple URLs in parallel"""
        loop = asyncio.get_event_loop()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers_content) as executor:
            tasks = [
                loop.run_in_executor(
                    executor, 
                    self._extract_single_content, 
                    item
                )
                for item in news_items
            ]
            
            return await asyncio.gather(*tasks, return_exceptions=True)
    
    def _extract_single_content(self, item: Dict) -> ProcessingResult:
        """Extract content from a single article with timeout"""
        start_time = time.time()
        
        try:
            from src.services.scraper_service import get_article_content
            
            # Add timeout mechanism
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("Content extraction timeout")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.timeout_content)
            
            try:
                content = get_article_content(item['url'])
                signal.alarm(0)  # Cancel timeout
                
                processing_time = time.time() - start_time
                
                if content and len(content.strip()) > 100:
                    return ProcessingResult(
                        url=item['url'],
                        success=True,
                        content=content,
                        processing_time=processing_time
                    )
                else:
                    return ProcessingResult(
                        url=item['url'],
                        success=False,
                        error="Content too short or empty",
                        processing_time=processing_time
                    )
                    
            except TimeoutError:
                signal.alarm(0)
                return ProcessingResult(
                    url=item['url'],
                    success=False,
                    error="Content extraction timeout",
                    processing_time=time.time() - start_time
                )
                
        except Exception as e:
            return ProcessingResult(
                url=item['url'],
                success=False,
                error=f"Extraction error: {str(e)}",
                processing_time=time.time() - start_time
            )
    
    async def _analyze_content_batch(self, items_with_content: List[tuple]) -> Dict[int, Dict]:
        """Analyze content in parallel with controlled concurrency"""
        if not items_with_content:
            return {}
        
        loop = asyncio.get_event_loop()
        
        # Create semaphore to limit concurrent AI calls
        semaphore = asyncio.Semaphore(self.max_workers_ai)
        
        async def analyze_with_semaphore(index, item, content):
            async with semaphore:
                return await loop.run_in_executor(
                    None, 
                    self._analyze_single_content, 
                    item, 
                    content
                )
        
        tasks = [
            analyze_with_semaphore(i, item, content)
            for i, (item, content) in enumerate(items_with_content)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Map results back to original indices
        analysis_dict = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Analysis error for item {i}: {result}")
            elif result:
                analysis_dict[i] = result
        
        return analysis_dict
    
    def _analyze_single_content(self, item: Dict, content: str) -> Optional[Dict]:
        """Analyze single content with AI"""
        try:
            from src.services.ai_service_market_enhanced import analyze_article_with_market_data as analyze_article
            
            # Add timeout for AI analysis
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("AI analysis timeout")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.timeout_ai)
            
            try:
                result = analyze_article(content)
                signal.alarm(0)
                return result
            except TimeoutError:
                signal.alarm(0)
                logger.warning(f"AI analysis timeout for {item['url']}")
                return None
                
        except Exception as e:
            logger.error(f"AI analysis error for {item['url']}: {e}")
            return None

# Performance monitoring decorator
def monitor_performance(func):
    """Decorator to monitor function performance"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        logger.info(f"Performance: {func.__name__} took {end_time - start_time:.2f} seconds")
        return result
    return wrapper

# Batch processor for database operations
class BatchDatabaseProcessor:
    """Optimized batch database operations"""
    
    def __init__(self, batch_size=50):
        self.batch_size = batch_size
    
    def update_news_batch(self, updates: List[Dict]) -> int:
        """Update multiple news items in a single transaction"""
        if not updates:
            return 0
        
        from src.core.database import get_db_connection
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Use executemany for batch updates
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
                    cursor.executemany('''
                        UPDATE news 
                        SET full_content = ?, ai_summary = ?, impact_score = ?, 
                            is_important = ?, sentiment = ?
                        WHERE url = ?
                    ''', update_data)
                    
                    conn.commit()
                    return len(update_data)
                
                return 0
                
        except Exception as e:
            logger.error(f"Batch update error: {e}")
            return 0

# Global processor instance
async_processor = AsyncNewsProcessor()
batch_db_processor = BatchDatabaseProcessor()
