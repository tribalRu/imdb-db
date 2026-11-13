"""unit tests for the pure parts of the codebase"""

import gzip

import pytest
from api.cache import TTLCache, etag_matches, make_etag
from api.params import validate_cursor
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


def test_validate_cursor_allows_first_page():
    validate_cursor(1, "tt0000001", "after_tconst")
    validate_cursor(1, None, "after_tconst")


def test_validate_cursor_rejects_offset_page():
    with pytest.raises(HTTPException) as exc_info:
        validate_cursor(2, "tt0000001", "after_tconst")
    assert exc_info.value.status_code == 400
    assert "after_tconst" in exc_info.value.detail


def test_ttl_cache_evicts_least_recently_used():
    cache = TTLCache(max_entries=2, ttl_seconds=60, clock=lambda: 0.0)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1  # "a" becomes the most recently used entry

    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert len(cache) == 2


def test_ttl_cache_expires_entries():
    now = [0.0]
    cache = TTLCache(max_entries=10, ttl_seconds=5, clock=lambda: now[0])
    cache.set("a", 1)

    now[0] = 4.9
    assert cache.get("a") == 1

    now[0] = 5.0
    assert cache.get("a") is None
    assert len(cache) == 0


def test_ttl_cache_is_disabled_with_zero_entries():
    cache = TTLCache(max_entries=0, ttl_seconds=60)
    cache.set("a", 1)
    assert cache.get("a") is None


def test_etag_is_stable_and_content_dependent():
    first = make_etag({"a": 1, "b": [1, 2]})
    assert first == make_etag({"b": [1, 2], "a": 1})
    assert first.startswith('W/"')
    assert make_etag({"a": 2}) != first


def test_etag_matches_handles_weak_and_lists():
    etag = 'W/"abc"'
    assert etag_matches(etag, etag)
    assert etag_matches('"abc"', etag)
    assert etag_matches('W/"zzz", W/"abc"', etag)
    assert etag_matches("*", etag)
    assert not etag_matches(None, etag)
    assert not etag_matches('W/"zzz"', etag)


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
