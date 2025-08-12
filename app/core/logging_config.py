import logging
import sys
from logging.handlers import RotatingFileHandler
from app.core.config import settings


def setup_logging():
    # Configure logging format
    log_format = logging.Formatter(settings.LOG_FORMAT)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        settings.LOG_DIR / settings.LOG_FILENAME,
        maxBytes=settings.LOG_ROTATION_SIZE,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(log_format)
    root_logger.addHandler(file_handler)

    # Set level for specific loggers
    logging.getLogger("uvicorn").setLevel(settings.LOG_LEVEL)
    logging.getLogger("fastapi").setLevel(settings.LOG_LEVEL)
