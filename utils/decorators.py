# utils/decorators.py
from functools import wraps
from flask import flash, redirect, url_for, current_app, request
from flask_login import current_user

# --- [MODIFIED] ROLE LISTS ---

# This role list is now only for top-level execs who see the main dashboard.
AGENCY_STAFF_ROLES = ['CEO', 'Founder']

# This is the single source of truth for who can access the main managerial portal.
# SalesManager and SalesAssistant are EXCLUDED from this list.
MANAGERIAL_PORTAL_ROLES = ['CEO', 'Founder']

# These roles have full management access to packages.
PACKAGE_MANAGEMENT_ROLES = ['SalesManager', 'SalesAssistant', 'CEO', 'Founder']

# These roles can view the package dashboard and lists.
PACKAGE_VIEW_ROLES = ['SalesManager', 'SalesAssistant', 'CEO', 'Founder']

# All other role lists (ADMIN_ROLES, etc.)
ADMIN_ROLES = ['Admin'] 
CANDIDATE_ROLES = ['Candidate']
ANNOUNCEMENT_MANAGEMENT_ROLES = ['Admin', 'CEO', 'Founder'] 
JOB_OFFER_MANAGEMENT_ROLES = ['CEO', 'Founder'] 
EXECUTIVE_ROLES = ['CEO', 'Founder']
LEADER_ROLES = ['CEO', 'Founder', 'HeadSourcingTeamLead', 'HeadAccountManager', 'SeniorAccountManager', 'SalesManager']


# --- [MODIFIED] CORE DECORATOR ---
def login_required_with_role(allowed_roles, insufficient_role_redirect='public_routes_bp.home_page'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please log in to access this page.", "info")
                return redirect(url_for('login_bp.login', next=request.url))
            
            user_role = getattr(current_user, 'role_type', None)
            
            current_app.logger.debug(
                f"Decorator Check: User: {getattr(current_user, 'email', 'N/A')}, "
                f"Role Type: {repr(user_role)}, Required: {allowed_roles}, Path: {request.path}"
            )
            
            # --- [NEW LOGIC] Special redirection for the Sales team ---
            # If a Sales team member tries to access a page they shouldn't,
            # redirect them to their dedicated packages dashboard.
            if user_role in ['SalesManager', 'SalesAssistant'] and user_role not in allowed_roles:
                current_app.logger.warning(
                    f"Access DENIED for Sales Team member {current_user.email} to {request.path}. Redirecting to packages dashboard."
                )
                flash('You do not have permission to access this specific managerial page.', 'danger')
                return redirect(url_for('package_mgmt_bp.packages_dashboard'))

            if user_role not in allowed_roles:
                current_app.logger.warning(
                    f"Access DENIED for user {current_user.email} with role '{user_role}' to {request.path}. Required: {allowed_roles}"
                )
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for(insufficient_role_redirect))
            
            current_app.logger.debug(
                f"Access GRANTED for user {current_user.email} with role '{user_role}' to {request.path}."
            )
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- GENERAL & SPECIFIC DECORATORS (Unchanged, but now use the new core logic) ---
def agency_staff_required(f):
    return login_required_with_role(AGENCY_STAFF_ROLES)(f)

def admin_portal_required(f):
    return login_required_with_role(ADMIN_ROLES, insufficient_role_redirect='public_routes_bp.home_page')(f)

def candidate_portal_required(f):
    return login_required_with_role(CANDIDATE_ROLES, insufficient_role_redirect='public_routes_bp.home_page')(f)

def course_management_access_required(f):
    # This specific decorator might now be redundant if you directly use login_required_with_role
    # in the package_mgmt_bp, but we'll leave it for compatibility.
    return login_required_with_role(PACKAGE_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')(f)

def sales_manager_portal_specific_access_required(f):
     return login_required_with_role(PACKAGE_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')(f)

def announcement_management_access_required(f):
    return login_required_with_role(ANNOUNCEMENT_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')(f)

def job_offer_management_required(f):
    return login_required_with_role(JOB_OFFER_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')(f)


def instructor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login_bp.login')) # Or your login route
        # Check for the specific 'Instructor' role
        if not hasattr(current_user, 'specific_role_details') or current_user.specific_role_details.get('Role') != 'Instructor':
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('public_routes_bp.home_page')) # Or a general access-denied page
        return f(*args, **kwargs)
    return decorated_function