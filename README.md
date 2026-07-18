# Lexinit AI

## Documentation

- [Project overview](./docs/PROJECT_OVERVIEW.md)
- [System architecture](./docs/ARCHITECTURE.md)
- [Backend architecture](./docs/BACKEND_ARCHITECTURE.md)
- [Frontend architecture](./docs/FRONTEND_ARCHITECTURE.md)
- [Production runbook](./docs/PRODUCTION_RUNBOOK.md)
- [Design system](./docs/DESIGN.md)
- [Product language](./docs/PRODUCT_LANGUAGE.md)

## Project Structure

```text
backend/   Flask API, database, auth, AI services
frontend/  React + Vite UI
```

## Backend

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

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## Production-Style Local Run

```powershell
cd frontend
npm install
npm run build
cd ..
cd backend
uv run python app.py
```

After a frontend build, Flask serves the React app from `frontend/dist`.
