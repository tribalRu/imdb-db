"""app dependencies"""

import secrets
from typing import Annotated, AsyncGenerator

import config
from database import AsyncSessionLocal
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async database session dependency"""
    async with AsyncSessionLocal() as session:
        yield session


async def verify_bearer_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Verify Authorization: Bearer <token> when API_TOKEN is configured."""
    api_token = config.API_TOKEN
    if not api_token:
        return

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, provided_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not provided_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(
        provided_token.encode("utf-8"),
        api_token.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
