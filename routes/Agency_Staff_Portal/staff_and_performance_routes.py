# routes/Agency_staff_portal/staff_and_performance_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app , jsonify
from flask_login import current_user
from utils.decorators import login_required_with_role, MANAGERIAL_PORTAL_ROLES
from db import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import random
import re

staff_perf_bp = Blueprint('staff_perf_bp', __name__,
                          template_folder='../../../templates',
                          url_prefix='/managerial/staff-performance')


ROLES_ELIGIBLE_FOR_POINTS = [
    'SourcingRecruiter',
    'SourcingTeamLead',
    'UnitManager'
]


# --- Helper Functions ---
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


# --- Staff Dashboard ---
@staff_perf_bp.route('/dashboard')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def staff_dashboard():
    """Displays a dashboard with key staff statistics and quick links."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Stat Card Data
    cursor.execute("""
        SELECT
            (SELECT COUNT(*) FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE u.AccountStatus = 'Active') as total_active_staff,
            (SELECT COUNT(*) FROM StaffApplications WHERE Status = 'Pending') as pending_applications,
            (SELECT COUNT(*) FROM SourcingTeams WHERE IsActive = 1) as sourcing_teams,
            (SELECT COUNT(*) FROM AccountManagerTeams) as am_teams;
    """)
    stats = cursor.fetchone()

    # Staff by Role
    cursor.execute("""
        SELECT Role, COUNT(s.StaffID) as count
        FROM Staff s
        JOIN Users u ON s.UserID = u.UserID
        WHERE u.AccountStatus = 'Active'
        GROUP BY s.Role
        ORDER BY count DESC;
    """)
    staff_by_role = cursor.fetchall()

    # SCHEMA CHANGE: Top 5 Monthly Performers now queries PointTransactions
    cursor.execute("""
        SELECT u.FirstName, u.LastName, s.Role, SUM(pt.Points) as Points
        FROM PointTransactions pt
        JOIN Staff s ON pt.RecipientStaffID = s.StaffID
        JOIN Users u ON s.UserID = u.UserID
        WHERE pt.TransactionDate >= DATE_FORMAT(NOW(), '%Y-%m-01') AND u.AccountStatus = 'Active'
        GROUP BY u.UserID, u.FirstName, u.LastName, s.Role
        HAVING SUM(pt.Points) > 0
        ORDER BY Points DESC LIMIT 5;
    """)
    top_performers = cursor.fetchall()
    
    # Recently Joined Staff
    cursor.execute("""
        SELECT u.FirstName, u.LastName, sa.DesiredRole as Role, sa.ReviewedAt
        FROM StaffApplications sa
        JOIN Users u ON sa.UserID = u.UserID
        WHERE sa.Status = 'Approved'
        ORDER BY sa.ReviewedAt DESC
        LIMIT 5;
    """)
    recent_hires = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('agency_staff_portal/staff/staff_dashboard.html',
                           title="Staff Dashboard",
                           stats=stats,
                           staff_by_role=staff_by_role,
                           top_performers=top_performers,
                           recent_hires=recent_hires)


# --- Application Review Flow ---

@staff_perf_bp.route('/review-applications')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def review_staff_applications():
    """Displays a list of all staff applications awaiting review from the new table."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT sa.ApplicationID, u.FirstName, u.LastName, u.Email, u.RegistrationDate, sa.DesiredRole, sa.CVFilePath
        FROM StaffApplications sa
        JOIN Users u ON sa.UserID = u.UserID
        WHERE sa.Status = 'Pending'
        ORDER BY sa.CreatedAt ASC
    """)
    pending_applications = cursor.fetchall()
    conn.close()
    return render_template('agency_staff_portal/staff/review_staff_applications.html',
                           title="Review Staff Applications",
                           pending_applications=pending_applications)

@staff_perf_bp.route('/applications/<int:application_id>/approve', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def approve_application(application_id):
    """Approves a staff application: Creates the Staff record and activates the User account."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT UserID, DesiredRole FROM StaffApplications WHERE ApplicationID = %s AND Status = 'Pending'", (application_id,))
        app_data = cursor.fetchone()

        if not app_data:
            flash("Application not found or has already been processed.", "warning")
            return redirect(url_for('.review_staff_applications'))
            
        user_id = app_data['UserID']
        role = app_data['DesiredRole']

        cursor.execute("INSERT INTO Staff (UserID, Role) VALUES (%s, %s)", (user_id, role))
        staff_id = cursor.lastrowid

        cursor.execute("UPDATE Users SET AccountStatus = 'Active' WHERE UserID = %s", (user_id,))

        cursor.execute("""
            UPDATE StaffApplications SET Status = 'Approved', ReviewedByStaffID = %s, ReviewedAt = NOW(), ApprovedStaffID = %s WHERE ApplicationID = %s
        """, (current_user.specific_role_id, staff_id, application_id))
        
        conn.commit()
        flash("Application approved. The staff member is now active and can log in.", "success")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error approving staff application {application_id}: {e}")
        flash("An error occurred during the approval process.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    return redirect(url_for('.review_staff_applications'))

@staff_perf_bp.route('/applications/<int:application_id>/reject', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def reject_application(application_id):
    """Rejects a staff application and deactivates the associated user account."""
    notes = request.form.get('rejection_notes', 'Application rejected by management.')
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT UserID FROM StaffApplications WHERE ApplicationID = %s", (application_id,))
        app_data = cursor.fetchone()
        if app_data:
             cursor.execute("UPDATE Users SET AccountStatus = 'Inactive' WHERE UserID = %s", (app_data['UserID'],))

        cursor.execute("""
            UPDATE StaffApplications SET Status = 'Rejected', ReviewedByStaffID = %s, ReviewedAt = NOW(), ReviewerNotes = %s WHERE ApplicationID = %s
        """, (current_user.specific_role_id, notes, application_id))

        conn.commit()
        flash("Application has been successfully rejected.", "info")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error rejecting staff application {application_id}: {e}")
        flash("An error occurred while rejecting the application.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.review_staff_applications'))


# --- Direct Staff Management ---

@staff_perf_bp.route('/list')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def list_all_staff():
    """Main view: Displays a list of all active and inactive staff members."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.UserID, s.StaffID, u.FirstName, u.LastName, u.Email, u.AccountStatus, s.Role,
               leader_user.FirstName AS LeaderFirstName, leader_user.LastName AS LeaderLastName
        FROM Staff s
        JOIN Users u ON s.UserID = u.UserID
        LEFT JOIN Staff leader_s ON s.ReportsToStaffID = leader_s.StaffID
        LEFT JOIN Users leader_user ON leader_s.UserID = leader_user.UserID
        WHERE u.AccountStatus IN ('Active', 'Inactive')
        ORDER BY u.AccountStatus, s.Role, u.LastName, u.FirstName
    """)
    staff_list = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(ApplicationID) as pending_count FROM StaffApplications WHERE Status = 'Pending'")
    pending_count = cursor.fetchone()['pending_count']

    conn.close()
    return render_template('agency_staff_portal/staff/list_all_staff.html',
                           title="Manage All Staff",
                           staff_list=staff_list,
                           pending_count=pending_count)

@staff_perf_bp.route('/add-staff', methods=['GET', 'POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def add_staff():
    """Provides a form for a manager to directly add a new ACTIVE staff member."""
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
                cursor.execute("INSERT INTO Users (Email, PasswordHash, FirstName, LastName, PhoneNumber, AccountStatus) VALUES (%s, %s, %s, %s, %s, 'Active')", (email, hashed_password, form_data.get('first_name'), form_data.get('last_name'), form_data.get('phone_number')))
                user_id = cursor.lastrowid
                cursor.execute("INSERT INTO Staff (UserID, Role, EmployeeID) VALUES (%s, %s, %s)", (user_id, form_data.get('role'), form_data.get('employee_id')))
                conn.commit()
                flash(f"Active staff member '{form_data.get('first_name')}' created successfully.", "success")
                return redirect(url_for('.list_all_staff'))
        except Exception as e:
            if conn: conn.rollback()
            flash(f"An error occurred while creating the new staff member: {e}", "danger")
        finally:
            if conn and conn.is_connected(): conn.close()
    
    return render_template('agency_staff_portal/staff/add_staff.html',
                           title="Add New Staff Member",
                           errors=errors, form_data=form_data, possible_roles=possible_roles)

@staff_perf_bp.route('/staff/<int:staff_id>/activate', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def activate_staff(staff_id):
    """Sets an inactive user's AccountStatus to 'Active'."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users u JOIN Staff s ON u.UserID = s.UserID SET u.AccountStatus = 'Active' WHERE s.StaffID = %s", (staff_id,))
        conn.commit()
        flash("Staff member has been activated successfully.", "success")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error activating StaffID {staff_id}: {e}")
        flash("An error occurred during activation.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    return redirect(request.referrer or url_for('.list_all_staff'))

@staff_perf_bp.route('/staff/<int:staff_id>/deactivate', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def deactivate_staff(staff_id):
    """Sets a user's AccountStatus to 'Inactive' and cleans up all structural links."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users u JOIN Staff s ON u.UserID = s.UserID SET u.AccountStatus = 'Inactive' WHERE s.StaffID = %s", (staff_id,))
        cursor.execute("UPDATE Staff SET ReportsToStaffID = NULL WHERE ReportsToStaffID = %s", (staff_id,))
        cursor.execute("UPDATE SourcingTeams SET TeamLeadStaffID = NULL WHERE TeamLeadStaffID = %s", (staff_id,))
        cursor.execute("UPDATE SourcingUnits SET UnitManagerStaffID = NULL WHERE UnitManagerStaffID = %s", (staff_id,))
        conn.commit()
        flash("Staff member has been deactivated and removed from all structural roles.", "success")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deactivating StaffID {staff_id}: {e}")
        flash("An error occurred during deactivation.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('.list_all_staff'))


# --- Profile and Team Views ---

@staff_perf_bp.route('/my-team')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def my_team():
    """Shows a performance overview of the current manager's direct reports or the whole company."""
    current_sort = request.args.get('sort', 'monthly')
    order_by_clause = "NetMonthlyPoints DESC" if current_sort == 'monthly' else "s.TotalPoints DESC"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # SCHEMA CHANGE: Base query now uses PointTransactions for monthly calculation
    base_query = f"""
        SELECT 
            u.UserID, u.FirstName, u.LastName, u.ProfilePictureURL,
            s.StaffID, s.Role, s.TotalPoints,
            COALESCE(monthly.NetMonthlyPoints, 0) as NetMonthlyPoints
        FROM Staff s
        JOIN Users u ON s.UserID = u.UserID
        LEFT JOIN (
            SELECT RecipientStaffID, SUM(Points) as NetMonthlyPoints
            FROM PointTransactions
            WHERE TransactionDate >= DATE_FORMAT(NOW() ,'%Y-%m-01')
            GROUP BY RecipientStaffID
        ) as monthly ON s.StaffID = monthly.RecipientStaffID
    """
    
    is_global_view = current_user.role_type in ['CEO', 'OperationsManager', 'Admin']
    params = []
    where_clause = "WHERE u.AccountStatus = 'Active'"
    if not is_global_view:
        where_clause += " AND s.ReportsToStaffID = %s"
        params.append(current_user.specific_role_id)
    
    final_query = f"{base_query} {where_clause} ORDER BY {order_by_clause}"
    cursor.execute(final_query, tuple(params))
    team_members = cursor.fetchall()
    
    # SCHEMA CHANGE: Team KPI query now uses PointTransactions
    kpi_query_where = "WHERE u.AccountStatus = 'Active'"
    if not is_global_view:
        kpi_query_where += f" AND s.ReportsToStaffID = {current_user.specific_role_id}"
        
    kpi_query = f"""
        SELECT
            COUNT(s.StaffID) as member_count,
            SUM(s.TotalPoints) as total_points,
            (SELECT SUM(Points) FROM PointTransactions pt JOIN Staff s_inner ON pt.RecipientStaffID = s_inner.StaffID JOIN Users u_inner ON s_inner.UserID = u_inner.UserID WHERE TransactionDate >= DATE_FORMAT(NOW(), '%Y-%m-01') AND {kpi_query_where.replace('WHERE', '')}) as monthly_net_points
        FROM Staff s JOIN Users u ON s.UserID = u.UserID
        {kpi_query_where}
    """
    cursor.execute(kpi_query)
    team_kpis = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template('agency_staff_portal/staff/my_team.html',
                           title="My Team Performance",
                           team_members=team_members,
                           team_kpis=team_kpis,
                           current_sort=current_sort,
                           is_global_view=is_global_view)

@staff_perf_bp.route('/profile/<int:user_id_viewing>')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES + ['SalesManager'])
def view_staff_profile(user_id_viewing):
    is_self_view = (current_user.id == user_id_viewing)
    if getattr(current_user, 'role_type', None) == 'SalesManager' and not is_self_view:
        flash("You only have permission to view your own profile.", "danger")
        return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT u.*, s.*, leader_user.FirstName AS LeaderFirstName, leader_user.LastName AS LeaderLastName, st.TeamName AS SourcingTeamName, amt.TeamName AS AMTeamName FROM Users u JOIN Staff s ON u.UserID = s.UserID LEFT JOIN Staff leader_s ON s.ReportsToStaffID = leader_s.StaffID LEFT JOIN Users leader_user ON leader_s.UserID = leader_user.UserID LEFT JOIN SourcingTeams st ON s.TeamID = st.TeamID LEFT JOIN AccountManagerTeams amt ON s.AMTeamID = amt.TeamID WHERE u.UserID = %s", (user_id_viewing,))
        user_profile_data = cursor.fetchone()

        if not user_profile_data:
            flash("Staff profile not found.", "danger")
            return redirect(url_for('.list_all_staff'))
            
        staff_id = user_profile_data['StaffID']
        
        is_profile_eligible_for_points = user_profile_data.get('Role') in ROLES_ELIGIBLE_FOR_POINTS


        cursor.execute("SELECT COUNT(ApplicationID) as AppsReferredThisMonth, SUM(CASE WHEN Status = 'Hired' THEN 1 ELSE 0 END) as HiresThisMonth FROM JobApplications WHERE ReferringStaffID = %s AND ApplicationDate >= DATE_FORMAT(NOW(), '%Y-%m-01')", (staff_id,))
        monthly_performance = cursor.fetchone()
        user_profile_data.update(monthly_performance)
        cursor.execute("SELECT SUM(Points) as PointsThisMonth FROM PointTransactions WHERE RecipientStaffID = %s AND TransactionDate >= DATE_FORMAT(NOW(), '%Y-%m-01')", (staff_id,))
        monthly_points = cursor.fetchone()
        user_profile_data['PointsThisMonth'] = monthly_points.get('PointsThisMonth') or 0
        cursor.execute("SELECT pt.Points, pt.Reason, pt.TransactionDate, u_assigner.FirstName as AssignerFirstName FROM PointTransactions pt JOIN Staff s_assigner ON pt.AssignerStaffID = s_assigner.StaffID JOIN Users u_assigner ON s_assigner.UserID = u_assigner.UserID WHERE pt.RecipientStaffID = %s ORDER BY pt.TransactionDate DESC LIMIT 10", (staff_id,))
        point_transactions = cursor.fetchall()
        cursor.execute("SELECT u.FirstName, u.LastName, s.Role, s.StaffID, u.UserID FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.ReportsToStaffID = %s AND u.AccountStatus = 'Active'", (staff_id,))
        direct_reports = cursor.fetchall()

        if is_self_view:
            return render_template('agency_staff_portal/staff/my_profile.html', title="My Profile", user_profile=user_profile_data, point_transactions=point_transactions, direct_reports=direct_reports)
        else:
            cursor.execute("SELECT StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE u.AccountStatus = 'Active' ORDER BY FullName")
            team_leaders = cursor.fetchall()
            cursor.execute("SHOW COLUMNS FROM Staff LIKE 'Role'")
            enum_str = cursor.fetchone()['Type']
            possible_roles = enum_str.replace("enum('", "").replace("')", "").split("','")
            
            return render_template('agency_staff_portal/staff/view_staff_profile.html', 
                                   title=f"Profile: {user_profile_data['FirstName']}", 
                                   user_profile=user_profile_data, 
                                   team_leaders=team_leaders, 
                                   possible_roles=possible_roles,
                                   point_transactions=point_transactions,
                                   direct_reports=direct_reports,
                                   # Pass the new authorization flag to the template
                                   is_profile_eligible_for_points=is_profile_eligible_for_points)
    finally:
        if conn and conn.is_connected():
             if 'cursor' in locals() and cursor: cursor.close()
             conn.close()


@staff_perf_bp.route('/profile/<int:staff_id_to_edit>/update-role', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def update_role(staff_id_to_edit):
    user_id_redirect = request.form.get('user_id')
    new_role = request.form.get('role')
    
    structural_roles = ['SourcingTeamLead', 'UnitManager', 'HeadUnitManager']
    if new_role in structural_roles:
        flash(f"The '{new_role}' role must be assigned from the Recruiter Portal's Organization page to ensure the structure is updated correctly.", "warning")
        return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_redirect))

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
    conn = get_db_connection()
    try:
        cursor_check = conn.cursor(dictionary=True)
        cursor_check.execute("SELECT Role FROM Staff WHERE StaffID = %s", (staff_id_award_points,))
        target_staff = cursor_check.fetchone()
        
        if not target_staff or target_staff.get('Role') not in ROLES_ELIGIBLE_FOR_POINTS:
            flash("This staff member's role is not eligible to receive points.", "danger")
            return redirect(request.referrer or url_for('.list_all_staff'))

        points = int(request.form.get('points'))
        reason = request.form.get('reason', 'Manual adjustment by manager.')
        
        if request.form.get('action_type') == 'deduct':
            points = -abs(points)
        else:
            points = abs(points)

        conn.start_transaction()
        cursor_transact = conn.cursor()
        
        sql_log = "INSERT INTO PointTransactions (RecipientStaffID, AssignerStaffID, Points, Reason) VALUES (%s, %s, %s, %s)"
        cursor_transact.execute(sql_log, (staff_id_award_points, current_user.specific_role_id, points, reason))
        
        sql_update = "UPDATE Staff SET TotalPoints = COALESCE(TotalPoints, 0) + %s WHERE StaffID = %s"
        cursor_transact.execute(sql_update, (points, staff_id_award_points))
        
        conn.commit()
        flash(f"{abs(points)} points processed successfully.", "success")

    except ValueError:
        flash("Invalid points value. Please enter a whole number.", "danger")
    except Exception as e:
        if conn.is_connected():
            conn.rollback()
        current_app.logger.error(f"Error processing points for StaffID {staff_id_award_points}: {e}")
        flash("A database error occurred while processing points.", "danger")
    finally:
        if conn.is_connected():
            conn.close()
            
    user_id_redirect = request.form.get('user_id')
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


# --- My Profile Routes ---

@staff_perf_bp.route('/my-profile/update-details', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES + ['SalesManager'])
def my_profile_update_details():
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    phone_number = request.form.get('phone_number', '').strip()

    if not first_name or not last_name:
        flash("First and last names are required.", "danger")
        return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET FirstName = %s, LastName = %s, PhoneNumber = %s WHERE UserID = %s", (first_name, last_name, phone_number, current_user.id))
        conn.commit()
        flash("Your profile details have been updated successfully.", "success")
    except Exception as e:
        if conn: conn.rollback()
        flash("A database error occurred. Please try again.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))

@staff_perf_bp.route('/my-profile/update-password', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES + ['SalesManager'])
def my_profile_update_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    redirect_url = url_for('.view_staff_profile', user_id_viewing=current_user.id)

    if not all([current_password, new_password, confirm_password]):
        flash("All password fields are required.", "danger")
        return redirect(redirect_url)
    if len(new_password) < 8:
        flash("New password must be at least 8 characters long.", "danger")
        return redirect(redirect_url)
    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(redirect_url)
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT PasswordHash FROM Users WHERE UserID = %s", (current_user.id,))
        user = cursor.fetchone()
        
        if not user or not check_password_hash(user['PasswordHash'], current_password):
            flash("Your current password is not correct.", "danger")
            return redirect(redirect_url)
            
        new_hashed_password = generate_password_hash(new_password)
        cursor.execute("UPDATE Users SET PasswordHash = %s WHERE UserID = %s", (new_hashed_password, current_user.id))
        conn.commit()
        flash("Your password has been changed successfully.", "success")
    except Exception as e:
        if conn: conn.rollback()
        flash("A database error occurred while changing your password.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    return redirect(redirect_url)


# --- Team Structure and Leaderboard Views ---

@staff_perf_bp.route('/team-structure')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def global_team_overview():
    return render_template('agency_staff_portal/staff/global_team_overview.html', title="Global Team Structure")

@staff_perf_bp.route('/api/team-hierarchy')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def api_team_hierarchy():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.StaffID AS id, s.ReportsToStaffID AS parentId, u.FirstName, u.LastName, s.Role, u.ProfilePictureURL
        FROM Staff s JOIN Users u ON s.UserID = u.UserID
        WHERE u.AccountStatus = 'Active'
    """)
    nodes = cursor.fetchall()
    conn.close()

    root_node = {
        'id': None, 'parentId': 'root', 'FirstName': 'Mosla', 'LastName': 'Pioneers',
        'Role': 'Organization', 'ProfilePictureURL': url_for('static', filename='images/mosla.jpg')
    }
    nodes.append(root_node)

    node_map = {node['id']: node for node in nodes}
    for node in nodes:
        node['name'] = f"{node['FirstName']} {node['LastName']}"
        parent_id = node.get('parentId')
        if parent_id in node_map:
            parent = node_map[parent_id]
            if 'children' not in parent: parent['children'] = []
            parent['children'].append(node)

    hierarchy_data = next((node for node in nodes if node.get('parentId') == 'root'), None)
    return jsonify(hierarchy_data)

@staff_perf_bp.route('/leaderboard/performance')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def performance_leaderboard():
    period = request.args.get('period', 'all_time')
    title = "All-Time Performance Leaderboard"
    
    sql = """
        SELECT u.FirstName, u.LastName, s.Role, s.TotalPoints as Points
        FROM Staff s JOIN Users u ON s.UserID = u.UserID
        WHERE s.TotalPoints IS NOT NULL AND s.TotalPoints != 0 AND u.AccountStatus = 'Active'
        ORDER BY s.TotalPoints DESC LIMIT 20
    """
    
    if period == 'monthly':
        title = "Top Performers (This Month)"
        sql = """
            SELECT u.FirstName, u.LastName, s.Role, SUM(pt.Points) as Points
            FROM PointTransactions pt
            JOIN Staff s ON pt.RecipientStaffID = s.StaffID
            JOIN Users u ON s.UserID = u.UserID
            WHERE pt.TransactionDate >= DATE_FORMAT(NOW(), '%Y-%m-01') AND u.AccountStatus = 'Active'
            GROUP BY u.UserID, u.FirstName, u.LastName, s.Role
            HAVING SUM(pt.Points) != 0
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