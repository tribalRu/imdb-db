"""ingest trigger endpoint"""

import asyncio
import logging
import time
from typing import Any

import config
from api.params import ImportTaskParams
from database import AsyncSessionLocal
from dependencies import get_session
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from models import ImportTask
from pydantic import BaseModel
from schemas import ImportTaskOut, StatsResponse, TriggerIngestResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.datasets import DATASET_TABLE_MAP
from src.import_handler import (
    SUPPORTED_DATASET_NAMES,
    ImportAlreadyRunningError,
    import_datasets,
    is_import_running,
    resolve_datasets,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ingest"])
INDEX_TABLES: tuple[str, ...] = tuple(DATASET_TABLE_MAP.values())

# Counting every row of the large tables takes over a second. The dashboard
# does not need real-time numbers, so cache the result briefly and drop the
# cache right after an import finishes.
STATS_CACHE_TTL_SECONDS = 60.0
_stats_cache: dict[str, Any] | None = None
_stats_cache_at = 0.0
_stats_lock = asyncio.Lock()


def invalidate_stats_cache() -> None:
    """forget the cached /api/stats response"""
    global _stats_cache, _stats_cache_at
    _stats_cache = None
    _stats_cache_at = 0.0


def _human_bytes(size_bytes: int) -> str:
    """format bytes as a human-readable string"""
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    size = float(size_bytes)
    unit_idx = 0
    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024
        unit_idx += 1
    return f"{size:.2f} {units[unit_idx]}"


class TriggerIngestRequest(BaseModel):
    """request model for import trigger"""

    data_set: list[str] | None = None
    force: bool = False


async def _run_ingest_task(dataset_names: list[str] | None, force: bool) -> None:
    """background task wrapper with logging"""
    try:
        await import_datasets(dataset_names=dataset_names, force=force)
    except ImportAlreadyRunningError:
        logger.warning("dataset ingest skipped, another ingest is running datasets=%s", dataset_names)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("dataset ingest task failed datasets=%s force=%s", dataset_names, force)
    finally:
        invalidate_stats_cache()


@router.post("/ingest", response_model=TriggerIngestResponse)
async def trigger_ingest(
    background_tasks: BackgroundTasks,
    payload: TriggerIngestRequest | None = Body(default=None),
) -> dict[str, object]:
    """spawn ingest background task and return immediately"""
    dataset_names = payload.data_set if payload else None
    force = payload.force if payload else False

    try:
        _, selected_dataset_names = resolve_datasets(dataset_names)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(exc),
                "supported_data_set": list(SUPPORTED_DATASET_NAMES),
            },
        ) from exc

    if is_import_running():
        raise HTTPException(
            status_code=409,
            detail="Another ingest is already running. Wait for it to finish or check /api/import-tasks.",
        )

    background_tasks.add_task(_run_ingest_task, dataset_names, force)
    return {
        "message": "Ingest task scheduled",
        "data_set": selected_dataset_names,
        "force": force,
    }


@router.get("/import-tasks", response_model=list[ImportTaskOut])
async def list_import_tasks(
    params: ImportTaskParams = Depends(),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """list paginated import task records"""
    stmt = select(ImportTask)
    if params.status:
        stmt = stmt.where(ImportTask.status == params.status)
    stmt = stmt.order_by(ImportTask.import_start_time.desc()).limit(params.size).offset((params.page - 1) * params.size)
    result = await session.execute(stmt)
    tasks = list(result.scalars().all())
    return [
        {
            **task.model_dump(),
            "size_compressed_mb": round(task.size_compressed / (1024 * 1024), 2),
            "size_raw_mb": round(task.size_raw / (1024 * 1024), 2),
        }
        for task in tasks
    ]


async def _collect_index_stats(session: AsyncSession) -> dict[str, Any]:
    """compute dataset and index stats"""
    tasks_result = await session.execute(
        select(
            ImportTask.filename,
            func.count().label("runs"),
            func.max(ImportTask.import_start_time).label("last_import_time"),
            func.sum(ImportTask.size_compressed).label("size_compressed_total"),
            func.sum(ImportTask.size_raw).label("size_raw_total"),
            func.avg(ImportTask.duration).label("avg_duration"),
        )
        .where(ImportTask.status == "completed")
        .group_by(ImportTask.filename)
    )
    task_rows = tasks_result.all()
    task_stats_by_filename = {
        row.filename: {
            "runs": row.runs,
            "last_import_time": row.last_import_time.isoformat() if row.last_import_time else None,
            "size_compressed_total": int(row.size_compressed_total or 0),
            "size_raw_total": int(row.size_raw_total or 0),
            "avg_duration_seconds": float(row.avg_duration or 0.0),
        }
        for row in task_rows
    }

    table_doc_counts: dict[str, int] = {}
    table_disk_sizes: dict[str, int] = {}
    for table_name in INDEX_TABLES:
        count_result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        table_count = int(count_result.scalar_one())
        table_doc_counts[table_name] = table_count

        table_size_result = await session.execute(text(f"SELECT pg_total_relation_size('{table_name}')"))
        table_disk_sizes[table_name] = int(table_size_result.scalar_one())

    datasets = []
    for dataset_name in SUPPORTED_DATASET_NAMES:
        stats = task_stats_by_filename.get(dataset_name, {})
        table_name = DATASET_TABLE_MAP[dataset_name]
        document_count = table_doc_counts.get(table_name, 0)
        table_disk_size_bytes = table_disk_sizes.get(table_name, 0)
        datasets.append(
            {
                "dataset_name": dataset_name,
                "indexed": bool(stats),
                "document_count": document_count,
                "disk_usage_bytes": table_disk_size_bytes,
                "disk_usage_human": _human_bytes(table_disk_size_bytes),
                **stats,
            }
        )

    db_size_result = await session.execute(text("SELECT pg_database_size(current_database())"))
    db_size_bytes = int(db_size_result.scalar_one())

    cache_size_bytes = 0
    cache_dir = config.CACHE_DIR
    if cache_dir.exists():
        cache_size_bytes = sum(path.stat().st_size for path in cache_dir.rglob("*") if path.is_file())

    return {
        "datasets": datasets,
        "total_document_count": sum(dataset["document_count"] for dataset in datasets),
        "disk_usage_bytes": {
            "database": db_size_bytes,
            "cache": cache_size_bytes,
            "total": db_size_bytes + cache_size_bytes,
        },
        "disk_usage_human": {
            "database": _human_bytes(db_size_bytes),
            "cache": _human_bytes(cache_size_bytes),
            "total": _human_bytes(db_size_bytes + cache_size_bytes),
        },
        "import_task_count": sum(dataset["runs"] for dataset in datasets if dataset.get("runs")),
    }


@router.get("/stats", response_model=StatsResponse)
async def get_index_stats(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """dataset and index stats (cached briefly)"""
    global _stats_cache, _stats_cache_at

    if _stats_cache is not None and time.monotonic() - _stats_cache_at < STATS_CACHE_TTL_SECONDS:
        return _stats_cache

    async with _stats_lock:
        if _stats_cache is not None and time.monotonic() - _stats_cache_at < STATS_CACHE_TTL_SECONDS:
            return _stats_cache
        _stats_cache = await _collect_index_stats(session)
        _stats_cache_at = time.monotonic()
        return _stats_cache


async def warm_stats_cache() -> None:
    """pre-fill the stats cache in the background (called at startup)"""
    global _stats_cache, _stats_cache_at

    async with _stats_lock:
        if _stats_cache is not None:
            return
        async with AsyncSessionLocal() as session:
            _stats_cache = await _collect_index_stats(session)
            _stats_cache_at = time.monotonic()
