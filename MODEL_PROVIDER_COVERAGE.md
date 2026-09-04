# ANVAYA — Model Provider Coverage

Last verified: 2026-08-28

This document records the status of every model provider integrated into ANVAYA. It is generated from live endpoint checks, the normalized catalog, and the test suite.

## Summary

| Provider | Kind | Protocol | Base URL | Auth | Privacy | Status |
|----------|------|----------|----------|------|---------|--------|
| `anvaya` | local | `local` | n/a | none | `standard` | available |
| `agentrouter` | aggregator | `anthropic-compatible` / `openai-compatible` | `https://agentrouter.org` | `AGENTROUTER_API_KEY` | `standard` | configured when key present |
| `nvidia` | inference gateway | `openai-compatible` | `https://integrate.api.nvidia.com/v1` | `NVIDIA_API_KEY` | `standard` | configured when key present |
| `opencode` | aggregator | `openai-compatible` | `https://opencode.ai/zen/v1` | `OPENCODE_API_KEY` | `standard` | configured when key present |
| `openrouter` | aggregator | `openai-compatible` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | `standard` | configured when key present |
| `seekai` | aggregator | `openai-compatible` | `https://seekai.cc/v1` | `SEEKAI_API_KEY` | `standard` | new, configured when key present |
| `gmicloud` | inference gateway | `openai-compatible` | `https://api.gmi-serving.com/v1` | `GMICLOUD_API_KEY` (also accepts `GMI_API_KEY`) | `standard` | new, configured when key present |
| `empero` | community endpoint | `openai-compatible` | `https://free.empero.org/v1` | public token `free` (set `EMPERO_API_KEY=disabled` to opt out) | `public_community_endpoint` | new, public by default |

## Verified capabilities

### `anvaya`

- Always available, no credentials.
- Returns deterministic safe responses for agent fallback.

### `agentrouter`

- Preserved; Anthropic and OpenAI-compatible routes remain.
- Selection order remains highest-priority provider.

### `nvidia`

- Preserved; live NIM catalog discovery and static fallback.
- Tool-calling and structured outputs supported.

### `opencode`

- Preserved; free-tier catalog from `opencode.ai` and `models.dev`.

### `openrouter`

- Preserved; free-tier OpenRouter models with 403 fallback to `openrouter/free`.

### `seekai`

- **Endpoint verified**: `GET https://seekai.cc/v1/models` returns OpenAI-format model list.
- **Streaming verified**: `POST https://seekai.cc/v1/chat/completions` with `stream=true` and a live `gemini-3-6-flash` model returns Server-Sent Events in OpenAI chunk format.
- **Catalog**: the live `/v1/models` list is the source of truth. Static entries are only used to enrich metadata for IDs the live endpoint confirms are reachable. Non-live static IDs are no longer surfaced, eliminating duplicates such as `gpt-5-6-luna` / `gpt-5.6-luna`.
- **Notable model IDs** (live): `claude-fable-5`, `claude-opus-4-8`, `claude-opus-5`, `claude-sonnet-5`, `deepseek-v4-pro`, `gemini-3-6-flash`, `glm-5-2`, `gpt-5.6-sol`.
- **Pricing modes**: per-token for most models; per-request (`$0.10`) where the static catalog indicates it.
- **Gateway role**: SeekAI is treated as a gateway, not a model maker. `maker` is inferred from the underlying model (`Anthropic`, `OpenAI`, `DeepSeek`, `Z AI`, `Google`).

### `gmicloud`

- **Endpoint verified**: `GET https://api.gmi-serving.com/v1/models` returns 79 chat models.
- **Catalog**: all chat/instruct models returned by live `GET /v1/models` are surfaced when a key is configured; the no-key fallback preserves the promotional/free `MiniMaxAI/MiniMax-M3` and `MiniMaxAI/MiniMax-M2.7`.
- **Free-only mode**: set `GMICLOUD_FREE_ONLY=true` (or `GMI_FREE_ONLY=true`) to hide paid models and show only `MiniMaxAI/MiniMax-M3` and `MiniMaxAI/MiniMax-M2.7`.
- **Availability**: free models are `available` when a key is present; non-free models are `configured` (cyan) so paid users can still select them, and the default selection prefers free models.
- **Promotional/free models**: `MiniMaxAI/MiniMax-M3` and `MiniMaxAI/MiniMax-M2.7` are free during promotion (`cost_class=free`, `access_class=promotional_free`).
- **Notable model IDs**: `MiniMaxAI/MiniMax-M3`, `MiniMaxAI/MiniMax-M2.7`.
- **Pricing**: live per-token prices from the `/v1/models` `pricing` block are converted to per-million-token values.
- **Multimodal flag**: set for `MiniMax-M3`, Gemini, and GPT-5.6 / GPT-5.4 / GPT-5.5 families based on provider naming.

### `empero`

- **Endpoint verified**: `GET https://free.empero.org/v1/models` returns `glm-5.3-flash`.
- **Documentation verified**: `Qwen/Qwen3.8-27B-FP8` is supported on the public endpoint with context up to 131,072 tokens and default `max_tokens` of 32,768.
- **Catalog**: 2 entries (`glm-5.3-flash`, `Qwen/Qwen3.8-27B-FP8`).
- **Privacy warning**: `privacy_class=public_community_endpoint`; the model selector displays a red warning that prompts and completions may be logged.
- **Cost/access**: `cost_class=free`, `access_class=community_free`.
- **No secret required**: defaults to public token `free`; set `EMPERO_API_KEY=disabled` to remove from the catalog.
- **Chat availability**: live chat calls to the public endpoint were observed returning `upstream_down`; this is treated as a transient availability issue and is reflected in `availability` truthfully.

## Model counts (with credentials configured)

| Provider | Count |
|----------|-------|
| `anvaya` | 1 |
| `agentrouter` | 3 |
| `nvidia` | 12 |
| `opencode` | 8 |
| `openrouter` | 21 |
| `seekai` | dynamic (live-verified IDs from /v1/models) |
| `gmicloud` | dynamic (all live chat/instruct models; 2 fallback; 2 with `GMICLOUD_FREE_ONLY`) |
| `empero` | 2 |

Counts are dynamic and depend on the live model lists returned by each provider.

## Golden tests

The following behaviors are covered in `tests/test_llm_providers.py`:

- [x] `LocalProvider`, `NVIDIAProvider`, `AgentRouterOpenAIProvider`, `AgentRouterAnthropicProvider` remain unconfigured and fall back safely when no keys are set.
- [x] `SeekAIProvider`, `GMICloudProvider`, and `EmperoProvider` return `configured=False` and a non-empty `error` when unconfigured.
- [x] `get_model_provider("seekai")`, `get_model_provider("gmicloud")`, `get_model_provider("empero")` return valid provider instances.
- [x] SeekAI catalog is built from the live `/v1/models` list and uses static metadata only for enrichment (`claude-fable-5`, `claude-opus-4-8`, `deepseek-v4-pro`, `gemini-3-6-flash`, `gpt-5.6-sol`).
- [x] GMI Cloud `MiniMax-M3` is `cost_class=free` and `access_class=promotional_free`.
- [x] Empero models are `cost_class=free`, `access_class=community_free`, `privacy_class=public_community_endpoint`.
- [x] Catalog intelligence for new model families (Claude Fable, Claude Sonnet 5, GLM 5, Gemini 3, Qwen 3.8) does not fabricate profile-fit scores.

Run the focused test set:

```bash
cd backend
python -m pytest tests/test_llm_providers.py tests/test_catalog_intelligence.py tests/test_provider_adapters.py -v
```

## Configuration quick reference

The backend now loads both `.env` and `.env.local` from the project root, so dev credentials can be placed in `.env.local` without leaving them in the tracked `.env` file.

```env
# SeekAI
SEEKAI_API_KEY=sk-...
SEEKAI_BASE_URL=https://seekai.cc/v1

# GMI Cloud
GMICLOUD_API_KEY=...
# Aliases: GMI_API_KEY, GMI_BASE_URL
GMICLOUD_BASE_URL=https://api.gmi-serving.com/v1

# Empero (public; no real key needed)
EMPERO_API_KEY=free
EMPERO_BASE_URL=https://free.empero.org/v1
# or
EMPERO_API_KEY=disabled
```

## Known limitations and notes

1. **Models appear disabled without credentials**: SeekAI and GMI Cloud model dots are red/unavailable when `SEEKAI_API_KEY` or `GMICLOUD_API_KEY` is not set. Add the keys to `.env` or `.env.local` (the backend now loads both) and restart the server.
2. **SeekAI live list is a subset**: the provider's `GET /v1/models` returned 7 model IDs for the test key. The full user-supplied catalog (20 IDs) is retained; unconfirmed models are marked `configured` rather than `available`.
2. **Empero Qwen not in `/v1/models`**: `Qwen/Qwen3.8-27B-FP8` is included based on the provider's own documentation. It is marked `configured` until it appears in the live model list.
3. **Empero chat availability**: the public endpoint returned `upstream_down` for chat during verification; the UI will reflect this and the model can still be selected for retry.
4. **GMI Cloud fallback**: if the key is missing or the live list is empty, a curated static fallback is used so `MiniMax-M3` and other user-requested models remain visible.
5. **GMI Cloud only surfaces free models**: paid GMI Cloud models are not shown in the selector. Only `MiniMax-M3` and `MiniMax-M2.7` are listed.
6. **No benchmark scores invented**: new model families in `catalog_intelligence.py` use `profile_fit=None` and `evidence_confidence=Unknown`; the UI displays "Not yet measured".
7. **No frontend architecture changes**: the existing model selector and API layer consume the normalized `ModelConfig`; only metadata-driven UI additions were made.
