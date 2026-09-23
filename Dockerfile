FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NODRIVER_HEADLESS=false \
    NODRIVER_BROWSER_PATH=/usr/bin/chromium \
    DISPLAY=:99

# Chromium + Xvfb: Requerido para resolver AWS WAF con nodriver en servidores cloud (Railway)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    xvfb \
    xauth \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "xvfb-run -a --server-args='-screen 0 1920x1080x24 -ac' uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
