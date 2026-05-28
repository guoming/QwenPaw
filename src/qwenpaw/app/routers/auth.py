# -*- coding: utf-8 -*-
"""Authentication API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..auth import (
    authenticate,
    delete_user,
    has_registered_users,
    list_users,
    register_user,
    reset_user_password,
    revoke_all_tokens,
    revoke_token,
    update_credentials,
    verify_token,
    verify_token_payload,
)
from ..deps import get_request_user_id, require_admin

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    expires_in: int | None = (
        None  # Token expiry in seconds, -1/0 for permanent
    )


class LoginResponse(BaseModel):
    token: str
    username: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    expires_in: int | None = (
        None  # Token expiry in seconds, -1/0 for permanent
    )


class AuthStatusResponse(BaseModel):
    enabled: bool
    has_users: bool


class VerifyResponse(BaseModel):
    valid: bool
    username: str
    user_id: str
    is_admin: bool


class UserRecord(BaseModel):
    user_id: str
    username: str
    is_admin: bool


@router.post("/login")
async def login(req: LoginRequest):
    """Authenticate with username and password."""
    token = authenticate(req.username, req.password, req.expires_in)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return LoginResponse(token=token, username=req.username)


@router.post("/register")
async def register(req: RegisterRequest):
    """Register a new user account."""
    if not req.username.strip() or not req.password.strip():
        raise HTTPException(
            status_code=400,
            detail="Username and password are required",
        )

    username = req.username.strip()
    token = register_user(username, req.password, req.expires_in)
    if token is None:
        raise HTTPException(
            status_code=409,
            detail="Registration failed (username may already exist)",
        )

    from ..auth import verify_token_payload

    payload = verify_token_payload(token)
    if payload and payload.get("user_id"):
        from ..user_migration import migrate_legacy_to_admin_user

        migrate_legacy_to_admin_user()

    return LoginResponse(token=token, username=username)


@router.get("/status")
async def auth_status():
    """Check whether users exist (auth is always enabled)."""
    return AuthStatusResponse(
        enabled=True,
        has_users=has_registered_users(),
    )


@router.get("/verify")
async def verify(request: Request):
    """Verify that the caller's Bearer token is still valid."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")

    payload = verify_token_payload(token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    return VerifyResponse(
        valid=True,
        username=payload["sub"],
        user_id=payload.get("user_id", ""),
        is_admin=bool(payload.get("is_admin", False)),
    )


class UpdateProfileRequest(BaseModel):
    current_password: str
    new_username: str | None = None
    new_password: str | None = None
    expires_in: int | None = (
        None  # Token expiry in seconds, -1/0 for permanent
    )


class CreateUserRequest(BaseModel):
    username: str
    password: str


class ResetUserPasswordRequest(BaseModel):
    new_password: str


@router.post("/update-profile")
async def update_profile(req: UpdateProfileRequest, request: Request):
    """Update username and/or password for the authenticated user."""
    if not has_registered_users():
        raise HTTPException(
            status_code=403,
            detail="No user registered",
        )

    auth_header = request.headers.get("Authorization", "")
    caller_token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    payload = verify_token_payload(caller_token) if caller_token else None
    if payload is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not req.new_username and not req.new_password:
        raise HTTPException(
            status_code=400,
            detail="Nothing to update",
        )

    if req.new_username is not None and not req.new_username.strip():
        raise HTTPException(
            status_code=400,
            detail="Username cannot be empty",
        )

    if req.new_password is not None and not req.new_password.strip():
        raise HTTPException(
            status_code=400,
            detail="Password cannot be empty",
        )

    token = update_credentials(
        username=payload["sub"],
        current_password=req.current_password,
        new_username=req.new_username,
        new_password=req.new_password,
        expiry_seconds=req.expires_in,
    )
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Current password is incorrect",
        )

    username = req.new_username.strip() if req.new_username else payload["sub"]
    return LoginResponse(token=token, username=username)


class RevokeTokenRequest(BaseModel):
    token: str | None = (
        None  # Optional: revoke specific token, or current if omitted
    )


@router.post("/revoke-token")
async def revoke_single_token(req: RevokeTokenRequest, request: Request):
    """Revoke a single token by adding it to the blacklist."""
    auth_header = request.headers.get("Authorization", "")
    caller_token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    if not caller_token or verify_token(caller_token) is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_to_revoke = req.token if req.token else caller_token
    is_current_token = token_to_revoke == caller_token

    success = revoke_token(token_to_revoke)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to revoke token",
        )

    message = (
        "Current token has been revoked. Please login again."
        if is_current_token
        else "Specified token has been revoked."
    )

    return {
        "message": message,
        "revoked": True,
        "revoked_current_token": is_current_token,
    }


@router.post("/revoke-all-tokens")
async def revoke_all_sessions(request: Request):
    """Revoke all existing tokens by rotating the JWT secret."""
    auth_header = request.headers.get("Authorization", "")
    caller_token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    if not caller_token or verify_token(caller_token) is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    success = revoke_all_tokens()
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to revoke tokens",
        )

    return {
        "message": "All tokens have been revoked. Please login again.",
        "revoked": True,
    }


@router.get("/users")
async def get_users(request: Request) -> list[UserRecord]:
    """Admin: list users."""
    require_admin(request)
    return [UserRecord(**u) for u in list_users()]


@router.post("/users")
async def create_user(req: CreateUserRequest, request: Request) -> UserRecord:
    """Admin: create a user account."""
    require_admin(request)
    username = req.username.strip()
    password = req.password.strip()
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="Username and password are required",
        )
    token = register_user(username, password)
    if token is None:
        raise HTTPException(
            status_code=409,
            detail="Username already exists",
        )

    created = next((u for u in list_users() if u.get("username") == username), None)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create user")
    return UserRecord(**created)


@router.post("/users/{user_id}/password")
async def admin_reset_password(
    user_id: str,
    req: ResetUserPasswordRequest,
    request: Request,
):
    """Admin: reset a user's password."""
    require_admin(request)
    new_password = req.new_password.strip()
    if not new_password:
        raise HTTPException(status_code=400, detail="Password cannot be empty")
    if not reset_user_password(user_id, new_password):
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@router.delete("/users/{user_id}")
async def remove_user(user_id: str, request: Request):
    """Admin: delete a non-admin user."""
    require_admin(request)
    actor_user_id = get_request_user_id(request)
    if not delete_user(user_id, actor_user_id=actor_user_id):
        users = list_users()
        target = next((u for u in users if u.get("user_id") == user_id), None)
        if target and target.get("is_admin"):
            raise HTTPException(status_code=400, detail="Cannot delete admin user")
        if actor_user_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}
