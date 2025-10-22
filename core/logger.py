import logging
import sys
import structlog
from config import config
import os
from datetime import datetime

# Flag to ensure configuration happens only once
_is_configured = False

def setup_logging():
    """
    Set up logging configuration for the application using structlog.
    This function is idempotent and will only configure the logging system once.
    """
    global _is_configured
    if _is_configured:
        return

    # 1. Get the root logger
    root_logger = logging.getLogger()
    
    # 2. Determine the logging level and clear any existing handlers
    log_level = config.logging.log_level.upper()
    numeric_level = getattr(logging, log_level, logging.INFO)
    root_logger.setLevel(numeric_level)
    
    # Clear any handlers that may have been set by other libraries or pytest
    if root_logger.hasHandlers():
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # 3. Create a shared formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

    # 3. Create handlers
    handlers = []
    
    # Console Handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)
    
    # File Handler (if configured)
    if config.logging.log_file_path:
        log_path = config.logging.log_file_path
        log_dir = log_path.parent
        log_stem = log_path.stem
        log_suffix = log_path.suffix
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_log_file = log_dir / f"{log_stem}_{timestamp}{log_suffix}"
        
        file_handler = logging.FileHandler(new_log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # 4. Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Set up the root logger
    logging.basicConfig(level=log_level, handlers=handlers, force=True)

    # 6. Configure structlog to process log records and pass them to standard logging
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso", utc=False, key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.render_to_log_kwargs,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    _is_configured = True


def get_structured_logger(name: str) -> structlog.BoundLogger:
    """
    Get a structured logger with the given name.
    
    Args:
        name: The name of the logger (usually __name__ of the module)
        
    Returns:
        A structured logger instance with context binding capabilities
    
    Example:
        >>> logger = get_structured_logger(__name__)
        >>> logger.info("user_login", user_id="123", ip_address="192.168.1.1")
    """
    return structlog.get_logger(name)


def bind_context(logger: structlog.BoundLogger, **context) -> structlog.BoundLogger:
    """
    Bind context data to a logger for all subsequent log entries.
    
    Args:
        logger: The structured logger to bind context to
        **context: Keyword arguments to bind as context
        
    Returns:
        A new logger with the bound context
    
    Example:
        >>> logger = get_structured_logger(__name__)
        >>> job_logger = bind_context(logger, job_id="12345", company="Example Inc")
        >>> job_logger.info("application_started")  # Will include job_id and company
    """
    return logger.bind(**context)
