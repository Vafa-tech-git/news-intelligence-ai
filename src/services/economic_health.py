"""
Economic Health Calculator
Computes composite Economic Health Index and regime classification.
"""
import logging
from datetime import datetime, date
from typing import Optional
from statistics import mean

from config import FRED_INDICATORS, CATEGORY_WEIGHTS, REGIME_THRESHOLDS
import database
from modules.indicator_normalizer import get_normalizer, normalize_indicators
from modules.fred_fetcher import get_fred_fetcher

logger = logging.getLogger(__name__)


class EconomicHealthCalculator:
    """Calculates composite economic health index and regime."""

    def __init__(self):
        self.normalizer = get_normalizer()

    def calculate_category_scores(self, indicator_scores: dict) -> dict:
        """
        Calculate average health score for each category.
        Returns {category: score}.
        """
        category_values = {}

        for series_id, data in indicator_scores.items():
            category = data.get('category', 'other')
            if category not in category_values:
                category_values[category] = []
            category_values[category].append(data['health_score'])

        category_scores = {}
        for category, values in category_values.items():
            if values:
                category_scores[category] = round(mean(values), 1)

        return category_scores

    def calculate_composite_score(self, category_scores: dict) -> float:
        """
        Calculate weighted composite Economic Health Index.
        """
        total_weight = 0
        weighted_sum = 0

        for category, weight in CATEGORY_WEIGHTS.items():
            if category in category_scores:
                weighted_sum += category_scores[category] * weight
                total_weight += weight

        if total_weight == 0:
            return 50.0

        # Normalize by actual weight used (in case some categories missing)
        return round(weighted_sum / total_weight * (total_weight / sum(CATEGORY_WEIGHTS.values())), 1)

    def classify_regime(self, score: float, trend: str = 'stable') -> str:
        """
        Classify economic regime based on composite score.
        """
        if score >= REGIME_THRESHOLDS['expansion']:
            return 'expansion'
        elif score >= REGIME_THRESHOLDS['peak']:
            return 'peak'
        elif score >= REGIME_THRESHOLDS['contraction']:
            return 'contraction'
        else:
            return 'trough'

    def detect_yield_curve_inversion(self) -> tuple:
        """
        Detect yield curve inversion and duration.
        Returns (is_inverted, months_inverted).
        """
        # Get T10Y2Y (10-year minus 2-year Treasury spread)
        history = database.get_yield_curve_history(months=6)

        if not history:
            return False, 0

        # Check current state
        latest = history[-1] if history else None
        is_inverted = latest and latest['value'] < 0

        # Count consecutive months of inversion
        months_inverted = 0
        if is_inverted:
            # Group by month and check consecutive inversions
            monthly_data = {}
            for h in history:
                month_key = h['observation_date'][:7]  # YYYY-MM
                if month_key not in monthly_data:
                    monthly_data[month_key] = []
                monthly_data[month_key].append(h['value'])

            # Check from most recent backwards
            sorted_months = sorted(monthly_data.keys(), reverse=True)
            for month in sorted_months:
                avg_value = mean(monthly_data[month])
                if avg_value < 0:
                    months_inverted += 1
                else:
                    break

        return is_inverted, months_inverted

    def calculate_recession_probability(self, indicator_scores: dict,
                                         yield_curve_inverted: bool,
                                         inversion_months: int) -> float:
        """
        Estimate recession probability based on leading indicators.
        """
        probability = 5.0  # Base probability

        # Yield curve inversion (+30% if inverted 3+ months)
        if yield_curve_inverted:
            if inversion_months >= 3:
                probability += 30
            elif inversion_months >= 1:
                probability += 15

        # Rising jobless claims
        icsa_data = indicator_scores.get('ICSA', {})
        if icsa_data.get('trend') == 'deteriorating':
            probability += 20
        elif icsa_data.get('health_score', 100) < 40:
            probability += 10

        # Consumer sentiment decline
        umcsent_data = indicator_scores.get('UMCSENT', {})
        if umcsent_data.get('trend') == 'deteriorating':
            probability += 15
        elif umcsent_data.get('health_score', 100) < 40:
            probability += 10

        # Industrial production decline
        indpro_data = indicator_scores.get('INDPRO', {})
        if indpro_data.get('trend') == 'deteriorating':
            probability += 10
        elif indpro_data.get('health_score', 100) < 40:
            probability += 5

        # Overall health score factor
        latest_health = database.get_latest_economic_health()
        if latest_health:
            overall = latest_health.get('overall_score', 50)
            if overall < 40:
                probability += 15
            elif overall < 50:
                probability += 10

        return min(95, max(5, probability))

    def calculate_health(self) -> dict:
        """
        Calculate and store complete economic health snapshot.
        Returns full health data including indicators, categories, composite, regime.
        """
        # Normalize all indicators
        indicator_scores = normalize_indicators()

        if not indicator_scores:
            logger.warning("No indicator data available for health calculation")
            return None

        # Calculate category scores
        category_scores = self.calculate_category_scores(indicator_scores)

        # Calculate composite score
        composite_score = self.calculate_composite_score(category_scores)

        # Detect yield curve inversion
        yield_curve_inverted, inversion_months = self.detect_yield_curve_inversion()

        # Classify regime
        regime = self.classify_regime(composite_score)

        # Calculate recession probability
        recession_probability = self.calculate_recession_probability(
            indicator_scores, yield_curve_inverted, inversion_months
        )

        # Determine overall trend
        improving_count = sum(1 for d in indicator_scores.values() if d.get('trend') == 'improving')
        deteriorating_count = sum(1 for d in indicator_scores.values() if d.get('trend') == 'deteriorating')

        if improving_count > deteriorating_count * 1.5:
            overall_trend = 'improving'
        elif deteriorating_count > improving_count * 1.5:
            overall_trend = 'deteriorating'
        else:
            overall_trend = 'stable'

        # Store composite in database
        today = date.today().isoformat()
        database.save_economic_health_composite(
            date=today,
            overall_score=composite_score,
            regime=regime,
            category_scores=category_scores,
            recession_probability=recession_probability,
            yield_curve_inverted=yield_curve_inverted,
            inversion_months=inversion_months
        )

        result = {
            'date': today,
            'overall_score': composite_score,
            'regime': regime,
            'category_scores': category_scores,
            'recession_probability': recession_probability,
            'recession_warning': yield_curve_inverted and inversion_months >= 3,
            'yield_curve_inverted': yield_curve_inverted,
            'inversion_months': inversion_months,
            'overall_trend': overall_trend,
            'indicators': indicator_scores,
            'data_completeness': round(len(indicator_scores) / len(FRED_INDICATORS) * 100, 1)
        }

        logger.info(f"Economic health calculated: {composite_score} ({regime})")
        return result

    def get_current_health(self) -> dict:
        """
        Get current economic health from database, calculating if needed.
        """
        # First check if we have any FRED data at all
        latest_indicators = database.get_latest_fred_indicators()
        if not latest_indicators:
            logger.warning("No FRED indicator data in database")
            return None

        latest = database.get_latest_economic_health()

        if latest:
            # Enrich with indicator details
            indicator_scores = database.get_latest_health_scores()

            # If no health scores but we have indicators, recalculate
            if not indicator_scores and latest_indicators:
                return self.calculate_health()

            latest['indicators'] = {}
            for series_id, data in indicator_scores.items():
                config = FRED_INDICATORS.get(series_id, {})
                latest['indicators'][series_id] = {
                    **data,
                    'name': config.get('name', series_id),
                    'category': config.get('category', 'other')
                }

            # Update data completeness based on actual indicators
            latest['data_completeness'] = round(len(indicator_scores) / len(FRED_INDICATORS) * 100, 1)

            latest['recession_warning'] = (
                latest.get('yield_curve_inverted') and
                latest.get('inversion_months', 0) >= 3
            )
            return latest

        # Calculate fresh data if we have indicators
        return self.calculate_health()

    def get_health_history(self, days: int = 730) -> list:
        """Get historical economic health data."""
        return database.get_economic_health_history(days)


# Global instance
_health_calculator = None


def get_health_calculator() -> EconomicHealthCalculator:
    """Get or create the global health calculator instance."""
    global _health_calculator
    if _health_calculator is None:
        _health_calculator = EconomicHealthCalculator()
    return _health_calculator


def calculate_economic_health() -> dict:
    """Convenience function to calculate economic health."""
    calculator = get_health_calculator()
    return calculator.calculate_health()


def get_economic_health() -> dict:
    """Convenience function to get current economic health."""
    calculator = get_health_calculator()
    return calculator.get_current_health()


def get_economic_health_history(days: int = 730) -> list:
    """Convenience function to get health history."""
    calculator = get_health_calculator()
    return calculator.get_health_history(days)


def refresh_economic_data(backfill: bool = False) -> dict:
    """
    Refresh FRED data and recalculate health.
    Use backfill=True for initial setup to fetch 10 years of history.
    """
    fetcher = get_fred_fetcher()

    # Fetch data from FRED
    count = fetcher.fetch_and_store(backfill=backfill)
    logger.info(f"Fetched {count} FRED observations")

    # Recalculate health
    health = calculate_economic_health()

    return {
        'observations_fetched': count,
        'health': health
    }
