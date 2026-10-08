# Route allow-list

The public upstream history intentionally remains available for license and audit context. It is not the deployed confidential runtime surface.

`ConfidentialOnlyMiddleware` is outermost in `backend/open_webui/main.py`. It rejects all API paths except:

- session/authentication: `/api/v1/auths/*`, `/api/v1/users/*`;
- configuration/model discovery: `/api/config`, `/api/version`, `/api/models`, `/api/v1/models`, `/api/v1/configs/*`;
- the verified confidential client: `/api/v1/confidential/*`; and
- health checks.

It blocks standard `/openai`, `/ollama`, `/api/chat/completions`, `/api/v1/chat/completions`, chat records, uploads, retrieval, tools, functions, prompts, skills, memories, tasks, automations, calendars and WebSockets before a body is consumed. The Svelte route tree also contains no standard Chat or Playground component.
