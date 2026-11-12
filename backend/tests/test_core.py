"""unit tests for the pure parts of the codebase"""

import pytest
from fastapi import HTTPException

from api.search import _normalized_query
from src.datasets import DATASET_TABLE_MAP
from src.import_handler import (
    INGEST_BY_DATASET_NAME,
    SUPPORTED_DATASET_NAMES,
    clean_cache_dir,
    is_import_running,
    resolve_datasets,
)


def test_dataset_table_map_covers_all_supported_datasets():
    assert set(DATASET_TABLE_MAP) == set(SUPPORTED_DATASET_NAMES)
    assert set(DATASET_TABLE_MAP) == set(INGEST_BY_DATASET_NAME)
    assert len(set(DATASET_TABLE_MAP.values())) == len(DATASET_TABLE_MAP)


def test_resolve_datasets_default_selects_everything():
    classes, names = resolve_datasets(None)
    assert names == list(SUPPORTED_DATASET_NAMES)
    assert len(classes) == len(names)


def test_resolve_datasets_selected_subset():
    classes, names = resolve_datasets(["title.basics.tsv"])
    assert names == ["title.basics.tsv"]
    assert classes[0].DATASET_NAME == "title.basics.tsv"


def test_resolve_datasets_rejects_unknown_dataset():
    with pytest.raises(ValueError, match="Unsupported dataset_name"):
        resolve_datasets(["unknown.tsv"])


def test_import_lock_is_released_by_default():
    assert is_import_running() is False


def test_normalized_query_strips_whitespace():
    class _Params:
        q = "  matrix  "

    assert _normalized_query(_Params()) == "matrix"


def test_normalized_query_rejects_blank():
    class _Params:
        q = "   "

    with pytest.raises(HTTPException) as exc_info:
        _normalized_query(_Params())
    assert exc_info.value.status_code == 422


def test_clean_cache_dir_keeps_recent_archives(tmp_path, monkeypatch):
    monkeypatch.setattr("src.import_handler.CACHE_DIR", tmp_path)
    monkeypatch.setattr("src.import_handler.DATASET_TO_KEEP", "1")

    old = tmp_path / "title.basics.tsv_2026-11-01"
    new = tmp_path / "title.basics.tsv_2026-11-02"
    other = tmp_path / "title.ratings.tsv_2026-10-30"
    for path in (old, new, other):
        path.write_text("x", encoding="utf-8")

    clean_cache_dir()

    assert not old.exists()
    assert new.exists()
    assert other.exists()


def test_clean_cache_dir_rejects_invalid_value(tmp_path, monkeypatch):
    monkeypatch.setattr("src.import_handler.CACHE_DIR", tmp_path)
    monkeypatch.setattr("src.import_handler.DATASET_TO_KEEP", "abc")

    with pytest.raises(ValueError, match="DATASET_TO_KEEP"):
        clean_cache_dir()
