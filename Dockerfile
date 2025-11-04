# First, build the application in the `/app` directory.
# See `Dockerfile` for details.
ARG PYTHON_VERSION=3.14t

FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev
ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-trixie-slim AS database
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Copy the application from the builder
COPY --from=builder --chown=app:app /app /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --only-group build

# Build the database
ARG HUB_REF=main
RUN uv run python -I build.py --git-ref $HUB_REF --exit-zero

# Then, use a final image without uv
FROM python:${PYTHON_VERSION}-slim-trixie
# It is important to use the image that matches the builder, as the path to the
# Python executable must be the same, e.g., using `python:3.11-slim-bookworm`
# will fail.

# Copy the application from the builder
COPY --from=builder --chown=app:app /app /app

# Copy the plugins database
COPY --from=database /app/plugins.db /app/plugins.db

ENV DB_PATH="/app/plugins.db"

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH" \
    GRANIAN_HOST='0.0.0.0' \
    GRANIAN_INTERFACE=asgi \
    GRANIAN_LOG_ACCESS_ENABLED=1

# Run the FastAPI application by default
CMD ["granian", "hub_api.main:app"]
