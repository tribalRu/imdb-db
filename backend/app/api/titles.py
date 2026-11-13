"""title endpoints"""

from typing import Annotated, Any

from api.params import CategoryParams, ListTitlesParams, validate_cursor
from dependencies import get_session
from fastapi import APIRouter, Depends, HTTPException, Query
from models import Person, Title, TitlePrincipal, TitleRating
from schemas import TitlePrincipalOut, TitleWithRating
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api", tags=["titles"])
MAX_TCONST_FILTER = 500


@router.get("/titles", response_model=list[TitleWithRating])
async def list_titles(
    params: ListTitlesParams = Depends(),
    tconst: Annotated[list[str] | None, Query()] = None,
    after_tconst: Annotated[str | None, Query(pattern=r"^tt\d+$")] = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """get list of titles"""
    validate_cursor(params.page, after_tconst, "after_tconst")

    filters: list[Any] = []
    if tconst:
        if len(tconst) > MAX_TCONST_FILTER:
            raise HTTPException(
                status_code=400,
                detail=f"tconst accepts at most {MAX_TCONST_FILTER} values.",
            )
        filters.append(Title.tconst.in_(tconst))  # type: ignore  # pylint: disable=no-member
    if params.genre:
        # `@>` (contains) is the array operator the GIN index supports;
        # `<value> = ANY(genres)` cannot use ix_titles_genres_gin.
        filters.append(Title.genres.contains([params.genre]))  # type: ignore  # pylint: disable=no-member
    if params.year_from:
        filters.append(Title.start_year >= params.year_from)
    if params.title_type:
        filters.append(Title.title_type == params.title_type)
    if after_tconst:
        # Keyset pagination: continue right after the last tconst of the
        # previous page instead of walking (and discarding) N index entries.
        filters.append(Title.tconst > after_tconst)

    # Page over titles only, then fetch ratings for the selected rows. Joining
    # ratings before LIMIT/OFFSET makes Postgres look up a rating for every
    # skipped row: page=100000 took 5.3s instead of 0.7s.
    page_stmt = select(Title.tconst).where(*filters)
    if params.min_rating is not None:
        page_stmt = page_stmt.join(TitleRating, TitleRating.tconst == Title.tconst).where(
            TitleRating.average_rating >= params.min_rating
        )
    offset = 0 if after_tconst else (params.page - 1) * params.size
    page_stmt = page_stmt.order_by(Title.tconst).limit(params.size).offset(offset)
    page_ids = page_stmt.subquery()

    stmt = (
        select(Title, TitleRating)
        .join(page_ids, page_ids.c.tconst == Title.tconst)
        .outerjoin(TitleRating, TitleRating.tconst == Title.tconst)
        .order_by(Title.tconst)
    )
    result = await session.execute(stmt)
    payloads: list[dict[str, Any]] = []
    for title, rating in result.all():
        payload = title.model_dump()
        if rating:
            payload.update(rating.model_dump())
            if payload.get("average_rating") is not None:
                payload["average_rating"] = round(payload["average_rating"], 1)
        else:
            payload["average_rating"] = None
            payload["num_votes"] = None
        payloads.append(payload)

    return payloads


@router.get("/titles/{tconst}", response_model=TitleWithRating)
async def get_title(
    tconst: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """get single title"""
    result = await session.execute(
        select(Title, TitleRating)
        .outerjoin(TitleRating, TitleRating.tconst == Title.tconst)
        .where(Title.tconst == tconst)
    )
    row = result.one_or_none()
    title = row[0] if row else None
    if title is None:
        raise HTTPException(status_code=404, detail="title not found")
    rating = row[1] if row else None
    payload = title.model_dump()
    if rating:
        payload.update(rating.model_dump())
        if payload.get("average_rating") is not None:
            payload["average_rating"] = round(payload["average_rating"], 1)
    else:
        payload["average_rating"] = None
        payload["num_votes"] = None
    return payload


@router.get("/titles/{tconst}/principals", response_model=list[TitlePrincipalOut])
async def list_title_principals(
    tconst: str,
    params: CategoryParams = Depends(),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """get list title principal"""
    stmt = (
        select(TitlePrincipal, Person)
        .join(Person, Person.nconst == TitlePrincipal.nconst)
        .where(TitlePrincipal.tconst == tconst)
    )
    if params.category:
        stmt = stmt.where(TitlePrincipal.category == params.category)
    stmt = stmt.order_by(TitlePrincipal.ordering)

    stmt = stmt.limit(params.size).offset((params.page - 1) * params.size)
    result = await session.execute(stmt)
    payloads: list[dict[str, Any]] = []
    for principal, person in result.all():
        payload = principal.model_dump()
        payload["person"] = person.model_dump()
        payloads.append(payload)
    return payloads
