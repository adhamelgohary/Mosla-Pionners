# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Create a non-root user for better security
RUN useradd --create-home appuser
USER appuser

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Copy the requirements file and install dependencies
# This is done first to leverage Docker layer caching
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY --chown=appuser:appuser . .

# Expose the port Gunicorn will run on
EXPOSE 12345

# Command to run the application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:12345", "--workers", "4", "app:app"]