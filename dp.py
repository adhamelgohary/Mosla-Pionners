# db.py
import os
import mysql.connector
from mysql.connector import Error
from flask import current_app

def get_db_connection():
    """
    Establishes a connection to the MySQL database using environment variables.
    """
    try:
        # Docker Secrets mount the password in a file. We read it from there.
        # The path is provided by an environment variable.
        db_password = None
        password_file_path = os.environ.get('DB_PASSWORD_FILE')
        if password_file_path:
            with open(password_file_path, 'r') as f:
                db_password = f.read().strip()
        else:
            # Fallback for local development if needed
            db_password = os.environ.get('DB_PASSWORD')

        if not db_password:
            current_app.logger.error("Database password not found.")
            return None

        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST'),
            database=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=db_password
        )

        if connection.is_connected():
            return connection

    except Error as e:
        # Use Flask's logger if available, otherwise print.
        log_message = f"Error connecting to MySQL: {e}"
        if current_app:
            current_app.logger.error(log_message)
        else:
            print(log_message)
        return None