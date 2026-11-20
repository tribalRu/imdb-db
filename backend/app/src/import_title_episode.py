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
        await self.execute_initial_insert(
            conn,
            f"""
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
            """,
        )

    async def _upsert_existing(self, conn: asyncpg.Connection) -> None:
        await self.execute_split_upsert(
            conn,
            insert_sql=f"""
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
            WHERE NOT EXISTS (
                SELECT 1 FROM episodes ep WHERE ep.tconst = e.tconst
            )
            """,
            update_sql=f"""
            UPDATE episodes ep
            SET
                parent_tconst = e.parent_tconst,
                season_number = e.season_number,
                episode_number = e.episode_number
            FROM {self.staging_table} e
            JOIN titles t ON t.tconst = e.tconst
            JOIN titles p ON p.tconst = e.parent_tconst
            WHERE ep.tconst = e.tconst
              AND (
                ep.parent_tconst IS DISTINCT FROM e.parent_tconst
                OR ep.season_number IS DISTINCT FROM e.season_number
                OR ep.episode_number IS DISTINCT FROM e.episode_number
              )
            """,
        )
