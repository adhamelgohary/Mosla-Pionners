# db.py
import os
import mysql.connector
from mysql.connector import Error
import logging
import time

# Configure logging for better debugging in Docker
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Establishes a connection to the MySQL database using environment variables
    that are set by the entrypoint.sh script from Docker secrets.
    """
    db_host = os.environ.get('DB_HOST')
    db_name = os.environ.get('DB_NAME')
    db_user = os.environ.get('DB_USER')
    # This now reads the DB_PASSWORD environment variable directly.
    # The entrypoint.sh script is responsible for creating this variable from the secret file.
    db_password = os.environ.get('DB_PASSWORD')

    # Log the credentials being used (except the password) for debugging
    logger.info(f"Attempting to connect to database: host={db_host}, user={db_user}, db={db_name}")

    if not all([db_host, db_name, db_user, db_password]):
        # Log which specific variable is missing for easier debugging
        if not db_host: logger.error("FATAL: DB_HOST environment variable not set in container.")
        if not db_name: logger.error("FATAL: DB_NAME environment variable not set in container.")
        if not db_user: logger.error("FATAL: DB_USER environment variable not set in container.")
        if not db_password: logger.error("FATAL: DB_PASSWORD environment variable was not exported by the entrypoint script.")
        return None

    # Retry mechanism to handle the case where the webapp container starts a little
    # faster than the database container is ready to accept connections.
    for i in range(5):
        try:
            connection = mysql.connector.connect(
                host=db_host,
                database=db_name,
                user=db_user,
                password=db_password,
                connection_timeout=10 # Set a timeout for the connection attempt
            )

            if connection.is_connected():
                logger.info(">>>> DATABASE CONNECTION SUCCESSFUL <<<<")
                return connection

        except Error as e:
            logger.error(f"Attempt {i+1}/5: Error connecting to MySQL database: {e}")
            # Wait 5 seconds before trying to connect again
            time.sleep(5)
    
    logger.error("FATAL: Could not connect to the database after several retries.")
    return None