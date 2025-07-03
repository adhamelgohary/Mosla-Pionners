# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed by Python packages
RUN apt-get update && apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code into the container
# This includes app.py, utils/, routes/, templates/, static/, etc.
COPY . .

# NEW: Copy the entrypoint script into the container
COPY entrypoint.sh .

# NEW: Make the script executable
RUN chmod +x ./entrypoint.sh

# NEW: Set this script as the entrypoint for the container
ENTRYPOINT ["./entrypoint.sh"]

# Expose the port that Gunicorn will run on
EXPOSE 8000

# The CMD will now be passed AS AN ARGUMENT to the entrypoint script
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]    