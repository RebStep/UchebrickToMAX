FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot/core ./core
COPY bot/bot_max ./bot_max
COPY bot/schema.sql .
COPY bot/certs ./certs
RUN mkdir -p /data/files && chown 1000:1000 /data/files
ENV FILES_DIR=/data/files WHISPER_DIR=/data/files/whisper
CMD ["python", "-m", "bot_max.main"]
