"""app entrypoint"""

import logging
from contextlib import asynccontextmanager
from os import environ
from pathlib import Path

try:

    from dotenv import load_dotenv

    if Path(".env").exists():
        print("loading local .env file")
        load_dotenv(".env")

except ModuleNotFoundError:
    pass

import config
from api.ingest import router as ingest_router
from api.people import router as people_router
from api.search import router as search_router
from api.series import router as series_router
from api.titles import router as titles_router
from dependencies import verify_bearer_token
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(levelname)s][%(name)s] %(message)s",
)
logging.getLogger().setLevel(logging.INFO)

git_tag = environ.get("GIT_TAG", "dev")
git_commit = environ.get("GIT_COMMIT", "unknown")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """startup checks"""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="IMDb Read-Only API",
    version=git_tag,
    description=f"build tag={git_tag} commit={git_commit}",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

FRONTEND_DIST = config.FRONTEND_DIST

app.include_router(titles_router, dependencies=[Depends(verify_bearer_token)])
app.include_router(series_router, dependencies=[Depends(verify_bearer_token)])
app.include_router(people_router, dependencies=[Depends(verify_bearer_token)])
app.include_router(search_router, dependencies=[Depends(verify_bearer_token)])
app.include_router(ingest_router, dependencies=[Depends(verify_bearer_token)])


@app.get("/api")
async def api_is_up():
    """hello world"""
    return {
        "ping": "pong",
        "git_tag": git_tag,
        "git_commit": git_commit,
        "has_auth": bool(config.API_TOKEN),
    }


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    logging.getLogger(__name__).info("serving frontend from %s", FRONTEND_DIST)
else:
    logging.getLogger(__name__).warning(
        "frontend bundle not found at %s; run frontend dev server on http://localhost:5173 for local development",
        FRONTEND_DIST,
    )

    @app.get("/")
    async def frontend_not_available():
        raise HTTPException(
            status_code=503,
            detail="Frontend bundle is not available on this server. In local dev use http://localhost:5173.",
        )
