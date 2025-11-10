from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlmodel import Session, select

from .database import get_session
from .models import Activity, ActivityEntityType, Store, User, UserRole
from .settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(settings.secret_key)
SESSION_COOKIE_NAME = "vape_crm_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_session_cookie(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id, "issued_at": datetime.utcnow().isoformat()})


def load_session_cookie(cookie_value: str) -> Optional[dict]:
    try:
        return serializer.loads(cookie_value, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None


async def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    payload = load_session_cookie(cookie)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = session.get(User, payload["user_id"])
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def require_roles(*roles: UserRole):
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role == UserRole.ADMIN:
            return current_user
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return current_user

    return dependency


def authenticate_user(email: str, password: str, session: Session) -> Optional[User]:
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def record_activity(
    session: Session,
    *,
    actor: Optional[User],
    entity_type: ActivityEntityType,
    entity_id: int,
    action: str,
    metadata: Optional[str] = None,
) -> Activity:
    activity = Activity(
        actor_user_id=actor.id if actor else None,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        details=metadata,
    )
    session.add(activity)
    session.commit()
    session.refresh(activity)
    return activity


def can_access_store(user: User, store: Store) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.SALESMAN and store.owner_user_id == user.id:
        return True
    if user.role == UserRole.SUBSALESMAN and store.sub_owner_user_id == user.id:
        return True
    if user.role == UserRole.CLIENT and store.id and store.owner_user_id == user.id:
        return True
    return False
