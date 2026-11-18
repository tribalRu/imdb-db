"""import title ratings"""

import asyncpg
from src.import_base import IngestDataset


class IngestTitleRatings(IngestDataset):
    """ingest dataset"""

    DATASET_NAME = "title.ratings.tsv"

    async def create_staging_table(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            CREATE TEMP TABLE IF NOT EXISTS {self.staging_table} (
                tconst TEXT,
                average_rating REAL,
                num_votes INT
            ) ON COMMIT DROP;
            """)

    async def merge_into_final(self, conn: asyncpg.Connection) -> None:
        if await self._is_first_import(conn):
            await self._insert_first_import(conn)
            return

        await self._upsert_existing(conn)

    async def _is_first_import(self, conn: asyncpg.Connection) -> bool:
        return await self._is_table_empty(conn, "title_ratings")

    async def _insert_first_import(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO title_ratings (tconst, average_rating, num_votes)
            SELECT
                s.tconst,
                s.average_rating,
                s.num_votes
            FROM {self.staging_table} s
            JOIN titles t ON t.tconst = s.tconst
            """)

    async def _upsert_existing(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO title_ratings (tconst, average_rating, num_votes)
            SELECT
                s.tconst,
                s.average_rating,
                s.num_votes
            FROM {self.staging_table} s
            JOIN titles t ON t.tconst = s.tconst
            WHERE NOT EXISTS (
                SELECT 1 FROM title_ratings tr WHERE tr.tconst = s.tconst
            );

            UPDATE title_ratings tr
            SET
                average_rating = s.average_rating,
                num_votes = s.num_votes
            FROM {self.staging_table} s
            WHERE tr.tconst = s.tconst
              AND (
                tr.average_rating IS DISTINCT FROM s.average_rating
                OR tr.num_votes IS DISTINCT FROM s.num_votes
              );
            """)
