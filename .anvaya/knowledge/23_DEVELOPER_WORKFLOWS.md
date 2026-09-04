# ANVAYA — Developer Workflows

## Quick start (Docker Compose)

```bash
cd /home/de3p/Documents/Next.js/Anavaya
docker compose up --build
```

Services:
- PostgreSQL on `5432`
- FastAPI on `8000`
- Next.js on `3000`

## Quick start (manual)

### Backend

```bash
cd /home/de3p/Documents/Next.js/Anavaya/backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd ..
anvaya serve
```

Or:

```bash
uvicorn anvaya.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd /home/de3p/Documents/Next.js/Anavaya/frontend
npm install
npm run dev
```

### Database

Default uses SQLite. For PostgreSQL, set:

```env
DATABASE_URL=postgresql://anvaya:anvaya@localhost:5432/anvaya
```

## Common commands

```bash
# Run all tests
python -m pytest tests/ -q --no-header

# Run focused tests
python -m pytest tests/test_live_scoring.py tests/test_agent.py -v

# Lint backend
ruff check backend/anvaya
mypy backend/anvaya

# Lint frontend
npm --prefix frontend run lint

# Interactive CLI
anvaya

# Train
anvaya train

# Watch a log file
anvaya watch --source /var/log/auth.log

# Generate synthetic feed
anvaya watch --source synthetic

# Run demo
anvaya demo
```

## Environment setup

```bash
cp .env.example .env.local
# edit .env.local with real credentials (do not commit)
```

## Build for deployment

### Backend

```bash
docker build -f Dockerfile.backend -t anvaya-backend .
```

### Frontend

```bash
cd frontend
docker build -f ../Dockerfile.frontend -t anvaya-frontend .
```

Or build for Vercel:

```bash
cd /home/de3p/Documents/Next.js/Anavaya/frontend
npm run build
```

## Deployment targets

- **Frontend:** Vercel (`fly.toml`, `railway.toml` also present for backend options).
- **Backend:** Railway or Fly.io.
- **Database:** PostgreSQL on Railway/Fly or managed service.

## Directory conventions

- Python code: `backend/anvaya/`
- ML: `ml/anvaya/`
- Synthetic data: `simulator/anvaya/`
- Datasets/CSVs: `datasets/`
- Trained models: `ml/artifacts/`
- Frontend: `frontend/`
- Tests: `tests/` + `backend/anvaya/tests/`
- Docs: `.anvaya/knowledge/`, `docs/`, `.devin/rules/`

## Active recall

- What is the default database?
- What command starts the FastAPI backend?
- What command starts the Next.js frontend?
- How do you run all tests?
- Where should secrets go?

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/docker-compose.yml" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/pyproject.toml" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/frontend/package.json" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/.env.example" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/fly.toml" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/railway.toml" />
