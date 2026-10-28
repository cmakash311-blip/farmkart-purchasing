import hashlib, hmac, secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, SessionToken

COOKIE_NAME = 'farmkart_session'

def encode_password(password: str) -> str:
    if len(password) < 12: raise ValueError('Password requires at least 12 characters')
    salt = secrets.token_bytes(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f'scrypt${salt.hex()}${result.hex()}'

def check_password(password: str, encoded: str) -> bool:
    try:
        algo, salt, expected = encoded.split('$')
        if algo != 'scrypt': return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(got.hex(), expected)
    except (ValueError, TypeError): return False

def hash_token(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()

def new_session(db: Session, user: User) -> tuple[str, SessionToken]:
    token = secrets.token_urlsafe(48)
    row = SessionToken(user_id=user.id, token_hash=hash_token(token), csrf_token=secrets.token_urlsafe(28), expires_at=datetime.now(timezone.utc)+timedelta(hours=12))
    db.add(row); db.commit(); db.refresh(row)
    return token, row

def get_session(request: Request, db: Session = Depends(get_db)) -> tuple[User,SessionToken]:
    token = request.cookies.get(COOKIE_NAME,'')
    if not token: raise HTTPException(401, 'Please sign in')
    session = db.scalar(select(SessionToken).where(SessionToken.token_hash==hash_token(token)))
    if not session or session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(401, 'Session expired')
    user = db.get(User, session.user_id)
    if not user or not user.active: raise HTTPException(401, 'User disabled')
    return user, session

def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user, session = get_session(request, db)
    if request.method not in ('GET','HEAD','OPTIONS'):
        csrf = request.headers.get('X-CSRF-Token','')
        if not csrf or not hmac.compare_digest(csrf, session.csrf_token):
            raise HTTPException(403, 'CSRF token required')
    return user

def can_access(user: User, branch_id: int) -> bool:
    return user.role=='OWNER' or user.branch_id==branch_id

def check_branch(user: User, branch_id: int):
    if not can_access(user, branch_id): raise HTTPException(403, 'Not assigned to this factory')

def allow(user: User, *roles: str):
    if user.role not in roles: raise HTTPException(403, 'Insufficient permission')
