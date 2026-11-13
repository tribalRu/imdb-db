"""import title principals"""

import asyncpg
from src.import_base import IngestDataset


class IngestTitlePrincipals(IngestDataset):
    """ingest dataset"""

    DATASET_NAME = "title.principals.tsv"
    REBUILD_INDEXES = (
        (
            "ix_title_principals_nconst",
            "CREATE INDEX IF NOT EXISTS ix_title_principals_nconst ON title_principals (nconst)",
        ),
    )

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
            JOIN titles t ON t.tconst = s.tconst
            JOIN people p ON p.nconst = s.nconst
            """)

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
            JOIN titles t ON t.tconst = s.tconst
            JOIN people p ON p.nconst = s.nconst
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
