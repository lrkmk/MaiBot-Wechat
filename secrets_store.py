"""Encrypted storage for sensitive per-user credentials (e.g. OAuth tokens
from third-party score-query services like lxns.net).

Separate from storage.py (which holds plain, non-sensitive data like
friend codes) because these are live credentials — leaking them is a much
bigger deal, so they're encrypted at rest.

This is demo-grade: the encryption key lives next to the ciphertext on the
same disk (data/.key), which protects against "someone reads the JSON file
casually" but not against "someone with full filesystem access". A real
deployment should pull the key from a secret manager instead.

Keyed by wechat_user_id (msg.user_id) — same key space as storage.py's
/mai bind — with a `provider` sub-key so one user can have tokens from
multiple services (lxns.net today, maybe others later).
"""

import json
from pathlib import Path

from cryptography.fernet import Fernet

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
KEY_PATH = DATA_DIR / ".key"
STORE_PATH = DATA_DIR / "secrets.enc.json"


def _get_key() -> bytes:
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    KEY_PATH.chmod(0o600)
    return key


_fernet = Fernet(_get_key())


def _load() -> dict:
    if not STORE_PATH.exists():
        return {}
    return json.loads(STORE_PATH.read_text("utf-8"))


def _save(data: dict) -> None:
    STORE_PATH.write_text(json.dumps(data), encoding="utf-8")
    STORE_PATH.chmod(0o600)


async def set_token(wechat_user_id: str, provider: str, fields: dict) -> None:
    data = _load()
    data.setdefault(wechat_user_id, {})[provider] = {
        k: _fernet.encrypt(str(v).encode()).decode() for k, v in fields.items()
    }
    _save(data)


async def get_token(wechat_user_id: str, provider: str) -> dict | None:
    entry = _load().get(wechat_user_id, {}).get(provider)
    if entry is None:
        return None
    return {k: _fernet.decrypt(v.encode()).decode() for k, v in entry.items()}
