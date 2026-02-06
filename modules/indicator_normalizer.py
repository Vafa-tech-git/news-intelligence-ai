"""
Indicator Normalizer
Normalizes economic indicators to 0-100 health scores based on their characteristics.
"""
import logging
from typing import Optional
from statistics import mean, stdev

from config import FRED_INDICATORS
import database

logger = logging.getLogger(__name__)


class IndicatorNormalizer:
    """Normalizes economic indicators to health scores."""

    def __init__(self):
        self.history_cache = {}

    def get_historical_values(self, series_id: str, years: int = 10) -> list:
        """Get historical values for an indicator."""
        if series_id not in self.history_cache:
            history = database.get_fred_indicator_history(series_id, years)
            self.history_cache[series_id] = [h['value'] for h in history if h['value'] is not None]
        return self.history_cache[series_id]

    def calculate_percentile(self, value: float, series_id: str) -> float:
        """Calculate percentile rank (0-100) of value in historical distribution."""
        history = self.get_historical_values(series_id)
        if not history:
            return 50.0  # Default to middle if no history

        count_below = sum(1 for v in history if v < value)
        percentile = (count_below / len(history)) * 100
        return percentile

    def calculate_trend(self, series_id: str, lookback_months: int = 3) -> str:
        """Calculate trend based on recent direction."""
        from datetime import datetime, timedelta
        start_date = (datetime.now() - timedelta(days=lookback_months * 30)).strftime('%Y-%m-%d')
        history = database.get_fred_indicator(series_id, start_date=start_date)

        if len(history) < 2:
            return 'stable'

        # Compare first third to last third
        third = max(1, len(history) // 3)
        early_avg = mean([h['value'] for h in history[:third]])
        late_avg = mean([h['value'] for h in history[-third:]])

        change_pct = ((late_avg - early_avg) / early_avg) * 100 if early_avg != 0 else 0

        if change_pct > 5:
            return 'improving'
        elif change_pct < -5:
            return 'deteriorating'
        return 'stable'

    def normalize_higher_better(self, value: float, series_id: str) -> float:
        """Higher values are healthier (e.g., GDP, payrolls)."""
        percentile = self.calculate_percentile(value, series_id)
        return percentile

    def normalize_lower_better(self, value: float, series_id: str) -> float:
        """Lower values are healthier (e.g., unemployment, VIX)."""
        percentile = self.calculate_percentile(value, series_id)
        return 100 - percentile

    def normalize_optimal_range(self, value: float, series_id: str,
                                 optimal_low: float, optimal_high: float) -> float:
        """
        Values within optimal range are healthiest.
        Score decreases as value moves away from optimal range.
        """
        if optimal_low <= value <= optimal_high:
            # Within optimal range: 80-100 score
            mid = (optimal_low + optimal_high) / 2
            distance_from_mid = abs(value - mid)
            range_half = (optimal_high - optimal_low) / 2
            return 100 - (distance_from_mid / range_half) * 20

        # Outside optimal range
        history = self.get_historical_values(series_id)
        if not history:
            return 50.0

        hist_min = min(history)
        hist_max = max(history)

        if value < optimal_low:
            # Below optimal
            distance = optimal_low - value
            max_distance = optimal_low - hist_min if hist_min < optimal_low else optimal_low
            score = 80 - (distance / max_distance) * 60 if max_distance > 0 else 50
        else:
            # Above optimal
            distance = value - optimal_high
            max_distance = hist_max - optimal_high if hist_max > optimal_high else 1
            score = 80 - (distance / max_distance) * 60 if max_distance > 0 else 50

        return max(0, min(80, score))

    def normalize_stable(self, value: float, series_id: str) -> float:
        """
        Stable/moderate change is healthiest (e.g., PPI).
        Calculate based on month-over-month change rate.
        """
        history = database.get_fred_indicator(series_id)
        if len(history) < 2:
            return 50.0

        # Calculate recent changes
        values = [h['value'] for h in history[-12:]]  # Last 12 observations
        if len(values) < 2:
            return 50.0

        changes = []
        for i in range(1, len(values)):
            if values[i-1] != 0:
                pct_change = ((values[i] - values[i-1]) / values[i-1]) * 100
                changes.append(abs(pct_change))

        if not changes:
            return 50.0

        avg_change = mean(changes)

        # Lower volatility = higher score
        if avg_change < 0.5:
            return 90 + (0.5 - avg_change) * 20
        elif avg_change < 1:
            return 80 + (1 - avg_change) * 20
        elif avg_change < 2:
            return 60 + (2 - avg_change) * 20
        elif avg_change < 5:
            return 30 + (5 - avg_change) * 10
        else:
            return max(0, 30 - (avg_change - 5) * 5)

    def normalize_context(self, value: float, series_id: str) -> float:
        """
        Context-dependent indicators (e.g., Fed Funds rate).
        Use moderate percentile - not too high, not too low.
        """
        percentile = self.calculate_percentile(value, series_id)
        # Favor middle values - extreme highs or lows are less healthy
        if 30 <= percentile <= 70:
            return 70 + (10 - abs(percentile - 50) / 2)
        elif percentile < 30:
            return 50 + percentile
        else:
            return 50 + (100 - percentile)

    def normalize_moderate_growth(self, value: float, series_id: str) -> float:
        """
        Moderate growth is healthiest (e.g., M2 money supply).
        """
        history = database.get_fred_indicator(series_id)
        if len(history) < 13:  # Need at least 13 months for YoY
            return 50.0

        # Calculate year-over-year growth
        current = history[-1]['value']
        year_ago = history[-13]['value'] if len(history) >= 13 else history[0]['value']

        if year_ago == 0:
            return 50.0

        yoy_growth = ((current - year_ago) / year_ago) * 100

        # Optimal M2 growth is around 3-6%
        if 3 <= yoy_growth <= 6:
            return 90 + (3 - abs(yoy_growth - 4.5)) * 3
        elif 0 <= yoy_growth < 3:
            return 70 + yoy_growth * 6
        elif 6 < yoy_growth <= 10:
            return 90 - (yoy_growth - 6) * 5
        elif yoy_growth < 0:
            return max(20, 70 + yoy_growth * 5)
        else:
            return max(20, 70 - (yoy_growth - 10) * 3)

    def normalize_indicator(self, series_id: str, value: float) -> dict:
        """
        Normalize an indicator to a 0-100 health score.
        Returns dict with health_score, trend, percentile.
        """
        if series_id not in FRED_INDICATORS:
            return {'health_score': 50, 'trend': 'stable', 'percentile': 50}

        config = FRED_INDICATORS[series_id]
        direction = config.get('direction', 'context')

        if direction == 'higher_better':
            health_score = self.normalize_higher_better(value, series_id)
        elif direction == 'lower_better':
            health_score = self.normalize_lower_better(value, series_id)
        elif direction == 'optimal_range':
            optimal = config.get('optimal', (0, 100))
            health_score = self.normalize_optimal_range(value, series_id, optimal[0], optimal[1])
        elif direction == 'stable':
            health_score = self.normalize_stable(value, series_id)
        elif direction == 'moderate_growth':
            health_score = self.normalize_moderate_growth(value, series_id)
        else:  # context
            health_score = self.normalize_context(value, series_id)

        # Calculate trend
        trend = self.calculate_trend(series_id)

        # Adjust trend label based on direction
        if direction == 'lower_better':
            # For "lower is better" indicators, improving means value is decreasing
            if trend == 'improving':
                trend = 'deteriorating'
            elif trend == 'deteriorating':
                trend = 'improving'

        percentile = self.calculate_percentile(value, series_id)

        return {
            'health_score': round(max(0, min(100, health_score)), 1),
            'trend': trend,
            'percentile': round(percentile, 1)
        }

    def normalize_all_indicators(self) -> dict:
        """
        Normalize all indicators and store health scores.
        Returns dict of {series_id: {health_score, trend, percentile}}.
        """
        latest = database.get_latest_fred_indicators()
        results = {}

        for series_id, data in latest.items():
            value = data['value']
            observation_date = data['observation_date']

            normalized = self.normalize_indicator(series_id, value)
            results[series_id] = {
                **normalized,
                'value': value,
                'observation_date': observation_date,
                'name': FRED_INDICATORS.get(series_id, {}).get('name', series_id),
                'category': FRED_INDICATORS.get(series_id, {}).get('category', 'other')
            }

            # Store in database
            database.save_indicator_health_score(
                series_id=series_id,
                observation_date=observation_date,
                raw_value=value,
                health_score=normalized['health_score'],
                trend=normalized['trend'],
                percentile=normalized['percentile']
            )

        return results

    def clear_cache(self):
        """Clear the history cache."""
        self.history_cache = {}


# Global instance
_normalizer = None


def get_normalizer() -> IndicatorNormalizer:
    """Get or create the global normalizer instance."""
    global _normalizer
    if _normalizer is None:
        _normalizer = IndicatorNormalizer()
    return _normalizer


def normalize_indicators() -> dict:
    """Convenience function to normalize all indicators."""
    normalizer = get_normalizer()
    return normalizer.normalize_all_indicators()
