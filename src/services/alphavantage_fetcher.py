"""
Alpha Vantage Sentiment Fetcher
Fetches pre-computed sentiment scores from Alpha Vantage News Sentiment API.
"""

import requests
from config import ALPHAVANTAGE_API_KEY
from modules.rate_limiter import acquire, can_request, get_remaining
import database

# Alpha Vantage sentiment scale is -0.35 to 0.35
# Normalize to -1.0 to 1.0
NORMALIZATION_FACTOR = 2.86  # 1 / 0.35


def normalize_score(raw_score):
    """Normalize Alpha Vantage score (-0.35 to 0.35) to -1.0 to 1.0."""
    if raw_score is None:
        return None
    normalized = raw_score * NORMALIZATION_FACTOR
    return max(-1.0, min(1.0, normalized))


def fetch_ticker_sentiment(ticker):
    """
    Fetch sentiment for a specific ticker from Alpha Vantage.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')

    Returns:
        dict with sentiment data or None if failed
    """
    if not ALPHAVANTAGE_API_KEY:
        print("⚠️ Alpha Vantage API key not configured")
        return None

    if not can_request('alphavantage'):
        remaining = get_remaining('alphavantage')
        print(f"⚠️ Alpha Vantage rate limit reached. Remaining: {remaining}")
        return None

    if not acquire('alphavantage', blocking=False):
        return None

    try:
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'NEWS_SENTIMENT',
            'tickers': ticker,
            'apikey': ALPHAVANTAGE_API_KEY,
            'limit': 50  # Get recent news
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if 'feed' not in data:
            if 'Note' in data:
                print(f"⚠️ Alpha Vantage rate limit: {data['Note']}")
            elif 'Error Message' in data:
                print(f"⚠️ Alpha Vantage error: {data['Error Message']}")
            return None

        # Process news items and aggregate sentiment
        articles = data.get('feed', [])
        if not articles:
            return None

        # Find sentiment scores specific to this ticker
        ticker_sentiments = []
        for article in articles:
            ticker_sentiment = article.get('ticker_sentiment', [])
            for ts in ticker_sentiment:
                if ts.get('ticker', '').upper() == ticker.upper():
                    score = float(ts.get('ticker_sentiment_score', 0))
                    relevance = float(ts.get('relevance_score', 0))
                    ticker_sentiments.append({
                        'score': score,
                        'relevance': relevance,
                        'label': ts.get('ticker_sentiment_label', '')
                    })

        if not ticker_sentiments:
            return None

        # Calculate weighted average by relevance
        total_weight = sum(s['relevance'] for s in ticker_sentiments)
        if total_weight > 0:
            weighted_score = sum(s['score'] * s['relevance'] for s in ticker_sentiments) / total_weight
        else:
            weighted_score = sum(s['score'] for s in ticker_sentiments) / len(ticker_sentiments)

        normalized_score = normalize_score(weighted_score)

        # Determine confidence based on article count and relevance
        confidence = min(1.0, len(ticker_sentiments) / 10) * min(1.0, total_weight / 5)

        result = {
            'ticker': ticker,
            'source': 'alphavantage',
            'raw_score': weighted_score,
            'sentiment_score': normalized_score,
            'confidence': confidence,
            'volume': len(ticker_sentiments),
            'metadata': {
                'article_count': len(articles),
                'ticker_mentions': len(ticker_sentiments),
                'avg_relevance': total_weight / len(ticker_sentiments) if ticker_sentiments else 0
            }
        }

        # Save to database
        database.save_sentiment_snapshot(
            ticker=ticker,
            source='alphavantage',
            sentiment_score=normalized_score,
            raw_score=weighted_score,
            confidence=confidence,
            volume=len(ticker_sentiments),
            metadata=result['metadata']
        )

        return result

    except requests.exceptions.Timeout:
        print(f"⚠️ Alpha Vantage timeout for {ticker}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Alpha Vantage request error for {ticker}: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Alpha Vantage error for {ticker}: {e}")
        return None


def fetch_market_news_sentiment():
    """
    Fetch general market news sentiment (not ticker-specific).

    Returns:
        dict with market sentiment data or None if failed
    """
    if not ALPHAVANTAGE_API_KEY:
        print("⚠️ Alpha Vantage API key not configured")
        return None

    if not acquire('alphavantage', blocking=False):
        print("⚠️ Alpha Vantage rate limit reached")
        return None

    try:
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'NEWS_SENTIMENT',
            'topics': 'financial_markets',
            'apikey': ALPHAVANTAGE_API_KEY,
            'limit': 50
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if 'feed' not in data:
            return None

        articles = data.get('feed', [])
        if not articles:
            return None

        # Aggregate overall sentiment
        scores = []
        for article in articles:
            score = float(article.get('overall_sentiment_score', 0))
            scores.append(score)

        if not scores:
            return None

        avg_score = sum(scores) / len(scores)
        normalized_score = normalize_score(avg_score)

        return {
            'source': 'alphavantage',
            'raw_score': avg_score,
            'sentiment_score': normalized_score,
            'article_count': len(articles),
            'metadata': {
                'topics': 'financial_markets'
            }
        }

    except Exception as e:
        print(f"⚠️ Alpha Vantage market sentiment error: {e}")
        return None


def get_sentiment_label(score):
    """Convert normalized score to human-readable label."""
    if score >= 0.6:
        return 'strong_bullish'
    elif score >= 0.2:
        return 'bullish'
    elif score > -0.2:
        return 'neutral'
    elif score > -0.6:
        return 'bearish'
    else:
        return 'strong_bearish'
