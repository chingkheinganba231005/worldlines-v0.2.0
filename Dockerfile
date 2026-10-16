FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend ./backend
COPY scripts ./scripts
COPY dist ./dist
COPY pyproject.toml ./
RUN pip install --no-deps . && useradd --uid 10001 --create-home worldline && mkdir -p /app/data && chown -R worldline:worldline /app
USER worldline
ENV WORLDLINE_ROOT=/app WORLDLINE_DB_PATH=/app/data/worldline.sqlite
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready',timeout=4)"
CMD ["python", "-m", "uvicorn", "worldline.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
