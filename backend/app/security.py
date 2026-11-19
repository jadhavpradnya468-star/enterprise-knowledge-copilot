import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import User


def hash_key(key: str) -> str:
    # API keys are high-entropy random strings, so a plain SHA-256 is adequate for lookup.
    return hashlib.sha256(key.encode()).hexdigest()


def bootstrap_users(db: Session, settings: Settings) -> None:
    keys = settings.parsed_api_keys()
    if settings.app_env == "production" and any(k == "demo-key" for k in keys.values()):
        raise RuntimeError("Refusing to start in production with the default demo API key.")
    for name, key in keys.items():
        uid = f"user_{name}"
        user = db.get(User, uid)
        if user is None:
            db.add(User(id=uid, name=name, api_key_hash=hash_key(key)))
        else:
            user.api_key_hash = hash_key(key)
    db.commit()
