# routes/homepage_routes.py
from flask import Blueprint, render_template, current_app, session # Added session
from db import get_db_connection # Import your database connection function
# No need to import datetime here unless you do specific datetime logic within the routes
# The current_year is handled by the context_processor in app.py
# Other datetime formatting is handled by Jinja filters registered in template_helpers.py

# Create a Blueprint.
# The first argument is the blueprint's name.
# The second is its import name (usually __name__).
# template_folder='templates' is not strictly necessary if your templates
# are in the app's main 'templates' directory, but it's good practice for clarity
# if a blueprint has its own sub-folder for templates.
# Since home.html is in the main templates folder, we don't need template_folder here.
homepage_bp = Blueprint('homepage_bp', __name__, template_folder='templates')

@homepage_bp.route('/')
def home_page():
    """
    Renders the main homepage.
    Checks database connectivity as an example.
    """
    current_app.logger.info(f"Accessing homepage. Current theme from session: {session.get('theme')}")
    db_conn = None
    db_status = "Not Connected"
    try:
        db_conn = get_db_connection()
        if db_conn and db_conn.is_connected():
            db_status = "Successfully connected to the database!"
            current_app.logger.info("Database connection successful for homepage.")
            # Optional: Perform a simple query to verify further
            # cursor = db_conn.cursor()
            # cursor.execute("SELECT VERSION();") # Example query
            # db_version = cursor.fetchone()
            # current_app.logger.info(f"MySQL Version: {db_version[0] if db_version else 'N/A'}")
            # cursor.close()
        else:
            db_status = "Failed to connect to the database."
            current_app.logger.warning("Database connection failed for homepage.")
    except Exception as e:
        db_status = f"Database connection error: {str(e)}"
        current_app.logger.error(f"Database connection error on homepage: {e}", exc_info=True)
    finally:
        if db_conn and db_conn.is_connected():
            db_conn.close()
            current_app.logger.info("Database connection closed after homepage check.")

    # The 'current_year' will be available from the context processor in app.py
    # The 'theme' for the html tag will be handled by the base.html using session
    return render_template('Website/home.html', db_status=db_status)

# If you had other routes specific to general site pages (like an About Us page, Contact page if not part of home),
# they could also go here. For example:
#
# @homepage_bp.route('/about-us')
# def about_us_page():
#     return render_template('about_us.html')
#
# @homepage_bp.route('/contact-us', methods=['GET', 'POST'])
# def contact_us_page():
#     if request.method == 'POST':
#         # Handle contact form submission
#         pass
#     return render_template('contact_us.html')