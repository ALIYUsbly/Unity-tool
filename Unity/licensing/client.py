import hashlib
import json
import os
import platform
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERIFY_URL = "https://aliyusbly.eu.pythonanywhere.com/api/license/verify"

# Ed25519 public key for this server's signing key (base64, 32 raw bytes).
# Safe to be public — it can only verify grants, never create or forge one.
# Must match the UNITY_GRANT_SIGNING_KEY private key set on the server.
_SERVER_PUBLIC_KEY_B64 = "Eu7d/jz2FXfD5OFZPZMbyZf6orpnykTO0qKgWyoij/I="

_last_grant = None


def get_hwid():
    raw = f"{platform.node()}-{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def digest(key):
    normalized = key.strip().upper() if isinstance(key, str) else ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def config_dir():
    p = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Unity"
    p.mkdir(parents=True, exist_ok=True)
    try:
        p.chmod(0o700)
    except OSError:
        pass
    return p


def key_path():
    return config_dir() / "license.json"


def cache_path():
    return config_dir() / "license_cache.json"


def load_saved_key():
    try:
        data = json.loads(key_path().read_text(encoding="utf-8"))
        return data.get("key") if isinstance(data.get("key"), str) else ""
    except (OSError, ValueError):
        return ""


def save_key(key):
    p = key_path()
    p.write_text(json.dumps({"key": key.strip()}), encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def clear_key():
    try:
        key_path().unlink()
    except FileNotFoundError:
        pass


def server_check(key, hwid):
    import urllib.request

    body = json.dumps({"key": key, "hwid": hwid}).encode("utf-8")
    req = urllib.request.Request(
        VERIFY_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_grant_signature(grant):
    if not isinstance(grant, dict):
        return False
    sig_b64 = grant.get("sig")
    if not isinstance(sig_b64, str):
        return False
    body = {k: v for k, v in grant.items() if k != "sig"}
    try:
        import base64

        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(_SERVER_PUBLIC_KEY_B64)
        )
        public_key.verify(base64.b64decode(sig_b64), _canonical_json(body))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _grant_matches(grant, key, hwid):
    return (
        isinstance(grant, dict)
        and grant.get("key_hash") == digest(key)
        and grant.get("hwid") == hwid
    )


def _grant_not_expired(grant):
    try:
        expires = datetime.fromisoformat(grant["expires_at"])
    except (KeyError, ValueError, TypeError):
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < expires


def _write_cache(grant):
    p = cache_path()
    p.write_text(json.dumps(grant), encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def _read_cache():
    try:
        return json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def current_grant():
    """The most recently verified grant in this process (online or cached
    offline). Populated by validate()/require_license(). Carries tier,
    credits, and the full tabs/operations rule set — nothing else needs a
    second network round trip to build access control from it."""
    return _last_grant


def validate(key):
    global _last_grant
    key = (key or "").strip()

    if not key:
        return False, None, "missing_key"

    hwid = get_hwid()

    try:
        result = server_check(key, hwid)
    except Exception as exc:
        cached = _read_cache()
        if (
            cached
            and _verify_grant_signature(cached)
            and _grant_matches(cached, key, hwid)
            and _grant_not_expired(cached)
        ):
            cached = dict(cached, source="offline_grace")
            _last_grant = cached
            return True, cached.get("tier", "standard"), "offline_grace"
        return False, None, f"server_unreachable: {exc}"

    if result.get("valid") is True:
        grant = result.get("grant")
        # The signature is checked even on a response that arrived over a
        # "successful" connection: a MITM that merely returns valid=True
        # without the server's private key cannot forge a grant that
        # verifies, so this also protects the online path, not just offline.
        if not _verify_grant_signature(grant) or not _grant_matches(grant, key, hwid):
            return False, None, "invalid_server_response"
        _write_cache(grant)
        grant = dict(grant, source="online")
        _last_grant = grant
        return True, grant.get("tier", "standard"), "online"

    # A server rejection overrides any previous offline approval.
    return False, None, result.get("reason", "license_rejected")


def require_license():
    key = load_saved_key()

    if not key:
        return False, None, "activation_required"

    return validate(key)
