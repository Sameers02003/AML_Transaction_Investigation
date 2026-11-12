from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.db import get_db
from app.core.limiter import limiter
from app.core.security import verify_pw, make_token, current_user, require, READ
from app.models import User

router = APIRouter(tags=["auth"])


class Login(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
@limiter.limit("10/minute")
def login(request: Request, b: Login, db=Depends(get_db)):
    u = db.scalar(select(User).where(User.username == b.username))
    if not u or not u.active or not verify_pw(b.password, u.password_hash):
        raise HTTPException(401, "bad credentials")
    return {"access_token": make_token(u), "role": u.role, "username": u.username}


@router.get("/me")
def me(u=Depends(current_user)):
    return {"id": str(u.id), "username": u.username, "role": u.role}


@router.get("/users")
def users(db=Depends(get_db), _=Depends(require(*READ))):
    return [{"id": str(u.id), "username": u.username, "role": u.role} for u in db.scalars(select(User))]