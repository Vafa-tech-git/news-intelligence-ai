import sys
import os
from datetime import datetime, timedelta

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import database

try:
    import yfinance as yf
except ImportError:
    print("yfinance not installed. Run: pip install yfinance")
    yf = None

INDICES = {
    '^IXIC': 'NASDAQ Composite',
    '^GSPC': 'S&P 500',
    '^DJI': 'Dow Jones Industrial Average'
}

def fetch_index_history(symbol, period='max'):
    """Fetch historical data for an index using yfinance."""
    if not yf:
        print("yfinance not available")
        return []

    print(f"Fetching {INDICES.get(symbol, symbol)} data...")
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            print(f"No data returned for {symbol}")
            return []

        data_rows = []
        prev_close = None
        for date, row in hist.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            close = row['Close']
            pct_change = None
            if prev_close and close:
                pct_change = round(((close - prev_close) / prev_close) * 100, 4)

            data_rows.append({
                'date': date_str,
                'open': round(row['Open'], 2) if row['Open'] else None,
                'high': round(row['High'], 2) if row['High'] else None,
                'low': round(row['Low'], 2) if row['Low'] else None,
                'close': round(close, 2) if close else None,
                'volume': int(row['Volume']) if row['Volume'] else None,
                'pct_change': pct_change
            })
            prev_close = close

        print(f"Fetched {len(data_rows)} records for {symbol}")
        return data_rows
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return []

def fetch_incremental(symbol):
    """Fetch only new data since last stored date."""
    latest_date = database.get_latest_market_date(symbol)

    if not latest_date:
        return fetch_index_history(symbol, period='max')

    start_date = datetime.strptime(latest_date, '%Y-%m-%d') + timedelta(days=1)
    if start_date.date() > datetime.now().date():
        print(f"{symbol}: Already up to date")
        return []

    print(f"Fetching {symbol} from {start_date.strftime('%Y-%m-%d')}...")
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date.strftime('%Y-%m-%d'))

        if hist.empty:
            return []

        last_known = database.get_market_data(symbol)
        prev_close = last_known[-1]['close'] if last_known else None

        data_rows = []
        for date, row in hist.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            close = row['Close']
            pct_change = None
            if prev_close and close:
                pct_change = round(((close - prev_close) / prev_close) * 100, 4)

            data_rows.append({
                'date': date_str,
                'open': round(row['Open'], 2) if row['Open'] else None,
                'high': round(row['High'], 2) if row['High'] else None,
                'low': round(row['Low'], 2) if row['Low'] else None,
                'close': round(close, 2) if close else None,
                'volume': int(row['Volume']) if row['Volume'] else None,
                'pct_change': pct_change
            })
            prev_close = close

        return data_rows
    except Exception as e:
        print(f"Error fetching incremental {symbol}: {e}")
        return []

def refresh_all_indices():
    """Refresh data for all indices."""
    results = {}
    for symbol in INDICES:
        count = database.get_market_data_count(symbol)
        if count == 0:
            data = fetch_index_history(symbol, period='max')
        else:
            data = fetch_incremental(symbol)

        if data:
            saved = database.save_market_data(symbol, data)
            results[symbol] = saved
        else:
            results[symbol] = 0
    return results

def ensure_data_loaded(symbol):
    """Ensure we have data for a symbol, fetch if empty."""
    count = database.get_market_data_count(symbol)
    if count == 0:
        data = fetch_index_history(symbol, period='max')
        if data:
            database.save_market_data(symbol, data)
            return len(data)
    return count

if __name__ == "__main__":
    results = refresh_all_indices()
    for symbol, count in results.items():
        print(f"{symbol}: {count} records updated")
