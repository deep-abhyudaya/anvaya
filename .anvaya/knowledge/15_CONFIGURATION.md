# ANVAYA — Configuration

## Configuration loading

`backend/anvaya/config.py` uses `pydantic_settings.BaseSettings`:

```python
class Config:
    env_file = [str(_PROJECT_ROOT / ".env"), str(_PROJECT_ROOT / ".env.local")]
```

`.env` is committed with defaults; `.env.local` is for secrets and overrides and should be git-ignored.

## Key settings

| Setting | Env var | Default | Purpose |
|---------|---------|---------|---------|
| `database_url` | `DATABASE_URL` | `sqlite:///./anvaya.db` | DB connection |
| `openai_api_key` | `OPENAI_API_KEY` | — | OpenAI API |
| `openai_model` | `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model |
| `nvidia_api_key` | `NVIDIA_API_KEY` | — | NVIDIA NIM |
| `tavily_api_key` | `TAVILY_API_KEY` | — | Tavily search |
| `n8n_webhook_url` | `N8N_WEBHOOK_URL` | — | n8n webhooks |
| `gmail_credentials_path` | `GMAIL_CREDENTIALS_PATH` | — | Gmail service account |
| `gmail_from_email` | `GMAIL_FROM_EMAIL` | — | Gmail sender |
| `lyzr_api_key` | `LYZR_API_KEY` | — | Lyzr |
| `swytchcode_api_key` | `SWYTCHCODE_API_KEY` | — | Swytchcode |
| `swytchcode_base_url` | `SWYTCHCODE_BASE_URL` | — | Swytchcode base |
| `openrouter_api_key` | `OPENROUTER_API_KEY` | — | OpenRouter |
| `opencode_api_key` | `OPENCODE_API_KEY` | — | OpenCode |
| `seekai_api_key` | `SEEKAI_API_KEY` | — | SeekAI |
| `gmicloud_api_key` | `GMICLOUD_API_KEY` / `GMI_API_KEY` | — | GMI Cloud |
| `empero_api_key` | `EMPERO_API_KEY` | — | Empero (public token `free`) |
| `better_auth_secret` | `BETTER_AUTH_SECRET` | — | Better Auth token HMAC |
| `api_host` | `API_HOST` | `0.0.0.0` | uvicorn host |
| `api_port` | `API_PORT` | `8000` | uvicorn port |
| `debug` | `DEBUG` | `true` | debug mode |
| `log_level` | `LOG_LEVEL` | `info` | structlog level |
| `cli_log_level` | `CLI_LOG_LEVEL` | `error` | CLI log level |
| `poll_interval_seconds` | `POLL_INTERVAL_SECONDS` | `4` | default poll interval |
| `cors_origins` | `CORS_ORIGINS` | localhost:3000/3001 | CORS allow-list |
| `isolation_forest_n_estimators` | — | `100` | IF trees |
| `isolation_forest_contamination` | — | `0.05` | IF contamination default |
| `detection_threshold` | — | `-0.5` | IF decision threshold |
| `max_repair_iterations` | — | `3` | Sentinel repair |

## Provider enablement methods

`Settings` exposes `is_*_enabled()`:

```python
is_llm_enabled()
is_tavily_enabled()
is_n8n_enabled()
is_gmail_enabled()
is_lyzr_enabled()
is_swytchcode_enabled()
is_nvidia_enabled()
is_openrouter_enabled()
...
```

These drive the provider status UI and adapter fallback logic.

## Frontend env

Only public env vars (prefixed `NEXT_PUBLIC_`) reach the browser:

- `NEXT_PUBLIC_API_URL` → `http://localhost:8000/api/v1`

## Feature flags

There is no centralized feature-flag system. Provider availability and `Settings.debug` act as implicit flags.

## Configuration verification

Run:

```bash
cd /home/de3p/Documents/Next.js/Anavaya
python -c "from anvaya.config import settings; print(settings.model_dump())"
```

This prints resolved settings (do not log in production — it contains secret placeholders).

## Security note

Never commit `.env.local` or any file with real keys. The committed `.env` should only contain safe defaults and localhost URLs.

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/config.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/.env.example" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/frontend/.env.example" />
