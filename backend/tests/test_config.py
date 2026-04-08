"""
Test configuration setup.

This module sets up the required environment variables for testing
before any other modules are imported. It should be imported first
in all test files.
"""

import os
import sys
import logging
from pathlib import Path

# Set required environment variables for testing if not already set
def setup_test_environment():
    """Set up minimal environment variables required for tests."""
    test_env = {
        "SECRET_KEY": "test-secret-key-min-32-bytes-long",  # Must be >= 32 bytes for SHA256
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
        "DEBUG": "true",
        "DOCS_ENABLED": "true",
    }
    
    for key, value in test_env.items():
        if key not in os.environ:
            os.environ[key] = value


def configure_test_logging():
    """Configure logging to suppress error logs during tests."""
    # Suppress uvicorn logger (used by adapters) during tests
    # This prevents expected error messages from cluttering test output
    logging.getLogger("uvicorn").setLevel(logging.CRITICAL)
    
    # Suppress httpx logger
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Setup environment before importing echogtfs
setup_test_environment()

# Configure logging for tests
configure_test_logging()

# Add src to path for imports outside docker
backend_dir = Path(__file__).parent.parent
src_dir = backend_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
