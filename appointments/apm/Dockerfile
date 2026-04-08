FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies for Playwright browsers
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    # Install Chromium via apt instead of Playwright's browser download
    chromium \
    chromium-sandbox \
    && rm -rf /var/lib/apt/lists/*

# Set Chromium path for Playwright
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

# Install Playwright Python package only (no browser download)
RUN pip install --no-cache-dir playwright==1.42.0

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy scraper code
COPY scraper.py .

# Run the scraper
CMD ["python", "scraper.py"]
