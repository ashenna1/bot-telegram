FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Isolated — do not use host network, do not expose 80/443/8000/5432
WORKDIR /app

# System deps: ffmpeg + deno (for yt-dlp)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates unzip sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Deno
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh && \
    /usr/local/bin/deno --version

# Python deps
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App
COPY bot/ bot/
COPY main.py .

RUN mkdir -p /app/data /app/tmp /app/cookies /app/logs && chmod 700 /app/data /app/cookies

# Health check (internal, no host port conflict)
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import sqlite3; sqlite3.connect('/app/data/bot.db').execute('select 1').fetchone()" || exit 1

CMD ["python", "-m", "bot"]
