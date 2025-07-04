# wsgi.py

from dotenv import load_dotenv

# This line loads the variables from the .env file into the environment
# It MUST be called before you import the 'app' object
print("--- wsgi.py: Loading .env file ---")
load_dotenv()
print("--- wsgi.py: .env file loaded. Importing app. ---")

# Now that the environment variables are set, we can import the app
from app import app

if __name__ == "__main__":
    app.run()