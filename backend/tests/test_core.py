"""unit tests for the pure parts of the codebase"""

import gzip

import pytest
from api.search import _like_pattern, _normalized_query
from fastapi import HTTPException
from src.datasets import DATASET_TABLE_MAP
from src.import_handler import (
    INGEST_BY_DATASET_NAME,
    SUPPORTED_DATASET_NAMES,
    clean_cache_dir,
    is_import_running,
    resolve_datasets,
)
from src.import_title_basic import IngestTitleBasics


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


def test_resolve_datasets_rejects_empty_selection():
    with pytest.raises(ValueError, match="at least one dataset"):
        resolve_datasets([])


def test_rebuild_index_statements_match_index_names():
    for ingest_class in INGEST_BY_DATASET_NAME.values():
        for index_name, ddl in ingest_class.REBUILD_INDEXES:
            assert f"CREATE INDEX IF NOT EXISTS {index_name}" in ddl
            assert index_name in ddl


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


def test_like_pattern_matches_plain_text():
    assert _like_pattern("matrix") == "%matrix%"


def test_like_pattern_escapes_wildcards():
    assert _like_pattern("100%") == "%100\\%%"
    assert _like_pattern("a_b") == "%a\\_b%"
    assert _like_pattern("c\\d") == "%c\\\\d%"


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


def test_extract_writes_tsv_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(IngestTitleBasics, "CACHE_DIR", tmp_path)
    ingest = IngestTitleBasics(pool=None)

    with gzip.open(ingest.gz_path, "wb") as gz:
        gz.write(b"tconst\tprimary_title\ntt0000001\tCarmencita\n")

    ingest._extract_if_needed()

    assert ingest.tsv_path.read_bytes() == b"tconst\tprimary_title\ntt0000001\tCarmencita\n"
    assert list(tmp_path.glob("*.part")) == []


def test_extract_failure_leaves_no_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(IngestTitleBasics, "CACHE_DIR", tmp_path)
    ingest = IngestTitleBasics(pool=None)
    ingest.gz_path.write_bytes(b"not a gzip archive")

    with pytest.raises(Exception):
        ingest._extract_if_needed()

    assert not ingest.tsv_path.exists()
    assert list(tmp_path.glob("*.part")) == []
