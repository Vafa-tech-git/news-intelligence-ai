# Enhanced Flask Application Factory with Structured Logging
from flask import Flask, render_template, request, jsonify, g
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Import core modules
from src.core.config import *
from src.core.extensions import init_extensions
from src.core.database import init_database, get_db_connection

# Import enhanced logging
from src.utils.logger import setup_logging, get_logger, log_request

# Import services
from src.services.ai_service_market_enhanced import analyze_article_with_market_data as analyze_article
from src.services.news_service import fetch_finnhub_news, fetch_rss_feeds
from src.services.scraper_service import get_article_content

# Import web components
from src.web.forms import ToggleSaveForm, ScanNewsForm, ResetDBForm
from src.web.routes import register_routes

# Import tasks
from src.tasks.celery_tasks import process_news_article

def create_app(config_name='development'):
    """Application factory"""
    # Set correct template folder path
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src', 'web', 'templates')
    app = Flask(__name__, template_folder=template_dir)
    
    # Configuration
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['WTF_CSRF_TIME_LIMIT'] = WTF_CSRF_TIME_LIMIT
    app.config['WTF_CSRF_ENABLED'] = WTF_CSRF_ENABLED
    app.config['WTF_CSRF_SSL_STRICT'] = CSRF_COOKIE_SECURE
    app.config['SESSION_COOKIE_SECURE'] = SESSION_COOKIE_SECURE
    app.config['SESSION_COOKIE_HTTPONLY'] = SESSION_COOKIE_HTTPONLY
    app.config['SESSION_COOKIE_SAMESITE'] = SESSION_COOKIE_SAMESITE
    
    # Initialize extensions
    csrf, limiter, talisman, security_logger = init_extensions(app)
    
    # Setup enhanced structured logging
    app_logger = setup_logging(app)
    
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
        os.chmod('logs', 0o700)
    
    # Add request logging middleware
    @app.before_request
    def log_request_info():
        g.start_time = datetime.utcnow()
    
    @app.after_request
    def log_response_info(response):
        if hasattr(g, 'start_time'):
            response_time = (datetime.utcnow() - g.start_time).total_seconds()
            log_request(app_logger, request, response_time)
        return response
    
    # Initialize database
    init_database()
    
    # Register routes
    register_routes(app, csrf, limiter, security_logger)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        if request.headers.get('HX-Request'):
            return jsonify({"error": "Pagina nu a fost găsită"}), 404
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Server Error: {type(error).__name__}")
        if request.headers.get('HX-Request'):
            return jsonify({"error": "A apărut o eroare internă. Vă rugăm încercați din nou."}), 500
        return render_template('500.html'), 500
    
    @app.errorhandler(429)
    def ratelimit_handler(e):
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        security_logger.warning(f"Rate limit exceeded! IP: {client_ip} - Path: {request.path}")
        
        if request.headers.get('HX-Request'):
            return jsonify({
                "error": "Prea multe cereri! Te rog așteaptă puțin înainte să încerci din nou.",
                "retry_after": str(e.retry_after) if hasattr(e, 'retry_after') else "60"
            }), 429
        return render_template('rate_limit_error.html'), 429
    
    app.logger.info('News AI Application startup with modular architecture')
    
    return app