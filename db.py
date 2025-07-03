# db.py
import os
import mysql.connector
from mysql.connector import Error
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Establishes a connection to the MySQL database using environment variables.
    """
    db_host = os.environ.get('DB_HOST')
    db_name = os.environ.get('DB_NAME')
    db_user = os.environ.get('DB_USER')

    # THE FIX IS HERE: Read the password directly from the environment
    db_password = os.environ.get('DB_PASSWORD') 

    # Log the credentials being used (except the password) for debugging
    logger.info(f"Attempting to connect to database: host={db_host}, user={db_user}, db={db_name}")

    if not all([db_host, db_name, db_user, db_password]):
        logger.error("FATAL: One or more database environment variables (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD) are not set.")
        return None

    try:
        connection = mysql.connector.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password
        )

        if connection.is_connected():
            logger.info("Database connection successful.")
            return connection

    except Error as e:
        logger.error(f"Error connecting to MySQL database: {e}")
        return None
        
    return None # Should not be reached, but as a fallback