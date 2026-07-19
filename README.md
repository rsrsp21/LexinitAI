# Lexinit AI

Lexinit is a personalized learning workspace that turns a topic or uploaded source into a structured five-module course. Each course brings together Study Materials, Flashcards, Assessments, Video Lectures, Additional Resources, progress tracking, review scheduling, and adaptive recommendations.

## How it works

1. A learner registers, accepts the policies, and completes their learning profile.
2. The learner creates a course from a topic, optional source, difficulty, and generation mode.
3. Lexinit generates a curriculum and one authoritative knowledge pack per module.
4. Study Materials, Flashcards, Assessments, and Video Lectures are aligned to those module packs.
5. The learner progresses module by module and completes learning activities.
6. Assessments and lecture knowledge checks produce learning evidence.
7. The adaptive engine identifies weak concepts, schedules reviews, and recommends focused next steps.
8. Course-level and overall progress are available in the Progress dashboard; earned completion badges appear in the profile.

## Main capabilities

- Topic-based and source-grounded course creation
- Five-module Learning Path with activity completion
- Study Materials with printable export
- Stacked, animated Flashcards
- Secured Multiple Choice, True/False, and One-word Assessments
- Server-side answer validation and grading
- Weak-concept detection and focused-course generation
- Ranked, module-aligned YouTube Video Lectures
- Transcript-based Lecture Guides and knowledge checks
- Course and overall learning analytics
- Spaced-review queue and adaptive recommendations
- Student, professional, and independent-learner profiles
- Password reset and profile management
- Durable, retryable generation jobs

## Technology

| Area | Stack |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, TanStack Router, TanStack Query, Tailwind CSS, Motion |
| Backend | Python, Flask, Pydantic, LangGraph, RQ |
| Data | MongoDB; Redis for production job queues |
| AI | Google Gemini structured generation |
| External learning | YouTube Data API and transcript retrieval |
| Documents | PyMuPDF/PyMuPDF4LLM with optional Google Vision OCR |
| Operations | OpenTelemetry, health/readiness endpoints, alert checks, encrypted backup tooling |

## Project structure

```text
backend/   Flask API, domain services, schemas, jobs, scripts
frontend/  React + Vite UI, routes, components, API contracts
docs/      Architecture, runbook, design system, product language
```

## Documentation

- [Project overview](./docs/PROJECT_OVERVIEW.md)
- [System architecture](./docs/ARCHITECTURE.md)
- [Backend architecture](./docs/BACKEND_ARCHITECTURE.md)
- [Frontend architecture](./docs/FRONTEND_ARCHITECTURE.md)
- [Production runbook](./docs/PRODUCTION_RUNBOOK.md)
- [Design system](./docs/DESIGN.md)
- [Product language](./docs/PRODUCT_LANGUAGE.md)

## Getting started

### Backend

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), create
`backend/.env` from `backend/.env.example`, then run:

```powershell
cd backend
uv sync
uv run python app.py
```

`uv sync` creates and manages the project environment automatically; no manual
activation is needed.

Generation runs are persisted in MongoDB. With no `REDIS_URL`, development uses
the built-in local worker. For production, configure Redis and start the API and
worker as separate processes:

```powershell
# terminal 1
uv run python app.py

# terminal 2
uv run python worker.py
```

Backend URL:

```text
http://127.0.0.1:5000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

### Production-style local run

```powershell
cd frontend
npm install
npm run build
cd ..
cd backend
uv run python app.py
```

After a frontend build, Flask serves the React app from `frontend/dist`.

### Quality gates

```powershell
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```
