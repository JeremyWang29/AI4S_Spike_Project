FROM python:3.12.7-slim-bookworm
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.12.5 && uv sync --frozen --no-dev
COPY . .
USER 65532
CMD ["uv", "run", "--frozen", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
