import logging
import os
import sys

try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # python-json-logger < 3.x
    from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore[no-redef]

_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    _configured = True


_configure()


def get_logger(name: str) -> logging.Logger:
    """Return a named logger backed by the configured JSON handler."""
    return logging.getLogger(name)
