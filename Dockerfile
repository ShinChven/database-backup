FROM python:3.12-alpine

# Install database clients and gzip
RUN apk add --no-cache \
    postgresql-client \
    mysql-client \
    gzip \
    && rm -rf /var/cache/apk/*

# Create non-root user
RUN addgroup -S backup && adduser -S backup -G backup

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Config is mounted at runtime
VOLUME ["/app/config.yaml"]

USER backup

CMD ["python", "-m", "src.main"]
