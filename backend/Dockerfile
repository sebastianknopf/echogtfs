FROM python:3.12-slim

WORKDIR /app

# Install git for setuptools_scm
RUN apt-get update && \
    apt-get install -y --no-install-recommends git protobuf-compiler && \
    rm -rf /var/lib/apt/lists/*

# Copy Git metadata for setuptools_scm version detection
COPY .git ./.git
COPY backend/pyproject.toml ./backend/pyproject.toml
# Kopiere .gitignore damit Git den richtigen State kennt
COPY .gitignore ./.gitignore

# setuptools_scm extrahiert die Dateien aus Git während pip install
RUN pip install --no-cache-dir ./backend

# Protobuf nach der Installation
COPY gtfs-realtime.proto ./
RUN protoc --python_out=/usr/local/lib/python3.12/site-packages/echogtfs/ gtfs-realtime.proto && \
    rm -rf .git

CMD ["echogtfs"]