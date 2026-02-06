"""
Sentiment Aggregator Module
Combines sentiment from multiple sources into composite scores with consensus tracking.
"""

import statistics
from datetime import datetime, timedelta
from config import SENTIMENT_WEIGHTS
import database
from modules.alphavantage_fetcher import fetch_ticker_sentiment
from modules.stocktwits_fetcher import fetch_social_sentiment
from modules.reddit_fetcher import fetch_ticker_velocity


class SentimentAggregator:
    """Aggregates sentiment from multiple sources with weighted scoring."""

    def __init__(self, weights=None):
        """
        Initialize aggregator with source weights.

        Args:
            weights: Dict of {source: weight} where weights sum to ~1.0
        """
        self.weights = weights or SENTIMENT_WEIGHTS

    def fetch_all_sources(self, ticker):
        """
        Fetch sentiment from all available sources for a ticker.

        Args:
            ticker: Stock symbol

        Returns:
            dict of {source: sentiment_data}
        """
        results = {}

        # Fetch from each source (non-blocking to handle rate limits gracefully)
        try:
            av_result = fetch_ticker_sentiment(ticker)
            if av_result:
                results['alphavantage'] = av_result
        except Exception as e:
            print(f"Alpha Vantage fetch error for {ticker}: {e}")

        try:
            st_result = fetch_social_sentiment(ticker)
            if st_result:
                results['stocktwits'] = st_result
        except Exception as e:
            print(f"StockTwits fetch error for {ticker}: {e}")

        try:
            reddit_result = fetch_ticker_velocity(ticker)
            if reddit_result:
                results['reddit'] = reddit_result
        except Exception as e:
            print(f"Reddit fetch error for {ticker}: {e}")

        return results

    def get_cached_sentiment(self, ticker, max_age_hours=1):
        """
        Get cached sentiment from database if fresh enough.

        Args:
            ticker: Stock symbol
            max_age_hours: Maximum age of cached data

        Returns:
            dict of {source: sentiment_data} or None if stale
        """
        return database.get_latest_sentiment_by_source(ticker)

    def calculate_composite(self, ticker, use_cache=True, max_cache_age=1):
        """
        Calculate composite sentiment score for a ticker.

        Args:
            ticker: Stock symbol
            use_cache: Whether to use cached data
            max_cache_age: Max cache age in hours

        Returns:
            dict with composite score, direction, confidence, etc.
        """
        # Get sentiment from sources
        if use_cache:
            sources = self.get_cached_sentiment(ticker, max_cache_age)
            if not sources:
                sources = self.fetch_all_sources(ticker)
        else:
            sources = self.fetch_all_sources(ticker)

        if not sources:
            return None

        # Also include Ollama AI sentiment from news analysis
        ollama_sentiment = self._get_ollama_sentiment(ticker)
        if ollama_sentiment:
            sources['ollama_ai'] = ollama_sentiment

        # Calculate weighted composite
        return self._aggregate_sources(ticker, sources)

    def _get_ollama_sentiment(self, ticker):
        """
        Get sentiment from Ollama AI news analysis.

        Args:
            ticker: Stock symbol

        Returns:
            dict with sentiment data or None
        """
        # Query recent news for this ticker
        news_items = database.get_news_with_signals()

        ticker_news = []
        for item in news_items:
            if item.get('tickers') and ticker.upper() in [t.upper() for t in item['tickers']]:
                ticker_news.append(item)

        if not ticker_news:
            return None

        # Aggregate direction signals
        bullish = sum(1 for n in ticker_news if n.get('direction') == 'bullish')
        bearish = sum(1 for n in ticker_news if n.get('direction') == 'bearish')
        total = len(ticker_news)

        # Calculate sentiment score
        if total > 0:
            # Convert direction counts to score
            score = (bullish - bearish) / total
            confidence = sum(n.get('confidence', 0) for n in ticker_news) / total
        else:
            score = 0
            confidence = 0

        return {
            'ticker': ticker,
            'source': 'ollama_ai',
            'sentiment_score': score,
            'confidence': confidence,
            'volume': total,
            'metadata': {
                'bullish_count': bullish,
                'bearish_count': bearish,
                'neutral_count': total - bullish - bearish
            }
        }

    def _aggregate_sources(self, ticker, sources):
        """
        Aggregate sentiment from multiple sources with weighting.

        Args:
            ticker: Stock symbol
            sources: dict of {source: sentiment_data}

        Returns:
            dict with aggregated sentiment data
        """
        if not sources:
            return None

        # Collect scores and weights
        weighted_scores = []
        total_weight = 0
        source_breakdown = {}

        for source, data in sources.items():
            score = data.get('sentiment_score', 0)
            weight = self.weights.get(source, 0.1)

            # Adjust weight by source confidence
            source_confidence = data.get('confidence', 0.5)
            adjusted_weight = weight * source_confidence

            weighted_scores.append((score, adjusted_weight))
            total_weight += adjusted_weight

            source_breakdown[source] = {
                'score': score,
                'confidence': source_confidence,
                'weight': weight,
                'volume': data.get('volume', 0)
            }

        # Calculate weighted average
        if total_weight > 0:
            composite_score = sum(s * w for s, w in weighted_scores) / total_weight
        else:
            composite_score = sum(s for s, w in weighted_scores) / len(weighted_scores)

        # Clamp to -1 to 1
        composite_score = max(-1.0, min(1.0, composite_score))

        # Calculate consensus strength (1 - standard deviation of scores)
        scores_only = [s for s, w in weighted_scores]
        if len(scores_only) >= 2:
            try:
                stdev = statistics.stdev(scores_only)
                consensus = max(0, 1 - stdev)
            except statistics.StatisticsError:
                consensus = 1.0
        else:
            consensus = 0.5  # Low confidence with single source

        # Determine direction
        direction = self._score_to_direction(composite_score)

        # Calculate overall confidence
        confidence = min(1.0, total_weight) * (len(sources) / 4)  # Max 4 sources

        # Calculate velocity if we have historical data
        velocity, momentum = self._calculate_velocity(ticker)

        result = {
            'ticker': ticker,
            'composite_score': round(composite_score, 4),
            'composite_direction': direction,
            'confidence': round(confidence, 4),
            'consensus_strength': round(consensus, 4),
            'momentum': momentum,
            'velocity': velocity,
            'source_breakdown': source_breakdown,
            'source_count': len(sources)
        }

        # Save to database
        database.save_ticker_sentiment(
            ticker=ticker,
            composite_score=result['composite_score'],
            composite_direction=result['composite_direction'],
            confidence=result['confidence'],
            consensus_strength=result['consensus_strength'],
            momentum=result['momentum'],
            velocity=result['velocity'],
            source_breakdown=result['source_breakdown']
        )

        return result

    def _score_to_direction(self, score):
        """Convert composite score to 5-level direction."""
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

    def _calculate_velocity(self, ticker):
        """
        Calculate sentiment velocity (rate of change).

        Args:
            ticker: Stock symbol

        Returns:
            tuple of (velocity, momentum_label)
        """
        # Get historical snapshots
        snapshots = database.get_sentiment_snapshots(ticker, hours=48)

        if len(snapshots) < 2:
            return 0, 'stable'

        # Sort by timestamp
        snapshots.sort(key=lambda x: x.get('timestamp', ''))

        # Get scores from 24h ago vs now
        now = datetime.now()
        recent_scores = []
        old_scores = []

        for snap in snapshots:
            try:
                ts = datetime.strptime(snap['timestamp'], '%Y-%m-%d %H:%M:%S')
                age_hours = (now - ts).total_seconds() / 3600

                if age_hours <= 12:
                    recent_scores.append(snap.get('sentiment_score', 0))
                elif age_hours >= 24:
                    old_scores.append(snap.get('sentiment_score', 0))
            except (ValueError, TypeError):
                continue

        if not recent_scores or not old_scores:
            return 0, 'stable'

        recent_avg = sum(recent_scores) / len(recent_scores)
        old_avg = sum(old_scores) / len(old_scores)

        velocity = recent_avg - old_avg

        # Classify momentum
        if velocity > 0.02:
            momentum = 'rising'
        elif velocity < -0.02:
            momentum = 'falling'
        else:
            momentum = 'stable'

        return round(velocity, 4), momentum


def aggregate_ticker_sentiment(ticker, use_cache=True):
    """
    Convenience function to aggregate sentiment for a ticker.

    Args:
        ticker: Stock symbol
        use_cache: Whether to use cached data

    Returns:
        dict with aggregated sentiment
    """
    aggregator = SentimentAggregator()
    return aggregator.calculate_composite(ticker, use_cache=use_cache)


def aggregate_multiple_tickers(tickers, use_cache=True):
    """
    Aggregate sentiment for multiple tickers.

    Args:
        tickers: List of stock symbols
        use_cache: Whether to use cached data

    Returns:
        dict of {ticker: sentiment_data}
    """
    aggregator = SentimentAggregator()
    results = {}

    for ticker in tickers:
        try:
            result = aggregator.calculate_composite(ticker, use_cache=use_cache)
            if result:
                results[ticker] = result
        except Exception as e:
            print(f"Error aggregating sentiment for {ticker}: {e}")

    return results


def get_market_sentiment_summary():
    """
    Get overall market sentiment summary from all tracked tickers.

    Returns:
        dict with market-wide sentiment metrics
    """
    all_sentiments = database.get_all_ticker_sentiments()

    if not all_sentiments:
        return None

    scores = [s.get('composite_score', 0) for s in all_sentiments if s.get('composite_score') is not None]

    if not scores:
        return None

    # Calculate distributions
    strong_bullish = sum(1 for s in scores if s >= 0.6)
    bullish = sum(1 for s in scores if 0.2 <= s < 0.6)
    neutral = sum(1 for s in scores if -0.2 < s < 0.2)
    bearish = sum(1 for s in scores if -0.6 < s <= -0.2)
    strong_bearish = sum(1 for s in scores if s <= -0.6)

    total = len(scores)
    bullish_ratio = (strong_bullish + bullish) / total if total > 0 else 0.5

    return {
        'avg_sentiment': round(sum(scores) / len(scores), 4),
        'median_sentiment': round(statistics.median(scores), 4),
        'bullish_ratio': round(bullish_ratio, 4),
        'distribution': {
            'strong_bullish': strong_bullish,
            'bullish': bullish,
            'neutral': neutral,
            'bearish': bearish,
            'strong_bearish': strong_bearish
        },
        'total_tickers': total
    }
