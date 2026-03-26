FROM python:3.14-slim

WORKDIR /app

# Install UV from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies (cached layer — only rebuilds if lock file changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Install Playwright's Chromium browser + system dependencies
RUN uv run playwright install chromium --with-deps

# Copy application source (app/ only — excludes deploy/, tests, database files, etc.)
COPY app/ .

EXPOSE 8003

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
