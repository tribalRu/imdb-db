"""import title episodes"""

import asyncpg
from src.import_base import IngestDataset


class IngestTitleEpisodes(IngestDataset):
    """ingest dataset"""

    DATASET_NAME = "title.episode.tsv"
    REBUILD_INDEXES = (
        (
            "ix_episodes_parent_tconst",
            "CREATE INDEX IF NOT EXISTS ix_episodes_parent_tconst ON episodes (parent_tconst)",
        ),
    )

    async def create_staging_table(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            CREATE TEMP TABLE IF NOT EXISTS {self.staging_table} (
                tconst TEXT,
                parent_tconst TEXT,
                season_number INTEGER,
                episode_number INTEGER
            ) ON COMMIT DROP;
            """)

    async def merge_into_final(self, conn: asyncpg.Connection) -> None:
        if await self._is_first_import(conn):
            await self._insert_first_import(conn)
            return

        await self._upsert_existing(conn)

    async def _is_first_import(self, conn: asyncpg.Connection) -> bool:
        return await self._is_table_empty(conn, "episodes")

    async def _insert_first_import(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO episodes (
                tconst,
                parent_tconst,
                season_number,
                episode_number
            )
            SELECT
                e.tconst,
                e.parent_tconst,
                e.season_number,
                e.episode_number
            FROM {self.staging_table} e
            JOIN titles t ON t.tconst = e.tconst
            JOIN titles p ON p.tconst = e.parent_tconst
            """)

    async def _upsert_existing(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO episodes (
                tconst,
                parent_tconst,
                season_number,
                episode_number
            )
            SELECT
                e.tconst,
                e.parent_tconst,
                e.season_number,
                e.episode_number
            FROM {self.staging_table} e
            JOIN titles t ON t.tconst = e.tconst
            JOIN titles p ON p.tconst = e.parent_tconst
            ON CONFLICT (tconst) DO UPDATE
            SET
                parent_tconst = EXCLUDED.parent_tconst,
                season_number = EXCLUDED.season_number,
                episode_number = EXCLUDED.episode_number
            WHERE
                episodes.parent_tconst IS DISTINCT FROM EXCLUDED.parent_tconst
                OR episodes.season_number IS DISTINCT FROM EXCLUDED.season_number
                OR episodes.episode_number IS DISTINCT FROM EXCLUDED.episode_number;
            """)
