"""define db models"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlmodel import Field, Relationship, SQLModel


class Title(SQLModel, table=True):
    """titles"""

    __tablename__ = "titles"
    __table_args__ = (
        Index(
            "ix_titles_primary_title_trgm",
            "primary_title",
            postgresql_using="gin",
            postgresql_ops={"primary_title": "gin_trgm_ops"},
        ),
        Index(
            "ix_titles_original_title_trgm",
            "original_title",
            postgresql_using="gin",
            postgresql_ops={"original_title": "gin_trgm_ops"},
        ),
        Index("ix_titles_genres_gin", "genres", postgresql_using="gin"),
    )

    tconst: str = Field(primary_key=True)
    title_type: str
    primary_title: str
    original_title: Optional[str]
    is_adult: bool
    start_year: Optional[int]
    end_year: Optional[int]
    runtime_minutes: Optional[int]

    genres: Optional[list[str]] = Field(sa_column=Column(ARRAY(TEXT)))

    rating: Optional["TitleRating"] = Relationship(
        back_populates="title",
        sa_relationship_kwargs={"uselist": False},
    )
    episodes: list["Episode"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={"foreign_keys": "[Episode.parent_tconst]"},
    )


class Person(SQLModel, table=True):
    """person people"""

    __tablename__ = "people"
    __table_args__ = (
        Index(
            "ix_people_primary_name_trgm",
            "primary_name",
            postgresql_using="gin",
            postgresql_ops={"primary_name": "gin_trgm_ops"},
        ),
    )

    nconst: str = Field(primary_key=True)
    primary_name: Optional[str]
    birth_year: Optional[int]
    death_year: Optional[int]

    primary_professions: Optional[list[str]] = Field(sa_column=Column(ARRAY(TEXT)))

    known_for_titles: Optional[list[str]] = Field(sa_column=Column(ARRAY(TEXT)))


class TitleRating(SQLModel, table=True):
    """ratings of title"""

    __tablename__ = "title_ratings"

    tconst: str = Field(
        foreign_key="titles.tconst",
        primary_key=True,
    )
    average_rating: float
    num_votes: int

    title: Optional[Title] = Relationship(back_populates="rating")


class Episode(SQLModel, table=True):
    """episode"""

    __tablename__ = "episodes"

    tconst: str = Field(
        primary_key=True,
        foreign_key="titles.tconst",
    )
    parent_tconst: str = Field(
        foreign_key="titles.tconst",
        index=True,
    )

    season_number: Optional[int]
    episode_number: Optional[int]

    parent: Optional[Title] = Relationship(
        back_populates="episodes",
        sa_relationship_kwargs={"foreign_keys": "[Episode.parent_tconst]"},
    )


class TitleAka(SQLModel, table=True):
    """title aka localized"""

    __tablename__ = "title_akas"

    title_id: str = Field(
        foreign_key="titles.tconst",
        primary_key=True,
    )
    ordering: int = Field(primary_key=True)

    title: str
    region: Optional[str]
    language: Optional[str]

    types: Optional[list[str]] = Field(sa_column=Column(ARRAY(TEXT)))

    attributes: Optional[list[str]] = Field(sa_column=Column(ARRAY(TEXT)))

    is_original: Optional[bool]


class TitlePrincipal(SQLModel, table=True):
    """Credits for a title (canonical IMDb credit table)"""

    __tablename__ = "title_principals"

    tconst: str = Field(
        foreign_key="titles.tconst",
        primary_key=True,
    )
    ordering: int = Field(primary_key=True)

    nconst: str = Field(
        foreign_key="people.nconst",
        index=True,
    )

    category: str
    job: Optional[str] = None
    characters: Optional[list[str]] = Field(
        default=None,
        sa_column=Column(ARRAY(TEXT)),
    )


class ImportTask(SQLModel, table=True):
    """Track metadata and timing for each imported IMDb dataset file."""

    __tablename__ = "import_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    size_compressed: int = Field(sa_column=Column(BigInteger, nullable=False))
    size_raw: int = Field(sa_column=Column(BigInteger, nullable=False))
    import_start_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    duration: float
    status: str = Field(
        default="completed",
        sa_column=Column(String(16), nullable=False, server_default="completed"),
    )
