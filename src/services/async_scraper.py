"""
Async Web Scraper with Browser Pool
High-performance article content extraction using async I/O and browser pooling.

Performance improvements:
- Browser pool: Reuses browser instances instead of launching new ones
- Async processing: Scrapes multiple articles concurrently
- Semaphore limiting: Controls concurrent requests to avoid overwhelming servers
"""

import asyncio
import random
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import aiohttp
from bs4 import BeautifulSoup

# For Playwright async
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[AsyncScraper] Playwright not available. Install with: pip install playwright")

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
]


class BrowserPool:
    """
    Manages a pool of reusable Playwright browser contexts.

    Instead of launching a new browser for each article (2-3s overhead),
    we maintain a pool of pre-launched browsers that can be reused.
    """

    def __init__(self, pool_size: int = 3):
        self.pool_size = pool_size
        self.contexts: asyncio.Queue = asyncio.Queue(maxsize=pool_size)
        self.playwright = None
        self.browser: Optional[Browser] = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Pre-launch browser and create context pool."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            if not PLAYWRIGHT_AVAILABLE:
                raise RuntimeError("Playwright not available")

            print(f"[BrowserPool] Initializing pool with {self.pool_size} contexts...")
            self.playwright = await async_playwright().start()

            # Launch a single browser instance
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )

            # Create multiple browser contexts (like incognito windows)
            for i in range(self.pool_size):
                context = await self.browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={'width': 1920, 'height': 1080}
                )
                await self.contexts.put(context)

            self._initialized = True
            print(f"[BrowserPool] Ready with {self.pool_size} contexts")

    async def acquire(self) -> BrowserContext:
        """Get a browser context from the pool (waits if none available)."""
        if not self._initialized:
            await self.initialize()
        return await self.contexts.get()

    async def release(self, context: BrowserContext):
        """Return a browser context to the pool."""
        # Rotate user agent for next use
        await context.close()
        new_context = await self.browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1920, 'height': 1080}
        )
        await self.contexts.put(new_context)

    async def close(self):
        """Shutdown the pool and close all browsers."""
        if not self._initialized:
            return

        print("[BrowserPool] Shutting down...")

        # Close all contexts
        while not self.contexts.empty():
            context = await self.contexts.get()
            await context.close()

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        self._initialized = False


# Global browser pool instance
_browser_pool: Optional[BrowserPool] = None


async def get_browser_pool() -> BrowserPool:
    """Get or create the global browser pool."""
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = BrowserPool(pool_size=3)
    if not _browser_pool._initialized:
        await _browser_pool.initialize()
    return _browser_pool


def extract_text_from_html(html_content: str) -> str:
    """Clean HTML and extract article text."""
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove unwanted elements
    for junk in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript", "form", "button"]):
        junk.decompose()

    # Extract paragraphs
    paragraphs = soup.find_all('p')
    clean_text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 40])

    return clean_text


async def scrape_with_aiohttp(url: str, timeout: int = 10) -> str:
    """Fast async HTTP scraping using aiohttp."""
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/'
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status != 200:
                    return ""
                html = await response.text()
                return extract_text_from_html(html)
    except Exception as e:
        print(f"   [aiohttp] Failed {url}: {e}")
        return ""


async def scrape_with_playwright_async(url: str, pool: BrowserPool = None) -> str:
    """Async Playwright scraping using browser pool."""
    if pool is None:
        pool = await get_browser_pool()

    context = await pool.acquire()
    text = ""

    try:
        page = await context.new_page()

        try:
            # First attempt: Quick load
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            html_content = await page.content()
            text = extract_text_from_html(html_content)

            # If content is too short, try harder
            if len(text) < 200:
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass

                # Scroll to trigger lazy loading
                await page.evaluate("""
                    async () => {
                        await new Promise((resolve) => {
                            let totalHeight = 0;
                            const distance = 200;
                            const timer = setInterval(() => {
                                window.scrollBy(0, distance);
                                totalHeight += distance;
                                if (totalHeight >= document.body.scrollHeight - window.innerHeight) {
                                    clearInterval(timer);
                                    resolve();
                                }
                            }, 50);
                            // Timeout after 3 seconds
                            setTimeout(() => { clearInterval(timer); resolve(); }, 3000);
                        });
                    }
                """)

                await asyncio.sleep(1)
                html_content = await page.content()
                text = extract_text_from_html(html_content)

        finally:
            await page.close()

    except Exception as e:
        print(f"   [Playwright] Error for {url}: {e}")

    finally:
        await pool.release(context)

    return text


async def scrape_article_async(url: str, use_playwright_fallback: bool = True) -> Tuple[str, str]:
    """
    Scrape a single article asynchronously.

    Returns:
        Tuple of (url, content)
    """
    # Try fast method first
    content = await scrape_with_aiohttp(url)

    if content and len(content) > 300:
        return (url, content)

    # Fallback to Playwright if enabled and available
    if use_playwright_fallback and PLAYWRIGHT_AVAILABLE:
        content = await scrape_with_playwright_async(url)

    return (url, content)


async def scrape_articles_batch(
    urls: List[str],
    max_concurrent: int = 3,
    use_playwright_fallback: bool = True,
    progress_callback = None
) -> Dict[str, str]:
    """
    Scrape multiple articles concurrently with controlled parallelism.

    Args:
        urls: List of URLs to scrape
        max_concurrent: Maximum concurrent scrapes
        use_playwright_fallback: Whether to use Playwright for failed fast scrapes
        progress_callback: Optional callback(completed, total) for progress updates

    Returns:
        Dict of {url: content}
    """
    results = {}
    semaphore = asyncio.Semaphore(max_concurrent)
    completed = 0
    total = len(urls)

    async def scrape_one(url: str) -> Tuple[str, str]:
        nonlocal completed
        async with semaphore:
            result = await scrape_article_async(url, use_playwright_fallback)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
            return result

    # Create tasks for all URLs
    tasks = [scrape_one(url) for url in urls]

    # Run concurrently and gather results
    scraped = await asyncio.gather(*tasks, return_exceptions=True)

    for item in scraped:
        if isinstance(item, tuple):
            url, content = item
            results[url] = content
        elif isinstance(item, Exception):
            print(f"   [Batch] Task exception: {item}")

    return results


def scrape_batch_sync(urls: List[str], max_concurrent: int = 3) -> Dict[str, str]:
    """
    Synchronous wrapper for batch scraping.
    Can be called from synchronous code.
    """
    return asyncio.run(scrape_articles_batch(urls, max_concurrent))


async def cleanup_browser_pool():
    """Cleanup the global browser pool."""
    global _browser_pool
    if _browser_pool:
        await _browser_pool.close()
        _browser_pool = None


# For easy integration with existing code
def get_article_content_async(url: str) -> str:
    """
    Async-compatible single article scrape.
    Can be awaited or run with asyncio.run()
    """
    async def _scrape():
        url_result, content = await scrape_article_async(url)
        return content

    return asyncio.run(_scrape())
