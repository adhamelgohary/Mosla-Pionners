# app.py
import os
import logging
from logging.handlers import RotatingFileHandler # ADDED for production logging
from flask import Flask, current_app, jsonify, session, request, url_for, render_template
from flask_login import current_user
from dotenv import load_dotenv # ADDED: To load environment variables from .env file

load_dotenv()

# --- Import Utility Functions ---
from utils.directory_configs import configure_directories
from utils.template_helpers import register_template_helpers

# --- Import Blueprints ---
from routes.Auth.login_routes import login_bp, init_login_manager
from routes.Auth.register_routes import register_bp
from routes.Agency_Staff_Portal.dashboard_routes import staff_dashboard_bp
from routes.Agency_Staff_Portal.course_mgmt_routes import course_mgmt_bp
from routes.Admin_Portal.admin_routes import admin_bp
from routes.Agency_Staff_Portal.announcement_mgmt_routes import announcement_bp
from routes.Agency_Staff_Portal.job_offer_mgmt_routes import job_offer_mgmt_bp
from routes.Agency_Staff_Portal.employee_mgmt_routes import employee_mgmt_bp
from routes.Agency_Staff_Portal.leaderboard_routes import leaderboard_bp
from routes.Agency_Staff_Portal.team_routes import team_bp
from routes.Account_Manager_Portal.am_portal_routes import account_manager_bp
from routes.Website.public_routes import public_routes_bp
from routes.Website.job_board_routes import job_board_bp
from routes.Candidate_Portal.candidate_routes import candidate_bp
from routes.Account_Manager_Portal.company_assignment_routes import company_assignment_bp
from routes.Agency_Staff_Portal.candidate_details_routes import candidate_details_bp
from routes.Client_Portal.dashboard_routes import client_dashboard_bp
from routes.Client_Portal.offer_routes import client_offers_bp
from routes.Website.courses_page_routes import courses_page_bp

from routes.Recruiter_Team_Portal.recruiter_routes import recruiter_bp
# --- Create Flask App ---
app = Flask(__name__)

# --- Core App Configuration ---
# CHANGED: Reads the secret key from the .env file
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')

# CHANGED: This check is now hardened. The app will crash on startup if the key is missing.
# This is a "fail-fast" approach, which is good for production setup.
if not app.config['SECRET_KEY']:
    raise ValueError("FATAL ERROR: FLASK_SECRET_KEY environment variable not set. App cannot run.")

app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('FLASK_SESSION_LIFETIME', 3600))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB upload limit

# Configure the upload folder
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Configure Production Logging ---
# REMOVED: logging.basicConfig(...) - it's not flexible enough for production.
# ADDED: Production-ready logging to a file.
if not app.debug:
    # Create a log file that rotates when it reaches 1MB, keeping 5 old copies.
    log_file = os.environ.get('LOG_FILE_PATH', 'app.log')
    file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024, backupCount=5)
    
    # Define the format for the log messages
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s [in %(pathname)s:%(lineno)d]')
    file_handler.setFormatter(formatter)
    
    # Set the logging level and add the handler to the app
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Mosla Pioneers App startup')

# --- Configure Custom Features using Utility Functions ---
configure_directories(app)
register_template_helpers(app)

# --- Initialize Extensions ---
init_login_manager(app) # Initialize Flask-Login

# --- Register Blueprints ---
# (No changes needed in this section)
app.register_blueprint(login_bp, url_prefix='/auth')
app.register_blueprint(register_bp, url_prefix='/auth')
app.register_blueprint(staff_dashboard_bp, url_prefix='/staff-portal')
app.register_blueprint(course_mgmt_bp, url_prefix='/staff-portal/courses')
app.register_blueprint(announcement_bp, url_prefix='/staff-portal/announcements')
app.register_blueprint(job_offer_mgmt_bp, url_prefix='/staff-portal/job-offers')
app.register_blueprint(employee_mgmt_bp, url_prefix='/staff-portal/employees')
app.register_blueprint(leaderboard_bp, url_prefix='/staff-portal/leaderboard')
app.register_blueprint(company_assignment_bp, url_prefix='/staff-portal/company-assignments')
app.register_blueprint(candidate_details_bp, url_prefix='/staff/candidate')
app.register_blueprint(team_bp, url_prefix='/staff-management/team')
app.register_blueprint(client_dashboard_bp , url_prefix='/client-portal')
app.register_blueprint(client_offers_bp, url_prefix='/client-portal')
app.register_blueprint(account_manager_bp, url_prefix='/account-manager-portal')
app.register_blueprint(recruiter_bp, url_prefix='/recruiter-portal')
app.register_blueprint(admin_bp)
app.register_blueprint(public_routes_bp)
app.register_blueprint(job_board_bp)
app.register_blueprint(candidate_bp)
app.register_blueprint(courses_page_bp)

# --- Global Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    app.logger.warning(f"404 Not Found: {request.path}")
    return "Page Not Found (404)", 404

@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error(f"500 Internal Server Error: {e} at {request.path}", exc_info=True)
    return "An internal error occurred (500). Please check the server logs.", 500

# --- Theme Setter Route ---
@app.route('/set_theme', methods=['POST'])
def set_theme():
    data = request.get_json()
    if data and 'theme' in data:
        session['theme'] = data['theme']
        app.logger.info(f"Theme set to: {session['theme']}")
        return jsonify(success=True, theme=session['theme'])
    app.logger.warning("Invalid theme data received for /set_theme.")
    return jsonify(success=False, error="Invalid theme data"), 400

# --- Health Check Endpoint ---
@app.route('/health')
def health_check():
    """A simple endpoint to check if the application is alive."""
    return "OK", 200

# --- Context Processor ---
@app.context_processor
def inject_current_app_utilities():
    def blueprint_exists(blueprint_name):
        return blueprint_name in current_app.blueprints
    return dict(blueprint_exists=blueprint_exists)
