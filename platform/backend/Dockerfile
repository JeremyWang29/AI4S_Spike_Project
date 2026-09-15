FROM python:3.12.7-slim-bookworm
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.12.5 && uv sync --frozen --no-dev
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
RUN chmod +x /app/entrypoint.sh && mkdir -p /srv/private && chown 65532:65532 /srv/private
USER 65532
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
