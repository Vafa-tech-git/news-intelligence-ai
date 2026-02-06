"""
Market Analyzer Module
Analyzes market conditions, regime detection, and sentiment-market correlation.
"""

import statistics
from datetime import datetime, timedelta
import database
from modules.economic_health import get_economic_health


class MarketAnalyzer:
    """Analyzes market context for signal generation."""

    def __init__(self):
        """Initialize market analyzer."""
        self.indices = {
            '^GSPC': 'S&P 500',
            '^IXIC': 'NASDAQ',
            '^DJI': 'Dow Jones'
        }

    def analyze_market_context(self):
        """
        Analyze current market conditions.

        Returns:
            dict with regime, volatility, mood, etc.
        """
        context = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'regime': 'neutral',
            'volatility_level': 15,
            'sp500_pct_change': 0,
            'nasdaq_pct_change': 0,
            'mood_score': 50,
            'bullish_ratio': 0.5,
            'sector_sentiment': {},
            'economic_health': None,
            'economic_regime': None
        }

        # Get market data
        sp500_data = database.get_market_data('^GSPC')
        nasdaq_data = database.get_market_data('^IXIC')

        if sp500_data:
            context.update(self._analyze_index(sp500_data, 'sp500'))

        if nasdaq_data:
            nasdaq_analysis = self._analyze_index(nasdaq_data, 'nasdaq')
            context['nasdaq_pct_change'] = nasdaq_analysis.get('nasdaq_pct_change', 0)

        # Determine regime from analysis
        context['regime'] = self._determine_regime(context)

        # Calculate market mood
        context['mood_score'] = self._calculate_mood_score(context)

        # Get sentiment distribution
        sentiment_summary = self._get_sentiment_summary()
        if sentiment_summary:
            context['bullish_ratio'] = sentiment_summary.get('bullish_ratio', 0.5)
            context['sector_sentiment'] = self._get_sector_sentiment()

        # Get economic health
        try:
            economic_health = get_economic_health()
            if economic_health:
                context['economic_health'] = {
                    'overall_score': economic_health.get('overall_score'),
                    'regime': economic_health.get('regime'),
                    'recession_probability': economic_health.get('recession_probability'),
                    'recession_warning': economic_health.get('recession_warning', False)
                }
                context['economic_regime'] = economic_health.get('regime')
        except Exception:
            pass  # Continue without economic data

        # Save context
        database.save_market_context(
            date=context['date'],
            regime=context['regime'],
            volatility_level=context['volatility_level'],
            sp500_pct_change=context['sp500_pct_change'],
            nasdaq_pct_change=context['nasdaq_pct_change'],
            mood_score=context['mood_score'],
            bullish_ratio=context['bullish_ratio'],
            sector_sentiment=context['sector_sentiment']
        )

        return context

    def _analyze_index(self, data, prefix):
        """
        Analyze a market index.

        Args:
            data: List of OHLCV dicts
            prefix: Prefix for result keys

        Returns:
            dict with analysis results
        """
        result = {}

        if not data or len(data) < 2:
            return result

        # Sort by date
        data = sorted(data, key=lambda x: x.get('date', ''))

        # Get recent data
        recent = data[-1] if data else {}
        prev = data[-2] if len(data) >= 2 else recent

        # Daily change
        if recent.get('close') and prev.get('close'):
            pct_change = ((recent['close'] - prev['close']) / prev['close']) * 100
            result[f'{prefix}_pct_change'] = round(pct_change, 2)

        # Calculate volatility (20-day realized volatility)
        if len(data) >= 20:
            returns = []
            for i in range(1, min(21, len(data))):
                if data[-i].get('close') and data[-i-1].get('close'):
                    ret = (data[-i]['close'] - data[-i-1]['close']) / data[-i-1]['close']
                    returns.append(ret)

            if len(returns) >= 5:
                try:
                    stdev = statistics.stdev(returns)
                    # Annualize (252 trading days)
                    volatility = stdev * (252 ** 0.5) * 100
                    result['volatility_level'] = round(volatility, 2)
                except statistics.StatisticsError:
                    pass

        # Check for correction (drop from recent high)
        if len(data) >= 60:
            recent_high = max(d.get('high', 0) for d in data[-60:])
            current = recent.get('close', 0)
            if recent_high > 0:
                drawdown = ((current - recent_high) / recent_high) * 100
                result[f'{prefix}_drawdown'] = round(drawdown, 2)

        # 200-day moving average check
        if len(data) >= 200:
            closes = [d.get('close', 0) for d in data[-200:] if d.get('close')]
            if closes:
                ma200 = sum(closes) / len(closes)
                current_close = recent.get('close', 0)
                result[f'{prefix}_above_ma200'] = current_close > ma200

        return result

    def _determine_regime(self, context):
        """
        Determine market regime based on indicators.

        Returns:
            str: 'bull', 'bear', 'sideways', or 'volatile'
        """
        volatility = context.get('volatility_level', 15)
        sp500_change = context.get('sp500_pct_change', 0)
        above_ma200 = context.get('sp500_above_ma200', True)
        drawdown = context.get('sp500_drawdown', 0)

        # High volatility regime
        if volatility >= 25:
            return 'volatile'

        # Bear market: below 200-day MA or in correction
        if not above_ma200 or drawdown <= -10:
            return 'bear'

        # Bull market: above 200-day MA with positive momentum
        if above_ma200 and sp500_change > -2:
            if drawdown > -5:
                return 'bull'

        return 'sideways'

    def _calculate_mood_score(self, context):
        """
        Calculate market mood score (0-100, Fear/Greed style).

        0-25: Extreme Fear
        25-45: Fear
        45-55: Neutral
        55-75: Greed
        75-100: Extreme Greed
        """
        score = 50  # Start neutral

        # Volatility factor (30%)
        volatility = context.get('volatility_level', 15)
        if volatility <= 12:
            score += 15  # Low vol = complacency/greed
        elif volatility <= 15:
            score += 5
        elif volatility >= 25:
            score -= 15  # High vol = fear
        elif volatility >= 20:
            score -= 10

        # Market momentum factor (25%)
        sp500_change = context.get('sp500_pct_change', 0)
        if sp500_change >= 2:
            score += 12
        elif sp500_change >= 0.5:
            score += 6
        elif sp500_change <= -2:
            score -= 12
        elif sp500_change <= -0.5:
            score -= 6

        # Drawdown factor (20%)
        drawdown = context.get('sp500_drawdown', 0)
        if drawdown <= -10:
            score -= 10
        elif drawdown <= -5:
            score -= 5
        elif drawdown > -2:
            score += 5

        # Sentiment distribution factor (25%)
        bullish_ratio = context.get('bullish_ratio', 0.5)
        score += (bullish_ratio - 0.5) * 25

        # Economic health factor (10% bonus/penalty)
        economic_health = context.get('economic_health')
        if economic_health:
            econ_score = economic_health.get('overall_score', 50)
            econ_regime = economic_health.get('regime', '')

            # Adjust mood based on economic health
            if econ_score >= 70:
                score += 5  # Strong economy = confidence
            elif econ_score <= 40:
                score -= 5  # Weak economy = fear

            # Recession warning adds fear
            if economic_health.get('recession_warning'):
                score -= 10

        return round(max(0, min(100, score)), 1)

    def _get_sentiment_summary(self):
        """Get sentiment distribution from tracked tickers."""
        from modules.sentiment_aggregator import get_market_sentiment_summary
        return get_market_sentiment_summary()

    def _get_sector_sentiment(self):
        """Calculate sentiment by sector."""
        all_sentiments = database.get_all_ticker_sentiments()
        news = database.get_news_with_signals()

        sector_scores = {}
        sector_counts = {}

        # Aggregate from news (which has sector info)
        for item in news:
            sector = item.get('sector')
            if not sector:
                continue

            tickers = item.get('tickers', [])
            direction = item.get('direction', 'neutral')

            # Convert direction to score
            score = {'bullish': 0.5, 'bearish': -0.5, 'neutral': 0}.get(direction, 0)

            if sector not in sector_scores:
                sector_scores[sector] = 0
                sector_counts[sector] = 0

            sector_scores[sector] += score
            sector_counts[sector] += 1

        # Calculate averages
        result = {}
        for sector in sector_scores:
            if sector_counts[sector] > 0:
                avg = sector_scores[sector] / sector_counts[sector]
                result[sector] = round(avg, 4)

        return result

    def is_correction(self, threshold=-5):
        """
        Check if market is in correction territory.

        Args:
            threshold: Percentage drop threshold (default -5%)

        Returns:
            bool
        """
        context = database.get_latest_market_context()
        if context:
            drawdown = context.get('sp500_drawdown', 0)
            return drawdown <= threshold
        return False

    def is_extended_rally(self, days=60):
        """
        Check if market has been rallying without significant pullback.

        Args:
            days: Number of days to check

        Returns:
            bool
        """
        data = database.get_market_data('^GSPC')
        if not data or len(data) < days:
            return False

        recent_data = data[-days:]

        # Check for any daily drop > 5%
        for d in recent_data:
            if d.get('pct_change', 0) <= -5:
                return False

        return True

    def get_regime_label(self, regime):
        """Get human-readable regime label."""
        labels = {
            'bull': 'Bull Market',
            'bear': 'Bear Market',
            'sideways': 'Range-Bound',
            'volatile': 'High Volatility'
        }
        return labels.get(regime, regime)

    def get_mood_label(self, score):
        """Get human-readable mood label."""
        if score <= 25:
            return 'Extreme Fear'
        elif score <= 45:
            return 'Fear'
        elif score <= 55:
            return 'Neutral'
        elif score <= 75:
            return 'Greed'
        else:
            return 'Extreme Greed'


def analyze_market():
    """Convenience function to analyze market context."""
    analyzer = MarketAnalyzer()
    return analyzer.analyze_market_context()


def get_market_context():
    """Get current market context (cached or fresh)."""
    cached = database.get_latest_market_context()
    if cached:
        return cached
    return analyze_market()


def is_buy_opportunity():
    """Check if market conditions favor buying."""
    context = get_market_context()
    if not context:
        return False, []

    reasons = []

    # Check for correction
    analyzer = MarketAnalyzer()
    if analyzer.is_correction():
        reasons.append("Market in correction territory")

    # Check volatility
    if context.get('volatility_level', 15) >= 20:
        reasons.append("Elevated volatility (fear)")

    # Check mood
    if context.get('mood_score', 50) <= 35:
        reasons.append("Fear sentiment elevated")

    return len(reasons) >= 2, reasons


def is_sell_opportunity():
    """Check if market conditions favor selling."""
    context = get_market_context()
    if not context:
        return False, []

    reasons = []

    # Check for extended rally
    analyzer = MarketAnalyzer()
    if analyzer.is_extended_rally():
        reasons.append("Extended rally without pullback")

    # Check volatility
    if context.get('volatility_level', 15) <= 12:
        reasons.append("Low volatility (complacency)")

    # Check mood
    if context.get('mood_score', 50) >= 70:
        reasons.append("Greed sentiment elevated")

    return len(reasons) >= 2, reasons
