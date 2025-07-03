#!/bin/sh
# entrypoint.sh

# Exit immediately if a command fails
set -e

# This function reads a secret from a file and makes it available as an environment variable
export_secret() {
  local secret_name="$1"
  local secret_file="/run/secrets/$2"
  
  if [ -f "$secret_file" ]; then
    export "$secret_name"="$(cat "$secret_file")"
  fi
}

# Use the function to export secrets needed by app.py and db.py
export_secret "FLASK_SECRET_KEY" "flask_secret_key"
export_secret "DB_PASSWORD" "db_password"

echo "--- Secrets exported. Starting Gunicorn server. ---"

# Run the command that was passed to the container (the CMD from the Dockerfile)
exec "$@"