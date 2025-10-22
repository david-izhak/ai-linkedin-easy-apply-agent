import logging
import sys
from config import LOG_LEVEL


def setup_logging():
    """
    Configures the root logger for the application.
    """
    # Get the numeric value for the log level from the string in config
    numeric_level = getattr(logging, LOG_LEVEL.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {LOG_LEVEL}")

    # Create a handler to stream logs to standard output (the console)
    handler = logging.StreamHandler(sys.stdout)

    # Create a formatter to define the log message format
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Set the formatter for the handler
    handler.setFormatter(formatter)

    # Get the root logger and configure it
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Avoid adding handlers multiple times
    if not root_logger.handlers:
        root_logger.addHandler(handler)
