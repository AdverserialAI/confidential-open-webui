"""Content-blind browser transport for confidential inference.

The browser verifies the runtime and encrypts the request with EHBP before it
reaches this router.  This service authenticates the Open WebUI session only
to obtain a billing entitlement, then relays ciphertext and the entitlement to
the configured confidential API.  It never accepts plaintext chat-completion
payloads on this route and deliberately does not log request or response
bodies.
"""

from __future__ import annotations

import os
import re
from typing import AsyncIterator
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from open_webui.utils.auth import get_verified_user_by_token

router = APIRouter()

_CANONICAL_MODEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}/[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256_FINGERPRINT = re.compile(r"^sha256:[A-Za-z0-9_-]{43}$")
_FORWARDED_REQUEST_HEADERS = frozenset(
    {
        "accept",
        "authorization",
        "content-type",
        "ehbp-encapsulated-key",
        "x-adverserial-nonce",
    }
)
_FORWARDED_RESPONSE_HEADERS = frozenset(
    {"content-type", "ehbp-response-nonce", "x-adverserial-receipt", "content-length"}
)


def _https_url(name: str, default: str, *, required_path: str | None = None) -> str:
    value = os.getenv(name, default).strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.params or parsed.query or parsed.fragment:
        raise RuntimeError(f"{name} must be an HTTPS URL without query or fragment")
    if required_path and parsed.path.rstrip("/") != required_path:
        raise RuntimeError(f"{name} must use the {required_path} path")
    return value.rstrip("/")


def _models() -> tuple[str, ...]:
    configured = os.getenv("CONFIDENTIAL_ALLOWED_MODELS", "lordx64/cyberglm")
    values = tuple(value.strip() for value in configured.split(",") if value.strip())
    if not values or any(not _CANONICAL_MODEL.fullmatch(value) for value in values):
        raise RuntimeError("CONFIDENTIAL_ALLOWED_MODELS must contain canonical publisher/model IDs")
    return values


CONFIDENTIAL_API_BASE_URL = _https_url(
    "CONFIDENTIAL_API_BASE_URL", "https://api.adverserial.ai/v1", required_path="/v1"
)
CONFIDENTIAL_ATTESTATION_URL = _https_url(
    "CONFIDENTIAL_ATTESTATION_URL", "https://api.adverserial.ai/attestation"
)
CONFIDENTIAL_POLICY_URL = _https_url(
    "CONFIDENTIAL_POLICY_URL", "https://verify.adverserial.ai/policies/production.json"
)
CONFIDENTIAL_BILLING_BASE_URL = _https_url(
    "CONFIDENTIAL_BILLING_BASE_URL", "https://billing.adverserial.ai"
)
CONFIDENTIAL_RECEIPT_ISSUER = _https_url(
    "CONFIDENTIAL_RECEIPT_ISSUER", "https://verify.adverserial.ai"
)
CONFIDENTIAL_RECEIPT_AUDIENCE = os.getenv("CONFIDENTIAL_RECEIPT_AUDIENCE", "https://chat.adverserial.ai").strip()
CONFIDENTIAL_MAX_OUTPUT_TOKENS = int(os.getenv("CONFIDENTIAL_MAX_OUTPUT_TOKENS", "65536"))
CONFIDENTIAL_MAX_CIPHERTEXT_BYTES = int(os.getenv("CONFIDENTIAL_MAX_CIPHERTEXT_BYTES", str(16 * 1024 * 1024)))
CONFIDENTIAL_ALLOWED_MODELS = _models()

if not CONFIDENTIAL_RECEIPT_AUDIENCE.startswith("https://"):
    raise RuntimeError("CONFIDENTIAL_RECEIPT_AUDIENCE must be an HTTPS audience")
if CONFIDENTIAL_MAX_OUTPUT_TOKENS < 1 or CONFIDENTIAL_MAX_CIPHERTEXT_BYTES < 1:
    raise RuntimeError("confidential request limits must be positive")


class EntitlementRequest(BaseModel):
    """The only account data that reaches billing before an encrypted request."""

    model_config = ConfigDict(extra="forbid")

    model: str
    max_input_tokens: int = Field(ge=1, le=1_000_000)
    max_output_tokens: int = Field(ge=1, le=1_000_000)
    endpoint_spki_sha256: str


class BillingUsageStatus(BaseModel):
    """Content-free membership data rendered in the chat account menu."""

    model_config = ConfigDict(extra="forbid")

    member: bool
    plan: str | None = None
    display_name: str | None = None
    credit_day_used: float | None = Field(default=None, ge=0)
    credit_day_cap: float | None = Field(default=None, gt=0)
    credit_week_used: float | None = Field(default=None, ge=0)
    credit_week_cap: float | None = Field(default=None, gt=0)
    output_day_used: int | None = Field(default=None, ge=0)
    output_day_cap: int | None = Field(default=None, gt=0)
    output_week_used: int | None = Field(default=None, ge=0)
    output_week_cap: int | None = Field(default=None, gt=0)
    daily_reset_at: str | None = None
    weekly_reset_at: str | None = None
    overage_enabled: bool | None = None


def _bearer_token(value: str | None) -> str | None:
    if not value or not value.startswith("Bearer "):
        return None
    token = value.removeprefix("Bearer ").strip()
    return token or None


def _session_token(request: Request, *, relay: bool = False) -> str | None:
    # Relay requests reserve Authorization for the signed one-use entitlement.
    # The Open WebUI session therefore travels in a separate, same-origin-only
    # header.  The token is consumed locally and is never forwarded upstream.
    header = "x-openwebui-authorization" if relay else "authorization"
    return _bearer_token(request.headers.get(header)) or request.cookies.get("token")


async def _verified_session(request: Request, *, relay: bool = False):
    token = _session_token(request, relay=relay)
    if not token or token.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Sign in with Open WebUI to use confidential inference.")
    user = await get_verified_user_by_token(token, getattr(request.app.state, "redis", None))
    if user is None:
        raise HTTPException(status_code=401, detail="Your Open WebUI session is invalid or expired.")
    return token, user


def _is_allowed_model(model: str) -> bool:
    return model in CONFIDENTIAL_ALLOWED_MODELS


@router.get("/config")
async def confidential_config(request: Request):
    """Expose public endpoint policy required by the browser SDK.

    This endpoint contains no credential, private key, or model prompt.  It is
    session gated so deployments do not advertise a relay configuration to
    anonymous callers.
    """

    await _verified_session(request)
    return {
        "version": 1,
        "api_base_url": CONFIDENTIAL_API_BASE_URL,
        "attestation_url": CONFIDENTIAL_ATTESTATION_URL,
        "policy_url": CONFIDENTIAL_POLICY_URL,
        "billing_base_url": CONFIDENTIAL_BILLING_BASE_URL,
        "receipt_issuer": CONFIDENTIAL_RECEIPT_ISSUER,
        "receipt_audience": CONFIDENTIAL_RECEIPT_AUDIENCE,
        "max_output_tokens": CONFIDENTIAL_MAX_OUTPUT_TOKENS,
        "models": [{"id": model} for model in CONFIDENTIAL_ALLOWED_MODELS],
    }


@router.get("/account")
async def confidential_account_status(request: Request):
    """Return a narrow, content-free membership snapshot for the signed-in user.

    Billing remains the source of truth. This service proxies only the plan and
    count-only allowance totals required by the local account menu; prompts,
    completions, and transcript identifiers are never requested or returned.
    """

    token, _user = await _verified_session(request)
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0), trust_env=False) as client:
        response = await client.get(
            f"{CONFIDENTIAL_BILLING_BASE_URL}/account/usage-status",
            headers={"authorization": f"Bearer {token}", "accept": "application/json"},
        )

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Billing could not verify your account session.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Billing account status is unavailable.")
    if "application/json" not in response.headers.get("content-type", ""):
        raise HTTPException(status_code=502, detail="Billing returned an invalid account status.")
    try:
        status = BillingUsageStatus.model_validate(response.json())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Billing returned an invalid account status.") from exc
    if not status.member:
        return {"member": False}
    if not status.plan or not status.display_name:
        raise HTTPException(status_code=502, detail="Billing returned an incomplete membership status.")
    return status.model_dump(exclude_none=True)


@router.post("/entitlements")
async def issue_entitlement(payload: EntitlementRequest, request: Request):
    """Exchange the authenticated Google/Open WebUI session for one entitlement.

    Billing independently validates this Open WebUI JWT against the same
    identity service.  Neither a prompt nor a model response is part of the
    request to billing.
    """

    token, _user = await _verified_session(request)
    if not _is_allowed_model(payload.model) or not _CANONICAL_MODEL.fullmatch(payload.model):
        raise HTTPException(status_code=400, detail="Unknown confidential model.")
    if payload.max_output_tokens > CONFIDENTIAL_MAX_OUTPUT_TOKENS:
        raise HTTPException(status_code=400, detail="Requested output limit exceeds this confidential client policy.")
    if not _SHA256_FINGERPRINT.fullmatch(payload.endpoint_spki_sha256):
        raise HTTPException(status_code=400, detail="A verified endpoint TLS fingerprint is required.")

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0), trust_env=False) as client:
        response = await client.post(
            f"{CONFIDENTIAL_BILLING_BASE_URL}/cc/entitlements",
            headers={
                "authorization": f"Bearer {token}",
                "accept": "application/json",
                "content-type": "application/json",
            },
            json=payload.model_dump(),
        )

    content_type = response.headers.get("content-type", "application/json")
    if response.status_code >= 400:
        # Billing's response contains an account/budget error only.  Do not add
        # Open WebUI request metadata or any content to it.
        try:
            body = response.json()
        except ValueError:
            body = {"detail": "Billing returned an invalid entitlement response."}
        return JSONResponse(status_code=response.status_code, content=body)
    if "application/json" not in content_type:
        raise HTTPException(status_code=502, detail="Billing returned an invalid entitlement response.")
    try:
        return JSONResponse(status_code=response.status_code, content=response.json())
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Billing returned an invalid entitlement response.") from exc


def _relay_headers(request: Request) -> dict[str, str]:
    return {
        name: value
        for name, value in request.headers.items()
        if name.lower() in _FORWARDED_REQUEST_HEADERS
    }


def _response_headers(headers: httpx.Headers) -> dict[str, str]:
    result = {"cache-control": "no-store", "x-content-type-options": "nosniff"}
    for name, value in headers.items():
        if name.lower() in _FORWARDED_RESPONSE_HEADERS:
            result[name] = value
    return result


async def _relay_stream(response: httpx.Response, client: httpx.AsyncClient) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_raw():
            yield chunk
    finally:
        await response.aclose()
        await client.aclose()


@router.post("/relay/chat/completions")
async def relay_ciphertext(request: Request):
    """Forward an EHBP envelope without accessing its encrypted content."""

    await _verified_session(request, relay=True)
    if not request.headers.get("ehbp-encapsulated-key"):
        raise HTTPException(status_code=400, detail="Confidential relay requires an EHBP encrypted request.")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > CONFIDENTIAL_MAX_CIPHERTEXT_BYTES:
                raise HTTPException(status_code=413, detail="Encrypted request exceeds the confidential relay limit.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid encrypted request length.") from exc

    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0), trust_env=False)
    upstream_request = client.build_request(
        "POST",
        f"{CONFIDENTIAL_API_BASE_URL}/chat/completions",
        headers=_relay_headers(request),
        content=request.stream(),
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="Confidential endpoint is unavailable.") from exc

    return StreamingResponse(
        _relay_stream(upstream, client),
        status_code=upstream.status_code,
        headers=_response_headers(upstream.headers),
    )
