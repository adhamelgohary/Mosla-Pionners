# routes/Admin_Portal/admin_routes.py
from flask import Blueprint, render_template, current_app
from flask_login import current_user # login_required is part of the decorator now
from utils.decorators import admin_portal_required # Import the new decorator

admin_bp = Blueprint('admin_bp', __name__,
                     template_folder='../../templates/admin_portal',
                     url_prefix='/admin-portal') # Define a URL prefix

@admin_bp.route('/dashboard')
@admin_portal_required # Use the decorator
def dashboard():
    """
    Main dashboard for System Administrators.
    """
    current_app.logger.info(f"Admin user {current_user.email} accessed admin dashboard.")
    return render_template('admin_dashboard.html', title='System Administration')

# Add more routes specific to the admin portal here
# For example:
# @admin_bp.route('/users')
# @admin_portal_required
# def manage_users():
#     # Logic to display and manage all system users
#     return render_template('admin_manage_users.html')

# @admin_bp.route('/settings')
# @admin_portal_required
# def system_settings():
#     # Logic for system-wide settings
#     return render_template('admin_settings.html')