# routes/Agency_staff_portal/staff_and_performance_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app , jsonify
from flask_login import current_user
# --- UPDATED IMPORT: The single source of truth for portal access ---
from utils.decorators import login_required_with_role, MANAGERIAL_PORTAL_ROLES
from db import get_db_connection
from werkzeug.security import generate_password_hash
import mysql.connector
import random
import re

from werkzeug.security import check_password_hash # Add this import at the top

# This blueprint is a unified module for all staff, team, and performance management.
# It is only accessible to users with roles in MANAGERIAL_PORTAL_ROLES.
staff_perf_bp = Blueprint('staff_perf_bp', __name__,
                          template_folder='../../../templates',
                          url_prefix='/managerial/staff-performance')


# --- Helper Functions for Data Integrity ---
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
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def check_email_exists_in_db(email, conn):
    """Checks if an email already exists using an existing connection."""
    cursor = conn.cursor()
    cursor.execute("SELECT UserID FROM Users WHERE Email = %s", (email,))
    exists = cursor.fetchone() is not None
    cursor.close()
    return exists


# --- Staff Management Views ---

@staff_perf_bp.route('/')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def list_all_staff():
    """Main view: Displays a list of all staff members."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.UserID, s.StaffID, u.FirstName, u.LastName, u.Email, u.IsActive, s.Role,
               leader_user.FirstName AS LeaderFirstName, leader_user.LastName AS LeaderLastName
        FROM Staff s
        JOIN Users u ON s.UserID = u.UserID
        LEFT JOIN Staff leader_s ON s.ReportsToStaffID = leader_s.StaffID
        LEFT JOIN Users leader_user ON leader_s.UserID = leader_user.UserID
        ORDER BY u.IsActive DESC, s.Role, u.LastName, u.FirstName
    """)
    staff_list = cursor.fetchall()
    conn.close()
    return render_template('agency_staff_portal/staff/list_all_staff.html',
                           title="Manage All Staff",
                           staff_list=staff_list)

@staff_perf_bp.route('/add-staff', methods=['GET', 'POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def add_staff():
    """Provides a form to add a new User and corresponding Staff entry."""
    errors, form_data = {}, {}
    conn_data = get_db_connection()
    cursor_data = conn_data.cursor()
    cursor_data.execute("SHOW COLUMNS FROM Staff LIKE 'Role'")
    enum_str = cursor_data.fetchone()[1]
    possible_roles = enum_str.replace("enum('", "").replace("')", "").split("','")
    cursor_data.close()
    conn_data.close()

    if request.method == 'POST':
        form_data = request.form.to_dict()
        email = form_data.get('email', '').strip()
        password = form_data.get('password', '')

        if not form_data.get('first_name'): errors['first_name'] = 'First name is required.'
        if not form_data.get('last_name'): errors['last_name'] = 'Last name is required.'
        if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email): errors['email'] = 'A valid email is required.'
        if len(password) < 8: errors['password'] = 'Password must be at least 8 characters long.'
        if not form_data.get('role') in possible_roles: errors['role'] = 'A valid role must be selected.'

        conn = get_db_connection()
        try:
            if not errors and check_email_exists_in_db(email, conn):
                errors['email'] = 'This email is already in use.'
            if not errors:
                hashed_password = generate_password_hash(password)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO Users (Email, PasswordHash, FirstName, LastName, PhoneNumber, IsActive) VALUES (%s, %s, %s, %s, %s, 1)", (email, hashed_password, form_data.get('first_name'), form_data.get('last_name'), form_data.get('phone_number')))
                user_id = cursor.lastrowid
                cursor.execute("INSERT INTO Staff (UserID, Role, EmployeeID) VALUES (%s, %s, %s)", (user_id, form_data.get('role'), form_data.get('employee_id')))
                conn.commit()
                flash(f"Staff member '{form_data.get('first_name')}' created successfully!", "success")
                return redirect(url_for('.list_all_staff'))
        except Exception as e:
            if conn: conn.rollback()
            flash(f"An error occurred while creating the new staff member: {e}", "danger")
        finally:
            if conn.is_connected(): conn.close()
    
    return render_template('agency_staff_portal/staff/add_staff.html',
                           title="Add New Staff Member",
                           errors=errors, form_data=form_data, possible_roles=possible_roles)

# --- REFACTORED: This route now serves both manager view and self-view ---
@staff_perf_bp.route('/profile/<int:user_id_viewing>')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def view_staff_profile(user_id_viewing):
    """
    Displays the profile page for a staff member.
    - If viewing another user, it shows the managerial view.
    - If viewing oneself, it shows the personal profile management view.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT u.*, s.* FROM Users u JOIN Staff s ON u.UserID = s.UserID WHERE u.UserID = %s", (user_id_viewing,))
        user_profile_data = cursor.fetchone()

        if not user_profile_data:
            flash("Staff profile not found.", "danger")
            return redirect(url_for('.list_all_staff'))
        
        # --- LOGIC FOR SELF-VIEW vs MANAGER-VIEW ---
        is_self_view = (current_user.id == user_id_viewing)

        if is_self_view:
            # Render the personal "My Profile" template
            return render_template('agency_staff_portal/staff/my_profile.html',
                                   title="My Profile",
                                   user_profile=user_profile_data)
        else:
            # Render the managerial view for another user
            cursor.execute("SELECT StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName FROM Staff s JOIN Users u ON s.UserID = u.UserID ORDER BY FullName")
            team_leaders = cursor.fetchall()
            
            cursor.execute("SHOW COLUMNS FROM Staff LIKE 'Role'")
            possible_roles = cursor.fetchone()['Type'].replace("enum('", "").replace("')", "").split("','")
            
            points_log, direct_reports = [], []
            if user_profile_data.get('StaffID'):
                cursor.execute("SELECT * FROM StaffPointsLog WHERE AwardedToStaffID = %s ORDER BY AwardDate DESC LIMIT 20", (user_profile_data['StaffID'],))
                points_log = cursor.fetchall()
                cursor.execute("SELECT u_report.UserID, u_report.FirstName, u_report.LastName, s_report.Role FROM Staff s_report JOIN Users u_report ON s_report.UserID = u_report.UserID WHERE s_report.ReportsToStaffID = %s", (user_profile_data['StaffID'],))
                direct_reports = cursor.fetchall()
            
            return render_template('agency_staff_portal/staff/view_staff_profile.html',
                                   title=f"Profile: {user_profile_data['FirstName']}",
                                   user_profile=user_profile_data, team_leaders=team_leaders,
                                   points_log=points_log, possible_roles=possible_roles,
                                   direct_reports=direct_reports)
    finally:
        if conn and conn.is_connected():
             if 'cursor' in locals() and cursor: cursor.close()
             conn.close()


# --- Staff Profile Action Routes ---

@staff_perf_bp.route('/profile/<int:staff_id_to_edit>/update-role', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def update_role(staff_id_to_edit):
    user_id_redirect = request.form.get('user_id')
    new_role = request.form.get('role')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Staff SET Role = %s WHERE StaffID = %s", (new_role, staff_id_to_edit))
    conn.commit()
    conn.close()
    flash("Staff role updated successfully.", "success")
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))

@staff_perf_bp.route('/profile/<int:staff_id_to_edit>/update-leader', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def update_leader(staff_id_to_edit):
    user_id_redirect = request.form.get('user_id')
    new_leader_id_str = request.form.get('leader_id')
    new_leader_id = int(new_leader_id_str) if new_leader_id_str else None

    if not _is_valid_new_leader(staff_id_to_edit, new_leader_id):
        flash("Invalid manager assignment: this would create a reporting loop.", "danger")
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Staff SET ReportsToStaffID = %s WHERE StaffID = %s", (new_leader_id, staff_id_to_edit))
        conn.commit()
        conn.close()
        flash("Staff manager updated successfully.", "success")
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))

@staff_perf_bp.route('/profile/<int:staff_id_award_points>/add-points', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def add_points(staff_id_award_points):
    user_id_redirect = request.form.get('user_id')
    try:
        points = int(request.form.get('points'))
        if request.form.get('action_type') == 'deduct': points = -points
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO StaffPointsLog (AwardedToStaffID, AwardedByStaffID, PointsAmount, ActivityType, Notes) VALUES (%s, %s, %s, %s, %s)",
                       (staff_id_award_points, current_user.specific_role_id, points, 'ManualAdjustment', request.form.get('reason')))
        cursor.execute("UPDATE Staff SET TotalPoints = COALESCE(TotalPoints, 0) + %s WHERE StaffID = %s", (points, staff_id_award_points))
        conn.commit()
        conn.close()
        flash(f"{abs(points)} points processed successfully.", "success")
    except ValueError:
        flash("Invalid points value. Please enter a whole number.", "danger")
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))

@staff_perf_bp.route('/profile/<int:target_staff_id>/generate-referral-code', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def generate_referral_code(target_staff_id):
    user_id_redirect = request.form.get('user_id_redirect')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT u.FirstName, s.ReferralCode FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s", (target_staff_id,))
    staff = cursor.fetchone()
    if staff.get('ReferralCode'):
        flash("This user already has a referral code.", "info")
    else:
        base_name = staff['FirstName'].upper().replace(' ', '')[:5]
        while True:
            new_code = f"{base_name}{random.randint(100, 999)}"
            cursor.execute("SELECT StaffID FROM Staff WHERE ReferralCode = %s", (new_code,))
            if not cursor.fetchone(): break
        cursor.execute("UPDATE Staff SET ReferralCode = %s WHERE StaffID = %s", (new_code, target_staff_id))
        conn.commit()
        flash(f"Referral code '{new_code}' generated successfully.", "success")
    conn.close()
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))


# --- Team Structure View ---

@staff_perf_bp.route('/team-structure')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def global_team_overview():
    """Renders the page that will display the org chart."""
    return render_template('agency_staff_portal/staff/global_team_overview.html',
                           title="Global Team Structure")

@staff_perf_bp.route('/api/team-hierarchy')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def api_team_hierarchy():
    """API endpoint that returns the staff data structured as a hierarchy for D3.js."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch all staff members with their manager's ID
    cursor.execute("""
        SELECT 
            s.StaffID AS id, 
            s.ReportsToStaffID AS parentId,
            u.FirstName, 
            u.LastName, 
            s.Role,
            u.ProfilePictureURL
        FROM Staff s
        JOIN Users u ON s.UserID = u.UserID
        WHERE u.IsActive = 1
    """)
    nodes = cursor.fetchall()
    conn.close()

    # The root of our organization chart
    # This node's 'id' should be the parentId of the top-level leader (e.g., the CEO)
    # or a unique value like 0 or None if the CEO has a NULL ReportsToStaffID.
    # The name is what will be displayed for the root.
    root_node = {
        'id': None,  # Corresponds to a NULL ReportsToStaffID for the top leader
        'parentId': 'root', # A virtual parent for the absolute root
        'FirstName': 'Mosla',
        'LastName': 'Pioneers',
        'Role': 'Organization',
        'ProfilePictureURL': url_for('static', filename='images/company-logo.png') # Optional: use a company logo
    }
    
    # Combine the virtual root with the actual staff data
    nodes.append(root_node)

    # Convert the flat list into a hierarchical structure (tree)
    # This is a standard algorithm for creating a tree from a parent-id list
    node_map = {node['id']: node for node in nodes}
    for node in nodes:
        node['name'] = f"{node['FirstName']} {node['LastName']}" # D3 uses the 'name' key by default
        parent_id = node.get('parentId')
        if parent_id in node_map:
            parent = node_map[parent_id]
            if 'children' not in parent:
                parent['children'] = []
            parent['children'].append(node)

    # Find the actual root of the tree (the one with the virtual parentId 'root')
    hierarchy_data = None
    for node in nodes:
        if node.get('parentId') == 'root':
            hierarchy_data = node
            break

    return jsonify(hierarchy_data)


# --- Leaderboard Views ---

@staff_perf_bp.route('/leaderboard/performance')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def performance_leaderboard():
    period = request.args.get('period', 'all_time')
    title = "All-Time Performance Leaderboard"
    sql = """
        SELECT u.FirstName, u.LastName, s.Role, s.TotalPoints as Points
        FROM Staff s
        JOIN Users u ON s.UserID = u.UserID
        WHERE s.TotalPoints IS NOT NULL AND s.TotalPoints != 0
        ORDER BY s.TotalPoints DESC LIMIT 20
    """
    if period == 'monthly':
        title = "Top Performers (This Month)"
        sql = """
            SELECT u.FirstName, u.LastName, s.Role, SUM(spl.PointsAmount) as Points
            FROM StaffPointsLog spl
            JOIN Staff s ON spl.AwardedToStaffID = s.StaffID
            JOIN Users u ON s.UserID = u.UserID
            WHERE spl.AwardDate >= DATE_FORMAT(NOW(), '%Y-%m-01')
            GROUP BY u.UserID, u.FirstName, u.LastName, s.Role
            HAVING SUM(spl.PointsAmount) != 0
            ORDER BY Points DESC LIMIT 20
        """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    leaders = cursor.fetchall()
    conn.close()
    return render_template('agency_staff_portal/staff/leaderboard.html',
                           title=title, leaders=leaders, current_period=period)

@staff_perf_bp.route('/leaderboard/companies')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def company_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT c.CompanyName, c.CompanyLogoURL, COUNT(jo.OfferID) as FilledJobsCount
        FROM Companies c
        JOIN JobOffers jo ON c.CompanyID = jo.CompanyID
        WHERE jo.Status = 'Filled'
        GROUP BY c.CompanyID, c.CompanyName, c.CompanyLogoURL
        ORDER BY FilledJobsCount DESC LIMIT 20
    """)
    top_companies = cursor.fetchall()
    conn.close()
    return render_template('agency_staff_portal/staff/company_leaderboard.html',
                           title="Top Partner Companies",
                           subtitle="Ranked by number of successfully filled positions.",
                           top_companies=top_companies)
    
@staff_perf_bp.route('/my-profile/update-details', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def my_profile_update_details():
    """Handles updates to the user's own basic details."""
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    phone_number = request.form.get('phone_number', '').strip()

    if not first_name or not last_name:
        flash("First and last names are required.", "danger")
        return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Users SET FirstName = %s, LastName = %s, PhoneNumber = %s WHERE UserID = %s",
            (first_name, last_name, phone_number, current_user.id)
        )
        conn.commit()
        flash("Your profile details have been updated successfully.", "success")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error updating user details for UserID {current_user.id}: {e}")
        flash("A database error occurred. Please try again.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

    return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))


@staff_perf_bp.route('/my-profile/update-password', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def my_profile_update_password():
    """Handles updating the user's own password."""
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not all([current_password, new_password, confirm_password]):
        flash("All password fields are required.", "danger")
        return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))
    
    if len(new_password) < 8:
        flash("New password must be at least 8 characters long.", "danger")
        return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))
        
    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT PasswordHash FROM Users WHERE UserID = %s", (current_user.id,))
        user = cursor.fetchone()
        
        if not user or not check_password_hash(user['PasswordHash'], current_password):
            flash("Your current password is not correct.", "danger")
            return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))
            
        new_hashed_password = generate_password_hash(new_password)
        cursor.execute("UPDATE Users SET PasswordHash = %s WHERE UserID = %s", (new_hashed_password, current_user.id))
        conn.commit()
        flash("Your password has been changed successfully.", "success")
    
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error updating password for UserID {current_user.id}: {e}")
        flash("A database error occurred while changing your password.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
            
    return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))