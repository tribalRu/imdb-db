"""title endpoints"""

from typing import Annotated, Any

from api.params import CategoryParams, ListTitlesParams
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
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """get list of titles"""
    stmt = select(Title, TitleRating).outerjoin(TitleRating, TitleRating.tconst == Title.tconst)

    if tconst:
        if len(tconst) > MAX_TCONST_FILTER:
            raise HTTPException(
                status_code=400,
                detail=f"tconst accepts at most {MAX_TCONST_FILTER} values.",
            )
        stmt = stmt.where(Title.tconst.in_(tconst))  # type: ignore  # pylint: disable=no-member
    if params.genre:
        stmt = stmt.where(Title.genres.any(params.genre))  # type: ignore  # pylint: disable=no-member
    if params.year_from:
        stmt = stmt.where(Title.start_year >= params.year_from)
    if params.title_type:
        stmt = stmt.where(Title.title_type == params.title_type)
    if params.min_rating is not None:
        stmt = stmt.where(TitleRating.average_rating >= params.min_rating)

    stmt = stmt.order_by(Title.tconst)
    stmt = stmt.limit(params.size).offset((params.page - 1) * params.size)
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
