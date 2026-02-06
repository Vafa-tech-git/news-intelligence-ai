"""
StockTwits Sentiment Fetcher
Fetches retail investor sentiment from StockTwits API.
"""

import requests
from modules.rate_limiter import acquire, can_request
import database


def normalize_bullish_percentage(bullish_pct):
    """
    Normalize StockTwits bullish percentage (0-100) to -1.0 to 1.0.
    Formula: (bullish% - 50) / 50
    50% bullish = 0.0 (neutral)
    100% bullish = 1.0
    0% bullish = -1.0
    """
    if bullish_pct is None:
        return None
    return (bullish_pct - 50) / 50


def fetch_social_sentiment(ticker):
    """
    Fetch social sentiment for a ticker from StockTwits.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')

    Returns:
        dict with sentiment data or None if failed
    """
    if not can_request('stocktwits'):
        print(f"⚠️ StockTwits rate limit reached")
        return None

    if not acquire('stocktwits', blocking=False):
        return None

    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get('response', {}).get('status') != 200:
            return None

        symbol_info = data.get('symbol', {})
        messages = data.get('messages', [])

        # Get sentiment from messages
        bullish_count = 0
        bearish_count = 0

        for msg in messages:
            sentiment = msg.get('entities', {}).get('sentiment', {})
            if sentiment:
                if sentiment.get('basic') == 'Bullish':
                    bullish_count += 1
                elif sentiment.get('basic') == 'Bearish':
                    bearish_count += 1

        total_sentiment_msgs = bullish_count + bearish_count

        # Calculate bullish percentage
        if total_sentiment_msgs > 0:
            bullish_pct = (bullish_count / total_sentiment_msgs) * 100
        else:
            bullish_pct = 50  # Neutral if no sentiment data

        normalized_score = normalize_bullish_percentage(bullish_pct)

        # Confidence based on volume of messages with sentiment
        confidence = min(1.0, total_sentiment_msgs / 20)

        result = {
            'ticker': ticker,
            'source': 'stocktwits',
            'raw_score': bullish_pct,
            'sentiment_score': normalized_score,
            'confidence': confidence,
            'volume': len(messages),
            'metadata': {
                'bullish_count': bullish_count,
                'bearish_count': bearish_count,
                'total_messages': len(messages),
                'sentiment_messages': total_sentiment_msgs,
                'watchlist_count': symbol_info.get('watchlist_count', 0)
            }
        }

        # Save to database
        database.save_sentiment_snapshot(
            ticker=ticker,
            source='stocktwits',
            sentiment_score=normalized_score,
            raw_score=bullish_pct,
            confidence=confidence,
            volume=len(messages),
            metadata=result['metadata']
        )

        return result

    except requests.exceptions.Timeout:
        print(f"⚠️ StockTwits timeout for {ticker}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"⚠️ StockTwits request error for {ticker}: {e}")
        return None
    except Exception as e:
        print(f"⚠️ StockTwits error for {ticker}: {e}")
        return None


def fetch_trending_tickers():
    """
    Fetch trending tickers from StockTwits.

    Returns:
        list of trending ticker symbols or empty list if failed
    """
    if not acquire('stocktwits', blocking=False):
        return []

    try:
        url = "https://api.stocktwits.com/api/2/trending/symbols.json"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get('response', {}).get('status') != 200:
            return []

        symbols = data.get('symbols', [])
        return [s.get('symbol') for s in symbols if s.get('symbol')]

    except Exception as e:
        print(f"⚠️ StockTwits trending error: {e}")
        return []


def fetch_watchlist_count(ticker):
    """
    Get watchlist count for a ticker (indicator of retail interest).

    Args:
        ticker: Stock symbol

    Returns:
        int watchlist count or 0 if failed
    """
    try:
        url = f"https://api.stocktwits.com/api/2/symbols/{ticker}.json"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        return data.get('symbol', {}).get('watchlist_count', 0)

    except Exception:
        return 0
