FROM python:3.12-slim

WORKDIR /app

# Install git for setuptools_scm version detection and protobuf compiler
RUN apt-get update && \
    apt-get install -y --no-install-recommends git protobuf-compiler && \
    rm -rf /var/lib/apt/lists/*

# Copy Git metadata for setuptools_scm version detection
COPY .git ./.git

# Copy backend package files
COPY backend/ ./backend/

# Copy protobuf definition and generate Python code
COPY gtfs-realtime.proto ./
RUN protoc --python_out=./backend/src/echogtfs/ gtfs-realtime.proto

# Install from backend directory (setuptools_scm reads git history)
RUN pip install --no-cache-dir ./backend&& \
    rm -rf .git 

CMD ["echogtfs"]
