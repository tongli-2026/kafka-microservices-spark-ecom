FROM python:3.11-slim

WORKDIR /app

# Install Java (required for Spark)
RUN apt-get update && apt-get install -y default-jre-headless && rm -rf /var/lib/apt/lists/*

# Copy analytics files
COPY analytics/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY analytics /app

CMD ["python", "-c", "import sys; print('Analytics container ready')"]
