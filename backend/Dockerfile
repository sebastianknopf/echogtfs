FROM python:3.12-slim

WORKDIR /app

# Install git for setuptools_scm version detection and protobuf compiler
RUN apt-get update && \
    apt-get install -y --no-install-recommends git protobuf-compiler && \
    rm -rf /var/lib/apt/lists/* && \
    git config --global core.autocrlf true

# Copy everything else for the backend container
# Copy Git metadata for setuptools_scm version detection
# Remove the .env file for the container to start, and other untracked files
# IMPORTANT: Remove ONLY untracked files, everything else will lead to an estimated version
# during installation in the Docker container!
COPY . .
RUN rm ./.env && rm -rf ./venv

# Install backend in editable mode so Python imports local source under /app/backend/src
# while still installing dependencies and the echogtfs console script.
RUN pip install --no-cache-dir -e ./backend

# Generate Python code from protobuf definition into the local source tree.
# Keeping generated code under /app/backend/src avoids debugger path mismatches.
RUN protoc --python_out=/app/backend/src/echogtfs/ gtfs-realtime.proto