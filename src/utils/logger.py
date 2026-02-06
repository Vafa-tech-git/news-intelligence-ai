# Enhanced Structured Logging System
import logging
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Dict, Any, Optional
import traceback

# Import security logger for cross-logging
try:
    from src.core.extensions import security_logger
except ImportError:
    security_logger = None

class StructuredLogger:
    """Enhanced structured logger with JSON output and multiple handlers"""
    
    def __init__(self, name: str, level: str = "INFO", log_dir: str = "logs"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # Clear existing handlers to prevent duplicates
        self.logger.handlers.clear()
        
        # Create log directory
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Setup formatters
        self.json_formatter = JsonFormatter()
        self.text_formatter = logging.Formatter(
            '%(asctime)s %(name)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        )
        
        # Setup handlers
        self._setup_handlers()
        
        # Prevent propagation to root logger to avoid duplicate logs
        self.logger.propagate = False
    
    def _setup_handlers(self):
        """Setup multiple handlers for different log types"""
        
        # Console handler with text format
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(self.text_formatter)
        console_handler.setLevel(logging.INFO)
        self.logger.addHandler(console_handler)
        
        # Main application log file (JSON format)
        app_handler = RotatingFileHandler(
            self.log_dir / 'app.json',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        app_handler.setFormatter(self.json_formatter)
        app_handler.setLevel(logging.DEBUG)
        self.logger.addHandler(app_handler)
        
        # Error-only log file (text format for easy reading)
        error_handler = RotatingFileHandler(
            self.log_dir / 'errors.log',
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )
        error_handler.setFormatter(self.text_formatter)
        error_handler.setLevel(logging.ERROR)
        self.logger.addHandler(error_handler)
        
        # Security-specific log (JSON format)
        security_handler = RotatingFileHandler(
            self.log_dir / 'security.json',
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )
        security_handler.setFormatter(self.json_formatter)
        security_handler.addFilter(SecurityFilter())
        security_handler.setLevel(logging.INFO)
        self.logger.addHandler(security_handler)
        
        # Performance log (JSON format)
        perf_handler = TimedRotatingFileHandler(
            self.log_dir / 'performance.json',
            when='midnight',
            interval=1,
            backupCount=7
        )
        perf_handler.setFormatter(self.json_formatter)
        perf_handler.addFilter(PerformanceFilter())
        perf_handler.setLevel(logging.DEBUG)
        self.logger.addHandler(perf_handler)
    
    def log_structured(self, level: str, message: str, **kwargs):
        """Log structured data with additional context"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'message': message,
            'level': level.upper(),
            'logger': self.logger.name,
            **kwargs
        }
        
        # Add extra data for the formatter
        extra_data = {'extra_data': log_data}
        
        getattr(self.logger, level.lower())(message, extra=extra_data)
    
    def debug(self, message: str, **kwargs):
        """Debug level logging with structured data"""
        self.log_structured('debug', message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Info level logging with structured data"""
        self.log_structured('info', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Warning level logging with structured data"""
        self.log_structured('warning', message, **kwargs)
    
    def error(self, message: str, exception: Exception = None, **kwargs):
        """Error level logging with exception details"""
        if exception:
            kwargs['exception_type'] = type(exception).__name__
            kwargs['exception_message'] = str(exception)
            kwargs['traceback'] = traceback.format_exc()
        
        self.log_structured('error', message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Critical level logging with structured data"""
        self.log_structured('critical', message, **kwargs)
    
    def security_event(self, event_type: str, details: Dict[str, Any], severity: str = "INFO"):
        """Log security-specific events"""
        self.log_structured(
            'info' if severity == 'INFO' else 'warning' if severity == 'WARNING' else 'critical',
            f"Security event: {event_type}",
            event_type=event_type,
            security=True,
            severity=severity,
            **details
        )
    
    def performance_metric(self, metric_name: str, value: float, unit: str = "ms", **kwargs):
        """Log performance metrics"""
        self.log_structured(
            'debug',
            f"Performance metric: {metric_name}",
            performance=True,
            metric_name=metric_name,
            metric_value=value,
            metric_unit=unit,
            **kwargs
        )
    
    def api_call(self, method: str, endpoint: str, status_code: int, response_time: float, **kwargs):
        """Log API calls"""
        self.log_structured(
            'info',
            f"API call: {method} {endpoint}",
            api_call=True,
            http_method=method,
            endpoint=endpoint,
            status_code=status_code,
            response_time_ms=response_time * 1000,
            **kwargs
        )
    
    def database_query(self, query_type: str, table: str, execution_time: float, row_count: int = 0, **kwargs):
        """Log database queries"""
        self.log_structured(
            'debug',
            f"Database query: {query_type} on {table}",
            database=True,
            query_type=query_type,
            table=table,
            execution_time_ms=execution_time * 1000,
            row_count=row_count,
            **kwargs
        )

class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra data if available
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
        
        return json.dumps(log_data, default=str)

class SecurityFilter(logging.Filter):
    """Filter for security-related logs"""
    
    def filter(self, record):
        # Check if this is a security log
        if hasattr(record, 'extra_data'):
            return record.extra_data.get('security', False) or 'security' in record.getMessage().lower()
        
        return 'security' in record.getMessage().lower()

class PerformanceFilter(logging.Filter):
    """Filter for performance-related logs"""
    
    def filter(self, record):
        # Check if this is a performance log
        if hasattr(record, 'extra_data'):
            return record.extra_data.get('performance', False) or 'performance' in record.getMessage().lower()
        
        return 'performance' in record.getMessage().lower()

# Performance monitoring decorator
def log_performance(logger: StructuredLogger, operation_name: str = None):
    """Decorator to log function performance"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = datetime.utcnow()
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            try:
                result = func(*args, **kwargs)
                end_time = datetime.utcnow()
                duration_ms = (end_time - start_time).total_seconds() * 1000
                
                logger.performance_metric(
                    metric_name=op_name,
                    value=duration_ms,
                    unit='ms',
                    success=True,
                    args_count=len(args),
                    kwargs_count=len(kwargs)
                )
                
                return result
                
            except Exception as e:
                end_time = datetime.utcnow()
                duration_ms = (end_time - start_time).total_seconds() * 1000
                
                logger.performance_metric(
                    metric_name=op_name,
                    value=duration_ms,
                    unit='ms',
                    success=False,
                    error=str(e)
                )
                
                logger.error(
                    f"Operation failed: {op_name}",
                    exception=e,
                    duration_ms=duration_ms
                )
                
                raise
                
        return wrapper
    return decorator

# Context manager for logging operations
class LogOperation:
    """Context manager for logging operations with timing"""
    
    def __init__(self, logger: StructuredLogger, operation_name: str, **kwargs):
        self.logger = logger
        self.operation_name = operation_name
        self.kwargs = kwargs
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.utcnow()
        self.logger.info(f"Starting operation: {self.operation_name}", **self.kwargs)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = datetime.utcnow()
        duration_ms = (end_time - self.start_time).total_seconds() * 1000
        
        if exc_type:
            self.logger.error(
                f"Operation failed: {self.operation_name}",
                exception=exc_val,
                duration_ms=duration_ms,
                **self.kwargs
            )
        else:
            self.logger.info(
                f"Operation completed: {self.operation_name}",
                duration_ms=duration_ms,
                **self.kwargs
            )

# Global logger instances
_app_logger = None
_security_logger = None
_performance_logger = None

def get_logger(name: str = None, level: str = "INFO") -> StructuredLogger:
    """Get or create a structured logger instance"""
    global _app_logger
    
    if _app_logger is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO')
        _app_logger = StructuredLogger('news_ai_app', log_level)
    
    return _app_logger

def get_security_logger() -> StructuredLogger:
    """Get or create a security-specific logger"""
    global _security_logger
    
    if _security_logger is None:
        _security_logger = StructuredLogger('news_ai_security', 'INFO')
    
    return _security_logger

def get_performance_logger() -> StructuredLogger:
    """Get or create a performance-specific logger"""
    global _performance_logger
    
    if _performance_logger is None:
        _performance_logger = StructuredLogger('news_ai_performance', 'DEBUG')
    
    return _performance_logger

# Setup logging on import
def setup_logging(app):
    """Setup logging configuration from Flask app"""
    log_level = app.config.get('LOG_LEVEL', 'INFO')
    log_dir = app.config.get('LOG_DIR', 'logs')
    
    # Create main logger
    logger = get_logger('news_ai_app', log_level)
    
    # Log application startup
    logger.info(
        "Application starting",
        debug_mode=app.debug,
        log_level=log_level,
        log_dir=log_dir
    )
    
    return logger

# Utility functions
def log_request(logger: StructuredLogger, request, response_time: float):
    """Log HTTP request details"""
    logger.api_call(
        method=request.method,
        endpoint=request.endpoint or request.path,
        status_code=getattr(request, 'status_code', 200),
        response_time=response_time,
        user_agent=request.headers.get('User-Agent', 'Unknown'),
        ip_address=request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    )

def log_database_operation(logger: StructuredLogger, operation: str, table: str, duration: float, **kwargs):
    """Log database operation details"""
    logger.database_query(
        query_type=operation,
        table=table,
        execution_time=duration,
        **kwargs
    )