"""Real-time progress tracking for dataset ingestion."""

import time
from typing import Any


class ImportProgress:
    """In-memory tracker for active and recent dataset imports."""

    def __init__(self) -> None:
        self.is_running: bool = False
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.total_count: int = 0
        self.completed_count: int = 0
        self.datasets: list[str] = []
        self.stages: dict[str, str] = {}
        self.durations: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.active_datasets: set[str] = set()

        # Detailed metrics per dataset
        self.active_details: dict[str, dict[str, Any]] = {}
        self.stage_start_times: dict[str, float] = {}

    def start(self, dataset_names: list[str]) -> None:
        self.is_running = True
        self.started_at = time.time()
        self.finished_at = None
        self.total_count = len(dataset_names)
        self.completed_count = 0
        self.datasets = list(dataset_names)
        self.stages = {name: "queued" for name in dataset_names}
        self.durations = {}
        self.errors = {}
        self.active_datasets = set()
        self.active_details = {}
        self.stage_start_times = {}

    def set_stage(self, dataset_name: str, stage: str, detail: str = "") -> None:
        if stage in ("completed", "failed"):
            self.active_datasets.discard(dataset_name)
        else:
            self.active_datasets.add(dataset_name)
        self.stages[dataset_name] = stage
        self.stage_start_times[f"{dataset_name}:{stage}"] = time.time()

        if stage not in ("completed", "failed"):
            self.active_details[dataset_name] = {
                "stage": stage,
                "detail": detail or stage,
                "bytes_current": 0,
                "bytes_total": 0,
                "uncompressed_bytes": 0,
                "percent": 0,
                "speed_mb_s": 0.0,
                "eta_seconds": None,
                "substage": None,
                "rows_inserted": None,
                "rows_updated": None,
                "index_total": None,
                "index_completed": None,
                "index_items": [],
            }

    def update_active_detail(
        self,
        dataset_name: str,
        stage: str,
        bytes_current: int = 0,
        bytes_total: int = 0,
        uncompressed_bytes: int = 0,
        detail: str = "",
        percent: int | None = None,
        speed_mb_s: float | None = None,
        eta_seconds: float | None = None,
        substage: str | None = None,
        rows_inserted: int | None = None,
        rows_updated: int | None = None,
        index_total: int | None = None,
        index_completed: int | None = None,
        index_items: list[dict[str, Any]] | None = None,
    ) -> None:
        existing = self.active_details.get(dataset_name, {})
        start_t = self.stage_start_times.get(f"{dataset_name}:{stage}", time.time())
        elapsed = max(0.1, time.time() - start_t)

        if speed_mb_s is None:
            speed_mb_s = 0.0
            if bytes_current > 0 and elapsed > 0.5:
                speed_mb_s = round((bytes_current / elapsed) / (1024 * 1024), 1)

        calc_percent = 0
        if bytes_total > 0:
            calc_percent = min(100, int((bytes_current / bytes_total) * 100))
        elif percent is not None:
            calc_percent = percent
        else:
            calc_percent = existing.get("percent", 0)

        if eta_seconds is None:
            if speed_mb_s > 0 and bytes_total > bytes_current:
                eta_seconds = round((bytes_total - bytes_current) / (speed_mb_s * 1024 * 1024), 1)
            else:
                eta_seconds = existing.get("eta_seconds")

        self.active_details[dataset_name] = {
            "stage": stage,
            "detail": detail or existing.get("detail", stage),
            "bytes_current": bytes_current or existing.get("bytes_current", 0),
            "bytes_total": bytes_total or existing.get("bytes_total", 0),
            "uncompressed_bytes": uncompressed_bytes or existing.get("uncompressed_bytes", 0),
            "percent": calc_percent,
            "speed_mb_s": speed_mb_s,
            "eta_seconds": eta_seconds,
            "substage": substage if substage is not None else existing.get("substage"),
            "rows_inserted": rows_inserted if rows_inserted is not None else existing.get("rows_inserted"),
            "rows_updated": rows_updated if rows_updated is not None else existing.get("rows_updated"),
            "index_total": index_total if index_total is not None else existing.get("index_total"),
            "index_completed": index_completed if index_completed is not None else existing.get("index_completed"),
            "index_items": index_items if index_items is not None else existing.get("index_items", []),
        }

    def complete_dataset(self, dataset_name: str, duration: float) -> None:
        self.active_datasets.discard(dataset_name)
        self.stages[dataset_name] = "completed"
        self.durations[dataset_name] = round(duration, 2)
        self.active_details.pop(dataset_name, None)
        self.completed_count = sum(1 for s in self.stages.values() if s == "completed")

    def fail_dataset(self, dataset_name: str, error: str, duration: float) -> None:
        self.active_datasets.discard(dataset_name)
        self.stages[dataset_name] = "failed"
        self.errors[dataset_name] = error
        self.durations[dataset_name] = round(duration, 2)
        self.active_details.pop(dataset_name, None)

    def finish(self) -> None:
        self.is_running = False
        self.finished_at = time.time()
        self.active_datasets.clear()
        self.active_details.clear()

    def to_dict(self) -> dict[str, Any]:
        elapsed = 0.0
        if self.started_at:
            end_time = self.finished_at or time.time()
            elapsed = round(end_time - self.started_at, 1)

        items = []
        for name in self.datasets:
            items.append(
                {
                    "name": name,
                    "status": self.stages.get(name, "queued"),
                    "duration": self.durations.get(name),
                    "error": self.errors.get(name),
                }
            )

        percent = 0
        if self.total_count > 0:
            percent = int((self.completed_count / self.total_count) * 100)

        # Primary active item details
        current_dataset = None
        current_detail = None
        if self.active_datasets:
            current_dataset = sorted(list(self.active_datasets))[0]
            current_detail = self.active_details.get(current_dataset)

        # Stepper for current dataset
        stage_steps = []
        current_stage = self.stages.get(current_dataset, "") if current_dataset else ""

        step_order = ["downloading", "copying", "merging", "indexing"]
        step_labels = {
            "downloading": "Download",
            "copying": "Stream COPY",
            "merging": "Merge / Upsert",
            "indexing": "Index Rebuild",
        }

        current_idx = step_order.index(current_stage) if current_stage in step_order else -1
        for idx, step_id in enumerate(step_order):
            if current_idx > idx:
                status = "completed"
            elif current_idx == idx:
                status = "running"
            else:
                status = "queued"

            step_percent = 0
            if status == "running" and current_detail:
                step_percent = current_detail.get("percent", 0)
            elif status == "completed":
                step_percent = 100

            stage_steps.append(
                {
                    "id": step_id,
                    "label": step_labels[step_id],
                    "status": status,
                    "percent": step_percent,
                }
            )

        return {
            "is_running": self.is_running,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": elapsed,
            "total_count": self.total_count,
            "completed_count": self.completed_count,
            "percent": percent,
            "active_datasets": sorted(list(self.active_datasets)),
            "current_dataset": current_dataset,
            "current_detail": current_detail,
            "stage_steps": stage_steps,
            "items": items,
        }


progress_tracker = ImportProgress()
