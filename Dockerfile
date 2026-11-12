FROM node:24 AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json /frontend/
RUN npm ci

COPY frontend/index.html /frontend/index.html
COPY frontend/src /frontend/src
COPY frontend/tsconfig.json frontend/tsconfig.node.json /frontend/
COPY frontend/vite.config.ts frontend/tailwind.config.ts /frontend/
RUN npm run build

FROM python:3.13.11-slim-trixie

ARG GIT_COMMIT=unknown
ARG GIT_TAG=0.0.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CACHE_DIR=/data/cache \
    FRONTEND_DIST=/app/frontend-dist

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /applib
ENV PATH="/applib/bin:$PATH"

WORKDIR /app

COPY backend/requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY backend /app/backend
COPY --from=frontend-builder /frontend/dist /app/frontend-dist
COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh

ENV GIT_COMMIT=${GIT_COMMIT} \
    GIT_TAG=${GIT_TAG}

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/run.sh"]
