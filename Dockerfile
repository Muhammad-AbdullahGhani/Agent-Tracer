FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose FastAPI port
EXPOSE 8000

ENV PYTHONPATH=.
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "agenttrace.cli", "serve", "8000"]
