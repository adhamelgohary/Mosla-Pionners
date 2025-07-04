# Dockerfile

# Use a modern, compatible Python version
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- THIS IS THE KEY CHANGE ---
# Copy the .env file created by the GitHub Action
COPY .env .
# Copy the rest of the application
COPY . .

EXPOSE 8000

# The command to run the app. It now uses wsgi.py
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "wsgi:app"]