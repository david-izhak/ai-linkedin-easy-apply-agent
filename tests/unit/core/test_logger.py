import pytest
import logging
import re
from core.logger import setup_logging
import time

@pytest.fixture(autouse=True)
def configured_logger():
    """
    A pytest fixture that ensures the logging is set up before each test.
    The autouse=True flag makes it automatically used for all tests in the module.
    """
    setup_logging()

# Get a logger instance for the test module
logger = logging.getLogger(__name__)

def test_logging_setup_produces_correct_log_record(caplog):
    """
    Tests if the logger setup produces a LogRecord with the correct attributes.
    """
    # Arrange is now handled by the configured_logger fixture
    
    # Act: Log a message
    with caplog.at_level(logging.INFO):
        test_message = "This is a test message for log record attributes."
        # Store the time just before logging
        pre_log_time = time.time()
        logger.info(test_message)

    # Assert: Check the attributes of the captured LogRecord object
    assert len(caplog.records) == 1, f"Should have captured exactly one log record, but captured {len(caplog.records)}."
    
    record = caplog.records[0]

    # 1. Check the log level
    assert record.levelname == "INFO", f"Log level should be 'INFO', but was '{record.levelname}'."

    # 2. Check the logger name
    assert record.name == __name__, f"Logger name should be '{__name__}', but was '{record.name}'."

    # 3. Check for the actual message content
    assert record.getMessage() == test_message, f"Log message should be '{test_message}', but was '{record.getMessage()}'."

    # 4. Check the timestamp (created time) of the record
    # The record.created attribute is a Unix timestamp.
    assert record.created >= pre_log_time, "The log record's timestamp should be after the pre-log time."
    assert record.created <= time.time(), "The log record's timestamp should be before the current time."
