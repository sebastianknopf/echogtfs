from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from echogtfs.services.database import SystemRepositoryInterface, get_system_repository
from echogtfs.services.database.models import User
from echogtfs.services.security import get_security_service
from echogtfs.validation.schemas import PasswordChange, UserCreate, UserRead, UserUpdate
from echogtfs.common.security import CurrentSuperuser, CurrentUser

router = APIRouter()

_Repo = Annotated[SystemRepositoryInterface, Depends(get_system_repository)]


@router.get("/me", response_model=UserRead)
async def read_me(current_user: CurrentUser) -> User:
    return current_user


@router.get("/", response_model=list[UserRead])
async def list_users(_: CurrentSuperuser, repository: _Repo) -> list[User]:
    return await repository.list_users()


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, _: CurrentSuperuser, repository: _Repo) -> User:
    user = await repository.get_user_by_id(user_id)

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_own_password(
    payload: PasswordChange, current_user: CurrentUser, repository: _Repo
) -> None:
    """Change password for the currently authenticated user. Requires current password verification."""
    if not get_security_service().verify_password(
        payload.current_password,
        current_user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    
    await repository.update_user(
        current_user.id,
        hashed_password=get_security_service().hash_password(payload.new_password),
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate, _: CurrentSuperuser, repository: _Repo
) -> User:
    """Admin-only registration endpoint for creating regular (non-superuser) accounts."""
    if await repository.user_exists_by_username_or_email(payload.username, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already taken",
        )
    
    return await repository.create_user(
        username=payload.username,
        email=payload.email,
        hashed_password=get_security_service().hash_password(payload.password),
    )


@router.put("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate, current_user: CurrentUser, repository: _Repo
) -> User:
    user = await repository.update_user(
        current_user.id,
        email=payload.email,
        hashed_password=(
            get_security_service().hash_password(payload.password)
            if payload.password is not None
            else None
        ),
    )

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current_superuser: CurrentSuperuser,
    repository: _Repo,
) -> User:
    existing_user = await repository.get_user_by_id(user_id)

    if existing_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.is_active is not None:
        if user_id == current_superuser.id and not payload.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate yourself",
            )

    if payload.is_superuser is not None:
        if user_id == current_superuser.id and current_superuser.is_superuser and not payload.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own admin privileges",
            )

    if payload.is_technical_contact is not None:
        if user_id == current_superuser.id and current_superuser.is_technical_contact and not payload.is_technical_contact:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own technical contact status",
            )

    user = await repository.update_user(
        user_id,
        email=payload.email,
        hashed_password=(
            get_security_service().hash_password(payload.password)
            if payload.password is not None
            else None
        ),
        is_active=payload.is_active,
        is_superuser=payload.is_superuser,
        is_technical_contact=payload.is_technical_contact,
    )

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int, current_superuser: CurrentSuperuser, repository: _Repo
) -> None:
    if user_id == current_superuser.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself"
        )
    
    deleted = await repository.delete_user(user_id)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
