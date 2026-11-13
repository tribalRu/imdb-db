"""integration tests against a throwaway Postgres database

These tests never run in CI. Point TEST_DATABASE_URL at a disposable
database (it is dropped and recreated between runs), for example:

    $env:TEST_DATABASE_URL = "postgresql+asyncpg://imdb-db:secret123@localhost:5432/imdb-db-test"
    python -m pytest backend/tests -q

TEST_DATABASE_URL_SYNC is derived from TEST_DATABASE_URL unless set
explicitly. Never use a database that holds real data.
"""

import os
from datetime import datetime, timezone

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["DATABASE_URL_SYNC"] = os.environ.get(
        "TEST_DATABASE_URL_SYNC",
        TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"),
    )

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="set TEST_DATABASE_URL to run integration tests",
)

TITLE_ID = "tt9000001"
PERSON_ID = "nm9000001"
EPISODE_ID_1 = "tt9000002"
EPISODE_ID_2 = "tt9000003"
LATER_TITLE_ID = "tt9000004"


def _add_import_task(filename: str, status: str) -> None:
    """insert an import task row through the sync engine"""
    import models
    from sqlalchemy import create_engine
    from sqlmodel import Session

    engine = create_engine(os.environ["DATABASE_URL_SYNC"])
    try:
        with Session(engine) as session:
            session.add(
                models.ImportTask(
                    filename=filename,
                    size_compressed=0,
                    size_raw=0,
                    import_start_time=datetime.now(timezone.utc),
                    duration=0.0,
                    status=status,
                )
            )
            session.commit()
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def client():
    """fresh schema and fixture data, then a TestClient for the real app"""
    import models
    from main import app
    from sqlalchemy import create_engine, text
    from sqlmodel import Session, SQLModel

    engine = create_engine(os.environ["DATABASE_URL_SYNC"])
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            models.Title(
                tconst=TITLE_ID,
                title_type="movie",
                primary_title="Integration Test Title",
                original_title="Integration Test Title",
                is_adult=False,
                start_year=2001,
                genres=["Test"],
            )
        )
        session.add(models.TitleRating(tconst=TITLE_ID, average_rating=8.7, num_votes=1234))
        session.add(
            models.Title(
                tconst=EPISODE_ID_1,
                title_type="tvEpisode",
                primary_title="Fixture Episode One",
                original_title="Fixture Episode One",
                is_adult=False,
                start_year=2001,
                genres=["Test"],
            )
        )
        session.add(
            models.Title(
                tconst=EPISODE_ID_2,
                title_type="tvEpisode",
                primary_title="Fixture Episode Two",
                original_title="Fixture Episode Two",
                is_adult=False,
                start_year=2001,
                genres=["Test"],
            )
        )
        session.add(
            models.Title(
                tconst=LATER_TITLE_ID,
                title_type="movie",
                primary_title="Later Fixture Movie",
                original_title="Later Fixture Movie",
                is_adult=False,
                start_year=2020,
                genres=["Test"],
            )
        )
        session.add(
            models.Episode(
                tconst=EPISODE_ID_1,
                parent_tconst=TITLE_ID,
                season_number=1,
                episode_number=1,
            )
        )
        session.add(
            models.Episode(
                tconst=EPISODE_ID_2,
                parent_tconst=TITLE_ID,
                season_number=1,
                episode_number=2,
            )
        )
        session.add(
            models.Person(
                nconst=PERSON_ID,
                primary_name="Integration Test Person",
                primary_professions=["actor"],
                known_for_titles=[TITLE_ID],
            )
        )
        session.add(
            models.TitlePrincipal(
                tconst=TITLE_ID,
                ordering=1,
                nconst=PERSON_ID,
                category="actor",
                characters=["Someone"],
            )
        )
        session.add(
            models.TitlePrincipal(
                tconst=LATER_TITLE_ID,
                ordering=1,
                nconst=PERSON_ID,
                category="actor",
                characters=["Someone Else"],
            )
        )
        session.add(
            models.ImportTask(
                filename="title.episode.tsv",
                size_compressed=0,
                size_raw=0,
                import_start_time=datetime.now(timezone.utc),
                duration=0.0,
                status="running",
            )
        )
        session.add(
            models.ImportTask(
                filename="title.basics.tsv",
                size_compressed=100,
                size_raw=200,
                import_start_time=datetime.now(timezone.utc),
                duration=12.5,
                status="completed",
            )
        )
        session.commit()

    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client

    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_titles_list_contains_fixture(client):
    resp = client.get("/api/titles", params={"size": 5})
    assert resp.status_code == 200
    match = [item for item in resp.json() if item["tconst"] == TITLE_ID]
    assert len(match) == 1
    assert match[0]["primary_title"] == "Integration Test Title"
    assert match[0]["average_rating"] == 8.7
    assert match[0]["num_votes"] == 1234


def test_title_not_found(client):
    assert client.get("/api/titles/tt9999999").status_code == 404


def test_search_finds_fixture(client):
    resp = client.get("/api/search/titles", params={"q": "Integration Test"})
    assert resp.status_code == 200
    assert [item["tconst"] for item in resp.json()] == [TITLE_ID]


def test_search_blank_rejected(client):
    resp = client.get("/api/search/titles", params={"q": "  "})
    assert resp.status_code == 422


def test_search_treats_wildcards_literally(client):
    # % and _ must be escaped, otherwise they match arbitrary rows.
    for query in ("%", "_"):
        resp = client.get("/api/search/titles", params={"q": query})
        assert resp.status_code == 200
        assert resp.json() == []


def test_genre_filter_matches_array_contains(client):
    resp = client.get("/api/titles", params={"genre": "Test", "size": 10})
    assert resp.status_code == 200
    assert TITLE_ID in {item["tconst"] for item in resp.json()}


def test_ingest_rejects_unknown_dataset(client):
    resp = client.post("/api/ingest", json={"data_set": ["nope.tsv"]})
    assert resp.status_code == 400


def test_ingest_rejects_empty_dataset_list(client):
    # an empty list is not "import nothing": omitting data_set means everything
    resp = client.post("/api/ingest", json={"data_set": []})
    assert resp.status_code == 400


def test_stats_reports_fixture_counts(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    payload = resp.json()
    datasets = {dataset["dataset_name"]: dataset for dataset in payload["datasets"]}
    assert datasets["title.basics.tsv"]["document_count"] == 4
    assert datasets["title.ratings.tsv"]["document_count"] == 1
    assert payload["total_document_count"] >= 1


def test_people_credits(client):
    resp = client.get(f"/api/people/{PERSON_ID}/credits")
    assert resp.status_code == 200
    credits = resp.json()
    # newest title first; the sort key is the release year, not tconst
    assert [credit["tconst"] for credit in credits] == [LATER_TITLE_ID, TITLE_ID]
    assert credits[0]["title"]["start_year"] == 2020
    assert credits[0]["category"] == "actor"


def test_series_episodes_are_paginated(client):
    first = client.get(f"/api/series/{TITLE_ID}/episodes", params={"size": 1, "page": 1})
    assert first.status_code == 200
    assert len(first.json()) == 1

    second = client.get(f"/api/series/{TITLE_ID}/episodes", params={"size": 1, "page": 2})
    assert second.status_code == 200
    assert len(second.json()) == 1
    assert first.json()[0]["tconst"] != second.json()[0]["tconst"]


def test_import_tasks_filter_by_status(client):
    _add_import_task("name.basics.tsv", "running")

    resp = client.get("/api/import-tasks", params={"status": "running"})
    assert resp.status_code == 200
    items = resp.json()
    assert items
    assert all(item["status"] == "running" for item in items)
    assert {item["filename"] for item in items} == {"name.basics.tsv"}


def test_startup_marks_stale_running_tasks_failed(client):
    # the fixture seeds a `running` row before the app starts; the lifespan
    # hook must not leave it stuck after that process is gone
    resp = client.get("/api/import-tasks", params={"status": "failed"})
    assert resp.status_code == 200
    assert "title.episode.tsv" in {item["filename"] for item in resp.json()}

    running = client.get("/api/import-tasks", params={"status": "running"})
    assert "title.episode.tsv" not in {item["filename"] for item in running.json()}


def test_import_tasks_reject_unknown_status(client):
    resp = client.get("/api/import-tasks", params={"status": "bogus"})
    assert resp.status_code == 422


def test_stats_only_counts_completed_imports(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    datasets = {dataset["dataset_name"]: dataset for dataset in resp.json()["datasets"]}
    assert datasets["title.basics.tsv"]["runs"] == 1
    # a running import must not be counted anywhere
    assert datasets["name.basics.tsv"]["runs"] is None
    assert datasets["name.basics.tsv"]["indexed"] is False
