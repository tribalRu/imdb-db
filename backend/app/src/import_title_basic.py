"""import title basic dataset"""

import asyncpg
from src.import_base import IngestDataset


class IngestTitleBasics(IngestDataset):
    """ingest title basic dataset"""

    DATASET_NAME = "title.basics.tsv"
    REBUILD_INDEXES = (
        (
            "ix_titles_primary_title_trgm",
            "CREATE INDEX IF NOT EXISTS ix_titles_primary_title_trgm "
            "ON titles USING GIN (primary_title gin_trgm_ops)",
        ),
        (
            "ix_titles_original_title_trgm",
            "CREATE INDEX IF NOT EXISTS ix_titles_original_title_trgm "
            "ON titles USING GIN (original_title gin_trgm_ops)",
        ),
        (
            "ix_titles_genres_gin",
            "CREATE INDEX IF NOT EXISTS ix_titles_genres_gin ON titles USING GIN (genres)",
        ),
    )

    async def create_staging_table(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            CREATE TEMP TABLE IF NOT EXISTS {self.staging_table} (
                tconst TEXT,
                title_type TEXT,
                primary_title TEXT,
                original_title TEXT,
                is_adult BOOLEAN,
                start_year SMALLINT,
                end_year SMALLINT,
                runtime_minutes BIGINT,
                genres TEXT
            ) ON COMMIT DROP
            """)

    async def merge_into_final(self, conn: asyncpg.Connection) -> None:
        if await self._is_first_import(conn):
            await self._insert_first_import(conn)
            return

        await self._upsert_existing(conn)

    async def _is_first_import(self, conn: asyncpg.Connection) -> bool:
        return await self._is_table_empty(conn, "titles")

    async def _insert_first_import(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO titles (
                tconst,
                title_type,
                primary_title,
                original_title,
                is_adult,
                start_year,
                end_year,
                runtime_minutes,
                genres
            )
            SELECT
                tconst,
                title_type,
                primary_title,
                NULLIF(original_title, ''),
                is_adult,
                start_year,
                end_year,
                runtime_minutes,
                string_to_array(genres, ',')
            FROM {self.staging_table}
            """)

    async def _upsert_existing(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO titles (
                tconst,
                title_type,
                primary_title,
                original_title,
                is_adult,
                start_year,
                end_year,
                runtime_minutes,
                genres
            )
            SELECT
                tconst,
                title_type,
                primary_title,
                NULLIF(original_title, ''),
                is_adult,
                start_year,
                end_year,
                runtime_minutes,
                string_to_array(genres, ',')
            FROM {self.staging_table}
            ON CONFLICT (tconst) DO UPDATE
            SET
                title_type = EXCLUDED.title_type,
                primary_title = EXCLUDED.primary_title,
                original_title = EXCLUDED.original_title,
                is_adult = EXCLUDED.is_adult,
                start_year = EXCLUDED.start_year,
                end_year = EXCLUDED.end_year,
                runtime_minutes = EXCLUDED.runtime_minutes,
                genres = EXCLUDED.genres
            WHERE
                titles.title_type IS DISTINCT FROM EXCLUDED.title_type
                OR titles.primary_title IS DISTINCT FROM EXCLUDED.primary_title
                OR titles.original_title IS DISTINCT FROM EXCLUDED.original_title
                OR titles.is_adult IS DISTINCT FROM EXCLUDED.is_adult
                OR titles.start_year IS DISTINCT FROM EXCLUDED.start_year
                OR titles.end_year IS DISTINCT FROM EXCLUDED.end_year
                OR titles.runtime_minutes IS DISTINCT FROM EXCLUDED.runtime_minutes
                OR titles.genres IS DISTINCT FROM EXCLUDED.genres
            """)
