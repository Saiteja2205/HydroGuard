# HydroGuard backend — CPU-only cloud image.
#
# Build context must be the hydroguard-backend/ directory (not the repo root),
# because the app package, the ml/ package and artifacts/checkpoints/ all live
# here and the image needs all three:
#
#   cd hydroguard-backend
#   docker build -t hydroguard-backend .
#   docker run -p 8000:8000 --env-file .env hydroguard-backend
#
# The three PyTorch checkpoints are git-tracked under artifacts/checkpoints/
# and total ~3.3 MB, so a build straight from a clone has everything it needs
# with no extra download step.

# Python 3.13 matches the version this backend is developed and tested against
# (see the local interpreter). slim keeps the final image small.
FROM python:3.13-slim

# Never write .pyc files and never buffer stdout. Unbuffered logs matter on
# Render/Railway, which tail the process output for the dashboard.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/hydroguard

# Install torch from the CPU wheel index FIRST, then the rest. Doing it in one
# step with a single requirements file would let the resolver pull the CUDA
# build from default PyPI (~2.5 GB) and blow the free-tier disk budget. The CPU
# wheels are ~200 MB and run all three models on CPU, which is all a
# CPU-only instance can use anyway.
#
# torch is installed unpinned so security fixes flow in; the version this
# backend is verified against is 2.14.0+cpu.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements-cpu.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements-cpu.txt

# Copy the application, the ml/ package and the model checkpoints. .dockerignore
# excludes caches, tests and reports so the layer stays small and reproducible.
# The root conftest.py is deliberately NOT copied: it is a pytest-only helper
# that redirects the database to a temp file, and pytest is not installed here.
COPY app ./app
COPY ml ./ml
COPY artifacts ./artifacts
COPY alembic ./alembic
COPY alembic.ini ./

# SQLite lives here by default. Mount a persistent disk at /srv/hydroguard/data
# (see render.yaml) or every redeploy starts from an empty database.
RUN mkdir -p /srv/hydroguard/data
VOLUME ["/srv/hydroguard/data"]

# Run as a non-root user. The app only needs read access to the code and
# read/write access to the data directory.
RUN useradd --create-home --shell /usr/sbin/nologin hydroguard \
    && chown -R hydroguard:hydroguard /srv/hydroguard
USER hydroguard

# $PORT is provided by Render/Railway/Fly; default to 8000 for local runs.
ENV PORT=8000
EXPOSE 8000

# /api/v1/health is public by design and reports dependency state from evidence
# gathered at request time, so it is a truthful readiness probe. The health
# check never loads ML checkpoints, so it stays fast.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/v1/health" || exit 1

# Bind 0.0.0.0 so the platform router can reach the container.
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
