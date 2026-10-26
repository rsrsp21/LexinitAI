# Lexinit backend architecture

## Entry points

- `backend/app.py`: WSGI and local-development entry point
- `backend/__init__.py`: application factory and extension setup
- `backend/worker.py`: RQ generation worker
- `backend/routes/`: HTTP transport and authorization boundaries
- `backend/services/`: generation orchestration and compatibility services
- `backend/lexinit/`: domain-oriented schemas, repositories, policies, and services

## Layers

```text
routes/                    HTTP parsing, authentication, ownership, responses
lexinit/api/               Shared API errors and Pydantic validation
lexinit/schemas/           Request, domain, and structured-generation contracts
lexinit/domain/            Pure grading and mastery policies
lexinit/services/          Application workflows
lexinit/repositories/      MongoDB persistence boundaries
lexinit/observability/     Request context, OpenTelemetry, alert evaluation
services/                  Course generation and durable run orchestration
server_session.py          MongoDB-backed Flask login sessions
session_store.py           Course (learning session) lookup and topic normalization
clients.py                 Gemini, YouTube, Google service clients
extensions.py              Mongo, mail, CORS, and shared extensions
security.py                CSRF, headers, throttling, and session controls
```

Routes do not calculate mastery or trust client scores. Domain and application services own those decisions.

## Route groups

| Module | Responsibility |
| --- | --- |
| `core.py` | Serves the built frontend (`frontend/dist`) and static images |
| `auth.py` | Registration with email verification code, login, logout, password reset, profile identity |
| `api.py` | Topic submission and compatibility API operations |
| `course.py` | Course reads, progress, and course-level actions |
| `learning_loop.py` | Secured Assessment attempts, answers, and finalization |
| `adaptive.py` | Mastery, weak concepts, recommendations, focused generation |
| `video_learning.py` | Lecture catalog, playback progress, guides, retrieval checks |
| `sources.py` / `uploads.py` | Source ingestion, extraction, search, and ownership |
| `activity.py` | Activity and compatibility endpoints |
| `health.py` | Liveness, readiness, metrics, and alerts |
| `security.py` | CSRF support and security-facing endpoints |

## Generation state

Generation runs live in MongoDB and include status, stage, progress, attempt count, leases, errors, completed steps, failed steps, and checkpoints. The orchestrator (`services/generation_jobs.py`) is a LangGraph `StateGraph` with the nodes `prepare → curriculum → knowledge → artifacts → save`; `prepare` exits early when a matching course already exists. A sequential equivalent runs when LangGraph is unavailable.

The `artifacts` node generates all pending artifact families in parallel (thread pool of four), validates each against the curriculum and knowledge packs, and checkpoints it individually. Cancellation is checked between steps. On failure or cancellation the run is marked failed/cancelled (retryable except for safety failures) and the generation quota is refunded.

Dispatch is controlled by `GENERATION_WORKER_MODE` (`auto`, `rq`, `local`). Workers claim runs with a lease (`GENERATION_LEASE_SECONDS`), and incomplete runs resume on startup when `GENERATION_RESUME_ON_STARTUP` is enabled.

Important checkpoints:

- `safety`
- `cache`
- `curriculum`
- `knowledge_packs`
- `artifact:study_materials`
- `artifact:flashcards`
- `artifact:mcqs`
- `artifact:true_false`
- `artifact:oneword`
- `artifact:course_content`
- `artifact:learningpath`
- `artifact:additionalresources`
- `saving`

Only a fully validated run inserts a new session. Idempotency keys and a generation fingerprint prevent duplicate or conflicting submissions.

## Data model

Principal MongoDB data includes users, sessions/courses, generation runs, sources and chunks, Assessment attempts/submissions, mastery evidence, concept mastery, adaptation decisions, review events, Video Lecture metadata/transcripts/guides/progress, and operational observations.

Course artifacts reference stable IDs:

```text
curriculum_id
module_id
concept_ids[]
objective_ids[]
knowledge_pack_id
knowledge_pack_version
source_ids[] / grounding_refs[]
prompt_version
validation_status
```

## Assessment integrity

1. The server creates a secured attempt from the private question bank.
2. The client receives questions and options without correct answers.
3. Every answer is validated and saved against the attempt.
4. Finalization rejects incomplete, expired, mismatched, replayed, or unauthorized attempts.
5. The server grades against saved answers and writes an immutable submission.
6. Mastery evidence and adaptive decisions are calculated server-side.

## Source grounding

Uploaded files are validated, extracted page-by-page, chunked, stored with hashes and lineage, and searched for relevant context. Source content is always treated as untrusted data. Knowledge packs store source references, allowing downstream artifacts to stay aligned without repeatedly sending entire Study Materials between generation calls.

## Operations

- `scripts/migrate_v1.py`: additive migration and dry-run/apply modes
- `scripts/backup_database.py`: encrypted backup creation and verification
- `scripts/load_smoke.py`: concurrent health/readiness load gate
- `scripts/check_mongo.py`: database connectivity check
- `scripts/seed_local_user.py`: local development fixture
- OpenTelemetry tracing and protected metrics/alert endpoints

## Backend verification

```powershell
uv sync --project backend
uv run --project backend python -m compileall -q backend
```

See [PRODUCTION_RUNBOOK.md](./PRODUCTION_RUNBOOK.md) before deployment or migration.
