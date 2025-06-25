# routes/Auth/login_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session # Added session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
import datetime
import re
from werkzeug.security import check_password_hash
from db import get_db_connection
import mysql.connector
from urllib.parse import urlparse, urljoin # For is_safe_url

login_bp = Blueprint('login_bp', __name__, template_folder='../../templates/auth')
login_manager = LoginManager()

# This list defines which roles are considered "Agency Staff" for redirection purposes
AGENCY_STAFF_ROLES = [
    'SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager',
    'AccountManager', 'SeniorAccountManager', 'HeadAccountManager',
    'OperationsManager', 'CEO', 'SalesManager', 'Admin'
]
CLIENT_ROLES = ['ClientContact'] # External clients

class LoginUser(UserMixin):
    def __init__(self, user_id, email, first_name, last_name, is_active_status, role_type, specific_role_id=None, company_id=None, reports_to_id=None, password_hash=None):
        self.id = int(user_id)
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self._is_active_status = bool(is_active_status)
        self.role_type = role_type
        self.specific_role_id = specific_role_id
        self.company_id = company_id
        self.reports_to_id = reports_to_id
        self.password_hash = password_hash

    @property
    def is_active(self):
        return self._is_active_status

    def check_password(self, password_to_check):
        if self.password_hash is None: return False
        return check_password_hash(self.password_hash, password_to_check)

def determine_user_identity(user_id, db_connection):
    """Determines user role from Staff, CompanyContacts, or Candidates."""
    cursor = db_connection.cursor(dictionary=True)
    identity = {'role': "Unknown", 'id': None, 'company_id': None, 'reports_to_id': None}
    try:
        cursor.execute("SELECT StaffID, Role, ReportsToStaffID FROM Staff WHERE UserID = %s", (user_id,))
        if record := cursor.fetchone():
            identity['role'] = record['Role']
            identity['id'] = record['StaffID']
            identity['reports_to_id'] = record['ReportsToStaffID']
        else:
            cursor.execute("SELECT ContactID, CompanyID FROM CompanyContacts WHERE UserID = %s", (user_id,))
            if record := cursor.fetchone():
                identity['role'] = "ClientContact"
                identity['id'] = record['ContactID']
                identity['company_id'] = record['CompanyID']
            else:
                cursor.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (user_id,))
                if record := cursor.fetchone():
                    identity['role'] = "Candidate"
                    identity['id'] = record['CandidateID']
    except Exception as e:
        current_app.logger.error(f"Error determining role for UserID {user_id}: {e}", exc_info=True)
        identity = {'role': "ErrorDeterminingRole", 'id': None, 'company_id': None, 'reports_to_id': None}
    finally:
        if cursor: cursor.close()
    return identity

def get_user_by_id(user_id):
    """Fetches a user and builds the complete LoginUser object."""
    conn = get_db_connection()
    if not conn:
        current_app.logger.error(f"get_user_by_id: DB connection failed for user_id {user_id}")
        return None
    user_obj = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE UserID = %s", (user_id,))
        if user_data := cursor.fetchone():
            identity = determine_user_identity(user_data['UserID'], conn)
            user_obj = LoginUser(
                user_id=user_data['UserID'], email=user_data['Email'], first_name=user_data['FirstName'],
                last_name=user_data['LastName'], is_active_status=user_data['IsActive'],
                role_type=identity['role'], specific_role_id=identity['id'], company_id=identity['company_id'],
                reports_to_id=identity['reports_to_id'], password_hash=user_data.get('PasswordHash')
            )
    except Exception as e:
        current_app.logger.error(f"Error in get_user_by_id for {user_id}: {e}", exc_info=True)
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return user_obj

def get_user_by_email(email):
    """Fetches a user by email and builds the complete LoginUser object."""
    conn = get_db_connection()
    if not conn:
        current_app.logger.error(f"get_user_by_email: DB connection failed for email {email}")
        return None
    user_obj = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE Email = %s", (email,))
        if user_data := cursor.fetchone():
            identity = determine_user_identity(user_data['UserID'], conn)
            user_obj = LoginUser(
                user_id=user_data['UserID'], email=user_data['Email'], first_name=user_data['FirstName'],
                last_name=user_data['LastName'], is_active_status=user_data['IsActive'],
                role_type=identity['role'], specific_role_id=identity['id'], company_id=identity['company_id'],
                reports_to_id=identity['reports_to_id'], password_hash=user_data.get('PasswordHash')
            )
    except Exception as e:
        current_app.logger.error(f"Error in get_user_by_email for {email}: {e}", exc_info=True)
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return user_obj

def is_valid_email_format(email):
    if email:
        return re.match(r"[^@]+@[^@]+\.[^@]+", email)
    return False

def init_login_manager(app):
    login_manager.init_app(app)
    login_manager.login_view = 'login_bp.login'
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"
    app.config.setdefault('REMEMBER_COOKIE_NAME', 'remember_token_mosla')
    app.config.setdefault('REMEMBER_COOKIE_DURATION', datetime.timedelta(days=30))
    app.config.setdefault('REMEMBER_COOKIE_SECURE', app.config.get('PREFERRED_URL_SCHEME') == 'https')
    app.config.setdefault('REMEMBER_COOKIE_HTTPONLY', True)
    app.config.setdefault('REMEMBER_COOKIE_SAMESITE', 'Lax')

    @login_manager.user_loader
    def load_user(user_id):
        return get_user_by_id(user_id)

def is_safe_url(target):
    """
    Checks if a target URL is safe for redirection.
    Ensures it's on the same host and uses http/https.
    Allows relative paths or full paths on the same host.
    """
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target)) # Resolves relative URLs
    
    # Check scheme and netloc (hostname and port)
    is_same_site = test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc
    
    # Allow relative paths or full paths that match the host URL
    is_valid_path_format = target.startswith('/') or target.startswith(request.host_url) or not urlparse(target).scheme # Allow simple relative paths like 'page'

    return is_same_site and is_valid_path_format

@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        next_page_from_url = request.args.get('next')
        if next_page_from_url and is_safe_url(next_page_from_url):
            current_app.logger.info(f"Authenticated user, redirecting to 'next': {next_page_from_url}")
            return redirect(next_page_from_url)

        # Default redirection for already authenticated users
        if current_user.role_type in AGENCY_STAFF_ROLES:
            return redirect(url_for('staff_dashboard_bp.main_dashboard'))
        elif current_user.role_type in CLIENT_ROLES:
            return redirect(url_for('client_portal_bp.dashboard')) # Assumed route
        elif current_user.role_type == 'Candidate':
            return redirect(url_for('candidate_bp.dashboard')) # Assumed route
        return redirect(url_for('homepage_bp.home_page'))

    errors = {}
    form_data = {}

    if request.method == 'GET':
        form_data = request.args.to_dict() # Pre-fill email if passed
        # Store referrer if no 'next' param, for potential candidate redirection
        if not request.args.get('next') and request.referrer:
            referrer_path = urlparse(request.referrer).path
            # Check if referrer is from the same site and not an auth path itself
            auth_blueprint_prefix = url_for('login_bp.login').rsplit('/', 1)[0] # e.g., /auth
            
            if urlparse(request.referrer).netloc == request.host and \
               not referrer_path.startswith(auth_blueprint_prefix) and \
               referrer_path != url_for('login_bp.login'): # Avoid self-referencing
                session['candidate_intended_destination'] = request.referrer
                current_app.logger.info(f"Login GET: Stored potential candidate destination: {request.referrer}")
            elif 'candidate_intended_destination' in session and \
                 (referrer_path.startswith(auth_blueprint_prefix) or referrer_path == url_for('login_bp.login')):
                 # Clear if now on an auth page to prevent loop or stale redirect
                 session.pop('candidate_intended_destination', None)
                 current_app.logger.info("Login GET: Cleared candidate_intended_destination due to auth page referrer.")


    if request.method == 'POST':
        form_data = request.form.to_dict()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        if not email: errors['email'] = 'Email address is required.'
        elif not is_valid_email_format(email): errors['email'] = 'Invalid email format.'
        if not password: errors['password'] = 'Password is required.'

        if not errors:
            user_obj = get_user_by_email(email)
            if user_obj and user_obj.check_password(password):
                if user_obj.is_active:
                    login_user(user_obj, remember=remember)
                    current_app.logger.info(f"User {user_obj.email} (Role: {user_obj.role_type}) logged in. Remember: {remember}")
                    flash('Logged in successfully!', 'success')
                    
                    conn_update = None
                    try:
                        conn_update = get_db_connection()
                        if conn_update:
                            cursor_update = conn_update.cursor()
                            cursor_update.execute("UPDATE Users SET LastLoginDate = %s WHERE UserID = %s", 
                                           (datetime.datetime.now(), user_obj.id))
                            conn_update.commit()
                    except Exception as e_update:
                        current_app.logger.error(f"Error updating LastLoginDate for user {user_obj.id}: {e_update}")
                    finally:
                        if 'cursor_update' in locals() and cursor_update: cursor_update.close()
                        if conn_update and conn_update.is_connected(): conn_update.close()

                    next_page = request.args.get('next')
                    if user_obj.role_type == 'Candidate':
                        # Priority 1: 'next' from URL (e.g., from @login_required or registration)
                        if next_page and is_safe_url(next_page): # is_safe_url is important!
                            current_app.logger.info(f"Candidate redirecting to 'next' from URL: {next_page}")
                            return redirect(next_page)
                        
                        intended_destination = session.pop('candidate_intended_destination', None)
                        if intended_destination and is_safe_url(intended_destination):
                            current_app.logger.info(f"Candidate redirecting to session stored 'intended_destination': {intended_destination}")
                            return redirect(intended_destination)
                        
                        current_app.logger.info("Candidate redirecting to default candidate dashboard.")
                        return redirect(url_for('candidate_bp.dashboard')) # Assumed route
                    
                    # For non-candidates, their dashboards are default, but 'next' takes priority
                    elif user_obj.role_type in AGENCY_STAFF_ROLES:
                        if next_page_from_url and is_safe_url(next_page_from_url):
                             current_app.logger.info(f"Agency Staff redirecting to 'next' from URL: {next_page_from_url}")
                             return redirect(next_page_from_url)
                        return redirect(url_for('staff_dashboard_bp.main_dashboard'))
                    elif user_obj.role_type in CLIENT_ROLES:
                        if next_page_from_url and is_safe_url(next_page_from_url):
                             current_app.logger.info(f"Client redirecting to 'next' from URL: {next_page_from_url}")
                             return redirect(next_page_from_url)
                        return redirect(url_for('client_portal_bp.dashboard')) # Assumed route
                    else: 
                        current_app.logger.warning(f"User {user_obj.email} with unknown role '{user_obj.role_type}' after login.")
                        if next_page_from_url and is_safe_url(next_page_from_url):
                            return redirect(next_page_from_url)
                        return redirect(url_for('homepage_bp.home_page'))
                else:
                    current_app.logger.warning(f"Login attempt for inactive user: {email}")
                    flash('Your account is inactive. Please contact support.', 'warning')
                    errors['form'] = 'Account inactive.'
            else:
                current_app.logger.warning(f"Failed login attempt for: {email}")
                flash('Invalid email or password. Please try again.', 'danger')
                errors['form'] = 'Invalid credentials.'
        else:
            flash('Please correct the errors below.', 'danger')
            
    return render_template('auth/login.html', title='Login', errors=errors, form_data=form_data)

@login_bp.route('/logout')
@login_required
def logout():
    user_email = current_user.email if hasattr(current_user, 'email') else f"UserID: {current_user.id}"
    # Clear any candidate-specific session data on logout
    session.pop('candidate_intended_destination', None)
    logout_user()
    flash('You have been logged out.', 'success')
    current_app.logger.info(f"User {user_email} logged out.")
    return redirect(url_for('login_bp.login'))