"""import interface"""

import asyncio
import logging
from collections import defaultdict
from typing import Type

import asyncpg
import config
from database import AsyncSessionLocal
from models import ImportTask
from sqlalchemy import update
from src.import_base import IngestDataset
from src.import_name_basic import IngestNameBasics
from src.import_progress import progress_tracker
from src.import_title_akas import IngestTitleAkas
from src.import_title_basic import IngestTitleBasics
from src.import_title_episode import IngestTitleEpisodes
from src.import_title_principals import IngestTitlePrincipals
from src.import_title_ratings import IngestTitleRatings

logger = logging.getLogger(__name__)

INGEST_CLASSES: tuple[Type[IngestDataset], ...] = (
    IngestTitleBasics,
    IngestNameBasics,
    IngestTitleRatings,
    IngestTitleEpisodes,
    IngestTitleAkas,
    IngestTitlePrincipals,
)
INGEST_BY_DATASET_NAME: dict[str, Type[IngestDataset]] = {
    ingest_class.DATASET_NAME: ingest_class for ingest_class in INGEST_CLASSES
}
SUPPORTED_DATASET_NAMES: tuple[str, ...] = tuple(INGEST_BY_DATASET_NAME.keys())
CACHE_DIR = config.CACHE_DIR
DATASET_TO_KEEP = config.DATASET_TO_KEEP

_IMPORT_LOCK = asyncio.Lock()


class ImportAlreadyRunningError(RuntimeError):
    """Raised when a dataset import is requested while another one is running."""


def is_import_running() -> bool:
    """Return True while a dataset import is in progress."""
    return _IMPORT_LOCK.locked()


def resolve_datasets(
    dataset_names: list[str] | None,
) -> tuple[list[Type[IngestDataset]], list[str]]:
    """resolve and validate selected dataset names"""
    if dataset_names is None:
        return list(INGEST_BY_DATASET_NAME.values()), list(SUPPORTED_DATASET_NAMES)

    if not dataset_names:
        raise ValueError("data_set must contain at least one dataset name, or be omitted to import everything.")

    selected_classes: list[Type[IngestDataset]] = []
    selected_dataset_names: list[str] = []
    for dataset_name in dataset_names:
        ingest_class = INGEST_BY_DATASET_NAME.get(dataset_name)
        if ingest_class is None:
            raise ValueError(f"Unsupported dataset_name: {dataset_name}")
        selected_classes.append(ingest_class)
        selected_dataset_names.append(dataset_name)

    return selected_classes, selected_dataset_names


def clean_cache_dir():
    """clean cache dir based on env var"""
    if DATASET_TO_KEEP is None:
        return

    if not DATASET_TO_KEEP.isdigit():
        raise ValueError("failed to parse DATASET_TO_KEEP, expected a none negative integer.")

    dataset_to_keep_int = int(DATASET_TO_KEEP)

    paths = sorted(list(CACHE_DIR.glob("*.tsv_*")), reverse=True)
    archives = defaultdict(list)

    for path in paths:
        archive_type = path.name.split(".tsv_", 1)[0]
        archives[archive_type].append(path)

    for paths in archives.values():
        for path in paths[dataset_to_keep_int:]:
            logger.info("clean cached archive path=%s", path)
            path.unlink()


async def reconcile_stale_import_tasks() -> int:
    """
    Mark import tasks left in `running` state by a previous process as failed.

    A task is only `running` while `import_datasets` holds the process-wide
    lock. If the process is restarted mid-import, that row would otherwise stay
    `running` forever and hide the failure from the dashboard.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(update(ImportTask).where(ImportTask.status == "running").values(status="failed"))
        await session.commit()
        stale_count = result.rowcount or 0

    if stale_count:
        logger.warning("marked stale import tasks as failed count=%s", stale_count)
    return stale_count


async def import_datasets(dataset_names: list[str] | None = None, force: bool = False) -> None:
    """run all imports, or selected imports by dataset names"""

    selected_classes, selected_dataset_names = resolve_datasets(dataset_names)

    if _IMPORT_LOCK.locked():
        raise ImportAlreadyRunningError("Another dataset import is already running.")

    async with _IMPORT_LOCK:
        progress_tracker.start(selected_dataset_names)
        pool = await asyncpg.create_pool(dsn=config.DATABASE_URL_SYNC)
        try:
            logger.info(
                "Starting dataset imports datasets=%s force=%s",
                ", ".join(selected_dataset_names),
                force,
            )

            # If both independent base datasets (titles and people) are requested,
            # run them in parallel to utilize multiple CPU cores and I/O channels.
            tier1 = [c for c in (IngestTitleBasics, IngestNameBasics) if c in selected_classes]
            remaining = [c for c in selected_classes if c not in tier1]

            if len(tier1) > 1:
                logger.info(
                    "Running independent base datasets concurrently: %s",
                    ", ".join(c.DATASET_NAME for c in tier1),
                )
                prefetch_task: asyncio.Task | None = None
                if remaining:
                    prefetch_task = asyncio.create_task(remaining[0](pool=pool, force=force)._download_if_needed())

                try:
                    await asyncio.gather(*(c(pool=pool, force=force).run() for c in tier1))
                finally:
                    if prefetch_task:
                        try:
                            await prefetch_task
                        except Exception:
                            logger.warning("prefetch failed", exc_info=True)

                work_queue = remaining
            else:
                work_queue = selected_classes

            prefetch_task = None
            for idx, ingest_class in enumerate(work_queue):
                # Trigger background prefetch for the next dataset
                if idx + 1 < len(work_queue):
                    next_ingest = work_queue[idx + 1](pool=pool, force=force)
                    prefetch_task = asyncio.create_task(next_ingest._download_if_needed())
                else:
                    prefetch_task = None

                try:
                    await ingest_class(pool=pool, force=force).run()
                finally:
                    if prefetch_task:
                        try:
                            await prefetch_task
                        except Exception:
                            logger.warning(
                                "prefetch failed for dataset=%s",
                                work_queue[idx + 1].DATASET_NAME,
                                exc_info=True,
                            )
                        prefetch_task = None
        finally:
            await pool.close()
            progress_tracker.finish()

    try:
        clean_cache_dir()
    except Exception:  # pylint: disable=broad-exception-caught
        # Cleanup is best-effort: do not fail an otherwise successful import.
        logger.warning("cache cleanup failed", exc_info=True)
