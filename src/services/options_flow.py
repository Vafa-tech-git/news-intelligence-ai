"""
Options Flow Analysis Module
Track unusual options activity for sentiment signals.

Options flow analysis provides insight into what sophisticated traders expect:
- High put/call ratio = Bearish sentiment
- Unusual call volume = Potential bullish catalyst expected
- Large block trades = Institutional positioning
- Sweeps = Urgency (trader willing to pay higher prices for immediate execution)
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from statistics import mean
import math

import database


class OptionsFlowAnalyzer:
    """Analyze options flow for trading signals."""

    # Thresholds for unusual activity
    UNUSUAL_VOLUME_MULTIPLIER = 2.0  # 2x average volume
    LARGE_BLOCK_THRESHOLD = 100  # Contracts
    SWEEP_SIZE_THRESHOLD = 50  # Minimum contracts for sweep consideration

    def __init__(self):
        # In a real implementation, this would connect to an options data provider
        # (e.g., Polygon.io, TDAmeritrade, CBOE data feed)
        self.data_provider = None

    def get_put_call_ratio(self, ticker: str) -> Dict:
        """
        Calculate Put/Call ratio for sentiment analysis.

        Put/Call Ratio interpretation:
        - < 0.7: Bullish (more calls than puts)
        - 0.7 - 1.0: Neutral
        - > 1.0: Bearish (more puts than calls)
        - > 1.5: Extreme fear / potential contrarian buy

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with put_call_ratio and interpretation
        """
        # This is a template - real implementation needs options data provider
        # Example structure of what this would return:
        return {
            'ticker': ticker,
            'put_call_ratio': None,
            'interpretation': 'Data not available',
            'call_volume': 0,
            'put_volume': 0,
            'data_available': False,
            'note': 'Requires options data provider integration (e.g., Polygon.io, CBOE)'
        }

    def detect_unusual_activity(self, ticker: str) -> Dict:
        """
        Detect unusual options activity.

        Unusual activity includes:
        - Volume significantly above average
        - Large block trades
        - Options sweep orders (aggressive, urgent trades)

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with unusual activity metrics
        """
        return {
            'ticker': ticker,
            'unusual_calls': [],
            'unusual_puts': [],
            'large_blocks': [],
            'sweeps_detected': False,
            'smart_money_signal': 'neutral',
            'data_available': False,
            'note': 'Requires real-time options data integration'
        }

    def analyze_options_sentiment(self, ticker: str) -> Dict:
        """
        Comprehensive options sentiment analysis.

        Combines multiple signals:
        - Put/Call ratio
        - Unusual volume detection
        - Open interest changes
        - Implied volatility skew

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with sentiment score and components
        """
        result = {
            'ticker': ticker,
            'sentiment_score': 0,  # -100 to +100
            'sentiment_label': 'neutral',
            'confidence': 0,
            'components': {},
            'signals': [],
            'data_available': False
        }

        # Put/Call Ratio Analysis
        pc_ratio = self.get_put_call_ratio(ticker)
        if pc_ratio.get('data_available'):
            ratio = pc_ratio.get('put_call_ratio', 1.0)

            # Convert ratio to score component
            if ratio < 0.5:
                pc_score = 30  # Very bullish
                result['signals'].append('Low P/C ratio indicates bullish sentiment')
            elif ratio < 0.7:
                pc_score = 15  # Bullish
            elif ratio > 1.5:
                pc_score = -30  # Very bearish (but could be contrarian buy)
                result['signals'].append('High P/C ratio may indicate excessive fear')
            elif ratio > 1.0:
                pc_score = -15  # Bearish
            else:
                pc_score = 0  # Neutral

            result['components']['put_call_ratio'] = {
                'value': ratio,
                'score': pc_score
            }
            result['sentiment_score'] += pc_score

        # Unusual Activity Analysis
        unusual = self.detect_unusual_activity(ticker)
        if unusual.get('data_available'):
            # Score based on unusual activity
            if unusual.get('unusual_calls'):
                result['sentiment_score'] += 20
                result['signals'].append(f"Unusual call activity detected")

            if unusual.get('unusual_puts'):
                result['sentiment_score'] -= 20
                result['signals'].append(f"Unusual put activity detected")

            if unusual.get('sweeps_detected'):
                result['signals'].append("Options sweeps detected - urgency signal")

            result['components']['unusual_activity'] = unusual
            result['data_available'] = True

        # Set label based on score
        score = result['sentiment_score']
        if score >= 40:
            result['sentiment_label'] = 'strong_bullish'
        elif score >= 15:
            result['sentiment_label'] = 'bullish'
        elif score <= -40:
            result['sentiment_label'] = 'strong_bearish'
        elif score <= -15:
            result['sentiment_label'] = 'bearish'
        else:
            result['sentiment_label'] = 'neutral'

        return result

    def get_implied_volatility_signal(self, ticker: str) -> Dict:
        """
        Analyze implied volatility for trading signals.

        IV signals:
        - IV Rank > 80%: Options expensive, potential mean reversion
        - IV Rank < 20%: Options cheap, good for buying options
        - IV Crush expected after earnings

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with IV analysis
        """
        return {
            'ticker': ticker,
            'current_iv': None,
            'iv_rank': None,  # Where current IV sits in 1-year range
            'iv_percentile': None,
            'hv_20': None,  # 20-day historical volatility
            'iv_hv_ratio': None,  # IV / HV ratio
            'signal': 'neutral',
            'data_available': False,
            'note': 'Requires options data provider for IV calculations'
        }

    def calculate_gex(self, ticker: str) -> Dict:
        """
        Calculate Gamma Exposure (GEX) for market maker positioning.

        GEX indicates how market makers are positioned:
        - Positive GEX: Market makers will buy dips, sell rips (dampens moves)
        - Negative GEX: Market makers amplify moves (buy on up, sell on down)

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with GEX data
        """
        return {
            'ticker': ticker,
            'gex': None,
            'gex_normalized': None,
            'flip_price': None,  # Price where GEX changes sign
            'interpretation': 'Data not available',
            'data_available': False,
            'note': 'Requires full options chain data for GEX calculation'
        }


class OptionsDataSimulator:
    """
    Simulate options data for testing when no real data provider is available.
    NOT FOR PRODUCTION USE - Only for UI/UX development.
    """

    @staticmethod
    def generate_sample_data(ticker: str) -> Dict:
        """Generate sample options flow data for testing."""
        import random

        # Simulate put/call ratio
        pc_ratio = random.uniform(0.5, 1.5)

        # Simulate some unusual activity
        has_unusual = random.random() > 0.7

        return {
            'ticker': ticker,
            'put_call_ratio': round(pc_ratio, 2),
            'call_volume': random.randint(1000, 50000),
            'put_volume': random.randint(1000, 50000),
            'unusual_calls': [
                {'strike': 150, 'expiry': '2024-01-19', 'volume': 5000, 'oi': 1000}
            ] if has_unusual and pc_ratio < 1.0 else [],
            'unusual_puts': [
                {'strike': 140, 'expiry': '2024-01-19', 'volume': 3000, 'oi': 500}
            ] if has_unusual and pc_ratio > 1.0 else [],
            'iv_rank': random.randint(10, 90),
            'data_available': True,
            'is_simulated': True
        }


# Global instance
_analyzer = None


def get_options_analyzer() -> OptionsFlowAnalyzer:
    """Get or create options analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = OptionsFlowAnalyzer()
    return _analyzer


def get_options_sentiment(ticker: str) -> Dict:
    """Get options-based sentiment for a ticker."""
    return get_options_analyzer().analyze_options_sentiment(ticker)


def get_put_call_ratio(ticker: str) -> Dict:
    """Get put/call ratio for a ticker."""
    return get_options_analyzer().get_put_call_ratio(ticker)
