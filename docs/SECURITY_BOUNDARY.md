# Security boundary

## What never receives plaintext conversation text

The browser-local confidential client does not call Open WebUI's standard chat APIs. The ASGI allow-list rejects them before request bodies are read. The only inference path is the browser-direct EHBP endpoint at the attested API after browser-side runtime verification. The Open WebUI backend does not accept inference envelopes.

The Open WebUI database is used for authentication/session state and model access. It does not receive confidential conversation records. The browser saves text-only conversation records in IndexedDB under `adverserial-confidential-chat`; this is the sole transcript store implemented by this distribution.

## What other services can receive

Billing can receive the authenticated account, selected model, token bounds, entitlement identifier, reservation/settlement state, and signed count-only meter event. It does not receive the prompt or completion through the confidential flow.

The attested runtime receives the encrypted prompt and produces an encrypted response and signed receipt. The client independently verifies the receipt against the policy's receipt keys.

## Release provenance

A tagged build injects `/release.json` containing the immutable repository, tag, source commit and source-tree identifier. GitHub Actions attaches build provenance to the release artifact. The release manifest is a provenance assertion, not a substitute for verifying runtime hardware evidence; the browser verifies both independently.
