#!/usr/bin/env python3
# Development Entry Point
import os
import sys

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.app import create_app

if __name__ == '__main__':
    # Development configuration
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Create and run app
    app = create_app('development')
    
    if debug_mode:
        app.logger.warning("⚠️ DEBUG MODE ACTIV - Folosiți doar pentru dezvoltare!")
    else:
        app.logger.info("🛡️ PRODUCTION MODE - Securitate activată")
    
    app.run(debug=debug_mode, port=5002, host='0.0.0.0')