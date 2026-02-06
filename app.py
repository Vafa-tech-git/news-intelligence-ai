from flask import Flask, render_template, request, jsonify
import sqlite3
import database
from modules import news_fetcher, web_scraper, ai_analyst, market_fetcher
from modules.sentiment_aggregator import aggregate_ticker_sentiment, get_market_sentiment_summary
from modules.signal_generator import generate_signal, get_actionable_signals
from modules.market_analyzer import analyze_market, get_market_context, MarketAnalyzer
from modules.economic_health import (
    get_economic_health, get_economic_health_history, refresh_economic_data
)
from modules.market_recommender import (
    get_recommendation, get_market_recommendation, get_ticker_recommendation
)
from config import FRED_INDICATORS, CATEGORY_WEIGHTS

app = Flask(__name__)

with app.app_context():
    database.init_db()

@app.route('/')
def index():
    """Main page with optional filters."""
    sector = request.args.get('sector')
    direction = request.args.get('direction')
    sentiment = request.args.get('sentiment')
    refresh = request.args.get('refresh', '60')

    news_list = database.get_news_with_signals(
        only_saved=False, sector_filter=sector, direction_filter=direction, sentiment_filter=sentiment
    )
    sectors = database.get_available_sectors()

    return render_template('index.html',
        news_list=news_list,
        showing_saved=False,
        sectors=sectors,
        current_sector=sector,
        current_direction=direction,
        current_sentiment=sentiment,
        refresh_interval=refresh
    )

@app.route('/saved')
def saved_news():
    sector = request.args.get('sector')
    direction = request.args.get('direction')
    sentiment = request.args.get('sentiment')

    news_list = database.get_news_with_signals(
        only_saved=True, sector_filter=sector, direction_filter=direction, sentiment_filter=sentiment
    )
    sectors = database.get_available_sectors()

    return render_template('index.html',
        news_list=news_list,
        showing_saved=True,
        sectors=sectors,
        current_sector=sector,
        current_direction=direction,
        current_sentiment=sentiment,
        refresh_interval='0'
    )

# --- RUTĂ NOUĂ PENTRU BUTONUL DE SAVE ---
@app.route('/toggle-save/<int:news_id>', methods=['POST'])
def toggle_save(news_id):
    # Schimbăm starea în DB
    new_status = database.toggle_save_status(news_id)
    
    # Returnăm doar butonul actualizat (nu toată pagina)
    # Iconița se schimbă în funcție de new_status
    return render_template('save_button.html', is_saved=new_status, news_id=news_id)

@app.route('/scan-news', methods=['POST'])
def scan_news():
    """HTMX endpoint - returns news cards HTML."""
    print("🚀 Scan started...")

    news_fetcher.fetch_finnhub_news()
    news_fetcher.fetch_rss_feeds()

    unprocessed = database.get_unprocessed_news()

    count = 0
    for item in unprocessed:
        if count >= 10:
            break

        print(f"   ⚙️ Processing: {item['title']}...")
        content = web_scraper.get_article_content(item['url'])

        if content:
            ai_result = ai_analyst.analyze_article(content)

            if ai_result:
                database.update_news_analysis(
                    item['url'],
                    content,
                    ai_result.get('summary'),
                    ai_result.get('impact_score'),
                    ai_result.get('is_important'),
                    tickers=ai_result.get('tickers'),
                    sector=ai_result.get('sector'),
                    direction=ai_result.get('direction'),
                    confidence=ai_result.get('confidence'),
                    catalysts=ai_result.get('catalysts')
                )
                count += 1
        else:
            print("   ⚠️ Could not extract content. Skipping.")

    all_news = database.get_news_with_signals()

    html_response = ""
    for news_item in all_news:
        html_response += render_template('news_card.html', news=news_item)

    if not all_news:
        return "<div class='p-4 text-gray-400 text-center'>No new important news found.</div>"

    return html_response

@app.route('/reset-db', methods=['POST'])
def reset_db():
    with sqlite3.connect(database.DB_NAME) as conn:
        conn.execute("DELETE FROM news WHERE is_saved = 0")

    all_news = database.get_news_with_signals()
    html_response = ""
    for news_item in all_news:
        html_response += render_template('news_card.html', news=news_item)

    if not all_news:
        return "<div class='p-4 text-gray-400 text-center'>Database cleared (saved items preserved).</div>"

    return html_response

@app.route('/api/tickers')
def api_tickers():
    """API endpoint for ticker aggregation."""
    tickers = database.get_ticker_aggregation()
    return jsonify(tickers)

@app.route('/tickers')
def tickers_view():
    """Ticker aggregation view."""
    tickers = database.get_ticker_aggregation()
    return render_template('tickers.html', tickers=tickers)

@app.route('/feed')
def feed_partial():
    """HTMX partial for auto-refresh."""
    sector = request.args.get('sector')
    direction = request.args.get('direction')
    sentiment = request.args.get('sentiment')

    news_list = database.get_news_with_signals(
        only_saved=False, sector_filter=sector, direction_filter=direction, sentiment_filter=sentiment
    )

    html_response = ""
    for news_item in news_list:
        html_response += render_template('news_card.html', news=news_item)

    if not news_list:
        return "<div class='p-4 text-gray-400 text-center'>No news found.</div>"

    return html_response

# --- MARKET INDICES ---
@app.route('/markets')
def markets_view():
    """Market indices historical charts view."""
    symbol = request.args.get('symbol', '^GSPC')
    market_fetcher.ensure_data_loaded(symbol)
    return render_template('markets.html',
        current_symbol=symbol,
        indices=database.MARKET_INDICES
    )

@app.route('/api/markets/<symbol>')
def api_market_data(symbol):
    """API endpoint for market data."""
    start = request.args.get('start')
    end = request.args.get('end')
    data = database.get_market_data(symbol, start_date=start, end_date=end)
    return jsonify(data)

@app.route('/refresh-markets', methods=['POST'])
def refresh_markets():
    """HTMX endpoint to refresh market data."""
    symbol = request.args.get('symbol', '^GSPC')
    results = market_fetcher.refresh_all_indices()
    total = sum(results.values())
    return f"<span class='refresh-status'>Updated {total} records</span>"


# --- SENTIMENT INTELLIGENCE ---

@app.route('/signals')
def signals_view():
    """Trading signals dashboard."""
    signal_filter = request.args.get('signal')
    if signal_filter:
        signals = database.get_signals_by_type([signal_filter])
    else:
        signals = get_actionable_signals()

    market_context = get_market_context()
    analyzer = MarketAnalyzer()

    return render_template('signals.html',
        signals=signals,
        market_context=market_context,
        mood_label=analyzer.get_mood_label(market_context.get('mood_score', 50)) if market_context else 'Unknown',
        regime_label=analyzer.get_regime_label(market_context.get('regime', 'neutral')) if market_context else 'Unknown',
        current_signal=signal_filter
    )

@app.route('/market-sentiment')
def market_sentiment_view():
    """Market sentiment overview page."""
    market_context = analyze_market()
    sentiment_summary = get_market_sentiment_summary()
    sector_sentiment = market_context.get('sector_sentiment', {}) if market_context else {}

    analyzer = MarketAnalyzer()

    return render_template('market_sentiment.html',
        market_context=market_context,
        sentiment_summary=sentiment_summary,
        sector_sentiment=sector_sentiment,
        mood_label=analyzer.get_mood_label(market_context.get('mood_score', 50)) if market_context else 'Unknown',
        regime_label=analyzer.get_regime_label(market_context.get('regime', 'neutral')) if market_context else 'Unknown'
    )

@app.route('/backtest')
def backtest_view():
    """Backtesting dashboard."""
    signal_stats = database.get_signal_performance_stats()
    source_accuracy = database.get_source_accuracy()

    return render_template('backtest.html',
        signal_stats=signal_stats,
        source_accuracy=source_accuracy
    )

# --- SENTIMENT API ENDPOINTS ---

@app.route('/api/sentiment/<ticker>')
def api_ticker_sentiment(ticker):
    """API endpoint for ticker sentiment details."""
    sentiment = database.get_ticker_sentiment(ticker)
    if sentiment:
        return jsonify(sentiment)
    return jsonify({'error': 'No sentiment data found'}), 404

@app.route('/api/signals')
def api_signals():
    """API endpoint for current signals."""
    signal_types = request.args.getlist('type')
    if signal_types:
        signals = database.get_signals_by_type(signal_types)
    else:
        signals = get_actionable_signals()
    return jsonify(signals)

@app.route('/api/signals/<ticker>')
def api_ticker_signal(ticker):
    """API endpoint for a specific ticker's signal."""
    sentiment = database.get_ticker_sentiment(ticker)
    if not sentiment:
        return jsonify({'error': 'No sentiment data found for ticker'}), 404

    market_context = get_market_context()
    signal = generate_signal(ticker, sentiment, market_context)

    return jsonify({
        'ticker': ticker,
        'sentiment': sentiment,
        'signal': signal,
        'market_context': market_context
    })

@app.route('/api/market-mood')
def api_market_mood():
    """API endpoint for market mood."""
    context = get_market_context()
    if context:
        analyzer = MarketAnalyzer()
        context['mood_label'] = analyzer.get_mood_label(context.get('mood_score', 50))
        context['regime_label'] = analyzer.get_regime_label(context.get('regime', 'neutral'))
        return jsonify(context)
    return jsonify({'error': 'No market data available'}), 404

@app.route('/api/backtest/accuracy')
def api_backtest_accuracy():
    """API endpoint for signal accuracy metrics."""
    stats = database.get_signal_performance_stats()
    source_acc = database.get_source_accuracy()
    return jsonify({
        'signal_stats': stats,
        'source_accuracy': source_acc
    })

@app.route('/scan-sentiment/<ticker>', methods=['POST'])
def scan_sentiment(ticker):
    """HTMX endpoint to fetch sentiment for a ticker."""
    try:
        result = aggregate_ticker_sentiment(ticker, use_cache=False)
        if result:
            market_context = get_market_context()
            signal = generate_signal(ticker, result, market_context)
            return jsonify({'success': True, 'data': result, 'signal': signal})
        return jsonify({'success': False, 'error': 'No sentiment data available'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- ECONOMIC HEALTH ---

@app.route('/economy')
def economy_view():
    """Economic Health Dashboard."""
    economic_health = get_economic_health()
    history = get_economic_health_history(days=730)

    # Get regime color and label
    regime_colors = {
        'expansion': 'green',
        'peak': 'yellow',
        'contraction': 'orange',
        'trough': 'red'
    }
    regime_labels = {
        'expansion': 'Expansion',
        'peak': 'Peak',
        'contraction': 'Contraction',
        'trough': 'Trough'
    }

    regime = economic_health.get('regime', 'unknown') if economic_health else 'unknown'

    return render_template('economic_health.html',
        health=economic_health,
        history=history,
        indicators=FRED_INDICATORS,
        category_weights=CATEGORY_WEIGHTS,
        regime_color=regime_colors.get(regime, 'gray'),
        regime_label=regime_labels.get(regime, 'Unknown')
    )


@app.route('/api/economic-health')
def api_economic_health():
    """API endpoint for economic health data."""
    health = get_economic_health()
    if health:
        return jsonify(health)
    return jsonify({'error': 'No economic health data available'}), 404


@app.route('/api/economic-health/history')
def api_economic_health_history():
    """API endpoint for economic health history."""
    days = request.args.get('days', 730, type=int)
    history = get_economic_health_history(days=days)
    return jsonify(history)


@app.route('/api/economic-health/indicators')
def api_economic_indicators():
    """API endpoint for configured indicators."""
    return jsonify(FRED_INDICATORS)


@app.route('/refresh-economic-data', methods=['POST'])
def refresh_economic():
    """HTMX endpoint to refresh economic data from FRED."""
    try:
        backfill = request.args.get('backfill', 'false').lower() == 'true'
        print(f"[REFRESH] Starting FRED data refresh (backfill={backfill})...")
        result = refresh_economic_data(backfill=backfill)

        if result and result.get('health'):
            health = result['health']
            return f"""<span class='refresh-status'>
                Updated {result.get('observations_fetched', 0)} observations.
                Economic Health: {health.get('overall_score', 'N/A')} ({health.get('regime', 'N/A')})
            </span>"""
        elif result and result.get('observations_fetched', 0) > 0:
            return f"<span class='refresh-status'>Fetched {result.get('observations_fetched')} observations but health calculation failed. Refresh the page.</span>"
        return "<span class='refresh-status'>No data fetched. Check FRED API key in .env file.</span>"
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"<span class='refresh-status error'>Error: {str(e)}</span>"


@app.route('/api/fred-status')
def api_fred_status():
    """Diagnostic endpoint to check FRED data status."""
    from modules.fred_fetcher import get_fred_fetcher
    fetcher = get_fred_fetcher()

    # Check what's in the database
    indicators_in_db = database.get_latest_fred_indicators()

    return jsonify({
        'fred_available': fetcher.is_available(),
        'api_key_set': bool(fetcher.api_key),
        'indicators_in_db': len(indicators_in_db),
        'indicator_ids': list(indicators_in_db.keys()) if indicators_in_db else [],
        'configured_indicators': len(FRED_INDICATORS)
    })


# --- MARKET RECOMMENDATION ---

@app.route('/recommendation')
def recommendation_view():
    """Market Recommendation Dashboard - Is now a good time to buy?"""
    ticker = request.args.get('ticker')

    try:
        if ticker:
            recommendation = get_ticker_recommendation(ticker.upper())
        else:
            recommendation = get_market_recommendation()
    except Exception as e:
        recommendation = {
            'ticker': ticker or 'MARKET',
            'recommendation': {
                'action': 'UNAVAILABLE',
                'color': '#6b7280',
                'bg_color': '#f3f4f6',
                'description': f'Could not calculate recommendation: {str(e)}',
                'short_desc': 'Error'
            },
            'composite_score': 0,
            'breakdown': {},
            'confidence': {'level': 'low', 'score': 0},
            'reasons': [str(e)],
            'timestamp': None
        }

    # Get market context for additional info
    market_context = get_market_context()
    analyzer = MarketAnalyzer()

    return render_template('recommendation.html',
        recommendation=recommendation,
        market_context=market_context,
        mood_label=analyzer.get_mood_label(market_context.get('mood_score', 50)) if market_context else 'Unknown',
        regime_label=analyzer.get_regime_label(market_context.get('regime', 'neutral')) if market_context else 'Unknown',
        current_ticker=ticker
    )


@app.route('/api/recommendation')
def api_recommendation():
    """API endpoint for market-wide recommendation."""
    try:
        recommendation = get_market_recommendation()
        return jsonify(recommendation)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/recommendation/<ticker>')
def api_ticker_recommendation(ticker):
    """API endpoint for ticker-specific recommendation."""
    try:
        recommendation = get_ticker_recommendation(ticker.upper())
        return jsonify(recommendation)
    except Exception as e:
        return jsonify({'error': str(e), 'ticker': ticker}), 500


@app.route('/refresh-recommendation', methods=['POST'])
def refresh_recommendation():
    """HTMX endpoint to refresh recommendation widget."""
    ticker = request.args.get('ticker')

    try:
        if ticker:
            recommendation = get_ticker_recommendation(ticker.upper())
        else:
            recommendation = get_market_recommendation()

        return render_template('recommendation_widget.html', recommendation=recommendation)
    except Exception as e:
        return f"<div class='text-red-400'>Error: {str(e)}</div>"


if __name__ == '__main__':
    # Pornim serverul în modul Debug (ne arată erorile în browser)
    app.run(debug=True, port=8080)