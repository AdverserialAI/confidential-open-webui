# Adverserial Confidential Open WebUI

A confidential-only, browser-local fork of [Open WebUI](https://github.com/open-webui/open-webui). It retains Open WebUI's original license and attribution; see [UPSTREAM.md](./UPSTREAM.md).

## Confidential-only runtime surface

This distribution intentionally does **not** mount Open WebUI's normal plaintext completion, chat-history, file, retrieval, tool, pipeline, memory, automation, WebSocket, or OpenAI/Ollama routes.

The active client:

1. verifies the published model policy, TEE evidence, GPU evidence, and attested EHBP key in the browser;
2. obtains a short-lived entitlement from billing without including the prompt;
3. encrypts the prompt to the attested runtime;
4. sends only ciphertext and the entitlement through the relay; and
5. verifies the signed inference receipt in the browser.

The server does not receive an Open WebUI chat transcript through this path. Conversations are persisted only in the browser's IndexedDB database, `adverserial-confidential-chat`, scoped by account ID and local conversation ID. Selecting **Delete local conversation** removes that record.

**Temporary Chat** keeps a conversation in memory for the current tab only: it never creates or updates an IndexedDB transcript. Turn Temporary Chat off, or choose **Save locally**, to persist the current conversation in that same browser-only IndexedDB store. Neither action sends the transcript to the Open WebUI database.

## Verification UI

The familiar Open WebUI composer includes **Verification preview** beside the model selector. It opens an explanation of the browser-side proof sequence: policy and release provenance, a fresh nonce-bound hardware receipt, signature/freshness checks, and the recipient-key binding. The persistent **VERIFY** control opens the right-side **Verification Center**. Its Runtime, Data is encrypted, and Code is auditable modules show `Pending` until the browser has validated current evidence; the interface never treats an unavailable or failed proof as verified.


Authentication remains server-backed so a user can sign in (including OAuth/Google where configured) and obtain a billing entitlement. Account/session data, model access, token reservations, and count-only billing events are outside the local transcript and are documented in [`docs/SECURITY_BOUNDARY.md`](./docs/SECURITY_BOUNDARY.md).

## Run it

Start from the normal Open WebUI deployment instructions, then configure the confidential backend variables documented in [`docs/CONFIDENTIAL_OPENWEBUI.md`](./docs/CONFIDENTIAL_OPENWEBUI.md). Do not add OpenAI, Ollama, file, retrieval, tool, or standard chat route configuration to this distribution.

## Verify a hosted release

A production build should set `RELEASE_TAG`, `RELEASE_COMMIT`, and `RELEASE_REPOSITORY`. The CI workflow emits a `release.json`, checksum, and GitHub build provenance attestation for every `v*` tag. The running client displays that pinned release in its interface. A deployment should serve the `release.json` built by the tagged workflow and must match the release asset on GitHub.

## Security reporting

Please report security vulnerabilities directly to [security@adverserial.ai](mailto:security@adverserial.ai).
