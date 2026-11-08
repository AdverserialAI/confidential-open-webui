"""Email identity contract shared with billing's identity.py.

Never trim, unquote, URL-decode, remove dots/plus tags, or Unicode-normalize an
identity received from an authenticated principal. Reject ambiguous input.
Case folding is limited to the existing case-insensitive account contract.
"""
import re
import unicodedata

_LOCAL = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}\Z", re.ASCII)
_USER_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z', re.ASCII)


def canonical_email(value: str) -> str:
    """Validate a mailbox without repairing whitespace or compatibility aliases."""
    if not isinstance(value, str) or len(value) > 254 or value.count('@') != 1:
        raise ValueError('Invalid account email')
    if any(c.isspace() or unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('Invalid account email')
    if unicodedata.normalize('NFKC', value) != value:
        raise ValueError('Noncanonical account email')
    local, domain = value.split('@')
    safe_local = bool(local) and len(local) <= 64 and all(
        _LOCAL.fullmatch(c) if c.isascii() else unicodedata.category(c)[0] in 'LMN' for c in local
    )
    if not safe_local or local.startswith('.') or local.endswith('.') or '..' in local:
        raise ValueError('Invalid account email')
    if domain != 'localhost' and '.' not in domain:
        raise ValueError('Invalid account email')
    if not all(label and len(label) <= 63 and label[0] != '-' and label[-1] != '-'
               and all(c.isalnum() or c == '-' for c in label) for label in domain.split('.')):
        raise ValueError('Invalid account email')
    return value.lower()


def valid_user_id(value: str) -> bool:
    return isinstance(value, str) and _USER_ID.fullmatch(value) is not None


def valid_identity_email(value: str) -> bool:
    try:
        canonical_email(value)
        return True
    except ValueError:
        return False


def email_claim_is_verified(claims: dict) -> bool:
    """OIDC email_verified is a boolean, never a truthy string."""
    return isinstance(claims, dict) and claims.get('email_verified') is True


def oauth_binding_matches(oauth: dict | None, provider: str, subject: str) -> bool:
    """Email linking must never replace a different immutable provider subject."""
    if not isinstance(oauth, dict) or provider not in oauth:
        return True
    binding = oauth[provider]
    return isinstance(binding, dict) and str(binding.get('sub')) == str(subject)
