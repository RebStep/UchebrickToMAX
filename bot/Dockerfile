FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
# Whisper (распознавание голоса) ставится всегда; саму модель бот скачивает при первом голосовом
RUN pip install --no-cache-dir -r requirements.txt faster-whisper==1.2.1 av==18.1.0
COPY core ./core
COPY bot_max ./bot_max
COPY schema.sql .
COPY certs ./certs
RUN mkdir -p /data/files && chown 1000:1000 /data/files
ENV FILES_DIR=/data/files WHISPER_DIR=/data/files/whisper
CMD ["python", "-m", "bot_max.main"]
