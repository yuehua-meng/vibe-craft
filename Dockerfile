# 单进程运行：进程内 asyncio 锁与 SQLite 不跨进程，不要增加 workers。
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8010

WORKDIR /app

COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt

COPY app/ ./app/
COPY web/ ./web/
COPY run.py .

EXPOSE 8010

CMD ["python", "run.py"]
