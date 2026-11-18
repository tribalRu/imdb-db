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
            WHERE NOT EXISTS (
                SELECT 1 FROM title_akas ta
                WHERE ta.title_id = s.title_id AND ta.ordering = s.ordering
            );

            UPDATE title_akas ta
            SET
                title = s.title,
                region = s.region,
                language = s.language,
                types = CASE WHEN s.types IS NULL THEN NULL ELSE string_to_array(s.types, ',') END,
                attributes = CASE WHEN s.attributes IS NULL THEN NULL ELSE string_to_array(s.attributes, ',') END,
                is_original = s.is_original
            FROM {self.staging_table} s
            WHERE ta.title_id = s.title_id AND ta.ordering = s.ordering
              AND (
                ta.title IS DISTINCT FROM s.title
                OR ta.region IS DISTINCT FROM s.region
                OR ta.language IS DISTINCT FROM s.language
                OR ta.types IS DISTINCT FROM (
                    CASE WHEN s.types IS NULL THEN NULL ELSE string_to_array(s.types, ',') END
                )
                OR ta.attributes IS DISTINCT FROM (
                    CASE WHEN s.attributes IS NULL THEN NULL ELSE string_to_array(s.attributes, ',') END
                )
                OR ta.is_original IS DISTINCT FROM s.is_original
              );
            """)
