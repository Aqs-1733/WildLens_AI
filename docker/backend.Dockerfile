FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
RUN pip install --upgrade pip && pip install ".[postgres]"
COPY data ./data
COPY storage ./storage
COPY models ./models
RUN mkdir -p storage/uploads storage/results storage/annotated storage/reports storage/logs

EXPOSE 8010
CMD ["python", "backend/main.py"]
