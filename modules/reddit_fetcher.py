"""
Reddit Sentiment Fetcher via ApeWisdom API
Tracks stock mentions and sentiment from WallStreetBets and other stock subreddits.
"""

import requests
import statistics
from modules.rate_limiter import acquire, can_request
import database


def fetch_reddit_mentions(limit=50):
    """
    Fetch top mentioned stocks from Reddit via ApeWisdom.

    Args:
        limit: Number of stocks to fetch

    Returns:
        list of dicts with ticker, mentions, rank info
    """
    if not acquire('apewisdom', blocking=False):
        print("⚠️ ApeWisdom rate limit reached")
        return []

    try:
        url = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/1"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        results = data.get('results', [])[:limit]

        processed = []
        for item in results:
            processed.append({
                'ticker': item.get('ticker', ''),
                'name': item.get('name', ''),
                'mentions': item.get('mentions', 0),
                'rank': item.get('rank', 0),
                'rank_24h_ago': item.get('rank_24h_ago', 0),
                'mentions_24h_ago': item.get('mentions_24h_ago', 0)
            })

        return processed

    except requests.exceptions.Timeout:
        print("⚠️ ApeWisdom timeout")
        return []
    except requests.exceptions.RequestException as e:
        print(f"⚠️ ApeWisdom request error: {e}")
        return []
    except Exception as e:
        print(f"⚠️ ApeWisdom error: {e}")
        return []


def calculate_velocity_zscore(current_mentions, previous_mentions, all_velocities=None):
    """
    Calculate z-score for mention velocity.
    Positive z-score = above average momentum
    Negative z-score = below average momentum

    Args:
        current_mentions: Current mention count
        previous_mentions: Mention count 24h ago
        all_velocities: List of all velocities for z-score calculation

    Returns:
        float z-score or raw velocity if no baseline provided
    """
    if previous_mentions <= 0:
        velocity = current_mentions  # Treat as all new mentions
    else:
        velocity = (current_mentions - previous_mentions) / previous_mentions

    if all_velocities and len(all_velocities) >= 3:
        try:
            mean = statistics.mean(all_velocities)
            stdev = statistics.stdev(all_velocities)
            if stdev > 0:
                return (velocity - mean) / stdev
        except statistics.StatisticsError:
            pass

    # Return clamped velocity as fallback (-1 to 1 scale)
    return max(-1.0, min(1.0, velocity))


def fetch_ticker_velocity(ticker):
    """
    Fetch mention velocity for a specific ticker from Reddit.

    Args:
        ticker: Stock symbol

    Returns:
        dict with velocity data or None if ticker not found
    """
    mentions_data = fetch_reddit_mentions(limit=100)
    if not mentions_data:
        return None

    # Find the ticker in results
    ticker_data = None
    for item in mentions_data:
        if item['ticker'].upper() == ticker.upper():
            ticker_data = item
            break

    if not ticker_data:
        return None

    # Calculate velocities for all tickers to compute z-score
    all_velocities = []
    for item in mentions_data:
        prev = item.get('mentions_24h_ago', 0)
        curr = item.get('mentions', 0)
        if prev > 0:
            vel = (curr - prev) / prev
            all_velocities.append(vel)

    # Calculate z-score for this ticker
    current = ticker_data.get('mentions', 0)
    previous = ticker_data.get('mentions_24h_ago', 0)
    velocity_zscore = calculate_velocity_zscore(current, previous, all_velocities)

    # Normalize z-score to -1 to 1 range (most z-scores fall within -3 to 3)
    normalized_score = max(-1.0, min(1.0, velocity_zscore / 3))

    # Confidence based on mention volume
    confidence = min(1.0, current / 100)

    # Rank change as additional signal
    rank_change = ticker_data.get('rank_24h_ago', 0) - ticker_data.get('rank', 0)

    result = {
        'ticker': ticker,
        'source': 'reddit',
        'raw_score': velocity_zscore,
        'sentiment_score': normalized_score,
        'confidence': confidence,
        'volume': current,
        'metadata': {
            'mentions': current,
            'mentions_24h_ago': previous,
            'rank': ticker_data.get('rank', 0),
            'rank_24h_ago': ticker_data.get('rank_24h_ago', 0),
            'rank_change': rank_change,
            'velocity_raw': velocity_zscore
        }
    }

    # Save to database
    database.save_sentiment_snapshot(
        ticker=ticker,
        source='reddit',
        sentiment_score=normalized_score,
        raw_score=velocity_zscore,
        confidence=confidence,
        volume=current,
        metadata=result['metadata']
    )

    return result


def fetch_trending_reddit():
    """
    Get trending stocks from Reddit with momentum data.

    Returns:
        list of dicts with ticker and momentum info
    """
    mentions_data = fetch_reddit_mentions(limit=20)
    if not mentions_data:
        return []

    trending = []
    for item in mentions_data:
        current = item.get('mentions', 0)
        previous = item.get('mentions_24h_ago', 0)

        if previous > 0:
            velocity = ((current - previous) / previous) * 100
        else:
            velocity = 100 if current > 0 else 0

        rank_change = item.get('rank_24h_ago', 0) - item.get('rank', 0)

        trending.append({
            'ticker': item['ticker'],
            'name': item.get('name', ''),
            'mentions': current,
            'velocity_pct': round(velocity, 1),
            'rank': item.get('rank', 0),
            'rank_change': rank_change,
            'momentum': 'rising' if velocity > 10 else 'falling' if velocity < -10 else 'stable'
        })

    return trending


def get_wsb_sentiment(ticker):
    """
    Get WallStreetBets-specific sentiment for a ticker.
    This is a convenience wrapper that focuses on WSB data.

    Args:
        ticker: Stock symbol

    Returns:
        dict with sentiment data or None
    """
    return fetch_ticker_velocity(ticker)
