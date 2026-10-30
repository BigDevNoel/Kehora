# API and agent worker image (same code, different command). Context: ./Backend
FROM python:3.12-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Dependencies first for layer caching, then the workspace itself.
COPY pyproject.toml uv.lock .python-version ./
COPY common/pyproject.toml common/
COPY schemas/pyproject.toml schemas/
COPY db/pyproject.toml db/
COPY api/pyproject.toml api/
COPY llm/pyproject.toml llm/
COPY engines/pyproject.toml engines/
COPY engines_runner/pyproject.toml engines_runner/
COPY agents/pyproject.toml agents/
RUN uv sync --frozen --no-dev --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 kehora
USER kehora
EXPOSE 8000
CMD ["uvicorn", "kehora_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
