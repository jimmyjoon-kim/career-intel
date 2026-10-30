import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Profile, User
from ..schemas import LoginIn, SignupIn, TokenOut
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

WINDOW = 15 * 60
_fails: dict[str, deque] = {}


def _recent(key: str) -> deque:
    q = _fails.setdefault(key, deque())
    while q and q[0] < time.time() - WINDOW:
        q.popleft()
    return q


def _locked(email: str) -> bool:
    n = get_settings().login_max_failures
    return len(_recent(email)) >= n or len(_recent("*")) >= n * 10


def _fail(email: str) -> None:
    now = time.time()
    _recent(email).append(now)
    _recent("*").append(now)


def signup_open(db: Session) -> bool:
    return get_settings().allow_signup or db.scalar(select(func.count(User.id))) == 0


@router.get("/config")
def auth_config(db: Session = Depends(get_db)):
    return {"signup_open": signup_open(db)}


def user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "is_admin": u.is_admin}


@router.post("/signup", response_model=TokenOut)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if not signup_open(db):
        raise HTTPException(403, "Sign-up is closed. Ask the administrator for an account.")
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, "An account with this email already exists")
    is_first = db.scalar(select(func.count(User.id))) == 0
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        name=body.name.strip(),
        is_admin=is_first or email in get_settings().admin_email_set,
    )
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    db.commit()
    return {"token": create_token(user.id), "user": user_dict(user)}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if _locked(email):
        raise HTTPException(429, "Too many failed sign-in attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or not verify_password(body.password, user.password_hash):
        _fail(email)
        raise HTTPException(401, "Incorrect email or password")
    _recent(email).clear()
    return {"token": create_token(user.id), "user": user_dict(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)
