"""people endpoints"""

from typing import Any

from api.params import CategoryParams
from dependencies import get_session
from fastapi import APIRouter, Depends, HTTPException
from models import Person, Title, TitlePrincipal
from schemas import CreditItem, PersonDetail
from sqlalchemy import func, select
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
    # Keep one credit row per title (a person can be listed as actor and
    # director on the same title), then sort by year. DISTINCT ON would force
    # tconst to lead the ORDER BY, which made the year sort a no-op.
    ranked = (
        select(
            TitlePrincipal.tconst,
            TitlePrincipal.ordering,
            TitlePrincipal.category,
            TitlePrincipal.job,
            TitlePrincipal.characters,
            Title.title_type,
            Title.primary_title,
            Title.original_title,
            Title.start_year,
            Title.end_year,
            func.row_number()
            .over(
                partition_by=TitlePrincipal.tconst,
                order_by=TitlePrincipal.ordering,
            )
            .label("row_number"),
        )
        .join(Title, Title.tconst == TitlePrincipal.tconst)
        .where(TitlePrincipal.nconst == nconst)
    )
    if params.category:
        ranked = ranked.where(TitlePrincipal.category == params.category)
    subquery = ranked.subquery()

    stmt = (
        select(subquery)
        .where(subquery.c.row_number == 1)
        .order_by(
            subquery.c.start_year.desc().nulls_last(),
            subquery.c.primary_title,
            subquery.c.tconst,
        )
        .limit(params.size)
        .offset((params.page - 1) * params.size)
    )
    result = await session.execute(stmt)

    people_credits: list[dict[str, Any]] = []
    for row in result.all():
        credit = row._mapping
        people_credits.append(
            {
                "tconst": credit["tconst"],
                "ordering": credit["ordering"],
                "category": credit["category"],
                "job": credit["job"],
                "characters": credit["characters"],
                "title": {
                    "tconst": credit["tconst"],
                    "title_type": credit["title_type"],
                    "primary_title": credit["primary_title"],
                    "original_title": credit["original_title"],
                    "start_year": credit["start_year"],
                    "end_year": credit["end_year"],
                },
            }
        )

    return people_credits
