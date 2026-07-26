from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.security import create_access_token, hash_password, verify_password
from backend.deps import get_current_user
from backend.models import User, UserPreference, now_utc
from backend.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut, UserProfileOut, UserProfileUpdate
from backend.services.text_clean import clean_text

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    exists = db.scalar(
        select(User).where(or_(User.username == payload.username, User.email == payload.email))
    )
    if exists:
        raise HTTPException(status_code=409, detail="用户名或邮箱已存在")
    if payload.role == "regulator" and payload.invite_code != settings.regulator_invite_code:
        raise HTTPException(status_code=403, detail="监管账号需要有效的邀请码")
    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(
        select(User).where(or_(User.username == payload.username, User.email == payload.username))
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    return TokenResponse(access_token=create_access_token(str(user.id)))


def _clean_user_profile(user: User) -> None:
    user.display_name = clean_text(user.display_name, f"自然观察者{user.id}")[:80]
    user.bio = clean_text(user.bio, "热爱自然，也热爱每一次发现。")[:300]


@router.get("/me", response_model=UserOut)
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
    _clean_user_profile(user)
    db.commit()
    return user


def _preference(db: Session, user: User) -> UserPreference:
    item = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    if not item:
        item = UserPreference(user_id=user.id)
        db.add(item)
        db.flush()
    return item


@router.get("/profile", response_model=UserProfileOut)
def profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    _clean_user_profile(user)
    pref = _preference(db, user)
    db.commit()
    return {"user": user, "home_location": pref.home_location, "frequent_locations": pref.frequent_locations or []}


@router.patch("/profile", response_model=UserProfileOut)
def update_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if payload.display_name.strip():
        user.display_name = clean_text(payload.display_name.strip(), user.display_name)[:80]
    if payload.bio.strip():
        user.bio = clean_text(payload.bio.strip(), user.bio)[:300]
    user.avatar_url = payload.avatar_url.strip() or None
    pref = _preference(db, user)
    pref.home_location = payload.home_location.strip()
    pref.frequent_locations = [item.strip() for item in payload.frequent_locations if item.strip()][:20]
    pref.updated_at = now_utc()
    db.commit()
    db.refresh(user)
    return {"user": user, "home_location": pref.home_location, "frequent_locations": pref.frequent_locations or []}
