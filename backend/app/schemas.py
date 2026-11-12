"""response models for the API (keep in sync with the payload builders)"""

from datetime import datetime

from pydantic import BaseModel


class TitleFields(BaseModel):
    """fields shared by every title payload"""

    tconst: str
    title_type: str
    primary_title: str
    original_title: str | None
    is_adult: bool
    start_year: int | None
    end_year: int | None
    runtime_minutes: int | None
    genres: list[str] | None


class TitleWithRating(TitleFields):
    """title payload with rating fields"""

    average_rating: float | None = None
    num_votes: int | None = None


class CreditTitle(BaseModel):
    """title summary used in person credits"""

    tconst: str
    title_type: str
    primary_title: str
    original_title: str | None
    start_year: int | None
    end_year: int | None


class CreditItem(BaseModel):
    """one title credit of a person"""

    tconst: str
    ordering: int
    category: str
    job: str | None
    characters: list[str] | None
    title: CreditTitle


class PersonBasic(BaseModel):
    """person payload without hydrated known-for titles"""

    nconst: str
    primary_name: str | None
    birth_year: int | None
    death_year: int | None
    primary_professions: list[str] | None
    known_for_titles: list[str] | None


class PersonDetail(BaseModel):
    """person payload with hydrated known-for titles"""

    nconst: str
    primary_name: str | None
    birth_year: int | None
    death_year: int | None
    primary_professions: list[str] | None
    known_for_titles: list[TitleFields]


class TitlePrincipalOut(BaseModel):
    """title principal with the person inlined"""

    tconst: str
    ordering: int
    nconst: str
    category: str
    job: str | None
    characters: list[str] | None
    person: PersonBasic


class EpisodeOut(TitleWithRating):
    """episode payload with the parent series inlined"""

    parent_tconst: str
    season_number: int | None
    episode_number: int | None
    parent: TitleFields


class ImportTaskOut(BaseModel):
    """import task record"""

    id: int
    filename: str
    size_compressed: int
    size_raw: int
    import_start_time: datetime
    duration: float
    status: str
    size_compressed_mb: float
    size_raw_mb: float


class DatasetStat(BaseModel):
    """per-dataset stats entry"""

    dataset_name: str
    indexed: bool
    document_count: int
    disk_usage_bytes: int
    disk_usage_human: str
    runs: int | None = None
    last_import_time: str | None = None
    size_compressed_total: int | None = None
    size_raw_total: int | None = None
    avg_duration_seconds: float | None = None


class StatsResponse(BaseModel):
    """dataset and index stats"""

    datasets: list[DatasetStat]
    total_document_count: int
    disk_usage_bytes: dict[str, int]
    disk_usage_human: dict[str, str]
    import_task_count: int


class TriggerIngestResponse(BaseModel):
    """response for POST /api/ingest"""

    message: str
    data_set: list[str]
    force: bool
