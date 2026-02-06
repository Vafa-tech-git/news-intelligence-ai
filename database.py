import sqlite3
import json
import math
from datetime import datetime

DB_NAME = "news_intelligence.db"

GICS_SECTORS = [
    "Technology", "Healthcare", "Financials", "Consumer Discretionary",
    "Consumer Staples", "Energy", "Materials", "Industrials",
    "Utilities", "Real Estate", "Communication Services"
]

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                title TEXT,
                url TEXT UNIQUE,
                published_at TEXT,
                full_content TEXT,
                ai_summary TEXT,
                impact_score INTEGER,
                is_important BOOLEAN,
                sentiment TEXT,
                is_saved BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tickers TEXT,
                sector TEXT,
                direction TEXT,
                confidence REAL,
                catalysts TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS market_indices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                date DATE NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                pct_change REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_market_symbol_date ON market_indices(symbol, date)')

        # Sentiment intelligence tables
        c.execute('''
            CREATE TABLE IF NOT EXISTS sentiment_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL,
                sentiment_score REAL,
                raw_score REAL,
                confidence REAL,
                volume INTEGER,
                metadata TEXT,
                UNIQUE(ticker, timestamp, source)
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_sentiment_ticker_time ON sentiment_snapshots(ticker, timestamp)')

        c.execute('''
            CREATE TABLE IF NOT EXISTS ticker_sentiment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL UNIQUE,
                composite_score REAL,
                composite_direction TEXT,
                confidence REAL,
                consensus_strength REAL,
                momentum TEXT,
                velocity REAL,
                last_updated DATETIME,
                source_breakdown TEXT,
                signal TEXT,
                signal_confidence REAL,
                signal_reasons TEXT,
                risk_factors TEXT,
                timing_score REAL
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_ticker_sentiment_signal ON ticker_sentiment(signal)')

        c.execute('''
            CREATE TABLE IF NOT EXISTS sentiment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date DATE NOT NULL,
                open_sentiment REAL,
                close_sentiment REAL,
                high_sentiment REAL,
                low_sentiment REAL,
                avg_sentiment REAL,
                volume INTEGER,
                UNIQUE(ticker, date)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS signal_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                signal_date DATE NOT NULL,
                signal_type TEXT,
                price_at_signal REAL,
                sentiment_at_signal REAL,
                return_1d REAL,
                return_5d REAL,
                return_20d REAL,
                max_gain REAL,
                max_drawdown REAL,
                was_profitable BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS source_accuracy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL UNIQUE,
                total_predictions INTEGER DEFAULT 0,
                correct_predictions INTEGER DEFAULT 0,
                accuracy_rate REAL,
                last_updated DATETIME
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS market_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL UNIQUE,
                regime TEXT,
                volatility_level REAL,
                sp500_pct_change REAL,
                nasdaq_pct_change REAL,
                mood_score REAL,
                bullish_ratio REAL,
                sector_sentiment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        _migrate_add_quant_columns(conn)
        _migrate_add_market_indices_table(conn)
        _migrate_add_sentiment_columns(conn)
        _migrate_add_fred_tables(conn)
    print("[OK] Database initialized!")

def _migrate_add_quant_columns(conn):
    """Add quant columns to existing tables (backwards compatible)."""
    c = conn.cursor()
    c.execute("PRAGMA table_info(news)")
    columns = [col[1] for col in c.fetchall()]

    new_cols = [
        ("tickers", "TEXT"),
        ("sector", "TEXT"),
        ("direction", "TEXT"),
        ("confidence", "REAL"),
        ("catalysts", "TEXT")
    ]

    for col_name, col_type in new_cols:
        if col_name not in columns:
            c.execute(f"ALTER TABLE news ADD COLUMN {col_name} {col_type}")
    conn.commit()

def _migrate_add_market_indices_table(conn):
    """Ensure market_indices table exists (backwards compatible)."""
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_indices'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE market_indices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                date DATE NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                pct_change REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_market_symbol_date ON market_indices(symbol, date)')
        conn.commit()

def _migrate_add_sentiment_columns(conn):
    """Add composite sentiment columns to news table (backwards compatible)."""
    c = conn.cursor()
    c.execute("PRAGMA table_info(news)")
    columns = [col[1] for col in c.fetchall()]

    new_cols = [
        ("composite_sentiment", "REAL"),
        ("sentiment_sources", "TEXT")
    ]

    for col_name, col_type in new_cols:
        if col_name not in columns:
            c.execute(f"ALTER TABLE news ADD COLUMN {col_name} {col_type}")
    conn.commit()


def _migrate_add_fred_tables(conn):
    """Add FRED economic indicator tables (backwards compatible)."""
    c = conn.cursor()

    # Raw FRED indicator values
    c.execute('''
        CREATE TABLE IF NOT EXISTS fred_indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id TEXT NOT NULL,
            indicator_name TEXT NOT NULL,
            category TEXT NOT NULL,
            value REAL NOT NULL,
            observation_date DATE NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(series_id, observation_date)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_fred_series_date ON fred_indicators(series_id, observation_date)')

    # Normalized health scores per indicator
    c.execute('''
        CREATE TABLE IF NOT EXISTS indicator_health_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id TEXT NOT NULL,
            observation_date DATE NOT NULL,
            raw_value REAL NOT NULL,
            health_score REAL NOT NULL,
            trend TEXT,
            percentile REAL,
            UNIQUE(series_id, observation_date)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_health_series_date ON indicator_health_scores(series_id, observation_date)')

    # Composite economic health
    c.execute('''
        CREATE TABLE IF NOT EXISTS economic_health_composite (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL UNIQUE,
            overall_score REAL NOT NULL,
            regime TEXT NOT NULL,
            growth_score REAL,
            labor_score REAL,
            inflation_score REAL,
            rates_score REAL,
            consumer_score REAL,
            financial_score REAL,
            recession_probability REAL,
            yield_curve_inverted BOOLEAN DEFAULT 0,
            inversion_months INTEGER DEFAULT 0,
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_health_date ON economic_health_composite(date)')

    conn.commit()

def add_news_placeholder(source, title, url, published_at):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR IGNORE INTO news (source, title, url, published_at)
                VALUES (?, ?, ?, ?)
            ''', (source, title, url, published_at))
            conn.commit()
            return c.lastrowid
    except Exception as e:
        print(f"Eroare DB: {e}")
        return None

def get_unprocessed_news():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        c.execute("SELECT * FROM news WHERE ai_summary IS NULL")
        return [dict(row) for row in c.fetchall()]

def update_news_analysis(url, content, summary, score, is_important,
                         tickers=None, sector=None, direction=None,
                         confidence=None, catalysts=None):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        tickers_json = json.dumps(tickers) if tickers else None
        catalysts_json = json.dumps(catalysts) if catalysts else None
        c.execute('''
            UPDATE news
            SET full_content = ?, ai_summary = ?, impact_score = ?, is_important = ?,
                tickers = ?, sector = ?, direction = ?, confidence = ?, catalysts = ?
            WHERE url = ?
        ''', (content, summary, score, is_important,
              tickers_json, sector, direction, confidence, catalysts_json, url))
        conn.commit()

def calculate_time_decay_score(impact_score, created_at_str):
    """Calculate time-decay weighted score. Half-life ~7 hours (λ=0.1)."""
    if not impact_score or not created_at_str:
        return impact_score or 0
    try:
        created_at = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
        hours_old = (datetime.now() - created_at).total_seconds() / 3600
        decay_factor = math.exp(-0.1 * hours_old)
        return round(impact_score * decay_factor, 2)
    except:
        return impact_score

def get_news_with_signals(only_saved=False, sector_filter=None, direction_filter=None, sentiment_filter=None):
    """Get analyzed news with optional filters."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        query = "SELECT * FROM news WHERE ai_summary IS NOT NULL"
        params = []

        if only_saved:
            query += " AND is_saved = 1"
        if sector_filter:
            query += " AND sector = ?"
            params.append(sector_filter)
        if direction_filter:
            query += " AND direction = ?"
            params.append(direction_filter)
        if sentiment_filter:
            query += " AND sentiment = ?"
            params.append(sentiment_filter)

        query += " ORDER BY published_at DESC"
        c.execute(query, params)

        results = []
        for row in c.fetchall():
            item = dict(row)
            if item.get('tickers'):
                item['tickers'] = json.loads(item['tickers'])
            if item.get('catalysts'):
                item['catalysts'] = json.loads(item['catalysts'])
            item['weighted_score'] = calculate_time_decay_score(
                item.get('impact_score'), item.get('created_at')
            )
            item['high_conviction'] = (
                (item.get('confidence') or 0) >= 0.8 and
                (item.get('impact_score') or 0) >= 7
            )
            results.append(item)
        return results

def get_ticker_aggregation():
    """Aggregate news by ticker with composite signals."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT tickers, direction, confidence, impact_score, COUNT(*) as count
            FROM news
            WHERE tickers IS NOT NULL AND ai_summary IS NOT NULL
            GROUP BY tickers
            ORDER BY count DESC
        """)

        aggregated = {}
        for row in c.fetchall():
            tickers_json = row['tickers']
            if not tickers_json:
                continue
            tickers = json.loads(tickers_json)
            for ticker in tickers:
                if ticker not in aggregated:
                    aggregated[ticker] = {
                        'ticker': ticker,
                        'count': 0,
                        'bullish': 0,
                        'bearish': 0,
                        'neutral': 0,
                        'avg_confidence': 0,
                        'max_impact': 0
                    }
                aggregated[ticker]['count'] += 1
                direction = row['direction'] or 'neutral'
                aggregated[ticker][direction] += 1
                if row['confidence']:
                    aggregated[ticker]['avg_confidence'] += row['confidence']
                if row['impact_score'] and row['impact_score'] > aggregated[ticker]['max_impact']:
                    aggregated[ticker]['max_impact'] = row['impact_score']

        for ticker in aggregated:
            count = aggregated[ticker]['count']
            if count > 0:
                aggregated[ticker]['avg_confidence'] = round(
                    aggregated[ticker]['avg_confidence'] / count, 2
                )
                bull = aggregated[ticker]['bullish']
                bear = aggregated[ticker]['bearish']
                if bull > bear:
                    aggregated[ticker]['composite_signal'] = 'bullish'
                elif bear > bull:
                    aggregated[ticker]['composite_signal'] = 'bearish'
                else:
                    aggregated[ticker]['composite_signal'] = 'neutral'

        return list(aggregated.values())

def get_available_sectors():
    """Get list of sectors that have news."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT sector FROM news
            WHERE sector IS NOT NULL AND ai_summary IS NOT NULL
            ORDER BY sector
        """)
        return [row[0] for row in c.fetchall()]

# --- TOGGLE SAVE ---
def toggle_save_status(news_id):
    """Schimbă statusul: dacă e salvat devine nesalvat și invers."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Verificăm starea actuală
        c.execute("SELECT is_saved FROM news WHERE id = ?", (news_id,))
        current_status = c.fetchone()[0]
        
        # O inversăm (0 devine 1, 1 devine 0)
        new_status = 0 if current_status else 1
        
        c.execute("UPDATE news SET is_saved = ? WHERE id = ?", (new_status, news_id))
        conn.commit()
        return new_status

# --- MARKET INDICES ---
MARKET_INDICES = {
    '^IXIC': 'NASDAQ',
    '^GSPC': 'S&P 500',
    '^DJI': 'Dow Jones'
}

def save_market_data(symbol, data_rows):
    """Bulk insert/update market data. data_rows is list of dicts with date, open, high, low, close, volume."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        for row in data_rows:
            c.execute('''
                INSERT OR REPLACE INTO market_indices (symbol, date, open, high, low, close, volume, pct_change)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (symbol, row['date'], row['open'], row['high'], row['low'], row['close'], row['volume'], row.get('pct_change')))
        conn.commit()
    return len(data_rows)

def get_market_data(symbol, start_date=None, end_date=None):
    """Get market data for a symbol with optional date range."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        query = "SELECT * FROM market_indices WHERE symbol = ?"
        params = [symbol]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date ASC"
        c.execute(query, params)
        return [dict(row) for row in c.fetchall()]

def get_latest_market_date(symbol):
    """Get the most recent date we have data for."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT MAX(date) FROM market_indices WHERE symbol = ?", (symbol,))
        result = c.fetchone()[0]
        return result

def calculate_pct_changes(symbol):
    """Calculate day-over-day percentage changes for stored data."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, date, close FROM market_indices
            WHERE symbol = ? ORDER BY date ASC
        """, (symbol,))
        rows = c.fetchall()

        prev_close = None
        for row in rows:
            id_, date_, close = row
            if prev_close and close:
                pct_change = ((close - prev_close) / prev_close) * 100
                c.execute("UPDATE market_indices SET pct_change = ? WHERE id = ?", (round(pct_change, 4), id_))
            prev_close = close
        conn.commit()

def get_down_days(symbol, threshold=-2.0):
    """Get days where close dropped more than threshold % from previous day."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT * FROM market_indices
            WHERE symbol = ? AND pct_change IS NOT NULL AND pct_change <= ?
            ORDER BY date DESC
        """, (symbol, threshold))
        return [dict(row) for row in c.fetchall()]

def get_market_data_count(symbol):
    """Get count of records for a symbol."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM market_indices WHERE symbol = ?", (symbol,))
        return c.fetchone()[0]


# --- SENTIMENT INTELLIGENCE ---

def save_sentiment_snapshot(ticker, source, sentiment_score, raw_score=None,
                            confidence=None, volume=None, metadata=None):
    """Save a sentiment reading from a specific source."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        metadata_json = json.dumps(metadata) if metadata else None
        c.execute('''
            INSERT OR REPLACE INTO sentiment_snapshots
            (ticker, source, sentiment_score, raw_score, confidence, volume, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (ticker, source, sentiment_score, raw_score, confidence, volume, metadata_json))
        conn.commit()
        return c.lastrowid

def get_sentiment_snapshots(ticker, hours=24):
    """Get recent sentiment snapshots for a ticker."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT * FROM sentiment_snapshots
            WHERE ticker = ? AND timestamp >= datetime('now', ?)
            ORDER BY timestamp DESC
        """, (ticker, f'-{hours} hours'))
        results = []
        for row in c.fetchall():
            item = dict(row)
            if item.get('metadata'):
                item['metadata'] = json.loads(item['metadata'])
            results.append(item)
        return results

def get_latest_sentiment_by_source(ticker):
    """Get the most recent sentiment from each source for a ticker."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT s1.* FROM sentiment_snapshots s1
            INNER JOIN (
                SELECT source, MAX(timestamp) as max_ts
                FROM sentiment_snapshots
                WHERE ticker = ?
                GROUP BY source
            ) s2 ON s1.source = s2.source AND s1.timestamp = s2.max_ts
            WHERE s1.ticker = ?
        """, (ticker, ticker))
        results = {}
        for row in c.fetchall():
            item = dict(row)
            if item.get('metadata'):
                item['metadata'] = json.loads(item['metadata'])
            results[item['source']] = item
        return results

def save_ticker_sentiment(ticker, composite_score, composite_direction, confidence,
                          consensus_strength=None, momentum=None, velocity=None,
                          source_breakdown=None, signal=None, signal_confidence=None,
                          signal_reasons=None, risk_factors=None, timing_score=None):
    """Save or update aggregated sentiment for a ticker."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        source_json = json.dumps(source_breakdown) if source_breakdown else None
        reasons_json = json.dumps(signal_reasons) if signal_reasons else None
        risks_json = json.dumps(risk_factors) if risk_factors else None
        c.execute('''
            INSERT OR REPLACE INTO ticker_sentiment
            (ticker, composite_score, composite_direction, confidence, consensus_strength,
             momentum, velocity, last_updated, source_breakdown, signal, signal_confidence,
             signal_reasons, risk_factors, timing_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?, ?)
        ''', (ticker, composite_score, composite_direction, confidence, consensus_strength,
              momentum, velocity, source_json, signal, signal_confidence,
              reasons_json, risks_json, timing_score))
        conn.commit()

def get_ticker_sentiment(ticker):
    """Get aggregated sentiment for a single ticker."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM ticker_sentiment WHERE ticker = ?", (ticker,))
        row = c.fetchone()
        if row:
            item = dict(row)
            if item.get('source_breakdown'):
                item['source_breakdown'] = json.loads(item['source_breakdown'])
            if item.get('signal_reasons'):
                item['signal_reasons'] = json.loads(item['signal_reasons'])
            if item.get('risk_factors'):
                item['risk_factors'] = json.loads(item['risk_factors'])
            return item
        return None

def get_all_ticker_sentiments(signal_filter=None):
    """Get sentiment for all tickers with optional signal filter."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        query = "SELECT * FROM ticker_sentiment"
        params = []
        if signal_filter:
            query += " WHERE signal = ?"
            params.append(signal_filter)
        query += " ORDER BY ABS(composite_score) DESC"
        c.execute(query, params)
        results = []
        for row in c.fetchall():
            item = dict(row)
            if item.get('source_breakdown'):
                item['source_breakdown'] = json.loads(item['source_breakdown'])
            if item.get('signal_reasons'):
                item['signal_reasons'] = json.loads(item['signal_reasons'])
            if item.get('risk_factors'):
                item['risk_factors'] = json.loads(item['risk_factors'])
            results.append(item)
        return results

def get_signals_by_type(signal_types=None):
    """Get tickers grouped by signal type."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        if signal_types:
            placeholders = ','.join('?' * len(signal_types))
            c.execute(f"""
                SELECT * FROM ticker_sentiment
                WHERE signal IN ({placeholders})
                ORDER BY signal_confidence DESC
            """, signal_types)
        else:
            c.execute("""
                SELECT * FROM ticker_sentiment
                WHERE signal IS NOT NULL
                ORDER BY signal_confidence DESC
            """)
        results = []
        for row in c.fetchall():
            item = dict(row)
            if item.get('source_breakdown'):
                item['source_breakdown'] = json.loads(item['source_breakdown'])
            if item.get('signal_reasons'):
                item['signal_reasons'] = json.loads(item['signal_reasons'])
            if item.get('risk_factors'):
                item['risk_factors'] = json.loads(item['risk_factors'])
            results.append(item)
        return results

def save_sentiment_history(ticker, date, open_sentiment, close_sentiment,
                           high_sentiment, low_sentiment, avg_sentiment, volume):
    """Save daily sentiment OHLC for backtesting."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO sentiment_history
            (ticker, date, open_sentiment, close_sentiment, high_sentiment,
             low_sentiment, avg_sentiment, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ticker, date, open_sentiment, close_sentiment, high_sentiment,
              low_sentiment, avg_sentiment, volume))
        conn.commit()

def get_sentiment_history(ticker, days=30):
    """Get historical sentiment for a ticker."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT * FROM sentiment_history
            WHERE ticker = ? AND date >= date('now', ?)
            ORDER BY date ASC
        """, (ticker, f'-{days} days'))
        return [dict(row) for row in c.fetchall()]

def save_signal_performance(ticker, signal_date, signal_type, price_at_signal,
                            sentiment_at_signal):
    """Record a signal for future performance tracking."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO signal_performance
            (ticker, signal_date, signal_type, price_at_signal, sentiment_at_signal)
            VALUES (?, ?, ?, ?, ?)
        ''', (ticker, signal_date, signal_type, price_at_signal, sentiment_at_signal))
        conn.commit()
        return c.lastrowid

def update_signal_performance(signal_id, return_1d=None, return_5d=None, return_20d=None,
                              max_gain=None, max_drawdown=None, was_profitable=None):
    """Update signal performance with actual returns."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        updates = []
        params = []
        if return_1d is not None:
            updates.append("return_1d = ?")
            params.append(return_1d)
        if return_5d is not None:
            updates.append("return_5d = ?")
            params.append(return_5d)
        if return_20d is not None:
            updates.append("return_20d = ?")
            params.append(return_20d)
        if max_gain is not None:
            updates.append("max_gain = ?")
            params.append(max_gain)
        if max_drawdown is not None:
            updates.append("max_drawdown = ?")
            params.append(max_drawdown)
        if was_profitable is not None:
            updates.append("was_profitable = ?")
            params.append(was_profitable)
        if updates:
            params.append(signal_id)
            c.execute(f"UPDATE signal_performance SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

def get_signal_performance_stats():
    """Get aggregated signal performance statistics."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT signal_type,
                   COUNT(*) as total,
                   SUM(CASE WHEN was_profitable = 1 THEN 1 ELSE 0 END) as profitable,
                   AVG(return_5d) as avg_return_5d,
                   AVG(return_20d) as avg_return_20d
            FROM signal_performance
            WHERE was_profitable IS NOT NULL
            GROUP BY signal_type
        """)
        return [dict(row) for row in c.fetchall()]

def save_source_accuracy(source, total_predictions, correct_predictions):
    """Update accuracy tracking for a sentiment source."""
    accuracy_rate = correct_predictions / total_predictions if total_predictions > 0 else 0
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO source_accuracy
            (source, total_predictions, correct_predictions, accuracy_rate, last_updated)
            VALUES (?, ?, ?, ?, datetime('now'))
        ''', (source, total_predictions, correct_predictions, accuracy_rate))
        conn.commit()

def get_source_accuracy():
    """Get accuracy stats for all sources."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM source_accuracy ORDER BY accuracy_rate DESC")
        return [dict(row) for row in c.fetchall()]

def save_market_context(date, regime, volatility_level, sp500_pct_change=None,
                        nasdaq_pct_change=None, mood_score=None, bullish_ratio=None,
                        sector_sentiment=None):
    """Save daily market context snapshot."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        sector_json = json.dumps(sector_sentiment) if sector_sentiment else None
        c.execute('''
            INSERT OR REPLACE INTO market_context
            (date, regime, volatility_level, sp500_pct_change, nasdaq_pct_change,
             mood_score, bullish_ratio, sector_sentiment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, regime, volatility_level, sp500_pct_change, nasdaq_pct_change,
              mood_score, bullish_ratio, sector_json))
        conn.commit()

def get_latest_market_context():
    """Get most recent market context."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM market_context ORDER BY date DESC LIMIT 1")
        row = c.fetchone()
        if row:
            item = dict(row)
            if item.get('sector_sentiment'):
                item['sector_sentiment'] = json.loads(item['sector_sentiment'])
            return item
        return None

def get_market_context_history(days=30):
    """Get market context history."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT * FROM market_context
            WHERE date >= date('now', ?)
            ORDER BY date ASC
        """, (f'-{days} days',))
        results = []
        for row in c.fetchall():
            item = dict(row)
            if item.get('sector_sentiment'):
                item['sector_sentiment'] = json.loads(item['sector_sentiment'])
            results.append(item)
        return results


# --- FRED ECONOMIC INDICATORS ---

def save_fred_indicator(series_id, indicator_name, category, value, observation_date):
    """Save a FRED indicator value."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO fred_indicators
            (series_id, indicator_name, category, value, observation_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (series_id, indicator_name, category, value, observation_date))
        conn.commit()
        return c.lastrowid


def save_fred_indicators_bulk(indicators):
    """Bulk save FRED indicator values. indicators is list of dicts."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        for ind in indicators:
            c.execute('''
                INSERT OR REPLACE INTO fred_indicators
                (series_id, indicator_name, category, value, observation_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (ind['series_id'], ind['indicator_name'], ind['category'],
                  ind['value'], ind['observation_date']))
        conn.commit()
    return len(indicators)


def get_fred_indicator(series_id, start_date=None, end_date=None):
    """Get FRED indicator values with optional date range."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        query = "SELECT * FROM fred_indicators WHERE series_id = ?"
        params = [series_id]
        if start_date:
            query += " AND observation_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND observation_date <= ?"
            params.append(end_date)
        query += " ORDER BY observation_date ASC"
        c.execute(query, params)
        return [dict(row) for row in c.fetchall()]


def get_latest_fred_indicators():
    """Get most recent value for each indicator."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT f1.* FROM fred_indicators f1
            INNER JOIN (
                SELECT series_id, MAX(observation_date) as max_date
                FROM fred_indicators
                GROUP BY series_id
            ) f2 ON f1.series_id = f2.series_id AND f1.observation_date = f2.max_date
        """)
        return {row['series_id']: dict(row) for row in c.fetchall()}


def get_fred_indicator_history(series_id, years=10):
    """Get historical data for percentile calculation."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT * FROM fred_indicators
            WHERE series_id = ? AND observation_date >= date('now', ?)
            ORDER BY observation_date ASC
        """, (series_id, f'-{years} years'))
        return [dict(row) for row in c.fetchall()]


def save_indicator_health_score(series_id, observation_date, raw_value, health_score,
                                 trend=None, percentile=None):
    """Save normalized health score for an indicator."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO indicator_health_scores
            (series_id, observation_date, raw_value, health_score, trend, percentile)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (series_id, observation_date, raw_value, health_score, trend, percentile))
        conn.commit()


def get_latest_health_scores():
    """Get most recent health score for each indicator."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT h1.* FROM indicator_health_scores h1
            INNER JOIN (
                SELECT series_id, MAX(observation_date) as max_date
                FROM indicator_health_scores
                GROUP BY series_id
            ) h2 ON h1.series_id = h2.series_id AND h1.observation_date = h2.max_date
        """)
        return {row['series_id']: dict(row) for row in c.fetchall()}


def save_economic_health_composite(date, overall_score, regime, category_scores,
                                    recession_probability=None, yield_curve_inverted=False,
                                    inversion_months=0):
    """Save composite economic health snapshot."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO economic_health_composite
            (date, overall_score, regime, growth_score, labor_score, inflation_score,
             rates_score, consumer_score, financial_score, recession_probability,
             yield_curve_inverted, inversion_months)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, overall_score, regime,
              category_scores.get('growth'),
              category_scores.get('labor'),
              category_scores.get('inflation'),
              category_scores.get('rates'),
              category_scores.get('consumer'),
              category_scores.get('financial'),
              recession_probability, yield_curve_inverted, inversion_months))
        conn.commit()


def get_latest_economic_health():
    """Get most recent economic health composite."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM economic_health_composite ORDER BY date DESC LIMIT 1")
        row = c.fetchone()
        return dict(row) if row else None


def get_economic_health_history(days=730):
    """Get economic health history (default 2 years)."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT * FROM economic_health_composite
            WHERE date >= date('now', ?)
            ORDER BY date ASC
        """, (f'-{days} days',))
        return [dict(row) for row in c.fetchall()]


def get_yield_curve_history(months=6):
    """Get yield curve spread history for inversion detection."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT observation_date, value FROM fred_indicators
            WHERE series_id = 'T10Y2Y' AND observation_date >= date('now', ?)
            ORDER BY observation_date ASC
        """, (f'-{months} months',))
        return [dict(row) for row in c.fetchall()]


if __name__ == "__main__":
    init_db()