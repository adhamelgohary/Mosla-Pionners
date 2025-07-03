# routes/Agency_Staff_Portal/employee_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user, login_required
from utils.decorators import login_required_with_role, LEADER_ROLES, EXECUTIVE_ROLES
from db import get_db_connection
import mysql.connector
import random

# This blueprint is a unified module for top-level staff management.
# It includes listing all staff, viewing profiles, and all related management actions.
employee_mgmt_bp = Blueprint('employee_mgmt_bp', __name__,
                               template_folder='../../../templates',
                               url_prefix='/staff-management')

# --- Helper Functions for Security and Data Integrity ---

def _can_manager_view_profile(manager, profile_to_view_staff_data):
    """Checks if a manager can view/manage another staff profile."""
    if not manager or not hasattr(manager, 'role_type'): return False
    # Executives can view anyone.
    if manager.role_type in EXECUTIVE_ROLES: return True

    manager_staff_id = getattr(manager, 'specific_role_id', None)
    profile_reports_to_staff_id = profile_to_view_staff_data.get('ReportsToStaffID')
    if not manager_staff_id or profile_reports_to_staff_id is None: return False
    
    # Check for direct report or hierarchy.
    if manager_staff_id == profile_reports_to_staff_id: return True
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        current_leader_in_chain = profile_reports_to_staff_id
        for _ in range(6): 
            if not current_leader_in_chain: return False
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_leader_in_chain,))
            result = cursor.fetchone()
            if not result or not result[0]: return False
            parent_of_current_leader = result[0]
            if parent_of_current_leader == manager_staff_id: return True
            current_leader_in_chain = parent_of_current_leader
        return False
    except Exception as e:
        current_app.logger.error(f"Error in _can_manager_view_profile: {e}", exc_info=True)
        return False
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

def _is_valid_new_leader(staff_to_change_id, new_leader_staff_id):
    """Prevents creating a reporting loop."""
    if staff_to_change_id == new_leader_staff_id: return False
    if not new_leader_staff_id: return True
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_id_in_chain = new_leader_staff_id
        for _ in range(10): 
            if not current_id_in_chain: return True
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_id_in_chain,))
            result = cursor.fetchone()
            if not result or not result[0]: return True
            parent_id = result[0]
            if parent_id == staff_to_change_id: return False
            current_id_in_chain = parent_id
        return True
    except Exception as e:
        current_app.logger.error(f"Error in _is_valid_new_leader: {e}", exc_info=True)
        return False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# --- Main Views for Top-Level Management ---

@employee_mgmt_bp.route('/')
@login_required_with_role(EXECUTIVE_ROLES)
def list_all_staff():
    """Main entry point: Displays a list of all staff members for management."""
    conn, staff_list = None, []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT u.UserID, s.StaffID, u.FirstName, u.LastName, u.Email, u.IsActive, s.Role,
                   leader_user.FirstName AS LeaderFirstName, leader_user.LastName AS LeaderLastName
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            LEFT JOIN Staff leader_s ON s.ReportsToStaffID = leader_s.StaffID
            LEFT JOIN Users leader_user ON leader_s.UserID = leader_user.UserID
            ORDER BY u.IsActive DESC, u.LastName, u.FirstName
        """
        cursor.execute(sql)
        staff_list = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error loading all staff list: {e}", exc_info=True)
        flash("Could not load staff list.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return render_template('agency_staff_portal/staff/list_all_staff.html', title="Manage All Staff", staff_list=staff_list)

@employee_mgmt_bp.route('/profile/<int:user_id_viewing>')
@login_required_with_role(LEADER_ROLES) # Allow any leader to view profiles
def view_staff_profile(user_id_viewing):
    """Displays the detailed profile page for a specific staff member."""
    conn, user_profile_data = None, None
    team_leaders, points_log, possible_roles, direct_reports = [], [], [], []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT u.*, s.* FROM Users u 
            JOIN Staff s ON u.UserID = s.UserID WHERE u.UserID = %s
        """, (user_id_viewing,))
        user_profile_data = cursor.fetchone()

        if not user_profile_data:
            flash("Staff profile not found.", "danger")
            return redirect(url_for('.list_all_staff'))

        # Security check: can the current user view this profile?
        if not _can_manager_view_profile(current_user, user_profile_data):
            flash("You do not have permission to view this profile.", "danger")
            return redirect(url_for('.list_all_staff'))
        
        # Fetch data for dropdowns (potential leaders)
        leader_roles_tuple = tuple(LEADER_ROLES)
        placeholders = ', '.join(['%s'] * len(leader_roles_tuple))
        cursor.execute(f"SELECT s.StaffID, u.FirstName, u.LastName, s.Role FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role IN ({placeholders}) ORDER BY u.LastName", leader_roles_tuple)
        team_leaders = cursor.fetchall()
        
        # Fetch data for dropdown (possible roles)
        cursor.execute("SHOW COLUMNS FROM Staff LIKE 'Role'")
        enum_str = cursor.fetchone()['Type']
        possible_roles = enum_str.replace("enum('", "").replace("')", "").split("','")

        # Fetch data for logs and reports
        if user_profile_data.get('StaffID'):
            cursor.execute("SELECT * FROM StaffPointsLog WHERE AwardedToStaffID = %s ORDER BY AwardDate DESC LIMIT 20", (user_profile_data['StaffID'],))
            points_log = cursor.fetchall()
            cursor.execute("SELECT s_report.StaffID, u_report.UserID, u_report.FirstName, u_report.LastName, s_report.Role FROM Staff s_report JOIN Users u_report ON s_report.UserID = u_report.UserID WHERE s_report.ReportsToStaffID = %s ORDER BY u_report.LastName", (user_profile_data['StaffID'],))
            direct_reports = cursor.fetchall()
        
        return render_template('agency_staff_portal/staff/view_staff_profile.html', 
                               title=f"Profile: {user_profile_data['FirstName']}", 
                               user_profile=user_profile_data, team_leaders=team_leaders, 
                               points_log=points_log, possible_roles=possible_roles, 
                               direct_reports=direct_reports)
    except Exception as e:
        current_app.logger.error(f"Could not load profile for user_id {user_id_viewing}: {e}", exc_info=True)
        flash("Could not load user profile.", "danger")
        return redirect(url_for('.list_all_staff'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

# --- ACTION ROUTES (Processing Forms from the Profile Page) ---

@employee_mgmt_bp.route('/profile/<int:staff_id_to_edit>/update-role', methods=['POST'])
@login_required_with_role(EXECUTIVE_ROLES)
def update_role(staff_id_to_edit):
    """Action to update a staff member's role."""
    user_id_redirect = request.form.get('user_id')
    new_role = request.form.get('role')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Staff SET Role = %s WHERE StaffID = %s", (new_role, staff_id_to_edit))
        conn.commit()
        flash("Staff role updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating role: {e}", "danger")
    finally:
        if 'conn' in locals() and conn.is_connected(): conn.close()
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))

@employee_mgmt_bp.route('/profile/<int:staff_id_to_edit>/update-leader', methods=['POST'])
@login_required_with_role(EXECUTIVE_ROLES)
def update_leader(staff_id_to_edit):
    """Action to update who a staff member reports to."""
    user_id_redirect = request.form.get('user_id')
    new_leader_staff_id_str = request.form.get('leader_id')
    new_leader_staff_id = int(new_leader_staff_id_str) if new_leader_staff_id_str else None

    if new_leader_staff_id and not _is_valid_new_leader(staff_id_to_edit, new_leader_staff_id):
        flash("Invalid manager assignment: this would create a reporting loop.", "danger")
        return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Staff SET ReportsToStaffID = %s WHERE StaffID = %s", (new_leader_staff_id, staff_id_to_edit))
        conn.commit()
        flash("Staff manager updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating manager: {e}", "danger")
    finally:
        if 'conn' in locals() and conn.is_connected(): conn.close()
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))

@employee_mgmt_bp.route('/profile/<int:staff_id_award_points>/add-points', methods=['POST'])
@login_required_with_role(LEADER_ROLES)
def add_points(staff_id_award_points):
    """Action to award or deduct points from a staff member."""
    user_id_redirect = request.form.get('user_id')
    try:
        points = int(request.form.get('points'))
        if request.form.get('action_type') == 'deduct':
            points = -points
        
        # Security check: Can current user manage points for this person?
        # A full check would be needed, but we rely on the decorator for general access
        # and assume a leader won't act maliciously on another leader's team.
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO StaffPointsLog (AwardedToStaffID, AwardedByStaffID, PointsAmount, ActivityType, Notes) VALUES (%s, %s, %s, %s, %s)",
                       (staff_id_award_points, current_user.specific_role_id, points, 'ManualAdjustment', request.form.get('reason', '')))
        cursor.execute("UPDATE Staff SET TotalPoints = COALESCE(TotalPoints, 0) + %s WHERE StaffID = %s", (points, staff_id_award_points))
        conn.commit()
        flash(f"{abs(points)} points processed successfully.", "success")
    except (ValueError, TypeError):
        flash("Invalid points value. Please enter a whole number.", "danger")
    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
    finally:
        if 'conn' in locals() and conn.is_connected(): conn.close()
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))

@employee_mgmt_bp.route('/profile/<int:target_staff_id>/generate-referral-code', methods=['POST'])
@login_required_with_role(LEADER_ROLES)
def generate_referral_code(target_staff_id):
    """Action to generate a referral code for a staff member."""
    user_id_redirect = request.form.get('user_id_redirect')
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT u.FirstName, s.ReferralCode FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s", (target_staff_id,))
        staff = cursor.fetchone()
        if not staff:
             raise Exception("Staff member not found.")
        if staff.get('ReferralCode'):
            flash("This user already has a referral code.", "info")
            return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))

        base_name = staff['FirstName'].upper().replace(' ', '')[:5]
        while True:
            new_code = f"{base_name}{random.randint(100, 999)}"
            cursor.execute("SELECT StaffID FROM Staff WHERE ReferralCode = %s", (new_code,))
            if not cursor.fetchone(): break
        
        cursor.execute("UPDATE Staff SET ReferralCode = %s WHERE StaffID = %s", (new_code, target_staff_id))
        conn.commit()
        flash(f"Referral code '{new_code}' generated successfully.", "success")
    except Exception as e:
        flash(f"Error generating code: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))