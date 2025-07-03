#!/bin/sh
set -e

echo "--- Running entrypoint.sh ---"

# Check for flask_secret_key and export it
if [ -f /run/secrets/flask_secret_key ]; then
    echo "Exporting FLASK_SECRET_KEY..."
    export FLASK_SECRET_KEY=$(cat /run/secrets/flask_secret_key)
fi

# Check for db_password and export it
if [ -f /run/secrets/db_password ]; then
    echo "Exporting DB_PASSWORD..."
    export DB_PASSWORD=$(cat /run/secrets/db_password)
fi

# Check for mail_password and export it (optional)
if [ -f /run/secrets/mail_password ]; then
    echo "Exporting MAIL_PASSWORD..."
    export MAIL_PASSWORD=$(cat /run/secrets/mail_password)
fi

echo "--- Entrypoint script finished. Executing main command: $@ ---"
exec "$@"