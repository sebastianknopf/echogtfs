FROM python:3.12-slim

WORKDIR /app

# Copy project metadata first so pip can resolve dependencies,
# then copy source so the package is installable.
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

CMD ["echogtfs"]
