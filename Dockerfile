# Use an official Python runtime as a parent image
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copy and prepare the entrypoint script
COPY entrypoint.sh .
RUN chmod +x ./entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

EXPOSE 8000

# This command is passed to the entrypoint script
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]