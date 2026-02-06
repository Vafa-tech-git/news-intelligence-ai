"""Quick diagnostic script to test FRED integration."""
import sys
sys.path.insert(0, '.')

print("=" * 60)
print("FRED Integration Diagnostic")
print("=" * 60)

# 1. Check config
print("\n[1] Checking configuration...")
try:
    from config import FRED_API_KEY, FRED_INDICATORS, CATEGORY_WEIGHTS
    print(f"    FRED_API_KEY: {'SET' if FRED_API_KEY else 'NOT SET'}")
    print(f"    Configured indicators: {len(FRED_INDICATORS)}")
    print(f"    Category weights: {list(CATEGORY_WEIGHTS.keys())}")
except Exception as e:
    print(f"    ERROR: {e}")

# 2. Check fredapi module
print("\n[2] Checking fredapi module...")
try:
    from fredapi import Fred
    print("    fredapi module: AVAILABLE")
except ImportError:
    print("    fredapi module: NOT INSTALLED")
    print("    Run: pip install fredapi")

# 3. Check FredFetcher
print("\n[3] Checking FredFetcher...")
try:
    from modules.fred_fetcher import get_fred_fetcher
    fetcher = get_fred_fetcher()
    print(f"    FredFetcher available: {fetcher.is_available()}")
    print(f"    API key set: {bool(fetcher.api_key)}")
except Exception as e:
    print(f"    ERROR: {e}")

# 4. Check database
print("\n[4] Checking database...")
try:
    import database
    indicators = database.get_latest_fred_indicators()
    print(f"    Indicators in database: {len(indicators)}")
    if indicators:
        print(f"    Sample indicators: {list(indicators.keys())[:5]}")
except Exception as e:
    print(f"    ERROR: {e}")

# 5. Test FRED API (fetch one indicator)
print("\n[5] Testing FRED API connection...")
try:
    from modules.fred_fetcher import get_fred_fetcher
    fetcher = get_fred_fetcher()
    if fetcher.is_available():
        print("    Fetching UNRATE (unemployment rate) as test...")
        data = fetcher.fetch_indicator('UNRATE')
        if data:
            print(f"    SUCCESS! Got {len(data)} observations")
            print(f"    Latest: {data[-1]['observation_date']} = {data[-1]['value']}")
        else:
            print("    FAILED: No data returned")
    else:
        print("    SKIPPED: FRED not available")
except Exception as e:
    print(f"    ERROR: {e}")
    import traceback
    traceback.print_exc()

# 6. Check economic health calculation
print("\n[6] Checking economic health calculation...")
try:
    from modules.economic_health import get_economic_health
    health = get_economic_health()
    if health:
        print(f"    Overall score: {health.get('overall_score')}")
        print(f"    Regime: {health.get('regime')}")
        print(f"    Data completeness: {health.get('data_completeness')}%")
        print(f"    Indicators: {len(health.get('indicators', {}))}")
    else:
        print("    No health data (need to fetch FRED data first)")
except Exception as e:
    print(f"    ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Diagnostic complete!")
print("=" * 60)
