from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.domain import AdminUser, Resident, ResidentUser

bearer_scheme = HTTPBearer(auto_error=False)


def _token_from_credentials(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacion requerida.")
    token = credentials.credentials.strip()
    # Evita el error comun de pegar "Bearer <jwt>" completo en Authorize de Swagger.
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def _decode_or_401(token: str, audience: str, invalid_detail: str) -> dict:
    try:
        return decode_access_token(token, audience)  # type: ignore[arg-type]
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesion expirada. Vuelve a iniciar sesion.",
        ) from None
    except JWTClaimsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                f"{invalid_detail} "
                "Verifica que el token sea del mismo rol (admin/residente) "
                "y no incluya el prefijo 'Bearer ' duplicado."
            ),
        ) from None
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=invalid_detail) from None


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    token = _token_from_credentials(credentials)
    try:
        payload = _decode_or_401(token, "admin", "Sesion administrativa invalida.")
        user_id = UUID(payload["sub"])
    except HTTPException:
        raise
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion administrativa invalida.")

    user = db.get(AdminUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Administrador inactivo o inexistente.")
    return user


def get_current_resident(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Resident:
    token = _token_from_credentials(credentials)
    try:
        payload = _decode_or_401(token, "resident", "Sesion de residente invalida.")
        user_id = UUID(payload["sub"])
    except HTTPException:
        raise
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion de residente invalida.")

    user = db.get(ResidentUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Residente inactivo o inexistente.")

    resident = db.scalar(select(Resident).where(Resident.user_id == user.id))
    if resident is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Perfil de residente no encontrado.")
    return resident
