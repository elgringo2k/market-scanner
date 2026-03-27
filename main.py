"""Entry point for the oddschecker-scraper service."""
import os
import sys

from dotenv import load_dotenv

# Load .env before any other imports that read env vars
load_dotenv()

from src.logger import get_logger  # noqa: E402 — must come after load_dotenv
from src.scheduler import start    # noqa: E402

logger = get_logger(__name__)

_REQUIRED_ENV_VARS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")


def _validate_env() -> None:
    missing = [var for var in _REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in a .env file or in the process environment."
        )


if __name__ == "__main__":
    try:
        _validate_env()
    except EnvironmentError as exc:
        logger.error("Startup validation failed", extra={"error": str(exc)})
        sys.exit(1)

    logger.info("oddschecker-scraper starting")
    start()
