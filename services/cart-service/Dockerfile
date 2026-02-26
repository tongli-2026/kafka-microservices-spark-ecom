FROM python:3.11-slim

# Sets the working directory inside the Docker container to /app.
# All subsequent commands in the Dockerfile (and when the container runs) will execute from this directory.
WORKDIR /app

# Copy the shared/ folder from local machine into the Docker container at /app/shared
COPY shared /app/shared

# Copy requirements.txt from local machine into the container's current working directory (/app).
COPY services/cart-service/requirements.txt .
# Installs all Python packages listed in requirements.txt.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the cart-service source code from the local machine into the Docker container at /app.
COPY services/cart-service /app

# Informs Docker that the container listens on port 8001 at runtime. 
EXPOSE 8001

# Sets the PYTHONPATH environment variable, telling Python where to look for importable modules.
# Multiple paths are separated by :
# PYTHONPATH=/app/shared: or PYTHONPATH=/app: or PYTHONPATH=${PYTHONPATH} which means any existing PYTHONPATH
ENV PYTHONPATH=/app/shared:/app:${PYTHONPATH}

# Starts the application by running the command python main.py when the container is launched.
CMD ["python", "main.py"]
