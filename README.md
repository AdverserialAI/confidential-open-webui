# Adverserial Confidential Open WebUI

A confidential-only, browser-local fork of [Open WebUI](https://github.com/open-webui/open-webui). It retains Open WebUI's original license and attribution; see [UPSTREAM.md](./UPSTREAM.md).

This repository is the source of the chat application at <https://chat.adverserial.ai>. The inference service it talks to is documented separately: the proxy is [attest-proxy](https://github.com/AdverserialAI/attest-proxy), the deployed composition is in [confidential-infra `deployed/`](https://github.com/AdverserialAI/confidential-infra/tree/main/deployed), and the policy the browser verifies against is published at <https://verify.adverserial.ai/policies/production.json>. The model in production is `adverserial/cyberseek`.

## Confidential-only runtime surface

This distribution intentionally does **not** mount Open WebUI's normal plaintext completion, chat-history, file, retrieval, tool, pipeline, memory, automation, WebSocket, or OpenAI/Ollama routes.

The active client:

1. verifies the published model policy, TEE evidence, GPU evidence, and attested EHBP key in the browser;
2. obtains a short-lived entitlement from billing without including the prompt;
3. encrypts the prompt to the attested runtime;
4. sends only ciphertext and the entitlement directly to the attested API; and
5. verifies the signed inference receipt in the browser.

The server does not receive an Open WebUI chat transcript through this path. Conversations are persisted only in the browser's IndexedDB database, `adverserial-confidential-chat`, scoped by account ID and local conversation ID. Selecting **Delete local conversation** removes that record.

**Temporary Chat** keeps a conversation in memory for the current tab only: it never creates or updates an IndexedDB transcript. Turn Temporary Chat off, or choose **Save locally**, to persist the current conversation in that same browser-only IndexedDB store. Neither action sends the transcript to the Open WebUI database.

## Verification UI

The familiar Open WebUI composer includes **Verification preview** beside the model selector. It opens an explanation of the browser-side proof sequence: policy and release provenance, a fresh nonce-bound hardware receipt, signature/freshness checks, and the recipient-key binding. The persistent **VERIFY** control opens the right-side **Verification Center**. Its Runtime, Data is encrypted, and Code is auditable modules show `Pending` until the browser has validated current evidence; the interface never treats an unavailable or failed proof as verified.


Authentication remains server-backed so a user can sign in and obtain a billing entitlement. On the hosted deployment, sign-in, sign-up, Google login and password reset happen at `accounts.adverserial.ai` (the `ACCOUNTS_GATEWAY` setting, on since 2026-11-24): the accounts service hands the browser to this application with a one-time signed assertion, and this application's own sign-in and sign-up routes answer only that service. With the setting off, which is the default in this source, Open WebUI's own sign-in (including OAuth/Google where configured) is used. Account/session data, model access, token reservations, and count-only billing events are outside the local transcript and are documented in [`docs/SECURITY_BOUNDARY.md`](./docs/SECURITY_BOUNDARY.md).

## Run it

Start from the normal Open WebUI deployment instructions, then configure the confidential backend variables documented in [`docs/CONFIDENTIAL_OPENWEBUI.md`](./docs/CONFIDENTIAL_OPENWEBUI.md). Do not add OpenAI, Ollama, file, retrieval, tool, or standard chat route configuration to this distribution.

## Verify a hosted release

A production build should set `RELEASE_TAG`, `RELEASE_COMMIT`, and `RELEASE_REPOSITORY`. The release workflow emits a `release.json`, checksum, and GitHub build provenance attestation for every `v*` tag. A deployment should serve the `release.json` built by the tagged workflow, and it must match the release asset on GitHub.

**The hosted deployment does not do this yet.** `chat.adverserial.ai` is built from the `main` branch as a container, not from a tagged release archive. Its `/release.json` and `/.well-known/adverserial-build.json` report `"status": "development"`, so the served bundle cannot currently be matched to a tagged release or its provenance attestation. The latest tag is `v0.2.6` (2026-10-09), which is older than the code now on `main`.

## Security reporting

Please report security vulnerabilities directly to [security@adverserial.ai](mailto:security@adverserial.ai).

## Licensing

This repository retains the upstream Open WebUI license and attribution in
[`LICENSE`](./LICENSE). Adverserial does not grant rights beyond the rights
already supplied by that upstream license. Third-party material, where present,
remains under its own terms.
