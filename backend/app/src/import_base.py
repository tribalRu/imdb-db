"""import dataset base functionality"""

import asyncio
import gzip
import logging
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import AsyncIterator, ClassVar, cast

import aiohttp
import asyncpg
import config
from database import AsyncSessionLocal
from models import ImportTask
from sqlalchemy import func, select
from src.datasets import DATASET_TABLE_MAP

logger = logging.getLogger(__name__)


class IngestDataset(ABC):
    """
    Base class for IMDb dataset ingestion using COPY + staging tables.
    """

    CHUNK_SIZE_LINES = 100_000
    BASE_URL = "https://datasets.imdbws.com"
    CACHE_DIR = config.CACHE_DIR
    DATASET_NAME: ClassVar[str] = ""
    # (index name, CREATE INDEX statement) pairs for indexes that are too
    # expensive to maintain row-by-row during a bulk load. They are dropped
    # before the COPY/merge and rebuilt once afterwards.
    REBUILD_INDEXES: ClassVar[tuple[tuple[str, str], ...]] = ()

    def __init__(self, pool: asyncpg.Pool, force: bool = False):
        if not self.DATASET_NAME:
            raise NotImplementedError(f"{self.__class__.__name__} must define DATASET_NAME")

        self.dataset_name = self.DATASET_NAME
        self.pool = pool
        self.force = force
        self.iso_date = datetime.now().date().isoformat()

    @property
    def gz_path(self) -> Path:
        """gzip path"""
        return Path(self.CACHE_DIR) / f"{self.dataset_name}_{self.iso_date}.gz"

    @property
    def tsv_path(self) -> Path:
        """tsv decompressed path"""
        return self.gz_path.with_suffix("")

    @property
    def gz_size(self) -> int:
        """compressed file size in bytes"""
        if self.gz_path.exists():
            return self.gz_path.stat().st_size

        return 0

    @property
    def tsv_size(self) -> int:
        """raw extracted file size in bytes"""
        if self.tsv_path.exists():
            return self.tsv_path.stat().st_size

        return 0

    @property
    def url(self) -> str:
        """download url"""
        return f"{self.BASE_URL}/{self.dataset_name}.gz"

    @property
    def staging_table(self) -> str:
        """staging table"""
        dataset_slug = self.dataset_name.removesuffix(".tsv").replace(".", "_")
        return f"staging_{dataset_slug}"

    async def run(self) -> None:
        """run download and import"""
        if not self.force and await self._is_already_imported():
            logger.info("skip, dataset %s already imported", self.dataset_name)
            return

        import_start_time = datetime.now(timezone.utc)
        start = perf_counter()
        import_task_id = await self._start_import_task(import_start_time)

        try:
            logger.info("import started dataset=%s", self.dataset_name)
            await self._download_if_needed()
            await asyncio.to_thread(self._extract_if_needed)

            async with self.pool.acquire() as conn:
                db_conn = cast(asyncpg.Connection, conn)
                target_table = DATASET_TABLE_MAP.get(self.dataset_name)
                try:
                    await self._drop_rebuild_indexes(db_conn)
                    async with conn.transaction():
                        await db_conn.execute("SET LOCAL synchronous_commit = off")
                        logger.info("ingest into temporary table staging_table=%s", self.staging_table)
                        await self.create_staging_table(db_conn)

                        async for lines in self._read_tsv_in_chunks():
                            await self.copy_chunk(db_conn, lines)

                        await db_conn.execute(f"ANALYZE {self.staging_table}")
                        staging_has_rows = await db_conn.fetchval(f"SELECT EXISTS (SELECT 1 FROM {self.staging_table})")
                        logger.info("merge temporary table into final table")
                        await self.merge_into_final(db_conn)

                        # A merge into a dependent table joins against titles/people.
                        # If those are missing, every row is filtered out and the
                        # import would otherwise be recorded as a success.
                        if staging_has_rows and target_table:
                            target_has_rows = await db_conn.fetchval(f"SELECT EXISTS (SELECT 1 FROM {target_table})")
                            if not target_has_rows:
                                raise RuntimeError(
                                    f"{self.dataset_name}: staging had rows but {target_table} stayed empty; "
                                    "import the referenced dataset first"
                                )
                finally:
                    await self._create_rebuild_indexes(db_conn)

                if target_table:
                    logger.info("analyze final table table=%s", target_table)
                    await db_conn.execute(f"ANALYZE {target_table}")

            await self._finish_import_task(
                import_task_id,
                duration=perf_counter() - start,
                status="completed",
            )
        except Exception:
            await self._finish_import_task(
                import_task_id,
                duration=perf_counter() - start,
                status="failed",
            )
            raise

        logger.info(
            "import completed dataset=%s size_compressed=%s size_raw=%s duration=%.3fs",
            self.dataset_name,
            self.gz_size,
            self.tsv_size,
            perf_counter() - start,
        )

        if Path(self.gz_path).exists():
            Path(self.gz_path).unlink()

    async def _is_already_imported(self) -> bool:
        """dataset has at least one completed import task row"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count())
                .select_from(ImportTask)
                .where(ImportTask.filename == self.dataset_name, ImportTask.status == "completed")
            )
            return bool(result.scalar_one())

    async def _download_if_needed(self) -> None:
        """download if not exist on file path"""
        if self.gz_path.exists() or self.tsv_path.exists():
            return

        self.gz_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("download dataset to gz_path=%s", self.gz_path)
        partial_path = self.gz_path.with_suffix(f"{self.gz_path.suffix}.part")
        partial_path.unlink(missing_ok=True)

        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=300)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.url) as resp:
                    resp.raise_for_status()
                    with open(partial_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            f.write(chunk)
            partial_path.replace(self.gz_path)
        except Exception:
            partial_path.unlink(missing_ok=True)
            raise

    def _extract_if_needed(self) -> None:
        """extract if not extracted"""
        if self.tsv_path.exists():
            return

        logger.info("extract gz archive to tsv_path=%s", self.tsv_path)
        partial_path = self.tsv_path.parent / f"{self.tsv_path.name}.part"
        try:
            with gzip.open(self.gz_path, "rb") as gz:
                with open(partial_path, "wb") as out:
                    shutil.copyfileobj(gz, out)
            partial_path.replace(self.tsv_path)
        except Exception:
            partial_path.unlink(missing_ok=True)
            raise

    async def _start_import_task(self, import_start_time: datetime) -> int:
        """Persist a running task row so progress is visible while importing."""
        import_task = ImportTask(
            filename=self.dataset_name,
            size_compressed=0,
            size_raw=0,
            import_start_time=import_start_time,
            duration=0.0,
            status="running",
        )
        async with AsyncSessionLocal() as session:
            session.add(import_task)
            await session.commit()
            await session.refresh(import_task)

        if import_task.id is None:
            raise RuntimeError("failed to create import task")
        return int(import_task.id)

    async def _finish_import_task(self, task_id: int, duration: float, status: str) -> None:
        """Update the task row with final sizes and status."""
        async with AsyncSessionLocal() as session:
            import_task = await session.get(ImportTask, task_id)
            if import_task is None:
                logger.warning("import task disappeared task_id=%s", task_id)
                return
            import_task.size_compressed = self.gz_size
            import_task.size_raw = self.tsv_size
            import_task.duration = duration
            import_task.status = status
            await session.commit()

    async def _read_tsv_in_chunks(self) -> AsyncIterator[list[str]]:
        """partial read tsv file"""
        loop = asyncio.get_running_loop()

        def generator():
            with open(self.tsv_path, "r", encoding="utf-8") as f:
                _ = next(f)  # skip header
                chunk = []
                for line in f:
                    chunk.append(line.rstrip("\n"))
                    if len(chunk) >= self.CHUNK_SIZE_LINES:
                        yield chunk
                        chunk = []
                if chunk:
                    yield chunk

        iterator = iter(generator())
        while True:
            chunk = await loop.run_in_executor(None, lambda: next(iterator, None))
            if chunk is None:
                break
            yield chunk

    async def copy_chunk(self, conn: asyncpg.Connection, lines: list[str]) -> None:
        """COPY raw TSV lines into staging table"""
        buf = BytesIO()
        for line in lines:
            buf.write(line.encode("utf-8"))
            buf.write(b"\n")
        buf.seek(0)

        await conn.copy_to_table(
            self.staging_table,
            source=buf,
            format="csv",
            delimiter="\t",
            null="\\N",
            quote="\b",
        )

    async def _is_table_empty(self, conn: asyncpg.Connection, table_name: str) -> bool:
        """check if final target table has rows"""
        return bool(await conn.fetchval(f"SELECT NOT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)"))

    async def _drop_rebuild_indexes(self, conn: asyncpg.Connection) -> None:
        """
        Drop indexes that are too expensive to maintain during a bulk load.

        A GIN trigram index costs far more per inserted row than a sequential
        build at the end, and the merge also updates almost every row. Dropping
        them first turned multi-hour imports into minutes on the full dataset.
        """
        for index_name, _ in self.REBUILD_INDEXES:
            logger.info("drop index before bulk load index=%s dataset=%s", index_name, self.dataset_name)
            await conn.execute(f'DROP INDEX IF EXISTS "{index_name}"')

    async def _create_rebuild_indexes(self, conn: asyncpg.Connection) -> None:
        """Recreate the indexes dropped by `_drop_rebuild_indexes` in one pass."""
        for index_name, ddl in self.REBUILD_INDEXES:
            logger.info("rebuild index index=%s dataset=%s", index_name, self.dataset_name)
            await conn.execute(ddl)

    @abstractmethod
    async def create_staging_table(self, conn: asyncpg.Connection) -> None:
        """to implement: create staging table"""

    @abstractmethod
    async def merge_into_final(self, conn: asyncpg.Connection) -> None:
        """to implement: merge staging into final table"""
