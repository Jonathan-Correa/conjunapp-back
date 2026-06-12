from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.domain import AdminUser, Resident, ResidentUser

bearer_scheme = HTTPBearer(auto_error=False)


def _token_from_credentials(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacion requerida.")
    return credentials.credentials


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    token = _token_from_credentials(credentials)
    try:
        payload = decode_access_token(token, "admin")
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
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
        payload = decode_access_token(token, "resident")
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion de residente invalida.")

    user = db.get(ResidentUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Residente inactivo o inexistente.")

    resident = db.scalar(select(Resident).where(Resident.user_id == user.id))
    if resident is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Perfil de residente no encontrado.")
    return resident
