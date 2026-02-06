# Enhanced Web Routes with State Management and Global News
from flask import Blueprint, render_template, request, jsonify, session
from src.core.database import get_db_connection
from src.web.forms import ToggleSaveForm, ScanNewsForm, ResetDBForm
from src.services.parallel_processor import enhanced_scan_news
from src.services.ai_service_market_enhanced import analyze_article_with_market_data
from src.services.state_management import get_global_state_manager
import json
import logging

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

@main_bp.route('/')
def index():
    """Main page with original UI design"""
    try:
        # Get all news (with optional recommendation filtering)
        with get_db_connection() as conn:
            # Check if there are any active recommendation filters in state
            state_manager = get_global_state_manager()
            filters = state_manager.get_filter_state()
            
            if filters.get("recommendation"):
                # If recommendation filter is active, exclude articles without recommendations
                query = """
                    SELECT * FROM news 
                    WHERE ai_summary IS NOT NULL AND recommendation = ?
                    ORDER BY impact_score DESC, created_at DESC 
                    LIMIT 100
                """
                cursor = conn.execute(query, (filters["recommendation"],))
            else:
                # Normal query - include all analyzed articles
                query = """
                    SELECT * FROM news 
                    WHERE ai_summary IS NOT NULL 
                    ORDER BY impact_score DESC, created_at DESC 
                    LIMIT 100
                """
                cursor = conn.execute(query)
            news_list = [dict(row) for row in cursor.fetchall()]
        
        # Parse JSON fields for templates
        for news in news_list:
            if news.get('instruments'):
                try:
                    if isinstance(news['instruments'], str):
                        news['instruments'] = json.loads(news['instruments'])
                    elif not isinstance(news['instruments'], list):
                        news['instruments'] = []
                except:
                    news['instruments'] = []
        
        return render_template('index.html', 
                          news_list=news_list, 
                          showing_saved=False)
        
    except Exception as e:
        logger.error(f"Error loading main page: {e}")
        return f"Error loading news: {e}"

@main_bp.route('/category/<category>')
def news_by_category(category):
    """News by category with state persistence"""
    try:
        # Validate category
        if category not in ['international', 'romania', 'global']:
            return jsonify({"error": "Invalid category"}), 400
        
        # Update user preference
        state_manager = get_global_state_manager()
        state_manager.update_category_preference(category)
        
        # Get news for category with enhanced filtering
        filters = state_manager.get_filter_state()
        
        # Build dynamic query
        query = '''
            SELECT * FROM news 
            WHERE ai_summary IS NOT NULL AND category = ?
        '''
        params = [category]
        
        # Add dynamic filters
        filter_conditions = []
        if filters.get('has_active_filters', False):
            if filters['impact_range']['min'] > 1:
                filter_conditions.append(' AND impact_score >= ?')
                params.append(filters['impact_range']['min'])
            
            if filters['impact_range']['max'] < 10:
                filter_conditions.append(' AND impact_score <= ?')
                params.append(filters['impact_range']['max'])
            
            if filters.get('recommendation'):
                filter_conditions.append(' AND recommendation = ?')
                params.append(filters['recommendation'])
        
        query += ''.join(filter_conditions)
        
        # Add sorting
        sort_type = state_manager.get_sort_preference()
        if sort_type == 'date':
            query += ' ORDER BY published_at DESC'
        elif sort_type == 'published_at':
            query += ' ORDER BY published_at DESC'
        else:  # default to impact
            query += ' ORDER BY impact_score DESC, published_at DESC'
        
        query += ' LIMIT 100'
        
        with get_db_connection() as conn:
            cursor = conn.execute(query, params)
            news_list = [dict(row) for row in cursor.fetchall()]
        
        # Parse JSON fields
        for news in news_list:
            if news.get('instruments'):
                try:
                    if isinstance(news['instruments'], str):
                        news['instruments'] = json.loads(news['instruments'])
                    elif not isinstance(news['instruments'], list):
                        news['instruments'] = []
                except:
                    news['instruments'] = []
        
        return render_template('enhanced_index.html', 
                         news_list=news_list, 
                         showing_saved=False, 
                         current_category=category)
        
    except Exception as e:
        logger.error(f"Error loading news for category {category}: {e}")
        return f"Error loading news: {e}"

@main_bp.route('/saved')
def saved_news():
    """Saved news page"""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM news 
                WHERE ai_summary IS NOT NULL AND is_saved = 1 
                ORDER BY impact_score DESC, created_at DESC 
                LIMIT 100
            ''')
            news_list = [dict(row) for row in cursor.fetchall()]
        
        # Parse JSON fields
        for news in news_list:
            if news.get('instruments'):
                try:
                    if isinstance(news['instruments'], str):
                        news['instruments'] = json.loads(news['instruments'])
                    elif not isinstance(news['instruments'], list):
                        news['instruments'] = []
                except:
                    news['instruments'] = []
        
        return render_template('index.html', 
                         news_list=news_list, 
                         showing_saved=True)
        
    except Exception as e:
        return f"Error loading saved news: {e}"

@main_bp.route('/scan-news', methods=['POST'])
def scan_news():
    """Enhanced scan with state preservation and category filtering"""
    from src.web.forms import ScanNewsForm
    form = ScanNewsForm()
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    
    if not form.validate_on_submit():
        return {"error": "Invalid CSRF token"}, 400
    
    try:
        # Get category from request
        category = request.form.get('category', 'all')
        
        # Get state manager
        state_manager = get_global_state_manager()
        
        # Preserve current state before scan
        preserved_state = state_manager.preserve_filters_during_scan()
        
        # Perform enhanced parallel scan with category filter
        updated_count, alerts_sent, html_articles = enhanced_scan_news(scan_limit=25, category=category)
        
        if not html_articles:
            # Return existing news when no new articles found
            with get_db_connection() as conn:
                if category == 'all':
                    cursor = conn.execute('''
                        SELECT * FROM news 
                        WHERE ai_summary IS NOT NULL 
                        ORDER BY impact_score DESC, created_at DESC 
                        LIMIT 50
                    ''')
                else:
                    cursor = conn.execute('''
                        SELECT * FROM news 
                        WHERE ai_summary IS NOT NULL AND category = ?
                        ORDER BY impact_score DESC, created_at DESC 
                        LIMIT 50
                    ''', (category,))
                existing_news = [dict(row) for row in cursor.fetchall()]
            
            # Generate HTML with existing news cards
            html_response = ""
            for news_item in existing_news:
                # Parse instruments for template
                if news_item.get('instruments'):
                    try:
                        if isinstance(news_item['instruments'], str):
                            news_item['instruments'] = json.loads(news_item['instruments'])
                        elif not isinstance(news_item['instruments'], list):
                            news_item['instruments'] = []
                    except:
                        news_item['instruments'] = []
                
                html_response += render_template('news_card.html', news=news_item)
            
            # Restore filters after scan completion
            state_manager.restore_filters_after_scan({'scan_completed': True})
            return html_response
        
        # Generate HTML with news cards
        html_response = ""
        for news_item in html_articles:
            # Prepare news with enhanced category data
            
            # Parse instruments for template
            if news_item.get('instruments'):
                try:
                    if isinstance(news_item['instruments'], str):
                        news_item['instruments'] = json.loads(news_item['instruments'])
                    elif not isinstance(news_item['instruments'], list):
                        news_item['instruments'] = []
                except:
                    news_item['instruments'] = []
            
            html_response += render_template('news_card.html', news=news_item)
        
        # Restore filters after scan completion
        state_manager.restore_filters_after_scan({'scan_completed': True})
        
        logger.info(f"Enhanced scan completed: {updated_count} articles updated, {alerts_sent} alerts sent")
        
        return html_response
        
    except Exception as e:
        logger.error(f"Enhanced scan error: {e}")
        return {"error": f"Enhanced scan error: {e}"}

@main_bp.route('/reset-db', methods=['POST'])
def reset_db():
    """Reset database with state management"""
    from src.web.forms import ResetDBForm
    form = ResetDBForm()
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    
    if not form.validate_on_submit():
        return {"error": "Invalid CSRF token"}, 400
    
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM news WHERE is_saved = 0")
            conn.commit()
        
        # Get remaining saved news with current category preference
        state_manager = get_global_state_manager()
        ui_state = state_manager.get_ui_state()
        
        with get_db_connection() as conn:
            query = '''
                SELECT * FROM news 
                WHERE ai_summary IS NOT NULL AND is_saved = 1
                AND category = ?
                ORDER BY impact_score DESC, created_at DESC 
                LIMIT 100
            '''
            cursor = conn.execute(query, (ui_state['current_category'],))
            all_news = [dict(row) for row in cursor.fetchall()]
        
        # Parse JSON fields
        for news in all_news:
            if news.get('instruments'):
                try:
                    if isinstance(news['instruments'], str):
                        news['instruments'] = json.loads(news['instruments'])
                    elif not isinstance(news['instruments'], list):
                        news['instruments'] = []
                except:
                    news['instruments'] = []
        
        html_response = ""
        # Categories preserved from database - no override needed
        
        if not all_news:
            return "<div class='p-4 text-gray-400 text-center'>Baza de date a fost curățată (elementele salvate au fost păstrate).</div>"
        
        logger.info(f"Database reset completed in category: {ui_state['current_category']}")
        
        return html_response
        
    except Exception as e:
        logger.error(f"Database reset error: {e}")
        return {"error": f"Database reset error: {e}"}

@main_bp.route('/toggle-save/<int:news_id>', methods=['POST'])
def toggle_save(news_id):
    """Toggle save with state management"""
    form = ToggleSaveForm()
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    
    if form.validate_on_submit():
        try:
            with get_db_connection() as conn:
                cursor = conn.execute("SELECT is_saved FROM news WHERE id = ?", (news_id,))
                current_status = cursor.fetchone()[0]
                new_status = 0 if current_status else 1
                
                conn.execute("UPDATE news SET is_saved = ? WHERE id = ?", (new_status, news_id))
                conn.commit()
            
            return render_template('save_button.html', 
                             is_saved=new_status, 
                             news_id=news_id, 
                             form=form)
            
        except Exception as e:
            logger.error(f"Database error in toggle_save: {e}")
            return {"error": f"Database error: {e}"}
    else:
        return {"error": "Invalid CSRF token"}, 400

# New API endpoints for state management
@main_bp.route('/api/state', methods=['POST'])
def api_save_state():
    """Save state via API for client-side state management"""
    try:
        state_data = request.get_json()
        if not state_data:
            return jsonify({"error": "No state data provided"}), 400
        
        state_manager = get_global_state_manager()
        success = state_manager.save_state(state_data)
        
        if success:
            return jsonify({
                "success": True,
                "message": "State saved successfully",
                "state": state_manager.get_ui_state()
            })
        else:
            return jsonify({"error": "Failed to save state"}), 500
            
    except Exception as e:
        logger.error(f"API state save error: {e}")
        return jsonify({"error": f"State save error: {e}"}), 500

@main_bp.route('/api/state', methods=['GET'])
def api_get_state():
    """Get current state via API"""
    try:
        state_manager = get_global_state_manager()
        return jsonify(state_manager.get_ui_state())
    except Exception as e:
        logger.error(f"API state get error: {e}")
        return jsonify({"error": f"State get error: {e}"}), 500

@main_bp.route('/api/filter-news', methods=['POST'])
def api_filter_news():
    """Enhanced filtering API endpoint with state management"""
    try:
        state_manager = get_global_state_manager()
        filter_data = request.get_json()
        
        if not filter_data:
            return jsonify({"error": "No filter data provided"}), 400
        
        category = filter_data.get('category', 'international')
        if category not in ['international', 'romania', 'global']:
            return jsonify({"error": "Invalid category"}), 400
        
        # Update state with filters
        filter_updates = {
            'filters': {
                **state_manager.state.get('filters', {}),
                'category': category,
                **filter_data.get('filters', {})
            }
        }
        
        success = state_manager.save_state(filter_updates)
        
        if not success:
            return jsonify({"error": "Failed to update filters"}), 500
        
        # Query with dynamic filtering
        query = f'''
            SELECT * FROM news 
            WHERE ai_summary IS NOT NULL AND category = ?
        '''
        params = [category]
        
        # Build filter conditions
        filters = filter_data.get('filters', {})
        
        # Impact score filter
        if filters.get('impact_min', 1) > 1 or filters.get('impact_max', 10) < 10:
            query += f" AND impact_score BETWEEN {filters.get('impact_min', 1)} AND {filters.get('impact_max', 10)}"
        
        # Recommendation filter
        if filters.get('recommendation'):
            valid_recs = ['Buy', 'Sell', 'Hold', 'Strong buy', 'Strong sell']
            if filters['recommendation'] in valid_recs:
                query += f" AND recommendation = '{filters['recommendation']}'"
        
        # Add sorting
        sort_type = filter_data.get('sort', 'impact')
        if sort_type == 'date':
            query += ' ORDER BY published_at DESC'
        elif sort_type == 'published_at':
            query += ' ORDER BY published_at DESC'
        else:  # default to impact
            query += ' ORDER BY impact_score DESC, published_at DESC'
        
        query += ' LIMIT 100'
        
        with get_db_connection() as conn:
            cursor = conn.execute(query, params)
            news_list = [dict(row) for row in cursor.fetchall()]
        
        # Parse JSON fields for template
        for news in news_list:
            if news.get('instruments'):
                try:
                    if isinstance(news['instruments'], str):
                        news['instruments'] = json.loads(news['instruments'])
                    elif not isinstance(news['instruments'], list):
                        news['instruments'] = []
                except:
                    news['instruments'] = []
        
        # Generate HTML with enhanced template
        html_response = ""
        for news_item in news_list:
            # Prepare news with enhanced category data
            news_item['category'] = category
            html_response += render_template('news_card_enhanced.html', news=news_item)
        
        return jsonify({
            "html": html_response,
            "count": len(news_list),
            "category": category,
            "filters": state_manager.get_filter_state(),
            "sort": state_manager.get_sort_preference(),
            "state": state_manager.get_ui_state()
        })
        
    except Exception as e:
        logger.error(f"Filter API error: {e}")
        return jsonify({"error": f"Filter error: {e}"}), 500

@main_bp.route('/api/performance-stats')
def api_performance_stats():
    """Get performance statistics"""
    try:
        from src.services.parallel_processor import get_global_processor
        processor = get_global_processor()
        stats = processor.get_performance_stats()
        
        # Add database stats
        with get_db_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                        COUNT(*) as total_news,
                        COUNT(CASE WHEN ai_summary IS NOT NULL THEN 1 END) as analyzed_news,
                        COUNT(CASE WHEN ai_summary IS NULL THEN 1 END) as pending_news,
                        AVG(CASE WHEN ai_summary IS NOT NULL THEN impact_score END) as avg_impact
                    FROM news
            ''')
            
            db_stats = dict(cursor.fetchone())
            
            # Add filtering stats
            state_manager = get_global_state_manager()
            filter_stats = state_manager.get_filter_state()
            
            stats.update({
                'database_stats': db_stats,
                'filter_stats': filter_stats,
                'active_category': state_manager.state.get('current_category'),
                'active_sort': state_manager.state.get('current_sort'),
                'ui_state': state_manager.get_ui_state()
            })
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Performance stats error: {e}")
        return jsonify({"error": f"Performance stats error: {e}"}, 500)

def register_routes(app, csrf, limiter, security_logger):
    """Register all routes with the Flask app"""
    
    # Register blueprint
    app.register_blueprint(main_bp)
    
    logger.info("✅ Enhanced routes with state management registered successfully")