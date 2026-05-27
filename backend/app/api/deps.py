"""FastAPI dependencies for authentication. Requirements: 13.1, 9.2"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.auth.jwt import TokenPayload, verify_token
from app.database import get_db
from app.exceptions import InvalidJWTError


def get_current_user(authorization: str = Header(default="")) -> TokenPayload:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token JWT ausente.")
    token = authorization[7:]
    try:
        return verify_token(token)
    except InvalidJWTError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def require_admin(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
    return user
