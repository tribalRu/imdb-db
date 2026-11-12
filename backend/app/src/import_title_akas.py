"""import title akas"""

import asyncpg
from src.import_base import IngestDataset


class IngestTitleAkas(IngestDataset):
    """ingest dataset"""

    DATASET_NAME = "title.akas.tsv"

    async def create_staging_table(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            CREATE TEMP TABLE IF NOT EXISTS {self.staging_table} (
                title_id TEXT,
                ordering INTEGER,
                title TEXT,
                region TEXT,
                language TEXT,
                types TEXT,
                attributes TEXT,
                is_original BOOLEAN
            ) ON COMMIT DROP;
            """)

    async def merge_into_final(self, conn: asyncpg.Connection) -> None:
        if await self._is_first_import(conn):
            await self._insert_first_import(conn)
            return

        await self._upsert_existing(conn)

    async def _is_first_import(self, conn: asyncpg.Connection) -> bool:
        return await self._is_table_empty(conn, "title_akas")

    async def _insert_first_import(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO title_akas (
                title_id,
                ordering,
                title,
                region,
                language,
                types,
                attributes,
                is_original
            )
            SELECT
                s.title_id,
                s.ordering,
                s.title,
                s.region,
                s.language,
                CASE
                    WHEN s.types IS NULL THEN NULL
                    ELSE string_to_array(s.types, ',')
                END,
                CASE
                    WHEN s.attributes IS NULL THEN NULL
                    ELSE string_to_array(s.attributes, ',')
                END,
                s.is_original
            FROM {self.staging_table} s
            JOIN titles t ON t.tconst = s.title_id
            """)

    async def _upsert_existing(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO title_akas (
                title_id,
                ordering,
                title,
                region,
                language,
                types,
                attributes,
                is_original
            )
            SELECT
                s.title_id,
                s.ordering,
                s.title,
                s.region,
                s.language,
                CASE
                    WHEN s.types IS NULL THEN NULL
                    ELSE string_to_array(s.types, ',')
                END,
                CASE
                    WHEN s.attributes IS NULL THEN NULL
                    ELSE string_to_array(s.attributes, ',')
                END,
                s.is_original
            FROM {self.staging_table} s
            JOIN titles t ON t.tconst = s.title_id
            ON CONFLICT (title_id, ordering) DO UPDATE
            SET
                title = EXCLUDED.title,
                region = EXCLUDED.region,
                language = EXCLUDED.language,
                types = EXCLUDED.types,
                attributes = EXCLUDED.attributes,
                is_original = EXCLUDED.is_original
            WHERE
                title_akas.title IS DISTINCT FROM EXCLUDED.title
                OR title_akas.region IS DISTINCT FROM EXCLUDED.region
                OR title_akas.language IS DISTINCT FROM EXCLUDED.language
                OR title_akas.types IS DISTINCT FROM EXCLUDED.types
                OR title_akas.attributes IS DISTINCT FROM EXCLUDED.attributes
                OR title_akas.is_original IS DISTINCT FROM EXCLUDED.is_original;
            """)
