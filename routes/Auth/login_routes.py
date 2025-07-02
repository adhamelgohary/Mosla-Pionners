# routes/Auth/login_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
import datetime
import re
from werkzeug.security import check_password_hash
from db11 import get_db_connection
import mysql.connector
from urllib.parse import urlparse, urljoin

login_bp = Blueprint('login_bp', __name__, template_folder='../../templates/auth')
login_manager = LoginManager()

# --- UPDATED ROLE CONSTANTS ---

# This list defines general staff roles for redirection to the main staff dashboard.
AGENCY_STAFF_ROLES = [
    'SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager',
    'OperationsManager', 'CEO', 'SalesManager', 'Admin', 'Founder'
]
# Defines Account Manager roles for redirection to the dedicated AM portal.
ACCOUNT_MANAGER_ROLES = ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager']
# Defines Client roles for redirection to the client portal.
CLIENT_ROLES = ['ClientContact']

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
        identity['role'] = "ErrorDeterminingRole"
    finally:
        if cursor: cursor.close()
    return identity

def get_user_by_id(user_id):
    conn = get_db_connection()
    if not conn: return None
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
    conn = get_db_connection()
    if not conn: return None
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
    return email and re.match(r"[^@]+@[^@]+\.[^@]+", email)

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
    if not target: return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    is_same_site = test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc
    is_valid_path_format = target.startswith('/') or (not urlparse(target).scheme and not urlparse(target).netloc) or target.startswith(request.host_url)
    return is_same_site and is_valid_path_format

@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        next_page_from_url_auth = request.args.get('next')
        if next_page_from_url_auth and is_safe_url(next_page_from_url_auth):
            return redirect(next_page_from_url_auth)
        
        # Default redirection for already authenticated users
        if current_user.role_type in ACCOUNT_MANAGER_ROLES:
            return redirect(url_for('account_manager_bp.portal_home'))
        elif current_user.role_type in AGENCY_STAFF_ROLES:
            return redirect(url_for('staff_dashboard_bp.main_dashboard'))
        elif current_user.role_type in CLIENT_ROLES:
            return redirect(url_for('client_dashboard_bp.dashboard'))
        elif current_user.role_type == 'Candidate':
            return redirect(url_for('candidate_bp.dashboard'))
        return redirect(url_for('public_routes_bp.home_page'))

    errors, form_data = {}, {}

    if request.method == 'POST':
        form_data = request.form.to_dict()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        if not email or not is_valid_email_format(email): errors['email'] = 'A valid email is required.'
        if not password: errors['password'] = 'Password is required.'

        if not errors:
            user_obj = get_user_by_email(email)
            if user_obj and user_obj.check_password(password):
                if user_obj.is_active:
                    login_user(user_obj, remember=remember)
                    current_app.logger.info(f"User {user_obj.email} (Role: {user_obj.role_type}) logged in successfully.")
                    
                    try:
                        conn_update = get_db_connection()
                        cursor_update = conn_update.cursor()
                        cursor_update.execute("UPDATE Users SET LastLoginDate = NOW() WHERE UserID = %s", (user_obj.id,))
                        conn_update.commit()
                    except Exception as e_update:
                        current_app.logger.error(f"Error updating LastLoginDate for user {user_obj.id}: {e_update}")
                    finally:
                        if 'conn_update' in locals() and conn_update.is_connected():
                            cursor_update.close()
                            conn_update.close()
                    
                    next_page_from_url = request.args.get('next')

                    # --- UPDATED REDIRECTION LOGIC ---
                    if user_obj.role_type == 'Candidate':
                        # Candidate logic remains the same
                        if next_page_from_url and is_safe_url(next_page_from_url):
                            return redirect(next_page_from_url)
                        intended_destination = session.pop('candidate_intended_destination', None)
                        if intended_destination and is_safe_url(intended_destination):
                            return redirect(intended_destination)
                        return redirect(url_for('candidate_bp.dashboard'))
                    
                    elif user_obj.role_type in ACCOUNT_MANAGER_ROLES:
                        # NEW: Redirect Account Managers to their dedicated portal
                        current_app.logger.info(f"Account Manager {user_obj.email} redirecting to AM Portal.")
                        return redirect(url_for('account_manager_bp.portal_home'))

                    elif user_obj.role_type in AGENCY_STAFF_ROLES:
                        # This now handles all other staff roles
                        if next_page_from_url and is_safe_url(next_page_from_url):
                             return redirect(next_page_from_url)
                        return redirect(url_for('staff_dashboard_bp.main_dashboard'))
                        
                    elif user_obj.role_type in CLIENT_ROLES:
                        if next_page_from_url and is_safe_url(next_page_from_url):
                             return redirect(next_page_from_url)
                        return redirect(url_for('client_dashboard_bp.dashboard'))
                        
                    else: 
                        current_app.logger.warning(f"User {user_obj.email} with unknown role '{user_obj.role_type}' logged in.")
                        if next_page_from_url and is_safe_url(next_page_from_url):
                            return redirect(next_page_from_url)
                        return redirect(url_for('public_routes_bp.home_page'))
                else:
                    flash('Your account is inactive. Please contact support.', 'warning')
            else:
                flash('Invalid email or password. Please try again.', 'danger')
        else:
            flash('Please correct the errors below.', 'danger')
            
    return render_template('auth/login.html', title='Login', errors=errors, form_data=form_data)

@login_bp.route('/logout')
@login_required
def logout():
    user_email = current_user.email if hasattr(current_user, 'email') else f"UserID: {current_user.id}"
    session.pop('candidate_intended_destination', None)
    logout_user()
    flash('You have been logged out.', 'success')
    current_app.logger.info(f"User {user_email} logged out.")
    return redirect(url_for('login_bp.login'))