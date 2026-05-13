# file: utils/logger.py

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with consistent formatting."""
    logger = logging.getLogger(f"tunnelforge.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        # Windows consoles default to cp1252/cp850 which cannot encode all
        # Unicode characters (emoji, em-dash, ...).  Reconfigure to UTF-8 so
        # log lines never raise UnicodeEncodeError.
        if hasattr(handler.stream, "reconfigure"):
            try:
                handler.stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
