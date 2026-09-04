# ANVAYA — Model Providers

## Design

`ModelProvider` is a provider-neutral interface that normalizes every LLM call into a `NormalizedModelResponse`. The abstraction is in `backend/anvaya/llm/providers.py`.

```python
class ModelProvider(Protocol):
    name: str

    def configured(self) -> bool: ...
    def healthy(self) -> bool: ...
    def availability(self) -> Literal["available", "configured", "unavailable", "unknown"]: ...
    def supports_capability(self, capability: str) -> bool: ...
    def chat_completion(self, messages, *, stream=False, **kwargs) -> NormalizedModelResponse | Iterator[NormalizedModelResponse]: ...
    def to_dict(self) -> dict[str, Any]: ...
```

## Providers

### `LocalProvider` (`anvaya`)

A deterministic, no-API-key fallback that always returns a safe response. It is used:

- When no external API is configured.
- When the requested model is unavailable.
- When the `ModelPlanner` is not needed.

It supports `chat`, `tools`, and `structured_output`. Streaming yields the message text in one chunk.

### `NVIDIAProvider` (`nvidia`)

Targets NVIDIA NIM / build endpoints. Configure with:

```env
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL_NAME=meta/llama-3.1-70b-instruct
NVIDIA_API_KEY=nvapi-...
```

- Supports chat and function-calling.
- Supports structured JSON output.
- Tool-call extraction via the `tool_calls` field.
- Falls back to `LocalProvider` if the key or base URL is missing.

### `OpenAIProvider` (`openai`)

Targets OpenAI-compatible endpoints, including `OPENAI_BASE_URL` for local proxies. Configure with:

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
```

### `SeekAIProvider` (`seekai`)

OpenAI-compatible gateway at `https://seekai.cc/v1`. It routes user-provided model IDs to the underlying maker APIs (e.g., Anthropic, OpenAI, DeepSeek, Z AI).

```env
SEEKAI_API_KEY=sk-...
SEEKAI_BASE_URL=https://seekai.cc/v1
```

- The live `GET /v1/models` response is the source of truth. Static metadata is used to enrich display names, pricing, and capabilities for IDs the live endpoint confirms are reachable.
- Streaming, tools, and reasoning are enabled for all catalog entries.
- Non-live static model IDs are not surfaced, so stale or duplicate IDs such as `gpt-5-6-luna` / `gpt-5.6-luna` no longer appear in the selector.

### `GMICloudProvider` (`gmicloud`)

OpenAI-compatible inference gateway at `https://api.gmi-serving.com/v1`.

```env
GMICLOUD_API_KEY=...
GMICLOUD_BASE_URL=https://api.gmi-serving.com/v1
```

- Catalog is discovered live from `GET /v1/models`.
- When a key is configured, all chat/instruct models returned by the live endpoint are exposed. Free models are `available`; paid models are `configured` (cyan).
- Set `GMICLOUD_FREE_ONLY=true` (or `GMI_FREE_ONLY=true`) to hide paid models and show only the promotional/free `MiniMaxAI/MiniMax-M3` and `MiniMaxAI/MiniMax-M2.7` models.
- Falls back to a curated static catalog of promotional/free `MiniMaxAI/MiniMax-M3` and `MiniMaxAI/MiniMax-M2.7` models when no key is configured.

### `EmperoProvider` (`empero`)

OpenAI-compatible public community endpoint at `https://free.empero.org/v1`.

```env
EMPERO_API_KEY=free
EMPERO_BASE_URL=https://free.empero.org/v1
```

- No user secret required; defaults to the public `free` token.
- All models are `cost_class=free`, `access_class=community_free`, and `privacy_class=public_community_endpoint`.
- The model selector warns that prompts and completions are logged.
- Set `EMPERO_API_KEY=disabled` to hide the catalog and prevent any calls.

### `LyzrProvider` (`lyzr`)

Reserved for Lyzr agent-platform orchestration. Configure with `LYZR_API_KEY`.

## Capability gating

A model's `capabilities` list is compared with the required capabilities from the active profile or planner. If a capability is missing (e.g., `streaming` or `tools`), the orchestrator rejects the model and picks the local fallback.

## Selection

`select_model_provider_for_profile(profile, models)` returns:

- The best available model from the registry.
- The matching `ModelProvider` instance.
- A human-readable `selection_note` explaining why the model was chosen.

The current default without external credentials is:

- Model: `anvaya-local-orchestrator`
- Provider: `LocalProvider`
- Note: `No LLM credentials configured; using local orchestrator`

## Registry

Models are declared in `backend/anvaya/agent/profiles.py::default_models()`. Each `ModelConfig` records:

- `id`, `provider`, `model`, `display_name`
- `capabilities` and boolean feature flags
- `context_window`
- `recommended_for` (profile IDs)
- `cost_class`, `latency_class`, `risk_class`
- `default_temperature`

The `/api/v1/agent/models` endpoint returns this list with `configured` / `healthy` / `availability` computed at request time.

Additional metadata added for gateway and community providers:

- `provider_model_id`: exact executable model ID at the gateway.
- `pricing_mode`: `per_token` or `per_request`.
- `cost_per_request`: set for `per_request` pricing.
- `access_class`: `standard`, `native_free`, `promotional_free`, `community_free`.
- `privacy_class`: `standard` or `public_community_endpoint`.
- `gateway_type`: `aggregator`, `inference gateway`, `community endpoint`.
- `aliases`: alternate model IDs for the same underlying model.
