"""Routes for sign-in through the accounts service. See utils/accounts_gateway.py for the contract."""

from __future__ import annotations

import json
import logging
import secrets
import unicodedata
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from open_webui.env import REDIS_KEY_PREFIX
from open_webui.internal.db import get_async_session
from open_webui.models.users import Users
from open_webui.routers.auths import create_session_response, signup_handler
from open_webui.utils import accounts_gateway as gateway
from open_webui.utils.auth import invalidate_token, revoke_user_tokens
from open_webui.utils.identity import canonical_email, valid_user_id
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)
router = APIRouter()

MIN_PASSWORD = 10
MAX_PASSWORD_BYTES = 72  # bcrypt ignores anything beyond 72 bytes
_ROLES = frozenset({'user', 'admin'})


def _refuse(error: gateway.Refused) -> HTTPException:
    return HTTPException(status_code=error.status, detail=error.detail)


def _failed_page(status: int) -> HTMLResponse:
    """What a person sees when a handoff is refused. Fixed text; nothing from the request is echoed."""
    target = gateway.accounts_origin() or 'https://accounts.adverserial.ai'
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign-in did not finish</title>'
        '<body style="font:16px/1.5 system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1.5rem">'
        '<h1 style="font-size:1.4rem">Sign-in did not finish</h1>'
        '<p>The sign-in link had expired or was already used. Nothing was changed.</p>'
        f'<p><a href="{target}/sso/chat">Try again</a></p></body></html>',
        status_code=status,
        headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'},
    )


@router.post('/exchange')
async def exchange(request: Request, db: AsyncSession = Depends(get_async_session)):
    """Turn a one-time handoff from the accounts site into this chat's own session cookie."""
    if not gateway.configured():
        raise HTTPException(503, 'Sign-in through your account is not configured.')
    if not gateway.browser_handoff_origin_ok(request):
        raise HTTPException(403, 'Untrusted request origin.')
    try:
        gateway.bounded_length(request)
        body = await request.body()
        if len(body) > gateway.MAX_BODY:
            raise gateway.Refused(413, 'Request too large.')
        token = parse_qs(body.decode('ascii')).get('handoff', [''])[0]
        claims = gateway.verify_handoff(token)
        user = await Users.get_user_by_id(claims['uid'], db=db)
        # The handoff names both the account id and its address; both must still be true here.
        if not user or user.role not in _ROLES or canonical_email(user.email) != claims['email']:
            raise gateway.Refused(401, 'Invalid or expired sign-in.')
        await gateway.consume(getattr(request.app.state, 'redis', None), REDIS_KEY_PREFIX, claims['jti'], claims['exp'])
    except (gateway.Refused, UnicodeError, ValueError) as error:
        return _failed_page(error.status if isinstance(error, gateway.Refused) else 401)

    # Replace, never stack: whatever session this browser had on this chat ends here.
    previous = request.cookies.get('token')
    if previous:
        try:
            await invalidate_token(request, previous)
        except Exception:
            log.warning('accounts gateway: could not end the previous session')
    response = RedirectResponse('/', status_code=303)
    try:
        await create_session_response(request, user, db, response, set_cookie=True, source='accounts')
    except HTTPException:
        return _failed_page(401)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


async def _call(request: Request, action: str) -> dict:
    """The JSON body of one admitted call from the accounts service."""
    try:
        body = await gateway.server_call(request, action, REDIS_KEY_PREFIX)
    except gateway.Refused as error:
        raise _refuse(error) from None
    try:
        data = json.loads(body.decode('utf-8'))
    except (UnicodeError, ValueError):
        raise HTTPException(400, 'Malformed request.') from None
    if not isinstance(data, dict):
        raise HTTPException(400, 'Malformed request.')
    return data


def _email(value) -> str:
    try:
        return canonical_email(value)
    except ValueError:
        raise HTTPException(400, 'Invalid account email') from None


def _name(value, email: str) -> str:
    if not isinstance(value, str):
        value = ''
    value = ' '.join(value.split())
    if any(unicodedata.category(c).startswith('C') for c in value) or len(value) > 80:
        raise HTTPException(400, 'Invalid name.')
    return value or email.split('@')[0]


def _subject(value) -> str:
    # Google's account identifier: digits today; allow a conservative superset, never free text.
    if not isinstance(value, str) or not value or len(value) > 255 or not value.isascii() or not value.replace('-', '').replace('_', '').isalnum():
        raise HTTPException(400, 'Invalid identity.')
    return value


@router.post('/provision')
async def provision(request: Request, db: AsyncSession = Depends(get_async_session)):
    """Create an account the accounts service has already vetted.

    With `password`: the accounts service proved the address by an emailed link and applied its
    password rules. With `google_sub`: Google vouched for the address in a sign-in the accounts
    service verified. Never both, and never an address that already has an account.
    """
    data = await _call(request, 'provision')
    email = _email(data.get('email'))
    name = _name(data.get('name'), email)
    password, subject = data.get('password'), data.get('google_sub')
    if (password is None) == (subject is None):
        raise HTTPException(400, 'Malformed request.')
    if password is not None:
        if not isinstance(password, str) or len(password) < MIN_PASSWORD or len(password.encode()) > MAX_PASSWORD_BYTES:
            raise HTTPException(400, 'Invalid password.')
    else:
        subject = _subject(subject)
        if await Users.get_user_by_oauth_sub('google', subject, db=db):
            raise HTTPException(409, 'That identity already has an account.')
    if await Users.get_user_by_email(email, db=db):
        raise HTTPException(409, 'That address already has an account.')
    if not await Users.has_users(db=db):
        # The first account of an installation becomes its administrator. That one is created by
        # the operator, never by whoever happens to sign up first.
        raise HTTPException(503, 'Not ready.')
    try:
        # A Google account gets a long random password nobody knows; its owner signs in with Google
        # and can set a real password later through the emailed reset link.
        user = await signup_handler(request, email, password if password is not None else secrets.token_urlsafe(48),
                                    name, db=db, source='accounts')
        if subject is not None:
            linked = await Users.update_user_oauth_by_id(user.id, 'google', subject, db=db)
            if not linked:
                # Say so rather than leave an account nobody can sign in to without a reset.
                log.error('accounts gateway: a new account could not be linked to its Google identity')
                raise HTTPException(500, 'The account was created but could not be linked.')
            user = linked
        if user.role not in _ROLES:
            log.warning('accounts gateway: a new account was created with a role that cannot sign in yet')
    except IntegrityError:
        raise HTTPException(409, 'That address already has an account.') from None
    return JSONResponse({'id': user.id, 'email': user.email, 'role': user.role}, headers={'Cache-Control': 'no-store'})


@router.post('/link')
async def link(request: Request, db: AsyncSession = Depends(get_async_session)):
    """Link a Google identity to an account whose owner is signed in at the accounts service."""
    data = await _call(request, 'link')
    uid, subject = data.get('uid'), _subject(data.get('google_sub'))
    if not valid_user_id(uid):
        raise HTTPException(400, 'Malformed request.')
    user = await Users.get_user_by_id(uid, db=db)
    if not user or user.role not in _ROLES:
        raise HTTPException(404, 'No such account.')
    owner = await Users.get_user_by_oauth_sub('google', subject, db=db)
    if owner and owner.id != user.id:
        raise HTTPException(409, 'That identity is linked to another account.')
    bound = (user.oauth or {}).get('google') if isinstance(user.oauth, dict) else None
    if isinstance(bound, dict) and bound.get('sub') is not None and str(bound.get('sub')) != subject:
        # One Google identity per account, and never a silent swap of who can sign in.
        raise HTTPException(409, 'This account is linked to a different identity.')
    await Users.update_user_oauth_by_id(user.id, 'google', subject, db=db)
    return JSONResponse({'id': user.id}, headers={'Cache-Control': 'no-store'})


@router.post('/revoke')
async def revoke(request: Request):
    """End every chat session of an account, for example after its password was reset."""
    data = await _call(request, 'revoke')
    uid = data.get('uid')
    if not valid_user_id(uid):
        raise HTTPException(400, 'Malformed request.')
    await revoke_user_tokens(request, uid)
    return JSONResponse({'ok': True}, headers={'Cache-Control': 'no-store'})
