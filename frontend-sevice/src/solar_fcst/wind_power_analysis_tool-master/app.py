"""
Main application entry point for Wind Speed Analysis Tool
"""
from flask import Flask, jsonify, render_template
from config import config
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')


def setup_logging(app, config_name='default'):
    """
    Setup application logging
    
    Args:
        app: Flask application instance
        config_name: Configuration name
    """
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Setup file handler with rotation
    file_handler = RotatingFileHandler(
        'logs/wind_analysis.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10
    )
    
    # Set log format
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    file_handler.setFormatter(formatter)
    
    # Set log level based on config
    if app.config['DEBUG']:
        file_handler.setLevel(logging.DEBUG)
        app.logger.setLevel(logging.DEBUG)
    else:
        file_handler.setLevel(logging.INFO)
        app.logger.setLevel(logging.INFO)
    
    # Add handler to app logger
    app.logger.addHandler(file_handler)
    
    # Also log to console in development
    if app.config['DEBUG']:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)
        app.logger.addHandler(console_handler)
    
    app.logger.info('='*60)
    app.logger.info('Wind Speed Analysis Tool Started')
    app.logger.info(f'Environment: {config_name}')
    app.logger.info(f'Debug Mode: {app.config["DEBUG"]}')
    app.logger.info('='*60)


def create_app(config_name='default'):
    """
    Application factory function
    
    Args:
        config_name: Configuration name ('development', 'production', 'testing')
    
    Returns:
        Flask application instance
    """
    app = Flask(__name__, 
                template_folder='frontend/templates',
                static_folder='frontend/static')
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Setup logging
    setup_logging(app, config_name)
    
    # Register blueprints
    from backend.routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Root route
    @app.route('/')
    def index():
        """Serve the main application page"""
        app.logger.info('Main page accessed')
        return render_template('index.html')
    
    # Health check endpoint
    @app.route('/health')
    def health():
        """Health check endpoint"""
        return jsonify({
            'status': 'healthy',
            'data_dir': app.config['DATA_DIR'],
            'data_dir_exists': os.path.exists(app.config['DATA_DIR'])
        })
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors"""
        return jsonify({'error': 'Resource not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        return jsonify({'error': 'Internal server error'}), 500
    
    return app


if __name__ == '__main__':
    # Get configuration from environment variable or use default
    env = os.environ.get('FLASK_ENV', 'development')
    app = create_app(env)
    
    # Run the application
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=app.config['DEBUG'])
