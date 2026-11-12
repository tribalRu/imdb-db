"""integration tests against a throwaway Postgres database

These tests never run in CI. Point TEST_DATABASE_URL at a disposable
database (it is dropped and recreated between runs), for example:

    $env:TEST_DATABASE_URL = "postgresql+asyncpg://imdb-db:secret123@localhost:5432/imdb-db-test"
    python -m pytest backend/tests -q

TEST_DATABASE_URL_SYNC is derived from TEST_DATABASE_URL unless set
explicitly. Never use a database that holds real data.
"""

import os

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


def test_ingest_rejects_unknown_dataset(client):
    resp = client.post("/api/ingest", json={"data_set": ["nope.tsv"]})
    assert resp.status_code == 400


def test_stats_reports_fixture_counts(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    payload = resp.json()
    datasets = {dataset["dataset_name"]: dataset for dataset in payload["datasets"]}
    assert datasets["title.basics.tsv"]["document_count"] == 1
    assert datasets["title.ratings.tsv"]["document_count"] == 1
    assert payload["total_document_count"] >= 1


def test_people_credits(client):
    resp = client.get(f"/api/people/{PERSON_ID}/credits")
    assert resp.status_code == 200
    credits = resp.json()
    assert credits[0]["tconst"] == TITLE_ID
    assert credits[0]["category"] == "actor"
