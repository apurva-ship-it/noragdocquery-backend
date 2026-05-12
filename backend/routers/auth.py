from datetime import datetime, timedelta
from typing import Annotated
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, validator

from ..dependencies import get_client_ip, get_remaining_attempts
from ..config import Settings

router = APIRouter(prefix="/v1/auth", tags=["auth"])

_users: dict[str, dict] = {}
_revoked_refresh_token_hashes: set[str] = set()

SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Credentials(BaseModel):
    username: str
    password: str

    @validator("password")
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password too short, must be at least 8 characters")
        if v.isnumeric() or v.isalpha():
            raise ValueError("Password must contain both letters and numbers")
        return v


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def _hash_token(token: str) -> str:
    """Deterministic SHA256 hash for refresh token storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(data: dict) -> str:
    payload = {**data, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    payload = {**data, "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _set_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = Settings()
    secure_flag = getattr(settings, "production", False)
    for key, value, max_age in [
        ("access_token", access_token, ACCESS_TOKEN_EXPIRE_MINUTES * 60),
        ("refresh_token", refresh_token, REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600),
    ]:
        response.set_cookie(
            key=key,
            value=value,
            httponly=True,
            samesite="strict",
            secure=secure_flag,
            max_age=max_age,
        )


def _get_current_user_id(request: Request) -> str:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise JWTError()
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: Credentials, response: Response):
    if body.username in _users:
        raise HTTPException(status_code=400, detail="User already exists")
    user_id = str(len(_users) + 1)
    _users[body.username] = {
        "id": user_id,
        "username": body.username,
        "hashed_password": get_password_hash(body.password),
    }
    access_token = create_access_token({"sub": user_id})
    refresh_token = create_refresh_token({"sub": user_id})
    _set_cookies(response, access_token, refresh_token)
    return {"id": user_id, "username": body.username}


@router.post("/login")
async def login(
    body: Credentials,
    response: Response,
    client_ip: Annotated[str, Depends(get_client_ip)],
    remaining: Annotated[int, Depends(get_remaining_attempts)],
):
    user = _users.get(body.username)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token({"sub": user["id"]})
    refresh_token = create_refresh_token({"sub": user["id"]})
    _set_cookies(response, access_token, refresh_token)
    return {"id": user["id"], "username": user["username"]}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    token_hash = _hash_token(refresh_token)
    if token_hash in _revoked_refresh_token_hashes:
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise JWTError()
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    # revoke used token
    _revoked_refresh_token_hashes.add(token_hash)
    # issue new tokens
    access_token = create_access_token({"sub": user_id})
    new_refresh = create_refresh_token({"sub": user_id})
    _set_cookies(response, access_token, new_refresh)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        _revoked_refresh_token_hashes.add(_hash_token(refresh_token))
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"msg": "Logged out"}


@router.get("/me")
async def me(request: Request):
    user_id = _get_current_user_id(request)
    user = next((u for u in _users.values() if u["id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user["id"], "username": user["username"]}
