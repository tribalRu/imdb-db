"""import dataset base functionality"""

import asyncio
import gzip
import logging
import shutil
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncIterator, ClassVar, cast

import aiohttp
import asyncpg
import config
from database import AsyncSessionLocal
from models import ImportTask
from sqlalchemy import func, select
from src.datasets import DATASET_TABLE_MAP
from src.import_progress import progress_tracker

logger = logging.getLogger(__name__)


def parse_pg_tag_count(tag: str | None) -> int:
    """Parse row count from PostgreSQL command tag (e.g. 'INSERT 0 45000' -> 45000, 'UPDATE 120' -> 120)."""
    if not tag:
        return 0
    try:
        return int(tag.strip().split()[-1])
    except Exception:
        return 0


class CountingReader:
    """Wrapper around a binary file-like object to count uncompressed bytes read and report live progress."""

    def __init__(self, file_obj, total_bytes: int = 0, on_progress=None):
        self._file_obj = file_obj
        self.total_bytes = total_bytes
        self.bytes_read = 0
        self._on_progress = on_progress
        self._last_report = 0.0

    def read(self, size: int = -1) -> bytes:
        chunk = self._file_obj.read(size)
        if chunk:
            self.bytes_read += len(chunk)
            now = time.monotonic()
            if self._on_progress and now - self._last_report >= 0.2:
                self._last_report = now
                fileobj = getattr(self._file_obj, "fileobj", self._file_obj)
                tell_fn = getattr(fileobj, "tell", None)
                pos = tell_fn() if tell_fn else self.bytes_read
                self._on_progress(pos, self.total_bytes, self.bytes_read)
        elif self._on_progress and self.total_bytes > 0:
            self._on_progress(self.total_bytes, self.total_bytes, self.bytes_read)
        return chunk

    def close(self) -> None:
        self._file_obj.close()


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
        """raw extracted file size in bytes (or bytes streamed if not uncompressed)"""
        if self.tsv_path.exists():
            return self.tsv_path.stat().st_size
        return getattr(self, "_raw_bytes_streamed", 0)

    @property
    def url(self) -> str:
        """download url"""
        return f"{self.BASE_URL}/{self.dataset_name}.gz"

    @property
    def staging_table(self) -> str:
        """staging table"""
        dataset_slug = self.dataset_name.removesuffix(".tsv").replace(".", "_")
        return f"staging_{dataset_slug}"

    def _open_data_stream(self) -> CountingReader:
        """Open binary stream directly from cached tsv or stream from gz archive."""

        def _report(pos: int, total: int, raw_bytes: int) -> None:
            progress_tracker.update_active_detail(
                dataset_name=self.dataset_name,
                stage="copying",
                bytes_current=pos,
                bytes_total=total,
                uncompressed_bytes=raw_bytes,
                detail=f"Streaming COPY into {self.staging_table}",
            )

        if self.tsv_path.exists():
            total = self.tsv_path.stat().st_size
            return CountingReader(open(self.tsv_path, "rb"), total_bytes=total, on_progress=_report)
        if self.gz_path.exists():
            total = self.gz_path.stat().st_size
            return CountingReader(gzip.open(self.gz_path, "rb"), total_bytes=total, on_progress=_report)
        raise FileNotFoundError(f"Neither {self.tsv_path} nor {self.gz_path} exists.")

    async def run(self) -> None:
        """run download and import"""
        if not self.force and await self._is_already_imported():
            logger.info("skip, dataset %s already imported", self.dataset_name)
            return

        import_start_time = datetime.now(timezone.utc)
        start = perf_counter()
        import_task_id = await self._start_import_task(import_start_time)

        backend_pid: int | None = None
        try:
            logger.info("import started dataset=%s", self.dataset_name)
            progress_tracker.set_stage(
                self.dataset_name,
                "downloading",
                detail="Checking or downloading archive from IMDb",
            )
            await self._download_if_needed()

            async with self.pool.acquire() as conn:
                db_conn = cast(asyncpg.Connection, conn)
                backend_pid = db_conn.get_server_pid()
                target_table = DATASET_TABLE_MAP.get(self.dataset_name)
                await self._execute_import_session(db_conn, target_table)

            duration = perf_counter() - start
            progress_tracker.complete_dataset(self.dataset_name, duration)
            await self._finish_import_task(
                import_task_id,
                duration=duration,
                status="completed",
            )
        except (asyncio.CancelledError, Exception) as exc:
            await self._cancel_backend(backend_pid)
            duration = perf_counter() - start
            progress_tracker.fail_dataset(self.dataset_name, str(exc), duration)
            await self._finish_import_task(
                import_task_id,
                duration=duration,
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

        if self.tsv_path.exists() and self.gz_path.exists():
            self.gz_path.unlink()

    async def _cancel_backend(self, backend_pid: int | None) -> None:
        """Cancel the backend query in PostgreSQL if the task was cancelled or aborted."""
        if backend_pid and self.pool:
            try:
                async with self.pool.acquire() as cancel_conn:
                    await cancel_conn.execute("SELECT pg_cancel_backend($1)", backend_pid)
                    logger.info("canceled postgres backend pid=%s on task termination", backend_pid)
            except Exception:
                pass

    async def _toggle_autovacuum(self, db_conn: asyncpg.Connection, target_table: str | None, enable: bool) -> None:
        """Temporarily disable or re-enable autovacuum on target table during bulk load."""
        if not target_table:
            return
        sql = (
            f"ALTER TABLE {target_table} RESET (autovacuum_enabled)"
            if enable
            else f"ALTER TABLE {target_table} SET (autovacuum_enabled = false)"
        )
        try:
            await db_conn.execute(sql)
        except Exception:
            pass

    async def _execute_import_session(self, db_conn: asyncpg.Connection, target_table: str | None) -> None:
        """Run the ingestion session for this dataset with optimized session settings."""
        await db_conn.execute("SET statement_timeout = 0")
        temp_buffers = getattr(config, "IMPORT_TEMP_BUFFERS", "256MB")
        await db_conn.execute(f"SET temp_buffers = '{temp_buffers}'")

        await self._toggle_autovacuum(db_conn, target_table, enable=False)
        try:
            progress_tracker.set_stage(
                self.dataset_name,
                "copying",
                detail=f"Streaming COPY into {self.staging_table}",
            )
            await self._drop_rebuild_indexes(db_conn, target_table=target_table)
            await self._perform_ingest(db_conn, target_table)
        finally:
            await self._toggle_autovacuum(db_conn, target_table, enable=True)
            indexes_to_build = getattr(self, "discovered_indexes", self.REBUILD_INDEXES)
            idx_count = len(indexes_to_build)
            progress_tracker.set_stage(
                self.dataset_name,
                "indexing",
                detail=f"Rebuilding {idx_count} indexes" if idx_count else "Finalizing table",
            )
            await self._create_rebuild_indexes(db_conn)

        if target_table:
            logger.info("analyze final table table=%s", target_table)
            await db_conn.execute(f"ANALYZE {target_table}")

    async def _perform_ingest(self, db_conn: asyncpg.Connection, target_table: str | None) -> None:
        """Stream COPY into staging table, analyze, and merge into target table."""
        async with db_conn.transaction():
            await db_conn.execute("SET LOCAL synchronous_commit = off")
            work_mem = getattr(config, "IMPORT_WORK_MEM", "256MB")
            maint_mem = getattr(config, "IMPORT_MAINTENANCE_WORK_MEM", "2047MB")
            parallel_workers = getattr(config, "IMPORT_PARALLEL_WORKERS", 4)
            await db_conn.execute(f"SET LOCAL work_mem = '{work_mem}'")
            await db_conn.execute(f"SET LOCAL maintenance_work_mem = '{maint_mem}'")
            await db_conn.execute(f"SET LOCAL max_parallel_maintenance_workers = {parallel_workers}")

            logger.info("ingest into temporary table staging_table=%s", self.staging_table)
            await self.create_staging_table(db_conn)

            stream = self._open_data_stream()
            try:
                await db_conn.copy_to_table(
                    self.staging_table,
                    source=stream,
                    format="csv",
                    delimiter="\t",
                    null="\\N",
                    quote="\b",
                    header=True,
                )
                self._raw_bytes_streamed = stream.bytes_read
            finally:
                stream.close()

            await db_conn.execute(f"ANALYZE {self.staging_table}")
            staging_has_rows = await db_conn.fetchval(f"SELECT EXISTS (SELECT 1 FROM {self.staging_table})")
            logger.info("merge temporary table into final table")
            staging_rows = (
                await db_conn.fetchval(f"SELECT reltuples::bigint FROM pg_class WHERE relname = '{self.staging_table}'")
                or 0
            )
            progress_tracker.set_stage(
                self.dataset_name,
                "merging",
                detail=f"Merging staging into final table ({max(0, staging_rows):,} rows)...",
            )
            await self.merge_into_final(db_conn)

            if staging_has_rows and target_table:
                target_has_rows = await db_conn.fetchval(f"SELECT EXISTS (SELECT 1 FROM {target_table})")
                if not target_has_rows:
                    raise RuntimeError(
                        f"{self.dataset_name}: staging had rows but {target_table} stayed empty; "
                        "import the referenced dataset first"
                    )

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
                    total_bytes = resp.content_length or 0
                    downloaded = 0
                    with open(partial_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            f.write(chunk)
                            downloaded += len(chunk)
                            progress_tracker.update_active_detail(
                                dataset_name=self.dataset_name,
                                stage="downloading",
                                bytes_current=downloaded,
                                bytes_total=total_bytes,
                                detail="Downloading archive from IMDb",
                            )
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

    async def _drop_rebuild_indexes(self, conn: asyncpg.Connection, target_table: str | None = None) -> None:
        """
        Drop indexes that are too expensive to maintain during a bulk load.

        Discovers all non-primary-key indexes on target_table from pg_indexes
        and combines them with self.REBUILD_INDEXES so any existing index is safely
        dropped before the bulk load and recreated afterwards.
        """
        known: dict[str, str] = {idx[0]: idx[1] for idx in self.REBUILD_INDEXES}

        if target_table:
            try:
                rows = await conn.fetch(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = $1
                      AND indexname NOT LIKE '%_pkey'
                    """,
                    target_table,
                )
                for r in rows:
                    name = r["indexname"]
                    defn = r["indexdef"]
                    if name not in known:
                        known[name] = defn
            except Exception:
                logger.warning("failed to query pg_indexes for table=%s", target_table, exc_info=True)

        self.discovered_indexes = tuple(known.items())

        for index_name, _ in self.discovered_indexes:
            logger.info("drop index before bulk load index=%s dataset=%s", index_name, self.dataset_name)
            await conn.execute(f'DROP INDEX IF EXISTS "{index_name}"')

    async def _monitor_pg_index_progress(
        self,
        stop_event: asyncio.Event,
        total_indexes: int,
        index_items: list[dict[str, Any]],
    ) -> None:
        if not self.pool:
            return
        while not stop_event.is_set():
            try:
                async with self.pool.acquire() as mon_conn:
                    db_mon = cast(asyncpg.Connection, mon_conn)
                    rows = await db_mon.fetch("""
                        SELECT phase, blocks_total, blocks_done, tuples_total, tuples_done
                        FROM pg_stat_progress_create_index
                        WHERE datname = current_database()
                        LIMIT 1
                        """)
                    if rows and not stop_event.is_set():
                        r = rows[0]
                        phase = r["phase"]
                        blocks_total = r["blocks_total"] or 0
                        blocks_done = r["blocks_done"] or 0
                        pct_str = ""
                        sub_pct = 0.3
                        if blocks_total > 0:
                            pct_val = int((blocks_done / blocks_total) * 100)
                            pct_str = f" ({pct_val}% blocks)"
                            sub_pct = pct_val / 100

                        done_count = sum(1 for it in index_items if it["status"] == "completed")
                        running_names = [it["name"] for it in index_items if it["status"] == "running"]
                        current_name = running_names[0] if running_names else ""
                        overall_pct = int(((done_count + sub_pct) / total_indexes) * 100)
                        overall_pct = max(0, min(99, overall_pct))

                        detail_text = (
                            f"Building {current_name}: {phase}{pct_str}"
                            if current_name
                            else f"Building indexes: {phase}{pct_str}"
                        )
                        progress_tracker.update_active_detail(
                            self.dataset_name,
                            stage="indexing",
                            index_total=total_indexes,
                            index_completed=done_count,
                            index_items=index_items,
                            percent=overall_pct,
                            detail=detail_text,
                        )
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=0.4)
            except asyncio.TimeoutError:
                pass

    async def _build_single_rebuild_index(
        self,
        index_name: str,
        ddl: str,
        total_indexes: int,
        index_items: list[dict[str, Any]],
        conn: asyncpg.Connection | None = None,
    ) -> None:
        for it in index_items:
            if it["name"] == index_name:
                it["status"] = "running"
        idx_start = time.time()

        if conn is None and self.pool:
            async with self.pool.acquire() as c:
                db_c = cast(asyncpg.Connection, c)
                maint_mem = getattr(config, "IMPORT_MAINTENANCE_WORK_MEM", "2047MB")
                workers = getattr(config, "IMPORT_PARALLEL_WORKERS", 4)
                await db_c.execute(f"SET maintenance_work_mem = '{maint_mem}'")
                await db_c.execute(f"SET max_parallel_maintenance_workers = {workers}")
                logger.info("rebuild index concurrently index=%s dataset=%s", index_name, self.dataset_name)
                await db_c.execute(ddl)
        elif conn is not None:
            logger.info("rebuild index index=%s dataset=%s", index_name, self.dataset_name)
            await conn.execute(ddl)

        dur = time.time() - idx_start
        for it in index_items:
            if it["name"] == index_name:
                it["status"] = "completed"
                it["duration"] = round(dur, 2)

        done_count = sum(1 for it in index_items if it["status"] == "completed")
        overall_pct = int((done_count / total_indexes) * 100)
        progress_tracker.update_active_detail(
            self.dataset_name,
            stage="indexing",
            index_total=total_indexes,
            index_completed=done_count,
            index_items=index_items,
            percent=overall_pct,
            detail=f"Rebuilt {done_count}/{total_indexes} indexes ({index_name} in {round(dur, 1)}s)",
        )

    async def _create_rebuild_indexes(self, conn: asyncpg.Connection) -> None:
        """Recreate the indexes dropped by `_drop_rebuild_indexes` (concurrently if multiple)."""
        indexes_to_build = getattr(self, "discovered_indexes", self.REBUILD_INDEXES)
        if not indexes_to_build:
            progress_tracker.update_active_detail(
                self.dataset_name,
                stage="indexing",
                index_total=0,
                index_completed=0,
                index_items=[],
                percent=100,
                detail="No rebuild indexes required.",
            )
            return

        total_indexes = len(indexes_to_build)
        index_items: list[dict[str, Any]] = [
            {"name": idx, "status": "queued", "phase": None, "duration": None} for idx, _ in indexes_to_build
        ]

        progress_tracker.update_active_detail(
            self.dataset_name,
            stage="indexing",
            index_total=total_indexes,
            index_completed=0,
            index_items=index_items,
            percent=0,
            detail=f"Rebuilding {total_indexes} indexes...",
        )

        stop_event = asyncio.Event()
        monitor_task = asyncio.create_task(self._monitor_pg_index_progress(stop_event, total_indexes, index_items))

        try:
            if total_indexes > 1 and self.pool:
                tasks = [
                    self._build_single_rebuild_index(idx, ddl, total_indexes, index_items)
                    for idx, ddl in indexes_to_build
                ]
                await asyncio.gather(*tasks)
            else:
                for index_name, ddl in indexes_to_build:
                    await self._build_single_rebuild_index(index_name, ddl, total_indexes, index_items, conn=conn)
        finally:
            stop_event.set()
            await monitor_task

        progress_tracker.update_active_detail(
            self.dataset_name,
            stage="indexing",
            index_total=total_indexes,
            index_completed=total_indexes,
            index_items=index_items,
            percent=100,
            detail=f"Rebuilt all {total_indexes} indexes successfully.",
        )

    async def execute_initial_insert(self, conn: asyncpg.Connection, insert_sql: str) -> None:
        """Helper to run initial bulk insert with progress tracking."""
        progress_tracker.update_active_detail(
            self.dataset_name,
            stage="merging",
            substage="inserting_initial",
            percent=30,
            detail="Bulk inserting initial dataset records...",
        )
        tag = await conn.execute(insert_sql)
        inserted = parse_pg_tag_count(tag)
        progress_tracker.update_active_detail(
            self.dataset_name,
            stage="merging",
            substage="completed",
            percent=100,
            rows_inserted=inserted,
            rows_updated=0,
            detail=f"Initial insert complete: {inserted:,} rows",
        )

    async def execute_split_upsert(
        self,
        conn: asyncpg.Connection,
        insert_sql: str,
        update_sql: str,
    ) -> None:
        """Helper to run split upsert (insert where not exists + update where is distinct) with progress tracking."""
        progress_tracker.update_active_detail(
            self.dataset_name,
            stage="merging",
            substage="inserting",
            percent=25,
            detail="Phase 1/2: Inserting new records (INSERT WHERE NOT EXISTS)...",
        )
        tag_insert = await conn.execute(insert_sql)
        inserted = parse_pg_tag_count(tag_insert)

        progress_tracker.update_active_detail(
            self.dataset_name,
            stage="merging",
            substage="updating",
            percent=65,
            rows_inserted=inserted,
            rows_updated=0,
            detail=f"Phase 2/2: Updating modified records (+{inserted:,} inserted)...",
        )
        tag_update = await conn.execute(update_sql)
        updated = parse_pg_tag_count(tag_update)

        progress_tracker.update_active_detail(
            self.dataset_name,
            stage="merging",
            substage="completed",
            percent=100,
            rows_inserted=inserted,
            rows_updated=updated,
            detail=f"Merge complete: +{inserted:,} inserted, {updated:,} updated",
        )

    @abstractmethod
    async def create_staging_table(self, conn: asyncpg.Connection) -> None:
        """to implement: create staging table"""

    @abstractmethod
    async def merge_into_final(self, conn: asyncpg.Connection) -> None:
        """to implement: merge staging into final table"""
