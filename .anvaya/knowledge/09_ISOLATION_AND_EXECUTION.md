# ANVAYA — Isolation and Execution

> This subsystem is intentionally limited. ANVAYA is a defensive simulator, not a sandboxed execution platform. There are no Docker-in-Docker, no network namespaces, and no seccomp profiles for the core runtime.

## What is isolated

### 1. Provider/API credentials

- API keys and secrets live only in environment variables (`backend/anvaya/config.py`) or service-account files (`gmail_credentials_path`).
- They are never sent to the frontend.
- The `.env.example` does not contain real keys.

### 2. Synthetic attack data

- All attacks are generated from deterministic templates (`simulator/anvaya/scenarios.py`).
- No real-world offensive actions are performed.
- `is_attack` is a boolean ground-truth label, not a live exploit.

### 3. Execution state per request

- FastAPI `get_session` creates a fresh SQLModel `Session` per request.
- CLI `get_session_sync` creates a fresh session per call.
- Execution contexts (`ExecutionContext`) are scoped to an `execution_id`.

## What is NOT isolated

- The CLI runs in the same Python process as the backend logic.
- `_do_shell` in the interactive CLI runs arbitrary commands with the user’s privileges.
- Docker Compose runs all services on the same host network by default.
- There is no privilege separation between the backend and the database.

## Execution mechanisms

### FastAPI request handling

| Question | Answer |
|----------|--------|
| Who initiates? | User / frontend / CLI `anvaya serve` |
| What executes? | FastAPI route handler → engine/method |
| Privileges | User privileges of the uvicorn process |
| Where? | Same host/container as backend |
| Filesystem | Full access to host/container filesystem |
| Network | Full access (subject to container network) |
| Inputs | HTTP JSON body, query params, path params |
| Outputs | HTTP JSON response |
| Failure | 500 global exception handler |
| Cleanup | Session context manager closes DB session |

### CLI shell command (`/shell`)

| Question | Answer |
|----------|--------|
| Who initiates? | User in interactive shell |
| What executes? | `subprocess.run(command, shell=False)` |
| Privileges | User running `anvaya` |
| Where? | Local machine |
| Filesystem | Full user access |
| Network | Full user access |
| Inputs | Parsed shell command string |
| Outputs | Stdout/stderr printed to console |
| Failure | Exception caught and rendered |
| Cleanup | Process exits normally |

Security note: `shell=False` means the command is split and passed as a list, but a single argument can still execute a binary. This is a privileged operation boundary; a compromised agent prompt could invoke it.

### Background threads

| Question | Answer |
|----------|--------|
| Who initiates? | `POST /agent/execute?background=true` or `POST /projects/{id}/build` |
| What executes? | Python `threading.Thread` running `AgentOrchestrator.run` or `build_artifact` |
| Privileges | Same as backend process |
| Where? | Same process |
| Filesystem | Same as backend |
| Network | Same as backend |
| Inputs | Execution context or build request |
| Outputs | Events written to DB; SSE/polling consumed by frontend |
| Failure | Exception logged; execution status updated |
| Cleanup | Thread completes or execution cancelled |

### Docker Compose

| Service | Image | Network | Volumes |
|---------|-------|---------|---------|
| db | `postgres:15-alpine` | default bridge | `pgdata` |
| backend | local Dockerfile | default bridge | `backend`, `ml`, `simulator`, `datasets` |
| frontend | local Dockerfile | default bridge | — |

There is no explicit inter-service network isolation beyond Docker’s default bridge.

## Subprocess / external process boundaries

- **Python code execution:** only the backend’s own code runs. No user-supplied Python is `exec`d.
- **Model training:** scikit-learn `IsolationForest` and `LogisticRegression` run in the backend process.
- **HTTP calls to providers:** `httpx.post` to Tavily, n8n, Lyzr, LLM gateways.
- **Gmail API:** `google-api-python-client` calls with service-account credentials.
- **No shell spawning from agent tools** (except the explicit `/shell` CLI command).

## Security-sensitive paths

- `backend/anvaya/agent/executor.py`: tool execution. Must not allow arbitrary code.
- `backend/anvaya/cli/shell.py`: `_do_shell` runs subprocess.
- `backend/anvaya/config.py`: loads secrets from environment.
- `backend/anvaya/agent/adapters.py`: external HTTP calls with keys.

## Active recall

- Is there a sandbox for user-supplied code? (No)
- What is the most dangerous CLI command and why? (`/shell`, it runs subprocess)
- How are background agent executions run? (`threading.Thread`)
- Where are secrets stored? (environment variables / service-account files)
- Does the frontend ever receive API keys? (No)

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/docker-compose.yml" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/Dockerfile.backend" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/cli/shell.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/executor.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/config.py" />
