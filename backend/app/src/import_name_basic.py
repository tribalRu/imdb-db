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
                s.nconst,
                s.primary_name,
                s.birth_year,
                s.death_year,
                string_to_array(s.primary_professions, ','),
                string_to_array(s.known_for_titles, ',')
            FROM {self.staging_table} s
            WHERE NOT EXISTS (
                SELECT 1 FROM people p WHERE p.nconst = s.nconst
            );

            UPDATE people p
            SET
                primary_name = s.primary_name,
                birth_year = s.birth_year,
                death_year = s.death_year,
                primary_professions = string_to_array(s.primary_professions, ','),
                known_for_titles = string_to_array(s.known_for_titles, ',')
            FROM {self.staging_table} s
            WHERE p.nconst = s.nconst
              AND (
                p.primary_name IS DISTINCT FROM s.primary_name
                OR p.birth_year IS DISTINCT FROM s.birth_year
                OR p.death_year IS DISTINCT FROM s.death_year
                OR p.primary_professions IS DISTINCT FROM string_to_array(s.primary_professions, ',')
                OR p.known_for_titles IS DISTINCT FROM string_to_array(s.known_for_titles, ',')
              );
            """)
