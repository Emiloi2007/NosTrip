FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && pip install --no-cache-dir -U yt-dlp

ENV OUTPUT_DIR=/data/output \
    TIKTOK_TOKEN_FILE=/data/tiktok_token.json \
    HF_HOME=/data/models

EXPOSE 8000
CMD ["uvicorn", "yt2tiktok.server:app", "--host", "0.0.0.0", "--port", "8000"]
