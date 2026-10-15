"""Content-blind browser transport for confidential inference.

The browser verifies the runtime and encrypts the request with EHBP before it
reaches the attested confidential API. This service authenticates the Open
WebUI session only to obtain a billing entitlement; it never accepts
chat-completion payloads.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import time
import uuid
from typing import Literal
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from open_webui.utils.auth import get_verified_user_by_token

router = APIRouter()

_CANONICAL_MODEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}/[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256_FINGERPRINT = re.compile(r"^sha256:[A-Za-z0-9_-]{43}$")
_HANDOFF_KID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
# Billing uses the email subject to locate an account. Do not turn a missing
# ORM value into the string "None" and accidentally create a shared subject.
_BILLING_SUBJECT_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}$")
_BILLING_HANDOFF_ISSUER = "https://chat.adverserial.ai"
_BILLING_HANDOFF_AUDIENCE = "https://billing.adverserial.ai"
_BILLING_HANDOFF_TYPE = "adverserial-billing-chat-handoff/v1"
_BILLING_HANDOFF_TTL_SECONDS = 60
_BILLING_HANDOFF_DESTINATIONS = frozenset({"account", "foothold", "hacker_manifesto", "godmod3"})


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
CONFIDENTIAL_ALLOWED_MODELS = _models()

if not CONFIDENTIAL_RECEIPT_AUDIENCE.startswith("https://"):
    raise RuntimeError("CONFIDENTIAL_RECEIPT_AUDIENCE must be an HTTPS audience")
if CONFIDENTIAL_MAX_OUTPUT_TOKENS < 1:
    raise RuntimeError("confidential request limits must be positive")


class EntitlementRequest(BaseModel):
    """The only account data that reaches billing before an encrypted request."""

    model_config = ConfigDict(extra="forbid")

    model: str
    max_input_tokens: int = Field(ge=1, le=1_000_000)
    max_output_tokens: int = Field(ge=1, le=1_000_000)
    endpoint_spki_sha256: str


class BillingHandoffRequest(BaseModel):
    """A fixed billing destination selected by the browser, signed by chat.

    The browser must never choose an arbitrary return URL or carry a reusable
    Open WebUI JWT to billing.  Billing accepts this short-lived assertion once
    and maps the signed destination to its own local route.
    """

    model_config = ConfigDict(extra="forbid")

    destination: Literal["account", "foothold", "hacker_manifesto", "godmod3"] = "account"


class BillingUsageStatus(BaseModel):
    """Content-free membership data rendered in the chat account menu."""

    model_config = ConfigDict(extra="forbid")

    member: bool
    plan: str | None = None
    display_name: str | None = None
    balance_usd: float | None = Field(default=None, ge=0)
    wallet_usd: float | None = Field(default=None, ge=0)
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
    # Old upstream UI code can interpolate a missing localStorage value as
    # `Bearer undefined`. Treat it as absent so the HttpOnly cookie can take
    # over during the migration, rather than turning it into a bogus credential.
    return token if token and token.lower() not in {"undefined", "null"} else None


def _session_token(request: Request) -> str | None:
    return _bearer_token(request.headers.get("authorization")) or request.cookies.get("token")


async def _verified_session(request: Request):
    token = _session_token(request)
    if not token or token.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Sign in with Open WebUI to use confidential inference.")
    user = await get_verified_user_by_token(token, getattr(request.app.state, "redis", None))
    if user is None:
        raise HTTPException(status_code=401, detail="Your Open WebUI session is invalid or expired.")
    return token, user


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_ed25519_seed(value: str) -> bytes:
    """Read exactly the sealed `ed25519:<base64url 32-byte seed>` format."""

    if not value.startswith("ed25519:"):
        raise ValueError("BILLING_HANDOFF_PRIVATE_KEY must use the ed25519: prefix")
    encoded = value.removeprefix("ed25519:")
    if not encoded or not re.fullmatch(r"[A-Za-z0-9_-]+", encoded):
        raise ValueError("BILLING_HANDOFF_PRIVATE_KEY must contain base64url data")
    try:
        seed = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, binascii.Error) as exc:
        raise ValueError("BILLING_HANDOFF_PRIVATE_KEY is not valid base64url") from exc
    if len(seed) != 32:
        raise ValueError("BILLING_HANDOFF_PRIVATE_KEY must contain a 32-byte Ed25519 seed")
    return seed


def _billing_handoff_signer() -> tuple[Ed25519PrivateKey, str]:
    """Load the separate chat-only billing assertion signer without logging it."""

    raw_key = os.getenv("BILLING_HANDOFF_PRIVATE_KEY", "").strip()
    kid = os.getenv("BILLING_HANDOFF_KEY_ID", "").strip()
    if not raw_key or not _HANDOFF_KID.fullmatch(kid):
        raise ValueError("Billing handoff signing is not configured")
    return Ed25519PrivateKey.from_private_bytes(_decode_ed25519_seed(raw_key)), kid


def _mint_billing_handoff(*, email: str, destination: str, now: int | None = None) -> str:
    """Create an independently verifiable, one-time Ed25519 billing assertion."""

    normalized_email = email.strip().lower()
    if len(normalized_email) > 254 or not _BILLING_SUBJECT_EMAIL.fullmatch(normalized_email):
        raise ValueError("A verified email address is required for billing")
    if destination not in _BILLING_HANDOFF_DESTINATIONS:
        raise ValueError("Billing handoff destination is not allowed")
    signer, kid = _billing_handoff_signer()
    issued_at = int(time.time()) if now is None else int(now)
    header = {"alg": "EdDSA", "kid": kid, "typ": "JWT"}
    claims = {
        "iss": _BILLING_HANDOFF_ISSUER,
        "aud": _BILLING_HANDOFF_AUDIENCE,
        "typ": _BILLING_HANDOFF_TYPE,
        "sub": normalized_email,
        "jti": str(uuid.uuid4()),
        "iat": issued_at,
        "exp": issued_at + _BILLING_HANDOFF_TTL_SECONDS,
        "destination": destination,
    }
    encoded_header = _base64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_claims = _base64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    return f"{encoded_header}.{encoded_claims}.{_base64url(signer.sign(signing_input))}"


def _is_allowed_model(model: str) -> bool:
    return model in CONFIDENTIAL_ALLOWED_MODELS


@router.get("/config")
async def confidential_config(request: Request):
    """Expose public endpoint policy required by the browser SDK.

    This endpoint contains no credential, private key, or model prompt.  It is
    session gated so deployments do not advertise the confidential endpoint configuration to
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
        # A non-member can still hold prepaid wallet credit. Keep that narrow
        # account display available without exposing any billing identifiers.
        return status.model_dump(include={"member", "balance_usd", "wallet_usd"}, exclude_none=True)
    if not status.plan or not status.display_name:
        raise HTTPException(status_code=502, detail="Billing returned an incomplete membership status.")
    return status.model_dump(exclude_none=True)


@router.post("/billing-handoff")
async def issue_billing_handoff(payload: BillingHandoffRequest, request: Request):
    """Mint a short-lived, one-time login assertion for the billing origin.

    This endpoint is deliberately same-origin and cookie-authenticated in the
    browser.  The response is a signed assertion only; no Open WebUI session
    JWT, prompt, completion, or arbitrary redirect reaches billing.
    """

    _token, user = await _verified_session(request)
    try:
        email = getattr(user, "email", None)
        if not isinstance(email, str):
            raise ValueError("A verified email address is required for billing")
        handoff = _mint_billing_handoff(email=email, destination=payload.destination)
    except ValueError as exc:
        # Configuration errors must fail closed, but never disclose key format
        # details or material to a browser client.
        raise HTTPException(status_code=503, detail="Secure billing handoff is unavailable.") from exc
    return {"handoff": handoff, "expires_in": _BILLING_HANDOFF_TTL_SECONDS}


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
