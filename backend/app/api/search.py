"""search endpoints"""

from typing import Annotated, Any

from api.params import SearchParams, validate_cursor
from dependencies import get_session
from fastapi import APIRouter, Depends, HTTPException, Query
from models import Person, Title
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/search", tags=["search"])

# Up to this many matches we fetch their primary keys and sort them in Python.
# That keeps rare searches (and searches with no matches) on the trigram GIN
# indexes instead of walking the whole primary-key index in tconst order.
# Above the limit an ordered primary-key scan is cheaper, so we fall back to it.
SELECTIVE_MATCH_LIMIT = 1000


def _normalized_query(params: SearchParams) -> str:
    """return the trimmed query, or reject a blank one"""
    q = params.q.strip()
    if not q:
        raise HTTPException(
            status_code=422,
            detail="q must contain at least one non-whitespace character",
        )
    return q


def _like_pattern(q: str) -> str:
    """wrap a query in %...% and escape LIKE wildcards so they match literally"""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def _search_paginated(
    session: AsyncSession,
    model: Any,
    key_column: Any,
    conditions: list[ColumnElement[bool]],
    params: SearchParams,
    after: str | None = None,
) -> list[Any]:
    """paginate search hits without scanning the whole table for rare terms"""
    probe = select(key_column).where(*conditions)
    if after:
        probe = probe.where(key_column > after)
    probe = probe.limit(SELECTIVE_MATCH_LIMIT)
    matched_keys = list((await session.execute(probe)).scalars().all())

    start = 0 if after else (params.page - 1) * params.size
    if len(matched_keys) < SELECTIVE_MATCH_LIMIT:
        page_keys = sorted(matched_keys)[start : start + params.size]
        if not page_keys:
            return []
        stmt = select(model).where(key_column.in_(page_keys)).order_by(key_column)
        return list((await session.execute(stmt)).scalars().all())

    stmt = select(model).where(*conditions)
    if after:
        stmt = stmt.where(key_column > after)
    stmt = stmt.order_by(key_column)
    stmt = stmt.limit(params.size).offset(start)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/titles", response_model=list[Title])
async def search_titles(
    params: SearchParams = Depends(),
    after_tconst: Annotated[str | None, Query(pattern=r"^tt\d+$")] = None,
    session: AsyncSession = Depends(get_session),
) -> list[Title]:
    """search titles"""
    validate_cursor(params.page, after_tconst, "after_tconst")
    like = _like_pattern(_normalized_query(params))
    conditions: list[ColumnElement[bool]] = [
        or_(
            Title.primary_title.ilike(like, escape="\\"),  # type: ignore
            Title.original_title.ilike(like, escape="\\"),  # type: ignore
        )
    ]
    if params.title_type:
        conditions.append(Title.title_type == params.title_type)
    if params.year_from:
        conditions.append(Title.start_year >= params.year_from)

    return await _search_paginated(session, Title, Title.tconst, conditions, params, after_tconst)


@router.get("/people", response_model=list[Person])
async def search_people(
    params: SearchParams = Depends(),
    after_nconst: Annotated[str | None, Query(pattern=r"^nm\d+$")] = None,
    session: AsyncSession = Depends(get_session),
) -> list[Person]:
    """search people"""
    validate_cursor(params.page, after_nconst, "after_nconst")
    like = _like_pattern(_normalized_query(params))
    conditions: list[ColumnElement[bool]] = [Person.primary_name.ilike(like, escape="\\")]  # type: ignore

    return await _search_paginated(session, Person, Person.nconst, conditions, params, after_nconst)
