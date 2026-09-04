---
trigger: always_on
---
# Rule 03 — Integration Tracing

Whenever implementing or changing an integration, document:

```text
CALLER
ENTRYPOINT
REQUEST
VALIDATION
AUTH
TRANSPORT
TARGET
TRANSFORMATION
RESPONSE
ERROR HANDLING
RETRY
TIMEOUT
LOGGING
SECURITY BOUNDARY
DOWNSTREAM CONSUMERS
```

Never document only the API endpoint. Place the trace in `.anvaya/knowledge/13_API_AND_EXTERNAL_INTEGRATIONS.md` or a feature-specific file, and update `04_INTEGRATION_GRAPH.md`.
