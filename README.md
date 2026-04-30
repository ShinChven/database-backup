# Database Backup

A headless Docker container that backs up **PostgreSQL** and **MySQL** databases on configurable cron schedules, uploads compressed dumps to **S3-compatible storage**, and enforces per-schema retention.

---

## Features

- ✅ PostgreSQL and MySQL support
- ✅ YAML-based configuration with environment variable substitution
- ✅ Per-instance and per-schema cron schedules and retention (`keep`) settings
- ✅ Backup verification before upload (integrity check)
- ✅ gzip compression
- ✅ Automatic retention enforcement — old files deleted after each successful backup
- ✅ Error isolation — one failing job never stops others
- ✅ Structured JSON logs for easy ingestion by Datadog, CloudWatch, Loki, etc.
- ✅ Runs as a non-root user inside an Alpine-based Docker image

---

## Quick Start

### 1. Create your config

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

Edit `config.yaml` with your database hosts and schemas. Edit `.env` with your AWS credentials and database passwords.

### 2. Run with Docker Compose

```bash
docker compose up -d
```

Logs stream to stdout:

```bash
docker compose logs -f backup
```

---

## Configuration

### `config.yaml`

```yaml
s3:
  bucket: my-backup-bucket
  prefix: db-backups          # Optional. Omit to write to bucket root.
  region: ap-southeast-1
  # endpoint_url: https://your-minio.example.com  # For MinIO / Cloudflare R2

defaults:
  keep: 7                     # Retain 7 backups per schema globally

instances:
  - name: prod-postgres
    type: postgresql           # "postgresql" or "mysql"
    host: db.example.com
    port: 5432
    user: backup_user
    password: "${PG_PASSWORD}" # Resolved from environment variable
    cron: "0 2 * * *"         # Default cron for all schemas in this instance
    keep: 14                   # Overrides global default
    schemas:
      - name: app_db
      - name: analytics_db
        cron: "0 4 * * *"     # Schema-level cron override
        keep: 5               # Schema-level keep override

  - name: prod-mysql
    type: mysql
    host: mysql.example.com
    port: 3306
    user: backup_user
    password: "${MYSQL_PASSWORD}"
    cron: "30 2 * * *"
    schemas:
      - name: users_db
      - name: orders_db
```

#### Inheritance rules

| Setting | Fallback chain |
|---|---|
| `keep` | schema → instance → `defaults.keep` (default: `7`) |
| `cron` | schema → instance (required at instance level) |

#### S3 key format

```
{prefix}/{instance_name}/{schema_name}/{schema_name}_YYYYMMDD_HHMMSS.sql.gz
```

Retention operations are scoped to each schema prefix, so schemas never interfere with each other.

### Environment variables

| Variable | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_DEFAULT_REGION` | AWS region (can also be set in `config.yaml`) |
| `AWS_ENDPOINT_URL` | Custom S3 endpoint (MinIO, Cloudflare R2, etc.) |
| Any `${VAR}` in config | Resolved at startup from the environment |

Copy `.env.example` to `.env` and fill in your values. Credentials are never baked into the image.

---

## Backup Verification

Before any upload, the dump is verified:

| Database | Method |
|---|---|
| PostgreSQL | `pg_restore --list <file>` — exits non-zero on a corrupt custom-format dump |
| MySQL | File size > 1 KB **and** `-- Dump completed` trailer present in the last 512 bytes |

If verification fails, the job is logged as an error and skipped — no corrupt file is ever uploaded.

---

## Error Handling

Each schema backup job is fully isolated. If one job fails at any stage (dump, verify, upload, retention), the error is logged and the scheduler continues with all remaining jobs. The next cron tick will retry automatically.

---

## Local Development

Start the backup service alongside local Postgres, MySQL, and [LocalStack](https://localstack.cloud/) (S3 emulator):

```bash
docker compose --profile dev up -d
```

| Service | Port |
|---|---|
| PostgreSQL | `5432` |
| MySQL | `3306` |
| LocalStack (S3) | `4566` |

Set `AWS_ENDPOINT_URL=http://localhost:4566` in your `.env` to point at LocalStack.

---

## Project Structure

```
.
├── Dockerfile
├── docker-compose.yml
├── config.example.yaml
├── requirements.txt
├── .env.example
└── src/
    ├── main.py              # Entrypoint
    ├── config.py            # YAML loader + env var substitution + validation
    ├── logger.py            # Structured JSON logger
    ├── scheduler.py         # APScheduler job registration + error isolation
    ├── backup/
    │   ├── base.py          # BackupJob ABC (dump → verify → compress → upload → retention)
    │   ├── postgresql.py    # PostgreSQL implementation
    │   └── mysql.py         # MySQL implementation
    └── storage/
        └── s3.py            # S3 upload + retention (list/delete)
```

---

## Log Format

All output is newline-delimited JSON, one object per event:

```json
{"timestamp": "2024-01-01T02:00:00Z", "level": "INFO", "message": "Starting dump", "instance": "prod-postgres", "schema": "app_db"}
{"timestamp": "2024-01-01T02:00:03Z", "level": "INFO", "message": "Backup complete", "instance": "prod-postgres", "schema": "app_db"}
{"timestamp": "2024-01-01T02:00:05Z", "level": "ERROR", "message": "Backup job failed — skipping", "instance": "prod-mysql", "schema": "orders_db", "exception": ["..."]}
```
