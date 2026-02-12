"""
Simple JSON logging for all services.
Logs to files in /var/log/bm/
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'service': record.name,
            'message': record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add any extra fields
        if hasattr(record, 'device_id'):
            log_data['device_id'] = record.device_id
        if hasattr(record, 'event'):
            log_data['event'] = record.event
        if hasattr(record, 'data'):
            log_data['data'] = record.data

        return json.dumps(log_data)


def setup_logger(name, log_file=None, level=logging.INFO):
    """
    Setup a logger with JSON formatting.

    Args:
        name: Logger name (typically service name)
        log_file: Optional log file path. If None, logs to stdout
        level: Logging level

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove any existing handlers
    logger.handlers = []

    # Create formatter
    formatter = JSONFormatter()

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        # Ensure directory exists
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def log_event(logger, event_name, device_id=None, data=None, level=logging.INFO):
    """
    Log an event with structured data.

    Args:
        logger: Logger instance
        event_name: Name of the event
        device_id: Optional device ID
        data: Optional event data dictionary
        level: Log level
    """
    extra = {'event': event_name}
    if device_id:
        extra['device_id'] = device_id
    if data:
        extra['data'] = data

    logger.log(level, event_name, extra=extra)


def log_error(logger, error, context=None):
    """
    Log an error with context.

    Args:
        logger: Logger instance
        error: Exception or error message
        context: Optional context dictionary
    """
    message = str(error)
    extra = {}

    if context:
        extra['data'] = context

    if isinstance(error, Exception):
        logger.error(message, exc_info=True, extra=extra)
    else:
        logger.error(message, extra=extra)
