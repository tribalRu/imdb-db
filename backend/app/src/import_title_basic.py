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
                s.tconst,
                s.title_type,
                s.primary_title,
                NULLIF(s.original_title, ''),
                s.is_adult,
                s.start_year,
                s.end_year,
                s.runtime_minutes,
                string_to_array(s.genres, ',')
            FROM {self.staging_table} s
            WHERE NOT EXISTS (
                SELECT 1 FROM titles t WHERE t.tconst = s.tconst
            );

            UPDATE titles t
            SET
                title_type = s.title_type,
                primary_title = s.primary_title,
                original_title = NULLIF(s.original_title, ''),
                is_adult = s.is_adult,
                start_year = s.start_year,
                end_year = s.end_year,
                runtime_minutes = s.runtime_minutes,
                genres = string_to_array(s.genres, ',')
            FROM {self.staging_table} s
            WHERE t.tconst = s.tconst
              AND (
                t.title_type IS DISTINCT FROM s.title_type
                OR t.primary_title IS DISTINCT FROM s.primary_title
                OR t.original_title IS DISTINCT FROM NULLIF(s.original_title, '')
                OR t.is_adult IS DISTINCT FROM s.is_adult
                OR t.start_year IS DISTINCT FROM s.start_year
                OR t.end_year IS DISTINCT FROM s.end_year
                OR t.runtime_minutes IS DISTINCT FROM s.runtime_minutes
                OR t.genres IS DISTINCT FROM string_to_array(s.genres, ',')
              );
            """)
