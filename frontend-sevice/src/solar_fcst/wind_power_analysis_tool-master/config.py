"""
Configuration file for Wind Speed Analysis Tool
"""
import os


class Config:
    """Base configuration"""
    # Data directory
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
    
    # Session configuration
    SESSION_TIMEOUT = 3600  # 1 hour in seconds
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Upload and processing limits
    MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB
    
    # Allowed time resolutions
    ALLOWED_RESOLUTIONS = ["15T", "30T", "1H", "3H", "1h", "3h"]  # Support both H and h
    
    # Default settings
    DEFAULT_RESOLUTION = "1H"
    DEFAULT_DATE_RANGE_DAYS = 15
    
    # Flask configuration
    JSON_AS_ASCII = False  # Support Chinese characters in JSON responses


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    DATA_DIR = os.path.join(os.path.dirname(__file__), "test_data")


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
