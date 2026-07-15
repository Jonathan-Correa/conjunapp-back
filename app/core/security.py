from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from jose import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

TokenAudience = Literal["admin", "resident"]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    # Bcrypt has a 72-byte limitation, truncate based on bytes not characters
    # This handles multi-byte UTF-8 characters (emoji, special chars, etc.)
    password_bytes = password.encode("utf-8")[:72]
    password_truncated = password_bytes.decode("utf-8", errors="ignore")
    return pwd_context.hash(password_truncated)


def verify_password(password: str, password_hash: str) -> bool:
    # Truncate password to match hashing behavior
    password_bytes = password.encode("utf-8")[:72]
    password_truncated = password_bytes.decode("utf-8", errors="ignore")
    return pwd_context.verify(password_truncated, password_hash)


def create_access_token(subject: UUID, audience: TokenAudience) -> str:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(subject),
        "aud": audience,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, audience: TokenAudience) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        audience=audience,
    )
