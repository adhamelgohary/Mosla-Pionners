# db.py
import os
import mysql.connector
from mysql.connector import Error
import logging
import time
from dotenv import load_dotenv # ADDED: To load environment variables from .env file

# ADDED: Load environment variables from a .env file at the project root
load_dotenv() 

# Configure logging (this is good, no changes needed here)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Establishes a connection to the MySQL database using environment variables
    loaded from a .env file, suitable for VPS deployment.
    """
    # CHANGED: These are now read from the .env file
    DB_HOST = os.getenv('DB_HOST')
    DB_NAME = os.getenv('DB_NAME')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')

    # Log the credentials being used (except the password) for debugging
    logger.info(f"Attempting to connect to database: host={DB_HOST}, user={DB_USER}, db={DB_NAME}")

    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
        # Log which specific variable is missing for easier debugging
        if not DB_HOST: logger.error("FATAL: DB_HOST environment variable not set. Check your .env file.")
        if not DB_NAME: logger.error("FATAL: DB_NAME environment variable not set. Check your .env file.")
        if not DB_USER: logger.error("FATAL: DB_USER environment variable not set. Check your .env file.")
        if not DB_PASSWORD: logger.error("FATAL: DB_PASSWORD environment variable not set. Check your .env file.")
        return None

    # Retry mechanism is still very useful, especially if the database is on a separate server
    # or takes a moment to start up.
    for i in range(5):
        try:
            connection = mysql.connector.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connection_timeout=10
            )

            if connection.is_connected():
                logger.info(">>>> DATABASE CONNECTION SUCCESSFUL <<<<")
                return connection

        except Error as e:
            logger.error(f"Attempt {i+1}/5: Error connecting to MySQL database: {e}")
            time.sleep(5)
    
    logger.error("FATAL: Could not connect to the database after several retries.")
    return None