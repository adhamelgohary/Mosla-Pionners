#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Helper function to read a secret from a file and export it as an env var.
# It checks if the file exists first.
export_secret() {
  local secret_name="$1"
  local secret_file="/run/secrets/$2" # The path to the secret file inside the container
  
  if [ -f "$secret_file" ]; then
    echo "Exporting secret from file: $secret_file"
    # Reads the file and exports it.
    export "$secret_name"="$(cat "$secret_file")"
  else
    echo "INFO: Secret file not found, skipping export for: $secret_file"
  fi
}

# --- Use the helper function for all secrets ---
export_secret "FLASK_SECRET_KEY" "flask_secret_key"
export_secret "DB_PASSWORD" "db_password"
export_secret "MAIL_PASSWORD" "mail_password"
# Add any other secrets you need here in the same format.

echo "--- Entrypoint script finished. Executing main command. ---"

# The 'exec "$@"' command runs the CMD from your Dockerfile (the gunicorn command)
exec "$@"