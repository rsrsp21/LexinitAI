# Lexinit production runbook

## Release order

1. Create and verify a database backup or Atlas snapshot.
2. Deploy the API with legacy compatibility routes still enabled.
3. Check `GET /api/v1/health/live` and `GET /api/v1/health/ready`.
4. Run `uv run --project backend python -m backend.scripts.migrate_v1` and review the dry-run counts.
5. Run the same command with `--apply` only after the backup is confirmed.
6. Deploy the frontend and verify sign-in, source upload, generation, assessments, video resume, and source citations.
7. Monitor 4xx/5xx rates, request duration, generation failures, provider quota usage, and worker queue depth.

## Required production configuration

- Use a long random `FLASK_SECRET_KEY` and `METRICS_TOKEN`.
- Set `SESSION_COOKIE_SECURE=true` and keep `SESSION_COOKIE_SAMESITE=Lax` unless cross-site hosting requires a reviewed alternative.
- Use explicit HTTPS origins in `CORS_ORIGINS`.
- Serve the API with a WSGI server such as Gunicorn (`gunicorn app:application` from `backend/`), never `python app.py`, which starts Flask's debug server.
- Configure Redis and run the RQ worker (`python worker.py`) separately from the web process.
- Configure `OTEL_EXPORTER_OTLP_ENDPOINT` for trace export.
- Keep database credentials, provider keys, and monitoring tokens outside source control.

## Migration and rollback

The v1 migration is additive: it moves embedded sessions when present and adds normalized/version fields. It does not delete legacy collections or content.

If validation fails:

1. Stop the frontend rollout.
2. Keep or restore the previous API build; compatibility routes remain available.
3. Restore the verified backup only if data integrity was affected.
4. Preserve request IDs, migration output, and worker logs for diagnosis without exporting learner answers or source text.

## Recovery checks

- Restart a worker during an active generation and confirm the leased run resumes.
- Temporarily disable each external provider and confirm retryable, learner-friendly errors.
- Confirm deleting a source removes its stored file, pages, and chunks.
- Confirm one user cannot read, retry, search, or delete another user's source.
- Confirm unsafe authenticated requests without a CSRF token return `403`.
- Confirm throttled clients receive `429` without starting generation or extraction.

## Backup validation

At least monthly, restore the latest backup into an isolated database, compare user/session/source counts, open a sample source-grounded session, and record restore duration. Never use production provider keys in the restore environment.

The repository backup command creates an AES-256-GCM encrypted BSON archive, a separate key, and a checksum, then verifies the archive by fully decoding every collection and checking document counts and checksums:

`uv run --project backend python -m backend.scripts.backup_database create`

Verify an existing archive with `uv run --project backend python -m backend.scripts.backup_database verify --archive <file>.lexbackup --key-file <file>.lexbackup.key`.

Store the `.lexbackup` archive and `.lexbackup.key` file in separate restricted locations. Neither file is committed to Git.

## Load and alert gates

Run the concurrent health/readiness gate against the deployed API URL before shifting traffic:

`uv run --project backend python -m backend.scripts.load_smoke --base-url https://api.example.com --requests 500 --concurrency 25`

The command fails when the error rate exceeds 1% or p95 response time exceeds 1.5 seconds. Increase duration and concurrency for capacity testing in a staging environment; do not stress production beyond an approved traffic envelope.

The protected `GET /api/v1/health/alerts` endpoint reports database availability, five-minute API server-error rate, and p95 latency. It uses the same bearer `METRICS_TOKEN` as the metrics endpoint. Configure the monitoring platform to poll it and page on HTTP `503`. Defaults can be overridden with `ALERT_WINDOW_SECONDS`, `ALERT_MIN_REQUESTS`, `ALERT_ERROR_RATE_PERCENT`, and `ALERT_P95_DURATION_MS`.
