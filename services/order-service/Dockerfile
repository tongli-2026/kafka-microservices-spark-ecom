FROM python:3.11-slim

WORKDIR /app

# Copy shared library
COPY shared /app/shared

# Copy service files
COPY services/order-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/order-service /app

EXPOSE 8002

# Set PYTHONPATH to include shared library
ENV PYTHONPATH=/app/shared:/app:${PYTHONPATH}

CMD ["python", "main.py"]
