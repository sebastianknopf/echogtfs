FROM python:3.12-slim

WORKDIR /app

# Install git for setuptools_scm version detection
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copy Git metadata for setuptools_scm version detection
COPY .git ./.git

# Copy backend package files
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/src/ ./backend/src/

# Install from backend directory (setuptools_scm reads git history)
RUN pip install --no-cache-dir ./backend && \
    rm -rf .git

CMD ["echogtfs"]
