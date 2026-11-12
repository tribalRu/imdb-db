"""import interface"""

import asyncio
import logging
from collections import defaultdict
from typing import Type

import asyncpg
import config
from src.import_base import IngestDataset
from src.import_name_basic import IngestNameBasics
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


async def import_datasets(dataset_names: list[str] | None = None, force: bool = False) -> None:
    """run all imports, or selected imports by dataset names"""

    selected_classes, selected_dataset_names = resolve_datasets(dataset_names)

    if _IMPORT_LOCK.locked():
        raise ImportAlreadyRunningError("Another dataset import is already running.")

    async with _IMPORT_LOCK:
        pool = await asyncpg.create_pool(dsn=config.DATABASE_URL_SYNC)
        try:
            logger.info(
                "Starting dataset imports datasets=%s force=%s",
                ", ".join(selected_dataset_names),
                force,
            )

            for ingest_class in selected_classes:
                await ingest_class(pool=pool, force=force).run()
        finally:
            await pool.close()

    clean_cache_dir()
