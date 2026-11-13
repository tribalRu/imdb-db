"""import name basic dataset"""

import asyncpg
from src.import_base import IngestDataset


class IngestNameBasics(IngestDataset):
    """ingest dataset"""

    DATASET_NAME = "name.basics.tsv"
    REBUILD_INDEXES = (
        (
            "ix_people_primary_name_trgm",
            "CREATE INDEX IF NOT EXISTS ix_people_primary_name_trgm " "ON people USING GIN (primary_name gin_trgm_ops)",
        ),
    )

    async def create_staging_table(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            CREATE TEMP TABLE IF NOT EXISTS {self.staging_table} (
                nconst TEXT,
                primary_name TEXT,
                birth_year SMALLINT,
                death_year SMALLINT,
                primary_professions TEXT,
                known_for_titles TEXT
            ) ON COMMIT DROP;
            """)

    async def merge_into_final(self, conn: asyncpg.Connection) -> None:
        if await self._is_first_import(conn):
            await self._insert_first_import(conn)
            return

        await self._upsert_existing(conn)

    async def _is_first_import(self, conn: asyncpg.Connection) -> bool:
        return await self._is_table_empty(conn, "people")

    async def _insert_first_import(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO people (
                nconst,
                primary_name,
                birth_year,
                death_year,
                primary_professions,
                known_for_titles
            )
            SELECT
                nconst,
                primary_name,
                birth_year,
                death_year,
                string_to_array(primary_professions, ','),
                string_to_array(known_for_titles, ',')
            FROM {self.staging_table}
            """)

    async def _upsert_existing(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f"""
            INSERT INTO people (
                nconst,
                primary_name,
                birth_year,
                death_year,
                primary_professions,
                known_for_titles
            )
            SELECT
                nconst,
                primary_name,
                birth_year,
                death_year,
                string_to_array(primary_professions, ','),
                string_to_array(known_for_titles, ',')
            FROM {self.staging_table}
            ON CONFLICT (nconst) DO UPDATE
            SET
                primary_name = EXCLUDED.primary_name,
                birth_year = EXCLUDED.birth_year,
                death_year = EXCLUDED.death_year,
                primary_professions = EXCLUDED.primary_professions,
                known_for_titles = EXCLUDED.known_for_titles
            WHERE
                people.primary_name IS DISTINCT FROM EXCLUDED.primary_name
                OR people.birth_year IS DISTINCT FROM EXCLUDED.birth_year
                OR people.death_year IS DISTINCT FROM EXCLUDED.death_year
                OR people.primary_professions IS DISTINCT FROM EXCLUDED.primary_professions
                OR people.known_for_titles IS DISTINCT FROM EXCLUDED.known_for_titles;
            """)
