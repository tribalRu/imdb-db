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

    def set_stage(self, dataset_name: str, stage: str) -> None:
        if stage in ("completed", "failed"):
            self.active_datasets.discard(dataset_name)
        else:
            self.active_datasets.add(dataset_name)
        self.stages[dataset_name] = stage

    def complete_dataset(self, dataset_name: str, duration: float) -> None:
        self.active_datasets.discard(dataset_name)
        self.stages[dataset_name] = "completed"
        self.durations[dataset_name] = round(duration, 2)
        self.completed_count = sum(1 for s in self.stages.values() if s == "completed")

    def fail_dataset(self, dataset_name: str, error: str, duration: float) -> None:
        self.active_datasets.discard(dataset_name)
        self.stages[dataset_name] = "failed"
        self.errors[dataset_name] = error
        self.durations[dataset_name] = round(duration, 2)

    def finish(self) -> None:
        self.is_running = False
        self.finished_at = time.time()
        self.active_datasets.clear()

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

        return {
            "is_running": self.is_running,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": elapsed,
            "total_count": self.total_count,
            "completed_count": self.completed_count,
            "percent": percent,
            "active_datasets": sorted(list(self.active_datasets)),
            "items": items,
        }


progress_tracker = ImportProgress()
