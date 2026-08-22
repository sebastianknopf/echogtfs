"""Backend unittest package for discovery from the backend root."""

import os
import tempfile
import warnings

warnings.filterwarnings(
    "ignore",
    message=".*HMAC key is .* below the minimum recommended length.*",
)

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")
for _env_key in (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "DEBUG_PORT",
    "FRONTEND_PORT",
):
    os.environ.pop(_env_key, None)

os.chdir(tempfile.mkdtemp(prefix="echogtfs-tests-"))