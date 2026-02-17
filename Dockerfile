FROM python:3.14-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy project
COPY . .

# Collect static files
RUN uv run python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

# Default: run the bot
CMD ["uv", "run", "python", "manage.py", "runbot"]
