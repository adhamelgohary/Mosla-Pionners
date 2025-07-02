# app.py
import os
import logging
from flask import Flask, current_app, jsonify, session, request, redirect, url_for, render_template
from flask_mail import Mail # Message is used in send_email_utility
from flask_login import login_required, current_user

# --- Import Utility Functions ---
from utils.MailConfig import MailConfig
from utils.directory_configs import configure_directories, save_file_from_config # Import the function
from utils.template_helpers import register_template_helpers

# --- Import Blueprints ---
from routes.Auth.login_routes import login_bp, init_login_manager # login_bp and its init function
from routes.Auth.register_routes import register_bp
from routes.Agency_Staff_Portal.dashboard_routes import staff_dashboard_bp # New
from routes.Agency_Staff_Portal.course_mgmt_routes import course_mgmt_bp # New
from routes.Admin_Portal.admin_routes import admin_bp               # New
from routes.Agency_Staff_Portal.announcement_mgmt_routes import announcement_bp
from routes.Agency_Staff_Portal.job_offer_mgmt_routes import job_offer_mgmt_bp
from routes.Agency_Staff_Portal.employee_mgmt_routes import employee_mgmt_bp
from routes.Agency_Staff_Portal.leaderboard_routes import leaderboard_bp
from routes.Agency_Staff_Portal.team_routes import team_bp
from routes.Account_Manager_Portal.am_portal_routes import account_manager_bp

from routes.Website.public_routes import public_routes_bp
from routes.Website.job_board_routes import job_board_bp # NEW: For job listings and details
from routes.Candidate_Portal.candidate_routes import candidate_bp # IMPORT IT
from routes.Account_Manager_Portal.company_assignment_routes import company_assignment_bp # New: For company assignments
from routes.Agency_Staff_Portal.candidate_details_routes import candidate_details_bp

from routes.Client_Portal.dashboard_routes import client_dashboard_bp
from routes.Client_Portal.offer_routes import client_offers_bp

# --- Create Flask App ---
app = Flask(__name__)

# --- Core App Configuration ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a-very-insecure-default-secret-key-for-dev')
if app.config['SECRET_KEY'] == 'a-very-insecure-default-secret-key-for-dev':
    app.logger.warning("SECURITY WARNING: Using default SECRET_KEY. Set FLASK_SECRET_KEY environment variable for production.")

app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('FLASK_SESSION_LIFETIME', 3600))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB upload limit

# Example UPLOAD_FOLDER configuration - configure_directories should handle this
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# --- Configure Logging ---
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO if not app.debug else logging.DEBUG)

# --- Configure Custom Features using Utility Functions ---
configure_directories(app) # <<< CALL IT HERE
register_template_helpers(app)

# --- Initialize Extensions ---
MailConfig.init_app(app)
mail = Mail(app)
init_login_manager(app) # Initialize Flask-Login via the function from login_routes

# --- Register Blueprints ---
app.register_blueprint(login_bp, url_prefix='/auth')
app.register_blueprint(register_bp, url_prefix='/auth')

# Agency Staff Portal Blueprints - both under /staff-portal
# The url_prefix in the blueprint definition will be appended to this
# So, staff_dashboard_bp routes will be like /staff-portal/dashboard/...
# And course_mgmt_bp routes will be like /staff-portal/courses/...
app.register_blueprint(staff_dashboard_bp, url_prefix='/staff-portal')
app.register_blueprint(course_mgmt_bp, url_prefix='/staff-portal/courses') # Will effectively be /staff-portal/courses/*
app.register_blueprint(announcement_bp, url_prefix='/staff-portal/announcements') # Will effectively be /staff-portal/announcements/*
app.register_blueprint(job_offer_mgmt_bp, url_prefix='/staff-portal/job-offers') # Will effectively be /staff-portal/job-offers/*
app.register_blueprint(employee_mgmt_bp, url_prefix='/staff-portal/employees')
app.register_blueprint(leaderboard_bp, url_prefix='/staff-portal/leaderboard')
app.register_blueprint(company_assignment_bp, url_prefix='/staff-portal/company-assignments') # Will effectively be /staff-portal/company-assignments/*
app.register_blueprint(candidate_details_bp, url_prefix='/staff/candidate') # url_prefix is defined in candidate_details_bp itself
app.register_blueprint(team_bp, url_prefix='/staff-management/team') # New, more specific prefix
app.register_blueprint(client_dashboard_bp , url_prefix='/client-portal')
app.register_blueprint(client_offers_bp, url_prefix='/client-portal') # Client Portal under /client-portal/*
app.register_blueprint(account_manager_bp, url_prefix='/account-manager-portal')


app.register_blueprint(admin_bp) # url_prefix is defined in admin_bp itself
app.register_blueprint(public_routes_bp) # url_prefix is defined in public_routes_bp itself
app.register_blueprint(job_board_bp) # url_prefix is defined in job_board_bp itself
app.register_blueprint(candidate_bp) # url_prefix is defined in candidate_bp itself



# --- Helper function to send email (Moved to app.py for broader access if needed) ---
def send_email_utility(subject, recipients, text_body, html_body=None, sender=None):
    from flask_mail import Message # Import here to avoid circular dependency if mail is not fully init
    if sender is None:
        sender = app.config.get('MAIL_DEFAULT_SENDER', app.config.get('MAIL_USERNAME', 'noreply@moslapioneers.com'))

    if not app.config.get('MAIL_SERVER') or not app.config.get('MAIL_USERNAME'):
        app.logger.error("Mail server or username not configured. Cannot send email.")
        return False

    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    if html_body:
        msg.html = html_body
    try:
        mail.send(msg)
        app.logger.info(f"Email sent successfully to {', '.join(recipients)} with subject '{subject}'")
        return True
    except Exception as e:
        app.logger.error(f"Failed to send email to {recipients} with subject '{subject}': {e}")
        return False

# --- Example Route to trigger email sending (for testing) ---
@app.route('/send-test-email')
def send_test_email_route():
    test_recipient_email = os.environ.get("TEST_EMAIL_RECIPIENT", "test@example.com")
    subject = "Flask-Mail Test Email from Mosla Pioneers"
    text_body = "This is a test email sent from your Mosla Pioneers Flask application."
    html_body = "<h1>Flask-Mail Test</h1><p>This is a test email from <b>Mosla Pioneers</b>.</p>"
    if send_email_utility(subject, [test_recipient_email], text_body, html_body):
        return jsonify(message=f"Test email sent to {test_recipient_email}!", status="success"), 200
    else:
        return jsonify(message="Failed to send test email. Check logs and mail config.", status="error"), 500

# --- Global Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    app.logger.warning(f"404 Not Found: {request.path}")
    # return render_template('errors/404.html', error=e), 404 # Create a specific 404 template
    return "Page Not Found (404)", 404

@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error(f"500 Internal Server Error: {e} at {request.path}", exc_info=True)
    # return render_template('errors/500.html', error=e), 500 # Create a specific 500 template
    return "An internal error occurred (500).", 500

@app.route('/set_theme', methods=['POST'])
def set_theme(): # <--- THIS IS THE FUNCTION NAME
    data = request.get_json()
    if data and 'theme' in data:
        session['theme'] = data['theme']
        app.logger.info(f"Theme set to: {session['theme']}")
        return jsonify(success=True, theme=session['theme'])
    app.logger.warning("Invalid theme data received.")
    return jsonify(success=False, error="Invalid theme data"), 400

# --- Health Check Endpoint ---
@app.route('/health')
def health_check():
    return "OK", 200

@app.context_processor
def inject_current_app_utilities():
    def blueprint_exists(blueprint_name):
        return blueprint_name in current_app.blueprints
    return dict(blueprint_exists=blueprint_exists)

# --- Run the App ---
if __name__ == '__main__':
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_RUN_PORT', 12345))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']

    app.logger.info(f"Starting Mosla Pioneers App on http://{host}:{port} (Debug: {debug})")
    app.run(debug=debug, host=host, port=port)