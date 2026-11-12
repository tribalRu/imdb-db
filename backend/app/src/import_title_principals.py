"""import title principals"""

import asyncpg
from src.import_base import IngestDataset


class IngestTitlePrincipals(IngestDataset):
    """ingest dataset"""

    DATASET_NAME = "title.principals.tsv"

    async def create_staging_table(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            CREATE TEMP TABLE IF NOT EXISTS {self.staging_table} (
                tconst TEXT,
                ordering INTEGER,
                nconst TEXT,
                category TEXT,
                job TEXT,
                characters TEXT
            ) ON COMMIT DROP;
            """)

    async def merge_into_final(self, conn: asyncpg.Connection) -> None:
        if await self._is_first_import(conn):
            await self._insert_first_import(conn)
            return

        await self._upsert_existing(conn)

    async def _is_first_import(self, conn: asyncpg.Connection) -> bool:
        return await self._is_table_empty(conn, "title_principals")

    async def _insert_first_import(self, conn: asyncpg.Connection) -> None:
        await self._drop_secondary_indexes(conn)
        try:
            await conn.execute(f"""
                INSERT INTO title_principals (
                    tconst,
                    ordering,
                    nconst,
                    category,
                    job,
                    characters
                )
                SELECT
                    s.tconst,
                    s.ordering,
                    s.nconst,
                    s.category,
                    s.job,
                    CASE
                        WHEN s.characters IS NULL THEN NULL
                        ELSE (
                            SELECT array_agg(value)
                            FROM jsonb_array_elements_text(s.characters::jsonb)
                        )
                    END
                FROM {self.staging_table} s
                WHERE EXISTS (
                    SELECT 1 FROM titles t WHERE t.tconst = s.tconst
                )
                AND EXISTS (
                    SELECT 1 FROM people p WHERE p.nconst = s.nconst
                )
                """)
        finally:
            await self._create_secondary_indexes(conn)

    async def _drop_secondary_indexes(self, conn: asyncpg.Connection) -> None:
        await conn.execute("DROP INDEX IF EXISTS ix_title_principals_nconst")

    async def _create_secondary_indexes(self, conn: asyncpg.Connection) -> None:
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_title_principals_nconst ON title_principals (nconst)")

    async def _upsert_existing(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO title_principals (
                tconst,
                ordering,
                nconst,
                category,
                job,
                characters
            )
            SELECT
                s.tconst,
                s.ordering,
                s.nconst,
                s.category,
                s.job,
                CASE
                    WHEN s.characters IS NULL THEN NULL
                    ELSE (
                        SELECT array_agg(value)
                        FROM jsonb_array_elements_text(s.characters::jsonb)
                    )
                END
            FROM {self.staging_table} s
            WHERE EXISTS (
                SELECT 1 FROM titles t WHERE t.tconst = s.tconst
            )
            AND EXISTS (
                SELECT 1 FROM people p WHERE p.nconst = s.nconst
            )
            ON CONFLICT (tconst, ordering) DO UPDATE
            SET
                nconst = EXCLUDED.nconst,
                category = EXCLUDED.category,
                job = EXCLUDED.job,
                characters = EXCLUDED.characters
            WHERE
                title_principals.nconst IS DISTINCT FROM EXCLUDED.nconst
                OR title_principals.category IS DISTINCT FROM EXCLUDED.category
                OR title_principals.job IS DISTINCT FROM EXCLUDED.job
                OR title_principals.characters IS DISTINCT FROM EXCLUDED.characters;
            """)
