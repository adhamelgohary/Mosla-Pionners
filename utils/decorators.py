# utils/decorators.py
from functools import wraps
from flask import flash, redirect, url_for, current_app, request
from flask_login import current_user

# --- ROLE LISTS ---
AGENCY_STAFF_ROLES = [
    'CEO', 
    'SalesManager',
    'Founder'
]
ADMIN_ROLES = ['Admin'] 
CANDIDATE_ROLES = ['Candidate']
ANNOUNCEMENT_MANAGEMENT_ROLES = ['Admin', 'CEO', 'Founder'] 
JOB_OFFER_MANAGEMENT_ROLES = ['CEO', 'Founder'] 
COURSE_MANAGEMENT_ROLES_DECORATOR = ['SalesManager', 'CEO', 'Founder']
SALES_MANAGER_SPECIFIC_ROLES = ['SalesManager', 'CEO', 'Founder']

# --- NEW: Central Authority for Managerial Access ---
# This is the single source of truth for who can access the new portal.
MANAGERIAL_PORTAL_ROLES = ['CEO', 'Founder']

# --- You can now also update EXECUTIVE_ROLES if you wish, or just use the new list ---
EXECUTIVE_ROLES = ['CEO', 'Founder'] # OM might still be exec but not see the portal
LEADER_ROLES = ['CEO', 'Founder', 'HeadSourcingTeamLead', 'HeadAccountManager', 'SeniorAccountManager', 'SalesManager']

# --- CORE DECORATOR ---
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
                f"Role Type from current_user: {repr(user_role)}, "
                f"Required: {allowed_roles}, Path: {request.path}"
            )
            
            if user_role not in allowed_roles:
                current_app.logger.warning(
                    f"Access DENIED for user {getattr(current_user, 'email', 'N/A')} "
                    f"with role '{user_role}' to {request.path}. Required one of: {allowed_roles}"
                )
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for(insufficient_role_redirect))
            
            current_app.logger.debug(
                f"Access GRANTED for user {getattr(current_user, 'email', 'N/A')} "
                f"with role '{user_role}' to {request.path}."
            )
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- GENERAL & SPECIFIC DECORATORS ---
def agency_staff_required(f):
    return login_required_with_role(AGENCY_STAFF_ROLES)(f)

def admin_portal_required(f):
    return login_required_with_role(ADMIN_ROLES, insufficient_role_redirect='public_routes_bp.home_page')(f)

def candidate_portal_required(f):
    return login_required_with_role(CANDIDATE_ROLES, insufficient_role_redirect='public_routes_bp.home_page')(f)

def course_management_access_required(f):
    return login_required_with_role(COURSE_MANAGEMENT_ROLES_DECORATOR, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')(f)

def sales_manager_portal_specific_access_required(f):
     return login_required_with_role(SALES_MANAGER_SPECIFIC_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')(f)

def announcement_management_access_required(f):
    return login_required_with_role(ANNOUNCEMENT_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')(f)

def job_offer_management_required(f):
    return login_required_with_role(JOB_OFFER_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')(f)