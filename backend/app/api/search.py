"""search endpoints"""

from typing import Any

from api.params import SearchParams
from dependencies import get_session
from fastapi import APIRouter, Depends
from models import Person, Title
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/search", tags=["search"])

# Up to this many matches we fetch their primary keys and sort them in Python.
# That keeps rare searches (and searches with no matches) on the trigram GIN
# indexes instead of walking the whole primary-key index in tconst order.
# Above the limit an ordered primary-key scan is cheaper, so we fall back to it.
SELECTIVE_MATCH_LIMIT = 1000


async def _search_paginated(
    session: AsyncSession,
    model: Any,
    key_column: Any,
    conditions: list[ColumnElement[bool]],
    params: SearchParams,
) -> list[Any]:
    """paginate search hits without scanning the whole table for rare terms"""
    probe = select(key_column).where(*conditions).limit(SELECTIVE_MATCH_LIMIT)
    matched_keys = list((await session.execute(probe)).scalars().all())

    start = (params.page - 1) * params.size
    if len(matched_keys) < SELECTIVE_MATCH_LIMIT:
        page_keys = sorted(matched_keys)[start : start + params.size]
        if not page_keys:
            return []
        stmt = select(model).where(key_column.in_(page_keys)).order_by(key_column)
        return list((await session.execute(stmt)).scalars().all())

    stmt = select(model).where(*conditions).order_by(key_column)
    stmt = stmt.limit(params.size).offset(start)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/titles")
async def search_titles(
    params: SearchParams = Depends(),
    session: AsyncSession = Depends(get_session),
) -> list[Title]:
    """search titles"""
    like = f"%{params.q}%"
    conditions: list[ColumnElement[bool]] = [
        or_(
            Title.primary_title.ilike(like),  # type: ignore
            Title.original_title.ilike(like),  # type: ignore
        )
    ]
    if params.title_type:
        conditions.append(Title.title_type == params.title_type)
    if params.year_from:
        conditions.append(Title.start_year >= params.year_from)

    return await _search_paginated(session, Title, Title.tconst, conditions, params)


@router.get("/people")
async def search_people(
    params: SearchParams = Depends(),
    session: AsyncSession = Depends(get_session),
) -> list[Person]:
    """search people"""
    like = f"%{params.q}%"
    conditions: list[ColumnElement[bool]] = [Person.primary_name.ilike(like)]  # type: ignore

    return await _search_paginated(session, Person, Person.nconst, conditions, params)
