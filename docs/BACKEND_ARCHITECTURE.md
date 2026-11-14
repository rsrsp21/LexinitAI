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
| `course.py` | Course reads and progress, final assessment, course goal dates |
| `coach.py` | In-course coaching: fix-it cards, explanations, practice sets, module pre-checks, daily mix, question reports |
| `learning_loop.py` | Secured Assessment attempts, answers, and finalization |
| `adaptive.py` | Mastery, weak concepts, recommendations, focused generation |
| `video_learning.py` | Lecture catalog, playback progress, guides, retrieval checks |
| `sources.py` / `uploads.py` | Source ingestion, extraction, search, and ownership |
| `activity.py` | Activity and compatibility endpoints |
| `health.py` | Liveness, readiness, metrics, and alerts |
| `security.py` | CSRF support and security-facing endpoints |

## Generation state

Generation runs live in MongoDB and include status, stage, progress, attempt count, leases, errors, completed steps, failed steps, and checkpoints. The orchestrator (`services/generation_jobs.py`) is a LangGraph `StateGraph` with the nodes `prepare → curriculum → knowledge → artifacts → save`; `prepare` exits early when a matching course already exists. A sequential equivalent runs when LangGraph is unavailable.

The `artifacts` node runs eight tasks side by side: video lectures, the learning path, additional resources, and one pipeline per module. A module pipeline writes the study material (`module_material:<module_id>` checkpoint), then writes that module's flashcards and questions from that material (`module_practice:<module_id>` checkpoint). Each module asks for three questions per type, checks every answer key with an independent solve (`question_quality.verify_answer_keys`), and keeps two per type; if too few survive it writes one more set, and any place still empty is filled with a question marked `validation_status: "unverified"`. When all modules are done, the per-module checkpoints are combined into the course-level artifacts and validated (exactly one study material and two items of each kind per module, correct module references, no duplicate questions). A retry redoes only the module stages that have no checkpoint.

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

A module assessment has four questions per type. When a learner has seen a module's questions, new ones are written on demand, weighted toward the concepts they got wrong (`concept_coach.refill_module_questions`). Every AI-written question added after course generation is solved a second time without its key and dropped if the key is disputed (`question_quality.verify_answer_keys`). Results store each question's concepts, module, and bank id, because attempt records expire about a day after use.

## Adaptive learning loop

Every answer, from any activity, becomes a `MasteryEvidence` record and updates one per-concept estimate (`domain/mastery/calculator.py`). Evidence sources and their relative weight:

| Source | Weight | Notes |
| --- | --- | --- |
| Module assessment, final assessment | 1.0 | Final uses only unseen questions |
| Daily mix | 0.9 | Due and weak concepts from every course |
| Practice set, module pre-check | 0.8 | Fresh questions per concept |
| Lecture knowledge check | 0.75 | Graded against the transcript |
| Fix-it check | 0.6 | Asked right after the explanation |
| Flashcard self-rating | 0.35 to 0.9 | By rating |
| Carry-over from another course | 0.5 | Same-named concept, clear signal only |

Correct answers are further scaled by difficulty, by the chance of guessing the format, and by whether the same question was seen recently; all evidence fades with a 45-day half-life. Reads apply a forgetting curve (`retention`), so mastery shown to the learner drops between reviews.

Services built on that estimate:

- `concept_coach.py`: responses sized to the gap (fix-it card, alternative explanation, practice set, pre-check, daily mix). Answers to coach questions stay on the server until submitted.
- `final_assessment.py`: unlocks when every module is passed; twelve new questions weighted toward weak concepts; 70% to pass; a 24-hour wait after a failed attempt. Passing is required for course completion and the badge.
- `learner_model.py`: knowledge map, mastery carry-over between courses, and course goal dates.
- `course_deletion.py`: removes a course with its attempts, results, coach history, progress and mastery; mastery for a concept also practised elsewhere is recalculated instead of deleted.

`scripts/evaluate_mastery.py` scores how well the estimate predicts each learner's next answer, on real evidence or simulated learners.

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
