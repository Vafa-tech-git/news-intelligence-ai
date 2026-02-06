"""
FRED Economic Data Fetcher
Fetches economic indicators from the Federal Reserve Economic Data API.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

try:
    from fredapi import Fred
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False
    Fred = None

from config import FRED_API_KEY, FRED_INDICATORS
import database
from modules.rate_limiter import acquire, can_request

logger = logging.getLogger(__name__)


class FredFetcher:
    """Fetches economic indicators from FRED API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or FRED_API_KEY
        self.fred = None
        if FRED_AVAILABLE and self.api_key:
            self.fred = Fred(api_key=self.api_key)

    def is_available(self) -> bool:
        """Check if FRED API is configured and available."""
        return self.fred is not None

    def fetch_indicator(self, series_id: str, start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None) -> list:
        """
        Fetch a single indicator from FRED.
        Returns list of {observation_date, value} dicts.
        """
        if not self.is_available():
            logger.warning("FRED API not available (missing fredapi or API key)")
            return []

        if not can_request('fred'):
            logger.warning("FRED rate limit reached, skipping fetch")
            return []

        try:
            acquire('fred')

            # Fetch all available data - don't restrict by dates
            # (FRED only has data up to the actual current date, not future dates)
            series = self.fred.get_series(series_id)

            if series is None or series.empty:
                logger.warning(f"No data returned for {series_id}")
                return []

            # If start_date specified, filter results
            results = []
            for date, value in series.items():
                # Skip if before start_date
                if start_date and date.to_pydatetime() < start_date:
                    continue
                # Skip NaN values
                if value is not None and not (isinstance(value, float) and value != value):
                    results.append({
                        'observation_date': date.strftime('%Y-%m-%d'),
                        'value': float(value)
                    })

            logger.info(f"Fetched {len(results)} observations for {series_id}")
            return results

        except Exception as e:
            logger.error(f"Error fetching {series_id}: {e}")
            return []

    def fetch_all_indicators(self, backfill: bool = False) -> dict:
        """
        Fetch all configured indicators.
        If backfill=True, fetches 10 years of history. Otherwise, fetches recent data.
        """
        if not self.is_available():
            logger.warning("FRED API not available")
            return {}

        results = {}
        start_date = None

        if not backfill:
            # Only fetch last 30 days for regular updates
            start_date = datetime.now() - timedelta(days=30)

        total = len(FRED_INDICATORS)
        for i, (series_id, config) in enumerate(FRED_INDICATORS.items(), 1):
            print(f"[FRED] Fetching {i}/{total}: {config['name']} ({series_id})...")
            logger.info(f"Fetching {i}/{total}: {series_id}")
            data = self.fetch_indicator(series_id, start_date=start_date)
            if data:
                results[series_id] = {
                    'config': config,
                    'data': data
                }
                print(f"[FRED] Got {len(data)} observations for {series_id}")

        print(f"[FRED] Complete! Fetched {len(results)}/{total} indicators.")
        return results

    def store_indicators(self, data: dict) -> int:
        """
        Store fetched indicator data in the database.
        Returns count of records stored.
        """
        total_stored = 0
        indicators_to_store = []

        for series_id, indicator_data in data.items():
            config = indicator_data['config']
            for obs in indicator_data['data']:
                indicators_to_store.append({
                    'series_id': series_id,
                    'indicator_name': config['name'],
                    'category': config['category'],
                    'value': obs['value'],
                    'observation_date': obs['observation_date']
                })

        if indicators_to_store:
            total_stored = database.save_fred_indicators_bulk(indicators_to_store)
            logger.info(f"Stored {total_stored} indicator observations")

        return total_stored

    def fetch_and_store(self, backfill: bool = False) -> int:
        """Convenience method to fetch and store all indicators."""
        data = self.fetch_all_indicators(backfill=backfill)
        return self.store_indicators(data)

    def get_latest_values(self) -> dict:
        """Get most recent value for each indicator from database."""
        return database.get_latest_fred_indicators()

    def get_indicator_history(self, series_id: str, years: int = 10) -> list:
        """Get historical data for an indicator from database."""
        return database.get_fred_indicator_history(series_id, years)


# Global instance
_fred_fetcher = None


def get_fred_fetcher() -> FredFetcher:
    """Get or create the global FredFetcher instance."""
    global _fred_fetcher
    if _fred_fetcher is None:
        _fred_fetcher = FredFetcher()
    return _fred_fetcher


def fetch_fred_data(backfill: bool = False) -> int:
    """Convenience function to fetch and store FRED data."""
    fetcher = get_fred_fetcher()
    return fetcher.fetch_and_store(backfill=backfill)


def get_latest_indicators() -> dict:
    """Get most recent indicator values."""
    fetcher = get_fred_fetcher()
    return fetcher.get_latest_values()
