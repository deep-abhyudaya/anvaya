# 12 — Deployment

## Local development

### Backend

```bash
pip install -e ".[dev]"
anvaya serve
```

Server runs on `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard runs on `http://localhost:3000`.

### Database

By default the backend uses SQLite (`sqlite:///./anvaya.db`). Set `DATABASE_URL` to a PostgreSQL string to use PostgreSQL:

```bash
DATABASE_URL="postgresql://user:password@localhost/anvaya"
```

## Docker

### Backend Dockerfile

`Dockerfile.backend` builds the FastAPI service.

### Frontend Dockerfile

`Dockerfile.frontend` builds a static or standalone Next.js image.

### Docker Compose

`docker-compose.yml` can start the backend, frontend, and a PostgreSQL container together.

```bash
docker-compose up --build
```

## Cloud configs

The repository includes production-ready deployment configs:

| File | Platform | Purpose |
|---|---|---|
| `frontend/vercel.json` | Vercel | Next.js frontend hosting |
| `railway.toml` | Railway | Backend and PostgreSQL |
| `fly.toml` | Fly.io | Backend container deployment |

## Environment variables

| Variable | Example | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://...` | Database connection |
| `OPENAI_API_KEY` | `sk-...` | Optional LLM rule naming |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model name |
| `API_HOST` | `0.0.0.0` | Backend bind address |
| `API_PORT` | `8000` | Backend port |
| `DEBUG` | `True` / `False` | CORS and logging mode |
| `CORS_ORIGINS` | JSON list | Allowed frontend origins |

## Security notes

- `DEBUG=False` in production to restrict CORS.
- Security headers are added by middleware.
- Do not commit `.env` files with real credentials.
- The audit chain uses SHA-256 hashes for integrity.
