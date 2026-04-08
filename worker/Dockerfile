FROM python:3.11-slim-bookworm

WORKDIR /app

# System dependencies for PDF processing and OCR
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libpq-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Surya OCR (includes donut and recognition models)
RUN pip install --no-cache-dir surya-ocr

# Copy application code
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Run Celery worker
CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=2"]
