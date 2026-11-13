FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY common /app/common
COPY bot /app/bot
COPY data/kirtans.db /app/data/kirtans.db

RUN chmod 0444 /app/data/kirtans.db \
    && mkdir -p /app/state \
    && chown -R 10001:10001 /app/state
USER 10001:10001

VOLUME ["/app/state"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-m", "bot.healthcheck"]

CMD ["python", "-m", "bot"]
