from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.database import get_db
from echogtfs.models import User
from echogtfs.schemas import UserCreate, UserRead, UserUpdate
from echogtfs.security import CurrentSuperuser, CurrentUser, hash_password

router = APIRouter()

_DB = Annotated[AsyncSession, Depends(get_db)]


# -- Open endpoints ------------------------------------------------------------

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: _DB) -> User:
    """Open registration – creates a regular (non-superuser) account."""
    existing = await db.execute(
        select(User).where(
            (User.username == payload.username) | (User.email == payload.email)
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already taken",
        )
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# -- Current-user endpoints (any authenticated user) ---------------------------

@router.get("/me", response_model=UserRead)
async def read_me(current_user: CurrentUser) -> User:
    return current_user


@router.put("/me", response_model=UserRead)
async def update_me(payload: UserUpdate, current_user: CurrentUser, db: _DB) -> User:
    if payload.email is not None:
        current_user.email = payload.email
    if payload.password is not None:
        current_user.hashed_password = hash_password(payload.password)
    await db.commit()
    await db.refresh(current_user)
    return current_user


# -- Admin endpoints (superuser only) -----------------------------------------

@router.get("/", response_model=list[UserRead])
async def list_users(_: CurrentSuperuser, db: _DB) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, _: CurrentSuperuser, db: _DB) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int, payload: UserUpdate, current_superuser: CurrentSuperuser, db: _DB
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.email is not None:
        user.email = payload.email
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_superuser is not None:
        if user_id == current_superuser.id and not payload.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own admin privileges",
            )
        user.is_superuser = payload.is_superuser
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int, current_superuser: CurrentSuperuser, db: _DB
) -> None:
    if user_id == current_superuser.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself"
        )
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.delete(user)
    await db.commit()
