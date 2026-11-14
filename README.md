# Lexinit AI

**An adaptive learning platform that turns any topic, PDF, or photographed page into a complete five-module course, then keeps adjusting to how the learner actually performs.**

Each course combines Study Materials, Flashcards, three kinds of Assessments, a curated Video Lecture per module, a Learning Path, and Additional Resources. All of them are generated from one shared plan, so they never contradict each other. Assessment results feed a mastery model that schedules spaced reviews and recommends what to study next.

**Stack:** React 19 · TypeScript · TanStack Router/Query · Tailwind · Flask · Pydantic · LangGraph · RQ/Redis · MongoDB · Google Gemini · YouTube Data API · OpenTelemetry

---

## Contents

- [What a learner gets](#what-a-learner-gets)
- [Engineering highlights](#engineering-highlights)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Running locally](#running-locally)
- [Configuration](#configuration)
- [Known limitations and next steps](#known-limitations-and-next-steps)
- [Further documentation](#further-documentation)

---

## What a learner gets

1. **Sign up and onboard.** Email verification by one-time code, then a learner profile (student, working professional, or independent learner) that personalises generated content.
2. **Create a course** from a topic, optionally grounded in uploaded PDFs or images, at easy, medium, or hard difficulty, in *Quick* or *Deep Focus* mode (a stronger reasoning model with its own quota).
3. **Study** five ordered modules: Study Materials (Markdown with LaTeX math, printable), animated Flashcards, and a Video Lecture with a transcript-based Lecture Guide and knowledge check.
4. **Get assessed** with Multiple Choice, True/False, and One-word questions, graded entirely on the server. Each module assessment has four questions per type, and a reattempt uses new questions.
5. **Get coached on mistakes.** A wrong answer opens a *fix-it card*: why that answer was tempting, the key idea, and one fresh question to prove the gap is closed. Any concept can be explained a different way (simpler, analogy, worked example, step by step) or practised with three new questions.
6. **Adapt across time.** Every answer updates per-concept mastery, which fades without practice. A daily mix reviews what is due or weak across all courses, a knowledge map shows what is known and what is fading, and a finish date becomes a daily pace.
7. **Earn the badge** by passing a final assessment: new questions across every module, weighted toward the learner's weakest concepts.

A public waitlist page and a pricing page (Free, Plus, Pro plans with different daily generation limits) sit alongside the app.

---

## Engineering highlights

The design choices below are the parts of the project worth reading the code for.

### 1. Course generation is a durable, checkpointed workflow, not a long HTTP request

Generating a course takes many LLM and API calls, and any of them can fail. Instead of doing this inside a request, the API records a **generation run** in MongoDB and hands it to a worker. The orchestrator ([`backend/services/generation_jobs.py`](./backend/services/generation_jobs.py)) is a **LangGraph `StateGraph`**:

```text
prepare (safety check, reuse a matching course) → curriculum → knowledge packs → artifacts (parallel) → save
```

- **Checkpoint per step.** Each completed step and each artifact family is stored on the run. A retry reruns only what is missing or failed.
- **MongoDB is the source of truth, not the graph state**, so a crash loses nothing. Workers take a **time-limited lease** on a run, and incomplete runs are resumed on startup.
- **Pluggable execution.** `GENERATION_WORKER_MODE=auto` uses an **RQ/Redis** queue when Redis is configured and falls back to an in-process thread pool otherwise. The same code runs in development and production.
- **Parallel artifacts.** The eight artifact families are generated concurrently (thread pool of four), and cancellation is checked as each one finishes.
- **All or nothing.** A course is inserted only after every artifact passes validation, so learners never see a half-built course.
- **Fair quotas.** Daily generation limits are consumed with conditional atomic updates, so concurrent requests cannot exceed them or open the 24-hour window twice. Each run records the charge it took, so a failed or cancelled run is **refunded** exactly once, and only within the window it was charged to.

### 2. One plan per module keeps every artifact consistent

Separate LLM calls for notes, flashcards, and quizzes tend to drift apart. Lexinit first generates a **curriculum** (exactly five modules, each with concepts and measurable objectives) and then one **knowledge pack** per module: definitions, facts, examples, common mistakes, difficulty boundaries, source references, and video search terms.

Each module then runs as its own small pipeline: its **study material** is written from the pack, and its flashcards and questions are written **from that study material**, so practice only tests what the learner was actually taught. The five modules run in parallel and each stage is checkpointed, so a failure retries one module instead of the whole course. Every question's answer key is checked by an independent solve before it is accepted, with one spare question per type so a disputed one can be dropped.

Every artifact is **checked against the plan** before it is accepted. Each artifact carries **lineage** (curriculum, module, concept, and objective IDs, plus pack and prompt versions), so any question or card can be traced back to the objective it tests. IDs are derived from stable hashes, so the same plan produces the same IDs.

### 3. AI creates content; deterministic code makes decisions

The LLM never grades, authorises, or decides what a learner should do next.

- **Mastery model** ([`lexinit/domain/mastery/calculator.py`](./backend/lexinit/domain/mastery/calculator.py)): a Bayesian **Beta-Bernoulli** estimate per concept, starting from a Beta(2, 2) prior. Each answer is weighted by how much it actually says:
  - **Difficulty is asymmetric.** A hard question answered correctly counts more; an easy question answered wrongly counts more.
  - **Guessing is discounted.** A correct True/False answer counts half, a recalled one-word answer in full.
  - **Repeats count less.** A correct answer to a question seen within a day counts about a third.
  - **Old evidence fades** with a 45-day half-life, and **forgetting** is modelled between reviews: mastery shown to the learner is 90% of its peak when a review falls due.
- **Adaptive policy** ([`lexinit/domain/mastery/policy.py`](./backend/lexinit/domain/mastery/policy.py)): a pure function that chooses one of seven actions. It asks for more evidence before labelling anyone, and only sends a learner back to prerequisites when mastery is actually low. Each decision is stored with **machine-readable reason codes** and the evidence IDs behind it.
- **The response matches the size of the gap** ([`lexinit/services/concept_coach.py`](./backend/lexinit/services/concept_coach.py)): one wrong answer gets a fix-it card, a weak concept gets a new explanation and practice, a concept still weak after practice gets a **booster** (a ten-minute lesson and five questions inside the course, with its own daily allowance), and a full new course is the last resort. Coach questions keep their answers on the server until answered, and every answer becomes mastery evidence.
- **Spaced review.** The next review date follows the mastery band (1, 3, 7, or 14 days), and a daily mix draws the due and weakest concepts from every course.
- **One learner model across courses** ([`lexinit/services/learner_model.py`](./backend/lexinit/services/learner_model.py)): a concept already learnt in one course gives the same-named concept a head start in the next.
- **Measured, not assumed.** [`scripts/evaluate_mastery.py`](./backend/scripts/evaluate_mastery.py) scores how well mastery predicts each learner's *next* answer. On 300 simulated learners it reaches a Brier score of 0.229 and AUC of 0.67, against 0.250 and 0.50 for always guessing 50% and 0.270 and 0.57 for a running average.
- Both modules are pure Python with no I/O, sitting behind repository interfaces (`typing.Protocol`), so they can be tested in isolation.

### 4. Assessments are built to resist tampering

- The client receives questions **without answers**, explanations, or misconception maps (which would reveal the answer by elimination). Correct answers stay in a private question bank on the server.
- **AI-written answer keys are checked.** New questions are solved a second time without the key; a question whose key is disputed or ambiguous is dropped ([`lexinit/services/question_quality.py`](./backend/lexinit/services/question_quality.py)). Learners can report a question, which removes it from their future attempts.
- **A pass has to be earned.** Answers are revealed after an attempt, so a reattempt gets new questions on the same concepts, weighted toward what the learner got wrong. The final assessment uses only unseen questions and has a 24-hour wait after a failed attempt.
- An attempt is created server-side, **expires after two hours**, and each answer is saved against it.
- Starting, answering, and finalising are **idempotent**: replaying a key returns the original result, and reusing a key for different data is rejected.
- Finalising requires a signed submission token (compared in constant time), rejects incomplete, expired, mismatched, or foreign attempts, grades against the stored answers, and writes an **immutable submission**. Only then is mastery evidence recorded.

### 5. Video Lectures are ranked, not just searched

For each module, the matcher runs several focused YouTube queries built from the knowledge pack.

- **Filtered out:** Shorts, non-embeddable videos, videos made for kids, non-English audio, and any video already used in another module.
- **Scored on:** concept coverage (45%), transcript coverage (30%), title and topic relevance (15%), and search rank and duration (10%).
- **Transcript re-check:** the top three candidates are re-scored against their actual transcripts.
- **No fallback:** if nothing clears the quality threshold, the step fails and can be retried, instead of silently using the first search result.

Lecture Guides and knowledge checks are grounded in the chosen video's transcript, but kept separate from the course's own answers, so an external video cannot change what counts as correct.

### 6. Uploaded sources are handled as untrusted input

- **Validation:** uploads are checked by extension, MIME type, *and* file signature (magic bytes). Limits are 10 MB per PDF, 150 pages, and 8 MB per image.
- **Extraction:** text is extracted page by page with PyMuPDF. Pages that contain only images go through **Google Cloud Vision OCR**, up to 30 pages.
- **Retrieval:** text is split into overlapping chunks (1,200 characters, 180 overlap), stored with hashes and page lineage, and retrieved with feature-hashed term vectors and cosine similarity.
- **Grounding:** the most relevant chunks are attached to the generation run, and knowledge packs record which source passages they used.

### 7. Structured LLM output with validation and model fallback

Prompts for the curriculum, knowledge packs, and practice questions ask Gemini for JSON that matches a **schema derived from the Pydantic model** ([`backend/clients.py`](./backend/clients.py)). The response is then **validated locally** with the same model. A configurable **fallback chain of models** is tried in order when a call fails. Prompts are versioned (for example `curriculum-v2`), and the version is stored on everything they produce.

### 8. Security and operations

- **Sessions and CSRF:** server-side sessions stored in MongoDB, and CSRF tokens on every state-changing request from a signed-in user.
- **Headers:** a strict Content Security Policy and other security headers.
- **Rate limits:** a sliding-window limiter, shared through Redis when `REDIS_URL` is set (in-process otherwise), with separate budgets for uploads, generation starts (including regenerate and retry), assessments, and waitlist signups. Login, signup and password-reset routes are limited per client address and per target email, against password guessing and email flooding.
- **Ownership:** checked on every course, source, attempt, and run, and all request bodies are validated by Pydantic.
- **Observability:** OpenTelemetry tracing, request IDs, liveness and readiness probes, and token-protected metrics and alert endpoints (error rate, p95 latency, database health).
- **Tooling:** encrypted **AES-256-GCM** database backups with restore verification, an additive migration script with a dry-run mode, and a load-test gate that fails above 1% errors or 1.5 s p95 latency.

---

## Architecture

```mermaid
flowchart LR
    UI[React app] --> API[Flask API]
    API --> SEC[Sessions · CSRF · rate limits]
    API --> LEARN[Learning services]
    API --> RUNS[(Generation runs)]
    RUNS --> DISPATCH{Worker mode}
    DISPATCH -->|Redis configured| RQ[RQ worker]
    DISPATCH -->|no Redis| LOCAL[In-process pool]
    RQ --> ORCH[LangGraph orchestrator]
    LOCAL --> ORCH
    ORCH --> GEMINI[Gemini]
    ORCH --> YT[YouTube + transcripts]
    ORCH --> SEARCH[Google Custom Search]
    ORCH --> SRC[Sources + OCR]
    ORCH --> DB[(MongoDB)]
    LEARN --> ADAPT[Mastery model + adaptive policy]
    LEARN --> DB
    ADAPT --> DB
```

```mermaid
flowchart TD
    PREPARE[prepare: safety + matching-course lookup] -->|match found| DONE([course ready])
    PREPARE -->|new course| CURRICULUM[curriculum: five modules]
    CURRICULUM --> KNOWLEDGE[knowledge packs: one per module]
    KNOWLEDGE --> ARTIFACTS
    subgraph ARTIFACTS[artifacts: parallel, each validated and checkpointed]
        direction LR
        A1[Study Materials]
        A2[Flashcards]
        A3[MCQ · True/False · One-word]
        A4[Video Lectures]
        A5[Learning Path]
        A6[Additional Resources]
    end
    ARTIFACTS --> SAVE[save: single atomic insert]
    SAVE --> DONE
```

```mermaid
flowchart LR
    ANSWER[Assessment or lecture check] --> EVIDENCE[Immutable evidence]
    EVIDENCE --> MASTERY[Beta-Bernoulli mastery]
    MASTERY --> POLICY[Adaptive policy + reason codes]
    POLICY --> REVIEW[Spaced-review queue]
    POLICY --> NEXT[Recommended next step]
    POLICY --> FOCUS[Focused course on weak concepts]
```

---

## Tech stack

| Area | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, TanStack Router (type-safe, file-based routes), TanStack Query, Tailwind CSS 4, Radix UI, Motion, Recharts, React Markdown + KaTeX, Zod, Lenis |
| Backend | Python 3.11+, Flask, Pydantic v2, LangGraph, RQ, Flask-Mail, Gunicorn, managed with `uv` |
| Data | MongoDB (with schema validation and indexes); Redis for the production job queue |
| AI and search | Google Gemini (structured JSON output), YouTube Data API, youtube-transcript-api, Google Custom Search |
| Documents | PyMuPDF / PyMuPDF4LLM, Google Cloud Vision OCR |
| Operations | OpenTelemetry, health/readiness/metrics/alert endpoints, encrypted backups, load-test gate |

---

## Project structure

```text
backend/
  app.py, worker.py        API entry point (WSGI `application`) and RQ worker
  routes/                  HTTP layer: parsing, auth, ownership checks, responses
  lexinit/
    domain/                Pure logic: grading, mastery model, adaptive policy
    services/              Learning workflows: assessments, reviews, video, sources, dashboard
    repositories/          MongoDB persistence behind Protocol interfaces
    schemas/               Pydantic contracts for requests, domain, and LLM output
    observability/         Request context, telemetry, alert evaluation
  services/                Generation orchestrator, run state, content generation
  scripts/                 Migration, encrypted backup, load test, DB check, seed user
frontend/
  src/routes/              Pages (TanStack file-based routing)
  src/components/          Shared UI and product components
  src/hooks/               Server-state hooks (current user, generation polling, session)
  src/lib/api.ts           Typed API client with CSRF handling and Zod validation
docs/                      Architecture, backend, frontend, runbook, design system, product language
```

---

## Running locally

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js, MongoDB (local or Atlas), and API keys for Gemini and the YouTube Data API.

### Backend

Create `backend/.env` from [`backend/.env.example`](./backend/.env.example), then:

```bash
cd backend
uv sync
uv run python app.py
```

The API runs at `http://127.0.0.1:5000`. Without `REDIS_URL`, course generation runs in an in-process worker, so nothing else is needed for development.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:5173`.

### Single-server build

```bash
cd frontend
npm run build
cd ../backend
uv run python app.py
```

Flask serves the built React app from `frontend/dist`.

### Production

`app.py` starts Flask's debug server, which is for development only. In production, set `REDIS_URL` and run the API under a WSGI server and the worker as a separate process (both from `backend/`):

```bash
uv run gunicorn app:application
```

```bash
uv run python worker.py
```

See [docs/PRODUCTION_RUNBOOK.md](./docs/PRODUCTION_RUNBOOK.md) for release order, migration, backups, and alerting.

### Quality checks

```bash
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

```bash
cd backend
uv run --group dev pytest                 # 84 tests; the database-backed ones need MongoDB and are skipped without it
```

```bash
python -m backend.scripts.evaluate_mastery --simulate   # does mastery predict the next answer?
```

Every push and pull request runs these checks in GitHub Actions ([`.github/workflows/ci.yml`](./.github/workflows/ci.yml)).

---

## Configuration

All settings are environment variables. [`backend/.env.example`](./backend/.env.example) lists every variable; these are the main ones.

| Variable | Purpose |
| --- | --- |
| `FLASK_SECRET_KEY` | Session signing key (long and random in production) |
| `MONGO_URI` / `USE_LOCAL_MONGO` | Database connection |
| `GEMINI_API_KEY`, `GEMINI_MODEL_NAME`, `GEMINI_DEEP_FOCUS_MODEL_NAME`, `GEMINI_FALLBACK_MODEL_NAMES` | LLM access, the Deep Focus model, and the fallback chain |
| `YOUTUBE_API_KEY` | Video Lecture search |
| `CUSTOM_SEARCH_API`, `SEARCH_ID` | Additional Resources search |
| `GOOGLE_CREDENTIALS_BASE64` | Optional Google Cloud Vision OCR for scanned pages |
| `REDIS_URL`, `GENERATION_WORKER_MODE` | Job queue (`auto`, `rq`, or `local`) |
| `MAIL_*`, `MAIL_SUPPRESS_SEND` | Verification and reset emails (suppressed mode prints codes to the console) |
| `METRICS_TOKEN`, `OTEL_EXPORTER_OTLP_ENDPOINT` | Protected metrics and alerts, trace export |
| `LOGIN_RATE_LIMIT`, `AUTH_CODE_SEND_RATE_LIMIT`, `AUTH_CODE_VERIFY_RATE_LIMIT` | Throttles for sign-in, sending codes, and checking codes |
| `TRUSTED_PROXY_COUNT` | Reverse proxies in front of the app, so limits apply per real client address |

---

## Known limitations and next steps

These are stated openly so reviewers know where the edges are:

- **The model itself is not tested in CI.** The 84 tests run the real orchestrator, checkpoints, validation, quotas and routes (against a throwaway MongoDB), with the model and web calls replaced by stand-ins. They prove a course is assembled, retried and cancelled correctly; the quality of what the model writes is checked by scripted runs against the real model.
- **The mastery weights are judgement, not fitted.** They beat simple baselines on simulated learners; there is not yet enough real evidence to tune them.
- **Grounding in the study text is by instruction, not measured.** Questions are written with the module's study material in the prompt and told to test only what it explains; there is no automatic check that each answer appears in the text.
- **No explicit prompt caching.** Each module call now sends only its own module's context, which removed most repeated input; the shared context is placed first in the prompt, but no cache is created explicitly.
- **Mastery carries over between courses only for concepts with the same name.**
- **Source retrieval is lexical.** Feature-hashed term vectors capture shared vocabulary but not meaning. Swapping in real embeddings (for example Gemini embeddings with a vector index) is a contained change inside `document_learning.py`.
- **Rate limiting needs Redis to be global.** Without `REDIS_URL`, the limiter is in memory, so with several Gunicorn workers each enforces its own budget.
- **Waitlist signups are stored but not yet emailed or exported.**

---

## Further documentation

- [Project overview](./docs/PROJECT_OVERVIEW.md)
- [System architecture](./docs/ARCHITECTURE.md)
- [Backend architecture](./docs/BACKEND_ARCHITECTURE.md)
- [Frontend architecture](./docs/FRONTEND_ARCHITECTURE.md)
- [Production runbook](./docs/PRODUCTION_RUNBOOK.md)
- [Design system](./docs/DESIGN.md)
- [Product language](./docs/PRODUCT_LANGUAGE.md)
