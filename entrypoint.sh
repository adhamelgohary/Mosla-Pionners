#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Read the contents of the secret files and export them as environment variables
# The 'export' command makes them available to the Gunicorn process
export FLASK_SECRET_KEY=$(cat /run/secrets/flask_secret_key)
export DB_PASSWORD=$(cat /run/secrets/db_password)

# Now, execute the command that was passed to this script (our Gunicorn command)
# The 'exec' command replaces the shell process with the Gunicorn process
exec "$@"