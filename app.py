# app.py
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, current_app, g, jsonify, session, request, url_for, render_template
from flask_login import current_user
from dotenv import load_dotenv
import humanize
from datetime import datetime, timezone, date, timedelta

load_dotenv()

# --- Import Utility Functions ---
from db import get_db_connection
from utils.decorators import MANAGERIAL_PORTAL_ROLES
from utils.directory_configs import configure_directories
from utils.template_helpers import register_template_helpers

# --- Import Blueprints ---

# [# <-- KEY FOR DASHBOARD] 1. Import the admin blueprint
from routes.admin.admin_routes import admin_bp

# Authentication Routes
from routes.Auth.login_routes import login_bp, init_login_manager
from routes.Auth.register_routes import register_bp

# Agency Staff Portal Routes
from routes.Agency_Staff_Portal.dashboard_routes import managerial_dashboard_bp
from routes.Agency_Staff_Portal.course_mgmt_routes import package_mgmt_bp
from routes.Agency_Staff_Portal.announcement_mgmt_routes import announcement_bp
from routes.Agency_Staff_Portal.job_offer_mgmt_routes import job_offer_mgmt_bp
from routes.Agency_Staff_Portal.staff_candidate_routes import staff_candidate_bp
from routes.Agency_Staff_Portal.reporting_routes import reporting_bp
from routes.Agency_Staff_Portal.staff_and_performance_routes import staff_perf_bp
from routes.Agency_Staff_Portal.inquiry_mgmt_routes import inquiry_mgmt_bp
from routes.Agency_Staff_Portal.client_management_routes import client_mgmt_bp
from routes.Agency_Staff_Portal.group_mgmt_routes import group_mgmt_bp

# Candidate Portal Routes
from routes.Candidate_Portal.candidate_routes import candidate_bp

# Client Portal Routes
from routes.Client_Portal.dashboard_routes import client_dashboard_bp
from routes.Client_Portal.offer_routes import client_offers_bp

# Website Routes
from routes.Website.courses_page_routes import courses_page_bp
from routes.Website.public_routes import public_routes_bp
from routes.Website.job_board_routes import job_board_bp

# Account Manager Portal Routes
from routes.Account_Manager_Portal.am_offer_mgmt_routes import am_offer_mgmt_bp
from routes.Account_Manager_Portal.am_schedule_mgmt_routes import am_schedule_mgmt_bp
from routes.Account_Manager_Portal.am_interview_mgmt_routes import am_interview_mgmt_bp
from routes.Account_Manager_Portal.company_assignment_routes import company_assignment_bp
from routes.Account_Manager_Portal.am_portal_routes import account_manager_bp
from routes.Account_Manager_Portal.am_organization_routes import am_org_bp

# Recruiter Portal Routes
from routes.Recruiter_Team_Portal.dashboard_routes import dashboard_bp
from routes.Recruiter_Team_Portal.organization_routes import organization_bp
from routes.Recruiter_Team_Portal.staff_routes import staff_bp
from routes.Recruiter_Team_Portal.jobs_routes import jobs_bp

# instructor portal routes
from routes.instructor_portal.portal_routes import instructor_portal_bp

# --- ROLE CONSTANTS ---
from routes.Recruiter_Team_Portal.organization_routes import (
    RECRUITER_PORTAL_ROLES,
    LEADER_ROLES_IN_PORTAL,
    ORG_MANAGEMENT_ROLES,
    TEAM_ASSIGNMENT_ROLES,
    UNIT_AND_ORG_MANAGEMENT_ROLES
)

# --- Create Flask App ---
app = Flask(__name__)

# --- Jinja Filter Definitions ---

@app.template_filter('humanize_date')
def humanize_date(dt, default=None):
    """
    Returns a human-readable string for a datetime object.
    e.g., "2 hours ago", "3 days ago"
    """
    if not isinstance(dt, (datetime, date)):
        return default
    
    now = datetime.now(dt.tzinfo if hasattr(dt, 'tzinfo') else None)
    
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, datetime.min.time(), tzinfo=now.tzinfo)

    return humanize.naturaltime(now - dt)

@app.template_filter('format_timedelta_to_time')
def format_timedelta_to_time(td_object, time_format='%I:%M %p'):
    """
    Custom Jinja filter to format a timedelta object into a time string.
    Example: a timedelta of 9 hours becomes '09:00 AM'.
    """
    if not isinstance(td_object, timedelta):
        return td_object
    
    dummy_date = datetime(2000, 1, 1, 0, 0, 0)
    result_time = (dummy_date + td_object).time()
    return result_time.strftime(time_format)

# --- Core App Configuration ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise ValueError("FATAL ERROR: FLASK_SECRET_KEY environment variable not set. App cannot run.")

app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('FLASK_SESSION_LIFETIME', 3600))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB upload limit

# Register the filters with Jinja
app.jinja_env.filters['humanize_date'] = humanize_date
app.jinja_env.filters['format_timedelta_to_time'] = format_timedelta_to_time

# Configure the upload folder
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # 50MB limit

# [# <-- KEY FOR DASHBOARD] 2. This logging configuration writes errors and other info to a file,
# which the admin dashboard reads to display recent logs. This block is essential.
if not app.debug:
    log_file = os.environ.get('LOG_FILE_PATH', 'app.log')
    # Using RotatingFileHandler to prevent log files from becoming excessively large.
    file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024, backupCount=5)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s [in %(pathname)s:%(lineno)d]')
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Mosla Pioneers App startup')

# --- Configure Custom Features using Utility Functions ---
configure_directories(app)
register_template_helpers(app)

# --- Initialize Extensions ---
init_login_manager(app) # Initialize Flask-Login

# [# <-- KEY FOR DASHBOARD] 3. Register the admin blueprint so its routes are active.
app.register_blueprint(admin_bp, url_prefix='/admin')

# --- Register Other Blueprints ---
app.register_blueprint(login_bp, url_prefix='/auth')
app.register_blueprint(register_bp, url_prefix='/auth')
app.register_blueprint(managerial_dashboard_bp, url_prefix='/staff-portal')
app.register_blueprint(package_mgmt_bp, url_prefix='/staff-portal/packages')
app.register_blueprint(announcement_bp, url_prefix='/staff-portal/announcements')
app.register_blueprint(job_offer_mgmt_bp, url_prefix='/staff-portal/job-offers')
app.register_blueprint(company_assignment_bp, url_prefix='/staff-portal/company-assignments')
app.register_blueprint(staff_candidate_bp, url_prefix='/staff-portal/candidates')
app.register_blueprint(inquiry_mgmt_bp, url_prefix='/staff-portal/inquiries')
app.register_blueprint(staff_perf_bp)
app.register_blueprint(reporting_bp)
app.register_blueprint(client_dashboard_bp , url_prefix='/client-portal')
app.register_blueprint(client_offers_bp, url_prefix='/client-portal')
app.register_blueprint(account_manager_bp, url_prefix='/account-manager-portal')
app.register_blueprint(am_offer_mgmt_bp, url_prefix='/account-manager-portal/offer-management')
app.register_blueprint(am_schedule_mgmt_bp, url_prefix='/account-manager-portal/schedule-management')
app.register_blueprint(am_interview_mgmt_bp, url_prefix='/account-manager-portal/interview-management')
app.register_blueprint(am_org_bp, url_prefix='/account-manager-portal/organization')
app.register_blueprint(public_routes_bp)
app.register_blueprint(job_board_bp)
app.register_blueprint(candidate_bp)
app.register_blueprint(courses_page_bp)
app.register_blueprint(client_mgmt_bp)
app.register_blueprint(group_mgmt_bp)

# --- Recruiter Portal Routes ---
app.register_blueprint(dashboard_bp)
app.register_blueprint(organization_bp)
app.register_blueprint(staff_bp)
app.register_blueprint(jobs_bp)

# --- Instructor Portal Routes ---
app.register_blueprint(instructor_portal_bp, url_prefix='/instructor-portal')


# ==========================================================
# --- START: COMBINED CONTEXT PROCESSOR ---
# ==========================================================
@app.context_processor
def inject_global_template_variables():
    """
    Injects globally needed variables and utility functions into the template context.
    """
    # 1. Logic for unread message count
    unread_count = 0
    if current_user.is_authenticated and hasattr(current_user, 'role_type') and current_user.role_type in MANAGERIAL_PORTAL_ROLES:
        if 'unread_message_count' not in g:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT COUNT(*) as count FROM ContactMessages WHERE Status = 'Unread'")
                result = cursor.fetchone()
                g.unread_message_count = result['count'] if result else 0
            except Exception:
                g.unread_message_count = 0 
            finally:
                if conn and conn.is_connected():
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn.close()
        unread_count = g.unread_message_count
    
    # 2. Logic for blueprint_exists utility
    def blueprint_exists(blueprint_name):
        return blueprint_name in current_app.blueprints

    # 3. Return a single dictionary containing all global variables
    return {
        'unread_message_count': unread_count,
        'blueprint_exists': blueprint_exists
    }
# ==========================================================
# --- END: COMBINED CONTEXT PROCESSOR ---
# ==========================================================


@app.context_processor
def inject_role_constants():
    """
    Injects role constants into the context of all templates.
    This allows templates to use expressions like:
    {% if current_user.role_type in LEADER_ROLES_IN_PORTAL %}
    """
    return dict(
        RECRUITER_PORTAL_ROLES=RECRUITER_PORTAL_ROLES,
        LEADER_ROLES_IN_PORTAL=LEADER_ROLES_IN_PORTAL,
        ORG_MANAGEMENT_ROLES=ORG_MANAGEMENT_ROLES,
        TEAM_ASSIGNMENT_ROLES=TEAM_ASSIGNMENT_ROLES,
        UNIT_AND_ORG_MANAGEMENT_ROLES=UNIT_AND_ORG_MANAGEMENT_ROLES
    )

# --- Global Error Handlers ---
@app.errorhandler(400)
def bad_request(e):
    description = e.description or "The server could not process the request due to a client error."
    app.logger.warning(f"400 Bad Request: {description} - URL: {request.path}")
    return render_template("Errors/400.html", title="Bad Request", error_description=description), 400

@app.errorhandler(401)
def unauthorized(e):
    app.logger.info(f"401 Unauthorized: Access attempt to {request.path} by unauthenticated user.")
    return render_template("Errors/401.html", title="Unauthorized"), 401

@app.errorhandler(403)
def forbidden(e):
    app.logger.warning(f"403 Forbidden: Access denied for path {request.path} by user '{current_user.id if current_user.is_authenticated else 'Anonymous'}'")
    return render_template("Errors/403.html", title="Access Forbidden"), 403

@app.errorhandler(404)
def page_not_found(e):
    app.logger.warning(f"404 Not Found: {request.path}")
    return render_template("Errors/404.html", title="Page Not Found"), 404

@app.errorhandler(429)
def ratelimit_handler(e):
    app.logger.warning(f"429 Too Many Requests: Rate limit exceeded for {request.remote_addr} on path {request.path}")
    return render_template("Errors/429.html", title="Too Many Requests"), 429

@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error(f"500 Internal Server Error: {e} at {request.path}", exc_info=True)
    return render_template("Errors/500.html", title="Internal Server Error"), 500

@app.errorhandler(503)
def service_unavailable(e):
    app.logger.critical(f"503 Service Unavailable: {e.description or 'The service is temporarily down.'}")
    return render_template("Errors/503.html", title="Service Unavailable"), 503

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
