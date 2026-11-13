"""shared API query parameter models"""

from typing import Annotated, Literal, Optional

from fastapi import HTTPException, Query
from pydantic import BaseModel


def validate_cursor(page: int, cursor: str | None, cursor_name: str) -> None:
    """reject mixing a keyset cursor with an offset page"""
    if cursor and page > 1:
        raise HTTPException(
            status_code=400,
            detail=f"{cursor_name} cannot be combined with page > 1; continue with the cursor instead",
        )


class PaginationParams(BaseModel):
    page: Annotated[int, Query(default=1, ge=1)]
    size: Annotated[int, Query(default=50, ge=1, le=500)]


class ImportTaskParams(PaginationParams):
    status: Annotated[Optional[Literal["running", "completed", "failed"]], Query(default=None)]


class CategoryParams(PaginationParams):
    category: Annotated[Optional[str], Query(default=None)]


class ListTitlesParams(PaginationParams):
    genre: Annotated[Optional[str], Query(default=None)]
    year_from: Annotated[Optional[int], Query(default=None, ge=1800)]
    min_rating: Annotated[Optional[float], Query(default=None, ge=0.0, le=10.0)]
    title_type: Annotated[Optional[str], Query(default=None)]


class ListSeriesEpisodesParams(PaginationParams):
    season_number: Annotated[Optional[int], Query(default=None, ge=1)]


class SearchParams(PaginationParams):
    q: Annotated[str, Query(min_length=1, max_length=100)]
    title_type: Annotated[Optional[str], Query(default=None)]
    year_from: Annotated[Optional[int], Query(default=None, ge=1800)]
