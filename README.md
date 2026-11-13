# IMDb DB

Your local IMDb Database.

## Core Functionality

- Import the datasets from [imdb](https://datasets.imdbws.com/).
- Index into Postgres.
- Serve through a small API layer.
- Built with Python and FastAPI.
- Simple React frontend for exploring the API.

## Included Datasets

All datasets are imported from official IMDb sources. They are provided by imdb for local private personal and non-commercial use. For more details see [here](https://developer.imdb.com/non-commercial-datasets/).

| Name                  | Comment                       | Rows  | .tsv.gz | .tsv   | indexed | Ingest  |
|-----------------------|-------------------------------|-------|---------|--------|---------|---------|
| title.basics.tsv      | All titles                    | 12 M  | 220 MB  | 1 GB   | 2 GB    | 1m 10s  |
| name.basics.tsv       | All names of people           | 15 M  | 300 MB  | 1 GB   | 2.4 GB  | 1m 40s  |
| title.ratings.tsv     | All ratings of titles         | 2 M   | 10 MB   | 30 MB  | 220 MB  | 30s     |
| title.episode.tsv     | Episode to season mappings    | 10 M  | 50 MB   | 250 MB | 1.4 GB  | 5m      |
| title.akas.tsv        | Alternative names for titles  | 55 M  | 500 MB  | 2.7 GB | 12.6 GB | 17m     |
| title.principals.tsv  | People to title relations     | 98 M  | 750 MB  | 4.3 GB | 24 GB   | 1h      |

- Ingest times are largely IO bound.
- These values are from local testing on consumer grade NVMe drives, YMMV.
- Upserts, aka subsequent ingests, can in some cases be faster, depending on the diff size or slower if the merging is complicated by foreign keys.
- During import until the vakuum task from Postgres hits, expect larger filesystem usage than described here.

You don't have to import all datasets.
- Make sure the relations can be established, e.g. importing the `title.akas` dataset without the `title.basics` dataset would not make sense.
- You can do partial upserts, e.g. refresh only `title.ratings`. This will ignore titles for new ratings missing from `title.basics`. To avoid that, upsert `title.basics` and `title.ratings` together.

## Requirements

- Docker (optional; recommended for the all-in-one setup)
- Python 3.13+
- PostgreSQL 17+
- Node.js 20+ (only to build or develop the frontend)
- ~100 GB free disk space for all datasets; 8 GB RAM recommended

## Installation

### Docker (recommended)

The compose file builds the API image from the local sources, so changes to
`backend/` and `frontend/` are included:

```bash
docker compose up -d --build
```

The API is available at http://127.0.0.1:8000, the interactive docs at
http://127.0.0.1:8000/docs. The first start runs Alembic migrations
automatically.

### Postgres container

- The sample healthcheck is recommended for proper startup check of the API container.
- The command extension configuring the WAL is recommended for more efficient bulk data merging. You can adjust these values should you be limited on disk space.

Environment variables are the standard postgres vars:

```
POSTGRES_USER=imdb-db
POSTGRES_PASSWORD=secret123
POSTGRES_DB=imdb-db
```

### API container

The API container can run under your own user by adding for example `user: 1000:1000`. If you do that, make sure to also set the volume permissions correctly.

- Interface is served on port 8000.
- Expects a volume at `/data` in the container. This is where the downloaded datasets go and where the decompressed files are stored.

- Optionally set `DATASET_TO_KEEP` to an integer to automatically clean up older cached datasets, e.g. `DATASET_TO_KEEP=2` to keep newest two cached.
- or clean periodically.

For env vars, you'll need to provide both sync and async connection strings to postgres. E.g.:

```
DATABASE_URL=postgresql+asyncpg://imdb-db:secret123@imdb-postgres:5432/imdb-db
DATABASE_URL_SYNC=postgresql://imdb-db:secret123@imdb-postgres:5432/imdb-db
```

## Endpoints

The docs are available at `/docs` or at `/openapi.json`.

Available endpoints:

- `/` React frontend
- `GET /health`
- `GET /api`
- `POST /api/ingest`
- `GET /api/import-tasks`
- `GET /api/stats`
- `GET /api/titles`
- `GET /api/titles/{tconst}`
- `GET /api/titles/{tconst}/principals`
- `GET /api/people/{nconst}`
- `GET /api/people/{nconst}/credits`
- `GET /api/series/{tconst}/episodes`
- `GET /api/search/titles`
- `GET /api/search/people`

## Ingest Dataset

In general, that works as such:

- Download the compressed *.tsv.gz file directly from imdb, store it in the cache folder
- Decompress the archive to *.tsv file in the cache folder
- Import the raw data into a temporary postgres staging table
- Upsert the staging table into the main table

Some testing has shown this approach to be the fastest, as that skips the ORM altogether, and all processing can be done directly in postgres. The main bottleneck will be IO on postgres during the COPY and INSERT commands.

### Trigger ingest for all datasets

```bash
curl -X POST http://localhost:8000/api/ingest
```

### Trigger ingest for selected datasets

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"data_set":["title.basics.tsv","title.ratings.tsv"]}'
```

### CLI

There is a small CLI utility included to trigger the ingest flows:

```
docker compose exec -it imdb-api ./backend/app/cli --help
```

## Local Development

You can run Postgres in Docker and the API locally:

```bash
docker compose up -d imdb-postgres
source .venv/bin/activate
pip install -r requirements-dev.txt
cp backend/app/.env.example backend/app/.env
cd backend
alembic -c alembic.ini upgrade head
cd app
fastapi dev main.py
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

`devstart.sh` also provides a tmux-based local dev workflow.

## Tests

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest backend/tests -q
```

The suite covers dataset resolution, cache cleanup and search input handling,
and runs in CI without a database.

There are also integration tests that exercise the API against a disposable
Postgres database (skipped by default):

```bash
psql -U postgres -c "CREATE DATABASE \"imdb-db-test\" OWNER \"imdb-db\";"
export TEST_DATABASE_URL="postgresql+asyncpg://imdb-db:secret123@localhost:5432/imdb-db-test"
python -m pytest backend/tests -q
```

The fixture drops and recreates the schema, so never point `TEST_DATABASE_URL`
at a database with real data.

## Deployment without Docker

Docker is not required. The application is a normal FastAPI process plus a
PostgreSQL database, and the frontend is a static Vite build that FastAPI can
serve. This is a good fit for a local machine, especially on Windows where
native PostgreSQL usually has better disk I/O than a bind-mounted Docker volume.

### 1. PostgreSQL

Install PostgreSQL 17 and create the role and database:

```sql
CREATE ROLE "imdb-db" LOGIN PASSWORD 'secret123';
CREATE DATABASE "imdb-db" OWNER "imdb-db";
```

For large imports, tune `postgresql.conf` (adjust to your RAM) and restart
PostgreSQL:

```ini
shared_buffers = 2GB
maintenance_work_mem = 1GB
work_mem = 64MB
min_wal_size = 2GB
max_wal_size = 20GB
checkpoint_timeout = 15min
checkpoint_completion_target = 0.9
```

### 2. Backend

Windows (PowerShell):

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item backend\app\.env.example backend\app\.env
# edit backend\app\.env if your database credentials differ
cd backend
alembic -c alembic.ini upgrade head
cd app
uvicorn main:app --host 127.0.0.1 --port 8000
```

Linux/macOS:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp backend/app/.env.example backend/app/.env
cd backend
alembic -c alembic.ini upgrade head
cd app
uvicorn main:app --host 127.0.0.1 --port 8000
```

`backend/app/.env` is loaded automatically. Relative paths such as
`CACHE_DIR=data/cache` and `FRONTEND_DIST=frontend/dist` are resolved against
the repository root.

### 3. Frontend

Build the static bundle once:

```bash
cd frontend
npm ci
npm run build
```

The default `FRONTEND_DIST=frontend/dist` makes FastAPI serve the bundle at
`/`. Restart the API after rebuilding the frontend. For frontend development,
run `npm run dev` instead; Vite proxies `/api` to `http://localhost:8000`.

### 4. Ingest data

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"data_set":["title.basics.tsv","title.ratings.tsv"]}'
```

Add `"force": true` to re-import datasets even when a cached `.tsv` already
exists. The same is available through the CLI:

```bash
cd backend/app
python cli ingest --dataset title.ratings.tsv --force
```

### 5. Run at boot (optional)

- Linux: a systemd unit running `uvicorn main:app` from `backend/app`.
- Windows: Task Scheduler or [NSSM](https://nssm.cc/) with the same command.

### Search indexes and performance

`alembic upgrade head` enables the `pg_trgm` extension and creates the GIN
indexes used by `/api/search/*` and the genre filter:

- `ix_titles_primary_title_trgm`, `ix_titles_original_title_trgm`
- `ix_titles_genres_gin`
- `ix_people_primary_name_trgm`

The indexes are built when the migration runs, so on an already populated
database expect a few minutes for the build. Each title trigram index is about
480 MB for the full dataset.

These indexes are too expensive to maintain row by row during a bulk load, so
the importer drops them before the merge and rebuilds them once afterwards
(`REBUILD_INDEXES` in the dataset importers). Search endpoints keep working
while a dataset is being imported, but fall back to sequential scans until the
rebuild finishes. The same applies to `ix_episodes_parent_tconst` and
`ix_title_principals_nconst`. If the process is killed during the merge, the
next start of that import rebuilds the indexes; until then the search endpoints
stay slow.

On Windows, exclude the PostgreSQL data directory and `postgres.exe` from
Windows Defender real-time scanning. Otherwise WAL writes during import can be
an order of magnitude slower:

```powershell
Add-MpPreference -ExclusionPath 'C:\Program Files\PostgreSQL\17\data'
Add-MpPreference -ExclusionProcess 'postgres.exe'
```

`/api/stats` counts rows in every table and is cached for 60 seconds; the cache
is dropped after each import, so repeated calls within a minute are served from
memory.

Native deployment means you manage PostgreSQL upgrades, backups and Python
dependencies yourself. Docker remains a better choice for a NAS/server where
reproducibility matters more than raw import speed.

## CI/CD Images

GitHub Actions builds and publishes multi-arch images to GHCR:
- `unstable` for `develop`/`master` pushes
- release tag images for GitHub releases

Build metadata is exposed by API using:
- `GIT_TAG`
- `GIT_COMMIT`

## Security Notes

Optionally set an `API_TOKEN` env var to enable authentication for the API. This expects an Auth header like so for example:

```
curl http://localhost:8000/api/stats -H "Authorization: Bearer xxxxxx"
```

The bundled frontend stores the token in a `SameSite=Strict` cookie for up to
30 days and sends it as a bearer header. Keep the API bound to `127.0.0.1`
unless you put it behind a reverse proxy with TLS.

## License

GPL-3.0. See [LICENSE.md](LICENSE.md).

This repository is a fork of [bbilly1/imdb-db](https://github.com/bbilly1/imdb-db).
