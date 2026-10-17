FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 INCIDENTLAB_DATA_DIR=/app/runtime
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN pip install --no-cache-dir uv==0.9.5 && uv sync --frozen --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home lab && mkdir -p /app/runtime /app/artifacts && chown -R lab:lab /app
USER lab
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
CMD ["incidentlab", "--host", "0.0.0.0", "--port", "8000", "--data-dir", "/app/runtime"]

FROM base AS test
USER root
RUN uv sync --frozen --extra dev --no-editable && chown -R lab:lab /app/.venv
COPY tests ./tests
USER lab
CMD ["python", "-m", "pytest", "-q"]
