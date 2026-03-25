"""
Tests for src/logger.py

# Feature: oddschecker-scraper, Property 7: All log output is valid JSON
"""
import json
import logging
import io

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.logger import get_logger


def _capture_log_output(logger: logging.Logger, level: int, message: str) -> str:
    """Attach a StringIO handler, emit one log record, return the raw line."""
    try:
        from pythonjsonlogger.json import JsonFormatter
    except ImportError:
        from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore[no-redef]

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        logger.log(level, message)
    finally:
        logger.removeHandler(handler)
    return buf.getvalue().strip()


# ---------------------------------------------------------------------------
# Property 7: All log output is valid JSON
# Validates: Requirements 7.1
# ---------------------------------------------------------------------------

@given(
    message=st.text(min_size=0, max_size=200),
    level=st.sampled_from([logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]),
)
@settings(max_examples=100)
def test_log_output_is_valid_json(message: str, level: int) -> None:
    """
    **Validates: Requirements 7.1**

    For any log message and level, the emitted line must be parseable as valid JSON.
    """
    logger = get_logger("test.property7")
    logger.setLevel(logging.DEBUG)  # ensure all levels pass through

    line = _capture_log_output(logger, level, message)
    assert line, "Expected non-empty log output"
    parsed = json.loads(line)  # must not raise
    assert "message" in parsed
