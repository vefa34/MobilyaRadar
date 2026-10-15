from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import audit, current_user, require_role
from app.models import Organization, User
from app.schemas import InviteIn, LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "email already registered")
    org = Organization(name=body.organization_name)
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password), role="owner")
    db.add(user)
    db.flush()
    audit(db, user, "auth.register", "organization", org.id, request=request)
    db.commit()
    return TokenOut(access_token=create_access_token(str(user.id), str(org.id), user.role), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash) or not user.is_active:
        raise HTTPException(401, "invalid credentials")
    audit(db, user, "auth.login", request=request)
    db.commit()
    return TokenOut(access_token=create_access_token(str(user.id), str(user.org_id), user.role), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/users", response_model=UserOut)
def invite(body: InviteIn, request: Request, user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "email already registered")
    u = User(org_id=user.org_id, email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.flush()
    audit(db, user, "user.create", "user", u.id, {"role": body.role}, request)
    db.commit()
    return u


@router.get("/users", response_model=list[UserOut])
def list_users(user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return db.scalars(select(User).where(User.org_id == user.org_id)).all()
