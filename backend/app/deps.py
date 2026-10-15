"""Auth & tenancy dependencies. Every query in routers must be filtered by ``user.org_id``."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog, User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)
ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2, "owner": 3}


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from None
    import uuid
    user = db.get(User, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user inactive")
    return user


def require_role(min_role: str):
    def dep(user: User = Depends(current_user)) -> User:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[min_role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role ≥ {min_role}")
        return user
    return dep


def audit(db: Session, user: User | None, action: str, entity_type: str | None = None, entity_id=None, details: dict | None = None,
          request: Request | None = None) -> None:
    db.add(AuditLog(org_id=user.org_id if user else None, user_id=user.id if user else None, action=action, entity_type=entity_type,
                    entity_id=str(entity_id) if entity_id else None, details=details or {},
                    ip_address=request.client.host if request and request.client else None))
