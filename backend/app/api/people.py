"""people endpoints"""

from typing import Any

from api.params import CategoryParams
from dependencies import get_session
from fastapi import APIRouter, Depends, HTTPException
from models import Person, Title, TitlePrincipal
from schemas import CreditItem, PersonDetail
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api", tags=["people"])


@router.get("/people/{nconst}", response_model=PersonDetail)
async def get_person(
    nconst: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """single person"""
    result = await session.execute(select(Person).where(Person.nconst == nconst))
    person = result.scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="person not found")
    known_for_titles: list[dict[str, Any]] = []
    if person.known_for_titles:
        titles_result = await session.execute(select(Title).where(Title.tconst.in_(person.known_for_titles)))
        titles = titles_result.scalars().all()
        titles_by_id = {title.tconst: title for title in titles}
        known_for_titles = [
            titles_by_id[tconst].model_dump() for tconst in person.known_for_titles if tconst in titles_by_id
        ]

    payload = person.model_dump()
    payload["known_for_titles"] = known_for_titles
    return payload


@router.get("/people/{nconst}/credits", response_model=list[CreditItem])
async def list_person_credits(
    nconst: str,
    params: CategoryParams = Depends(),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """list of credits of person"""
    stmt = (
        select(TitlePrincipal, Title)
        .join(Title, Title.tconst == TitlePrincipal.tconst)
        .where(TitlePrincipal.nconst == nconst)
        .distinct(TitlePrincipal.tconst)
        .order_by(TitlePrincipal.tconst, Title.start_year.desc(), Title.primary_title)  # type: ignore
    )
    if params.category:
        stmt = stmt.where(TitlePrincipal.category == params.category)

    stmt = stmt.limit(params.size).offset((params.page - 1) * params.size)
    result = await session.execute(stmt)

    people_credits: list[dict[str, Any]] = []
    for principal, title in result.all():
        people_credits.append(
            {
                "tconst": principal.tconst,
                "ordering": principal.ordering,
                "category": principal.category,
                "job": principal.job,
                "characters": principal.characters,
                "title": {
                    "tconst": title.tconst,
                    "title_type": title.title_type,
                    "primary_title": title.primary_title,
                    "original_title": title.original_title,
                    "start_year": title.start_year,
                    "end_year": title.end_year,
                },
            }
        )

    return people_credits
