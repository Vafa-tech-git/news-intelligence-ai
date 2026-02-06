"""
Short Interest Tracker
Track short interest data for squeeze potential and sentiment analysis.

Short interest signals:
- High short interest (>20%): Potential squeeze candidate
- Rising short interest: Increasing bearish bets
- High days to cover: More squeeze pressure
- Cost to borrow: Indicates demand to short
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from statistics import mean
import math

import database


class ShortInterestTracker:
    """Track and analyze short interest data."""

    # Thresholds for analysis
    HIGH_SHORT_INTEREST = 0.20  # 20% of float
    VERY_HIGH_SHORT_INTEREST = 0.30  # 30%
    HIGH_DAYS_TO_COVER = 5  # Days
    CRITICAL_DAYS_TO_COVER = 10  # Days

    def __init__(self):
        # In production, this would connect to data providers like:
        # - FINRA (official short interest data, bi-weekly)
        # - Ortex (real-time estimates)
        # - S3 Partners
        # - Fintel
        self.data_provider = None

    def get_short_interest(self, ticker: str) -> Dict:
        """
        Get short interest data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with short interest metrics
        """
        # Template structure - real implementation needs data provider
        return {
            'ticker': ticker,
            'short_interest': None,  # Number of shares short
            'short_interest_pct': None,  # % of float
            'short_interest_ratio': None,  # Same as days to cover
            'days_to_cover': None,  # Shares short / Avg daily volume
            'short_float': None,  # % of float shorted
            'shares_outstanding': None,
            'float_shares': None,
            'avg_volume': None,
            'data_date': None,
            'data_available': False,
            'note': 'Requires short interest data provider (FINRA, Ortex, etc.)'
        }

    def calculate_squeeze_score(
        self,
        short_pct: float,
        days_to_cover: float,
        cost_to_borrow: float = None,
        volume_spike: bool = False,
        price_momentum: float = 0
    ) -> Dict:
        """
        Calculate short squeeze potential score.

        Factors:
        - Short interest % of float
        - Days to cover
        - Cost to borrow
        - Recent volume spikes
        - Price momentum (shorts getting squeezed)

        Args:
            short_pct: Short interest as % of float (0.0 to 1.0)
            days_to_cover: Days to cover ratio
            cost_to_borrow: Annual cost to borrow (e.g., 0.05 = 5%)
            volume_spike: Whether recent volume is above average
            price_momentum: Recent price change %

        Returns:
            Dict with squeeze score (0-100) and breakdown
        """
        score = 0
        factors = []

        # Short Interest Score (max 35 points)
        if short_pct >= 0.40:
            score += 35
            factors.append(f"Extremely high short interest ({short_pct:.1%})")
        elif short_pct >= 0.30:
            score += 30
            factors.append(f"Very high short interest ({short_pct:.1%})")
        elif short_pct >= 0.20:
            score += 20
            factors.append(f"High short interest ({short_pct:.1%})")
        elif short_pct >= 0.10:
            score += 10
            factors.append(f"Moderate short interest ({short_pct:.1%})")

        # Days to Cover Score (max 25 points)
        if days_to_cover >= 10:
            score += 25
            factors.append(f"Very high days to cover ({days_to_cover:.1f} days)")
        elif days_to_cover >= 7:
            score += 20
            factors.append(f"High days to cover ({days_to_cover:.1f} days)")
        elif days_to_cover >= 5:
            score += 15
            factors.append(f"Elevated days to cover ({days_to_cover:.1f} days)")
        elif days_to_cover >= 3:
            score += 8

        # Cost to Borrow Score (max 20 points)
        if cost_to_borrow is not None:
            if cost_to_borrow >= 0.50:  # 50%+ annual
                score += 20
                factors.append(f"Very high borrow cost ({cost_to_borrow:.0%})")
            elif cost_to_borrow >= 0.20:
                score += 15
                factors.append(f"High borrow cost ({cost_to_borrow:.0%})")
            elif cost_to_borrow >= 0.10:
                score += 10
            elif cost_to_borrow >= 0.05:
                score += 5

        # Volume Spike Score (max 10 points)
        if volume_spike:
            score += 10
            factors.append("Recent volume spike detected")

        # Price Momentum Score (max 10 points)
        if price_momentum > 10:  # Up 10%+
            score += 10
            factors.append(f"Strong upward momentum ({price_momentum:.1f}%)")
        elif price_momentum > 5:
            score += 5

        # Determine squeeze potential level
        if score >= 80:
            level = 'extreme'
            description = 'Extreme squeeze potential - all factors aligned'
        elif score >= 60:
            level = 'high'
            description = 'High squeeze potential'
        elif score >= 40:
            level = 'moderate'
            description = 'Moderate squeeze potential'
        elif score >= 20:
            level = 'low'
            description = 'Low squeeze potential'
        else:
            level = 'minimal'
            description = 'Minimal squeeze potential'

        return {
            'squeeze_score': min(100, score),
            'level': level,
            'description': description,
            'factors': factors,
            'inputs': {
                'short_pct': short_pct,
                'days_to_cover': days_to_cover,
                'cost_to_borrow': cost_to_borrow,
                'volume_spike': volume_spike,
                'price_momentum': price_momentum
            }
        }

    def analyze_short_sentiment(self, ticker: str) -> Dict:
        """
        Analyze short interest for sentiment signals.

        Rising short interest = More bearish bets being placed
        Falling short interest = Shorts covering (potentially bullish)

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with short sentiment analysis
        """
        result = {
            'ticker': ticker,
            'sentiment': 'neutral',
            'sentiment_score': 0,  # -100 to +100
            'short_data': None,
            'squeeze_analysis': None,
            'signals': [],
            'data_available': False
        }

        # Get current short interest
        short_data = self.get_short_interest(ticker)
        result['short_data'] = short_data

        if not short_data.get('data_available'):
            return result

        short_pct = short_data.get('short_interest_pct', 0)
        days_to_cover = short_data.get('days_to_cover', 0)

        # Calculate squeeze score
        result['squeeze_analysis'] = self.calculate_squeeze_score(
            short_pct=short_pct,
            days_to_cover=days_to_cover
        )

        # Determine sentiment
        # High short interest can be:
        # 1. Bearish signal (smart money betting against)
        # 2. Bullish contrarian signal (squeeze potential)

        if short_pct >= self.HIGH_SHORT_INTEREST:
            # High short interest - potential squeeze
            if days_to_cover >= self.HIGH_DAYS_TO_COVER:
                result['sentiment'] = 'contrarian_bullish'
                result['sentiment_score'] = 30
                result['signals'].append(
                    f"High short interest ({short_pct:.1%}) with elevated days to cover ({days_to_cover:.1f}) - squeeze potential"
                )
            else:
                result['sentiment'] = 'mixed'
                result['sentiment_score'] = 0
                result['signals'].append(
                    f"High short interest ({short_pct:.1%}) but manageable days to cover"
                )
        elif short_pct >= 0.10:
            result['sentiment'] = 'slightly_bearish'
            result['sentiment_score'] = -15
            result['signals'].append(f"Moderate short interest ({short_pct:.1%})")
        else:
            result['sentiment'] = 'neutral'
            result['sentiment_score'] = 0

        result['data_available'] = True
        return result

    def get_most_shorted(self, min_short_pct: float = 0.15, limit: int = 20) -> List[Dict]:
        """
        Get list of most shorted stocks.

        Args:
            min_short_pct: Minimum short interest percentage
            limit: Maximum number of results

        Returns:
            List of stocks with high short interest
        """
        # This would query a database or API for most shorted stocks
        # Template return structure:
        return []

    def track_short_changes(self, ticker: str, periods: int = 5) -> Dict:
        """
        Track changes in short interest over time.

        Args:
            ticker: Stock ticker symbol
            periods: Number of reporting periods to analyze

        Returns:
            Dict with short interest trend analysis
        """
        return {
            'ticker': ticker,
            'current': None,
            'previous': None,
            'change_pct': None,
            'trend': 'unknown',
            'history': [],
            'data_available': False,
            'note': 'Requires historical short interest data'
        }


class ShortInterestSimulator:
    """
    Simulate short interest data for testing.
    NOT FOR PRODUCTION USE.
    """

    @staticmethod
    def generate_sample_data(ticker: str) -> Dict:
        """Generate sample short interest data for testing."""
        import random

        short_pct = random.uniform(0.05, 0.35)
        avg_volume = random.randint(1000000, 10000000)
        short_shares = int(short_pct * random.randint(50000000, 500000000))
        days_to_cover = short_shares / avg_volume

        return {
            'ticker': ticker,
            'short_interest': short_shares,
            'short_interest_pct': round(short_pct, 4),
            'days_to_cover': round(days_to_cover, 2),
            'short_float': round(short_pct * 100, 2),
            'avg_volume': avg_volume,
            'cost_to_borrow': round(random.uniform(0.01, 0.30), 4) if short_pct > 0.15 else round(random.uniform(0.005, 0.05), 4),
            'data_date': datetime.now().strftime('%Y-%m-%d'),
            'data_available': True,
            'is_simulated': True
        }


# Global instance
_tracker = None


def get_short_tracker() -> ShortInterestTracker:
    """Get or create short interest tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = ShortInterestTracker()
    return _tracker


def get_short_interest(ticker: str) -> Dict:
    """Get short interest data for a ticker."""
    return get_short_tracker().get_short_interest(ticker)


def get_squeeze_score(ticker: str) -> Dict:
    """Get squeeze potential score for a ticker."""
    short_data = get_short_interest(ticker)

    if not short_data.get('data_available'):
        return {
            'ticker': ticker,
            'squeeze_score': 0,
            'data_available': False
        }

    return get_short_tracker().calculate_squeeze_score(
        short_pct=short_data.get('short_interest_pct', 0),
        days_to_cover=short_data.get('days_to_cover', 0),
        cost_to_borrow=short_data.get('cost_to_borrow')
    )


def analyze_short_sentiment(ticker: str) -> Dict:
    """Analyze short interest sentiment for a ticker."""
    return get_short_tracker().analyze_short_sentiment(ticker)
