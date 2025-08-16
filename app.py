# app.py
import os
import logging
import traceback
import json
from logging.handlers import RotatingFileHandler
from flask import Flask, current_app, g, jsonify, session, request, url_for, render_template, flash, redirect
from flask_login import current_user
from dotenv import load_dotenv
import humanize
from datetime import datetime, date, timedelta

load_dotenv()

# --- Import Utility Functions & Blueprints ---
from db import get_db_connection
from utils.decorators import MANAGERIAL_PORTAL_ROLES
from utils.directory_configs import configure_directories
from utils.template_helpers import register_template_helpers

from routes.admin.admin_routes import admin_bp
from routes.Auth.login_routes import login_bp, init_login_manager
from routes.Auth.register_routes import register_bp
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
from routes.Candidate_Portal.candidate_routes import candidate_bp
from routes.Client_Portal.dashboard_routes import client_dashboard_bp
from routes.Client_Portal.offer_routes import client_offers_bp
from routes.Website.courses_page_routes import courses_page_bp
from routes.Website.public_routes import public_routes_bp
from routes.Website.job_board_routes import job_board_bp
from routes.Account_Manager_Portal.am_offer_mgmt_routes import am_offer_mgmt_bp
from routes.Account_Manager_Portal.am_schedule_mgmt_routes import am_schedule_mgmt_bp
from routes.Account_Manager_Portal.am_interview_mgmt_routes import am_interview_mgmt_bp
from routes.Account_Manager_Portal.company_assignment_routes import company_assignment_bp
from routes.Account_Manager_Portal.am_portal_routes import account_manager_bp
from routes.Account_Manager_Portal.am_organization_routes import am_org_bp
from routes.Recruiter_Team_Portal.dashboard_routes import dashboard_bp
from routes.Recruiter_Team_Portal.organization_routes import organization_bp
from routes.Recruiter_Team_Portal.staff_routes import staff_bp
from routes.Recruiter_Team_Portal.jobs_routes import jobs_bp
from routes.instructor_portal.portal_routes import instructor_portal_bp

from routes.Recruiter_Team_Portal.organization_routes import (
    RECRUITER_PORTAL_ROLES,
    LEADER_ROLES_IN_PORTAL,
    ORG_MANAGEMENT_ROLES,
    TEAM_ASSIGNMENT_ROLES,
    UNIT_AND_ORG_MANAGEMENT_ROLES
)

app = Flask(__name__)

# --- Core App Configuration ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise ValueError("FATAL ERROR: FLASK_SECRET_KEY environment variable not set.")

app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('FLASK_SESSION_LIFETIME', 3600))
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # 50MB limit

# --- Jinja Filter Definitions ---
@app.template_filter('humanize_date')
def humanize_date(dt, default=None):
    if not isinstance(dt, (datetime, date)):
        return default
    now = datetime.now(dt.tzinfo if hasattr(dt, 'tzinfo') else None)
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, datetime.min.time(), tzinfo=now.tzinfo)
    return humanize.naturaltime(now - dt)

@app.template_filter('format_timedelta_to_time')
def format_timedelta_to_time(td_object, time_format='%I:%M %p'):
    if not isinstance(td_object, timedelta):
        return td_object
    dummy_date = datetime(2000, 1, 1, 0, 0, 0)
    result_time = (dummy_date + td_object).time()
    return result_time.strftime(time_format)

app.jinja_env.filters['humanize_date'] = humanize_date
app.jinja_env.filters['format_timedelta_to_time'] = format_timedelta_to_time

# [# <-- KEY FOR DASHBOARD] This logging configuration is essential for the admin dashboard.
if not app.debug:
    log_file = os.environ.get('LOG_FILE_PATH', 'app.log')
    file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024, backupCount=5)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s [in %(pathname)s:%(lineno)d]')
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Mosla Pioneers App startup')

# --- Configure Custom Features, Extensions, and Blueprints ---
configure_directories(app)
register_template_helpers(app)
init_login_manager(app)

app.register_blueprint(admin_bp, url_prefix='/admin')
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
app.register_blueprint(dashboard_bp)
app.register_blueprint(organization_bp)
app.register_blueprint(staff_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(instructor_portal_bp, url_prefix='/instructor') # Corrected Prefix

# --- Context Processors ---
@app.context_processor
def inject_global_template_variables():
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
                if conn and conn.is_connected(): conn.close()
        unread_count = g.unread_message_count
    
    def blueprint_exists(blueprint_name):
        return blueprint_name in current_app.blueprints

    return {'unread_message_count': unread_count, 'blueprint_exists': blueprint_exists}

@app.context_processor
def inject_role_constants():
    return dict(
        RECRUITER_PORTAL_ROLES=RECRUITER_PORTAL_ROLES,
        LEADER_ROLES_IN_PORTAL=LEADER_ROLES_IN_PORTAL,
        ORG_MANAGEMENT_ROLES=ORG_MANAGEMENT_ROLES,
        TEAM_ASSIGNMENT_ROLES=TEAM_ASSIGNMENT_ROLES,
        UNIT_AND_ORG_MANAGEMENT_ROLES=UNIT_AND_ORG_MANAGEMENT_ROLES
    )

@app.context_processor
def inject_current_time():
    return {'now': datetime.now}

# --- Global Error Handling and Logging ---
def log_error_to_db(e):
    """Logs a Python exception to the ErrorLog database table."""
    tb_str = traceback.format_exc()
    
    # --- PORTAL DETECTION LOGIC ---
    path = request.path
    portal = "Unknown" # Default value
    if path.startswith('/admin'):
        portal = "Admin Portal"
    elif path.startswith('/instructor'):
        portal = "Instructor Portal"
    elif path.startswith('/staff-portal'):
        portal = "Staff Portal"
    elif path.startswith('/candidate'):
        portal = "Candidate Portal"
    elif path.startswith('/client-portal'):
        portal = "Client Portal"
    elif path.startswith('/account-manager-portal'):
        portal = "Account Manager Portal"
    elif path.startswith('/recruiter-portal'): # Assuming this prefix exists
        portal = "Recruiter Portal"
    elif path.startswith('/auth'):
        portal = "Authentication"
    else:
        portal = "Public Website"
    # --- END PORTAL LOGIC ---

    try:
        request_data = {
            'form': request.form.to_dict(),
            'args': request.args.to_dict(),
            'json': request.get_json(silent=True)
        }
        request_data_str = json.dumps(request_data)
    except Exception:
        request_data_str = "Could not serialize request data."

    conn = None
    try:
        user_id = current_user.id if current_user.is_authenticated else None
        
        if request.headers.getlist("X-Forwarded-For"):
            ip_address = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip_address = request.remote_addr

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Updated SQL to include Portal
        sql = """
            INSERT INTO ErrorLog 
            (UserID, IPAddress, Portal, Route, RequestMethod, RequestData, ErrorMessage, Traceback)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        # Updated params tuple
        params = (
            user_id,
            ip_address,
            portal, # <-- Add the detected portal name
            request.path,
            request.method,
            request_data_str,
            str(e),
            tb_str
        )
        cursor.execute(sql, params)
        conn.commit()
    except Exception as log_e:
        app.logger.critical("--- DATABASE LOGGING FAILED ---")
        app.logger.error(f"Original Error: {e}\n{tb_str}")
        app.logger.error(f"DB Logging Error: {log_e}\n{traceback.format_exc()}")
    finally:
        if conn and conn.is_connected(): conn.close()

@app.errorhandler(Exception)
def handle_exception(e):
    """Global handler to catch all unhandled exceptions."""
    log_error_to_db(e)
    
    # For API-like requests, return JSON
    if request.path.startswith('/api/') or request.is_json:
        return jsonify(error="An internal server error occurred."), 500
        
    # For web pages, flash a message and redirect to a safe page
    flash("An unexpected error occurred. The issue has been logged.", "danger")
    
    if request.path.startswith('/instructor'):
        return redirect(url_for('instructor_portal_bp.dashboard'))
    if request.path.startswith('/staff-portal'):
        return redirect(url_for('managerial_dashboard_bp.dashboard'))
    if request.path.startswith('/admin'):
        return redirect(url_for('admin_bp.admin_dashboard'))
    
    return render_template("Errors/500.html"), 500 # Fallback to a generic error page

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

# --- Other Routes ---
@app.route('/set_theme', methods=['POST'])
def set_theme():
    data = request.get_json()
    if data and 'theme' in data:
        session['theme'] = data['theme']
        return jsonify(success=True, theme=session['theme'])
    return jsonify(success=False, error="Invalid theme data"), 400

@app.route('/health')
def health_check():
    """A simple endpoint to check if the application is alive."""
    return "OK", 200