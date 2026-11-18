FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application files
COPY app/ ./app/
COPY static/ ./static/

EXPOSE 8000

CMD ["fastapi", "run", "app/main.py", "--port", "8000"]
