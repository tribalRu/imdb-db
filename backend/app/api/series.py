"""series endpoints"""

from typing import Any

from api.params import ListSeriesEpisodesParams
from dependencies import get_session
from fastapi import APIRouter, Depends, HTTPException
from models import Episode, Title, TitleRating
from schemas import EpisodeOut
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api", tags=["series"])


@router.get("/series/{tconst}/episodes", response_model=list[EpisodeOut])
async def list_series_episodes(
    tconst: str,
    params: ListSeriesEpisodesParams = Depends(),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """episodes in series"""
    parent_result = await session.execute(select(Title).where(Title.tconst == tconst))
    parent = parent_result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=404, detail="series not found")

    stmt = (
        select(Episode, Title, TitleRating)
        .join(Title, Title.tconst == Episode.tconst)
        .outerjoin(TitleRating, TitleRating.tconst == Title.tconst)
        .where(Episode.parent_tconst == tconst)
        .order_by(Episode.season_number, Episode.episode_number)
    )
    if params.season_number:
        stmt = stmt.where(Episode.season_number == params.season_number)

    result = await session.execute(stmt)
    payloads: list[dict[str, Any]] = []
    parent_payload = parent.model_dump()
    for episode, title, rating in result.all():
        payload = episode.model_dump()
        payload.update(title.model_dump())
        if rating:
            payload.update(rating.model_dump())
            if payload.get("average_rating") is not None:
                payload["average_rating"] = round(payload["average_rating"], 1)
        else:
            payload["average_rating"] = None
            payload["num_votes"] = None
        payload["parent"] = parent_payload
        payloads.append(payload)
    return payloads
