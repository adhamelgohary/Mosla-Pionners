# wsgi.py
# This file points Gunicorn to your main app instance.
from app import app

if __name__ == "__main__":
    app.run()