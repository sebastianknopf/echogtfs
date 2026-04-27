FROM python:3.12-slim

WORKDIR /app

# Install git for setuptools_scm version detection and protobuf compiler
RUN apt-get update && \
    apt-get install -y --no-install-recommends git protobuf-compiler && \
    rm -rf /var/lib/apt/lists/*

# Copy Git metadata for setuptools_scm version detection
# Copy everything else for the backend container
COPY ./.git ./.git
COPY ./.gitignore ./.gitignore
COPY ./backend ./backend
COPY ./gtfs-realtime.proto ./gtfs-realtime.proto


# Install from backend directory BEFORE generating protobuf
# This ensures setuptools_scm reads clean git state without generated files
RUN pip install --no-cache-dir ./backend

# Generate Python code from protobuf definition AFTER installation
# This prevents the generated file from interfering with setuptools_scm version detection
RUN protoc --python_out=/usr/local/lib/python3.12/site-packages/echogtfs/ gtfs-realtime.proto && \
   rm -rf .git

CMD ["echogtfs"]