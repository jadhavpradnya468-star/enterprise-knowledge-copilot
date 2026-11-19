from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.deps import Deps
from app.api.errors import AppError
from app.db import SessionLocal, User
from app.security import hash_key


def get_db():
    with SessionLocal() as session:
        yield session


def get_deps(request: Request) -> Deps:
    return request.app.state.deps


def get_graph(request: Request):
    return request.app.state.graph


def get_current_user(
    x_api_key: str | None = Header(default=None), db: Session = Depends(get_db)
) -> User:
    if not x_api_key:
        raise AppError(401, "missing_api_key", "Provide your API key in the X-API-Key header.")
    user = db.scalar(select(User).where(User.api_key_hash == hash_key(x_api_key)))
    if user is None:
        raise AppError(401, "invalid_api_key", "The API key is not valid.")
    return user
