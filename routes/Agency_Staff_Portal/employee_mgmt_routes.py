# routes/Agency_Staff_Portal/employee_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user, login_required
# Ensure LEADER_ROLES and EXECUTIVE_ROLES are correctly defined in decorators.py
# reflecting the roles in your Staff.Role ENUM
from utils.decorators import login_required_with_role, LEADER_ROLES, EXECUTIVE_ROLES
from db import get_db_connection
import mysql.connector
import random # For referral code generation

employee_mgmt_bp = Blueprint('employee_mgmt_bp', __name__,
                               template_folder='../../../templates',
                               url_prefix='/staff-management') # Consistent prefix

# --- Helper Functions for Security and Data Integrity ---
def _can_manager_view_profile(manager, profile_to_view_staff_data):
    """
    Checks if a manager (current_user) has permission to view/manage another staff profile.
    `manager` is the current_user object.
    `profile_to_view_staff_data` is a dictionary of the staff member being viewed,
    containing at least 'ReportsToStaffID' and their 'StaffID'.
    """
    if not manager or not hasattr(manager, 'role_type'): return False # Should not happen for logged-in user
    if manager.role_type in EXECUTIVE_ROLES: return True

    manager_staff_id = getattr(manager, 'specific_role_id', None) # This is the StaffID of the manager
    
    # If profile_to_view_staff_data doesn't have ReportsToStaffID, it means they are top-level (e.g. CEO)
    # or their data is incomplete. Only executives can view top-level if not self.
    profile_reports_to_staff_id = profile_to_view_staff_data.get('ReportsToStaffID')

    if not manager_staff_id: return False # Manager doesn't have a staff ID (shouldn't happen for leaders)
    if profile_reports_to_staff_id is None: return False # Profile reports to no one (e.g. CEO), only execs can see

    # Check if the profile reports directly to the manager
    if manager_staff_id == profile_reports_to_staff_id:
        return True

    # Hierarchical check: trace up from the profile's direct manager
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        current_leader_in_chain = profile_reports_to_staff_id
        for _ in range(6): # Max hierarchy depth to check to prevent infinite loops
            if not current_leader_in_chain: # Should not happen if profile_reports_to_staff_id was not None
                return False
            # We need the StaffID of the manager of the current_leader_in_chain
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_leader_in_chain,))
            result = cursor.fetchone()
            if not result or not result[0]: # Reached the top of this hierarchy branch
                return False
            
            parent_of_current_leader = result[0]
            if parent_of_current_leader == manager_staff_id:
                return True # The manager is a superior of the profile's direct manager
            current_leader_in_chain = parent_of_current_leader # Move up the chain
        return False # Not found in the hierarchy chain within depth
    except Exception as e:
        current_app.logger.error(f"Error in _can_manager_view_profile: {e}", exc_info=True)
        return False
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

def _is_valid_new_leader(staff_to_change_id, new_leader_staff_id):
    """Prevents assigning a user to report to one of their own subordinates."""
    if staff_to_change_id == new_leader_staff_id: return False # Cannot report to self
    if not new_leader_staff_id: return True # Assigning to "no leader" is always valid in terms of loops

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Trace up from the proposed new_leader_staff_id. If we encounter staff_to_change_id, it's a loop.
        current_id_in_chain = new_leader_staff_id
        for _ in range(10): # Max depth for safety
            if not current_id_in_chain: return True # Reached top, no loop
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_id_in_chain,))
            result = cursor.fetchone()
            if not result or not result[0]: return True # Reached top, no loop
            
            parent_id = result[0]
            if parent_id == staff_to_change_id: return False # Loop detected!
            current_id_in_chain = parent_id
        return True # Default to true if no loop found within depth limit
    except Exception as e:
        current_app.logger.error(f"Error in _is_valid_new_leader: {e}", exc_info=True)
        return False # Fail safe
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# --- Main Routes ---
@employee_mgmt_bp.route('/')
@login_required
def staff_hub():
    if current_user.role_type in LEADER_ROLES: # LEADER_ROLES from decorators.py
        return redirect(url_for('.my_team'))
    # Non-leaders (e.g. SourcingRecruiter) go to their own profile
    return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))

@employee_mgmt_bp.route('/dashboard') # Executive Staff Dashboard
@login_required_with_role(EXECUTIVE_ROLES) # EXECUTIVE_ROLES from decorators.py
def staff_dashboard_view():
    conn, kpis = None, {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(u.UserID) as count FROM Users u JOIN Staff s ON u.UserID = s.UserID WHERE u.IsActive = 1")
        res = cursor.fetchone(); kpis['total_staff'] = res['count'] if res else 0
        
        cursor.execute("SELECT Role, COUNT(StaffID) as count FROM Staff GROUP BY Role")
        kpis['role_breakdown'] = {row['Role']: row['count'] for row in cursor.fetchall()}
        
        cursor.execute("SELECT COUNT(UserID) as count FROM Users WHERE RegistrationDate >= DATE_SUB(NOW(), INTERVAL 30 DAY) AND UserID IN (SELECT UserID FROM Staff)")
        res = cursor.fetchone(); kpis['new_staff_30_days'] = res['count'] if res else 0
        
        return render_template('agency_staff_portal/staff/staff_dashboard.html', title="Staff Management Dashboard", kpis=kpis)
    except Exception as e:
        current_app.logger.error(f"Error loading staff dashboard: {e}", exc_info=True)
        flash("Could not load staff dashboard.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard')) # Fallback to general dashboard
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

@employee_mgmt_bp.route('/my-team')
@login_required_with_role(LEADER_ROLES)
def my_team():
    leader_staff_id = getattr(current_user, 'specific_role_id', None) # This is StaffID for staff users
    if not leader_staff_id and current_user.role_type not in EXECUTIVE_ROLES:
        flash("Your staff profile ID could not be found to display your team/group.", "warning")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))

    sort_by = request.args.get('sort', 'monthly')
    conn, team_members = None, []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        order_clause = "ORDER BY NetMonthlyPoints DESC, u.LastName"
        if sort_by == 'total': order_clause = "ORDER BY s.TotalPoints DESC, u.LastName"

        base_sql = """
            SELECT u.UserID, u.FirstName, u.LastName, u.ProfilePictureURL, 
                   s.StaffID, s.Role, s.TotalPoints, u.IsActive,
                   COALESCE(monthly_points.net_monthly, 0) AS NetMonthlyPoints
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            LEFT JOIN (
                SELECT AwardedToStaffID, SUM(PointsAmount) as net_monthly
                FROM StaffPointsLog 
                WHERE AwardDate >= DATE_FORMAT(NOW(), '%Y-%m-01')
                GROUP BY AwardedToStaffID
            ) AS monthly_points ON s.StaffID = monthly_points.AwardedToStaffID
        """
        params = []
        role = current_user.role_type
        page_title = "My Team Performance" # Default
        where_clause = ""

        if role in EXECUTIVE_ROLES:
            page_title = "All Staff Performance" 
            # No WHERE clause, selects all staff
        else: 
            # For other leaders, use recursive CTE to find all staff under them
            where_clause = """
            WITH RECURSIVE Subordinates AS (
                SELECT StaffID FROM Staff WHERE StaffID = %s 
                UNION ALL
                SELECT s_child.StaffID FROM Staff s_child
                INNER JOIN Subordinates s_parent ON s_child.ReportsToStaffID = s_parent.StaffID
            )
            WHERE s.StaffID IN (SELECT StaffID FROM Subordinates WHERE StaffID != %s) 
            """
            params.extend([leader_staff_id, leader_staff_id]) # Param for anchor and to exclude self
            
            if role == 'UnitManager': page_title = "My Unit's Performance"
            elif role == 'HeadSourcingTeamLead': page_title = "My Division's Performance"
            elif role == 'HeadAccountManager': page_title = "My Account Management Group Performance"
            elif role == 'SeniorAccountManager': page_title = "My Account Managers' Performance"
            # SourcingTeamLead uses default "My Team Performance"

        final_sql = f"{base_sql} {where_clause} {order_clause}"
        cursor.execute(final_sql, tuple(params))
        team_members = cursor.fetchall()
        
        team_kpis = {
            'member_count': len(team_members),
            'total_points': sum(member.get('TotalPoints', 0) or 0 for member in team_members),
            'monthly_net_points': sum(member.get('NetMonthlyPoints', 0) for member in team_members)
        }
        is_global_view = role in EXECUTIVE_ROLES # Flag for template rendering

        return render_template('agency_staff_portal/staff/my_team.html', 
                               title=page_title, team_members=team_members, 
                               team_kpis=team_kpis, current_sort=sort_by, 
                               is_global_view=is_global_view)
    except Exception as e:
        current_app.logger.error(f"Error fetching team/staff list for user {current_user.id} (Role: {role}): {e}", exc_info=True)
        flash("Could not load team/staff information.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

@employee_mgmt_bp.route('/list-all')
@login_required_with_role(EXECUTIVE_ROLES)
def list_all_staff():
    conn, staff_list = None, []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Updated SQL to correctly join Staff and Users for leaders
        sql = """
            SELECT u.UserID, u.FirstName, u.LastName, u.Email, u.IsActive, s.Role, s.TotalPoints, 
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
@login_required
def view_staff_profile(user_id_viewing):
    conn, user_profile_data = None, None
    team_leaders, points_log, possible_roles, direct_reports = [], [], [], []
    direct_reports_section_title = "Manages Directly" # Default
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch staff profile data
        cursor.execute("""
            SELECT u.UserID, u.FirstName, u.LastName, u.Email, u.ProfilePictureURL, u.IsActive, u.RegistrationDate, 
                   s.StaffID, s.Role, s.TotalPoints, s.ReferralCode, s.ReportsToStaffID,
                   s.Bio, s.Specialization, s.Region, s.PortfolioDescription, s.EmployeeID
            FROM Users u 
            JOIN Staff s ON u.UserID = s.UserID 
            WHERE u.UserID = %s
        """, (user_id_viewing,))
        user_profile_data = cursor.fetchone()

        if not user_profile_data:
            flash("Staff profile not found.", "danger")
            return redirect(url_for('.staff_hub'))

        # Permission check
        if user_id_viewing != current_user.id and not _can_manager_view_profile(current_user, user_profile_data):
            flash("You do not have permission to view this profile.", "danger")
            return redirect(url_for('.staff_hub'))
        
        # Fetch potential leaders for dropdown (all staff who are in LEADER_ROLES)
        # LEADER_ROLES is a list of role strings
        leader_roles_tuple = tuple(LEADER_ROLES)
        placeholders = ', '.join(['%s'] * len(leader_roles_tuple))
        cursor.execute(f"""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role 
            FROM Staff s JOIN Users u ON s.UserID = u.UserID 
            WHERE s.Role IN ({placeholders})
            ORDER BY u.LastName, u.FirstName
        """, leader_roles_tuple)
        team_leaders = cursor.fetchall()
        
        # Fetch possible roles from ENUM definition in Staff table
        cursor.execute("SHOW COLUMNS FROM Staff LIKE 'Role'")
        enum_str = cursor.fetchone()['Type']
        possible_roles = enum_str.replace("enum('", "").replace("')", "").split("','")

        if user_profile_data.get('StaffID'):
            # Fetch points log
            cursor.execute("SELECT PointsAmount, ActivityType, AwardDate, Notes FROM StaffPointsLog WHERE AwardedToStaffID = %s ORDER BY AwardDate DESC LIMIT 20", (user_profile_data['StaffID'],))
            points_log = cursor.fetchall()

            # Fetch direct reports for this staff member
            cursor.execute("""
                SELECT s_report.StaffID, u_report.UserID, u_report.FirstName, u_report.LastName, s_report.Role 
                FROM Staff s_report
                JOIN Users u_report ON s_report.UserID = u_report.UserID
                WHERE s_report.ReportsToStaffID = %s 
                ORDER BY u_report.LastName
            """, (user_profile_data['StaffID'],))
            direct_reports = cursor.fetchall()

            # Customize direct reports section title
            viewed_role = user_profile_data.get('Role')
            if viewed_role == 'CEO': direct_reports_section_title = "Executive Leadership Team"
            elif viewed_role == 'OperationsManager': direct_reports_section_title = "Direct Managerial Reports"
            elif viewed_role == 'UnitManager': direct_reports_section_title = "Head Team Leaders in Unit"
            elif viewed_role == 'HeadSourcingTeamLead' or viewed_role == 'HeadAccountManager': direct_reports_section_title = "Team Leaders / Senior Staff"
            elif viewed_role == 'SourcingTeamLead' or viewed_role == 'SeniorAccountManager': direct_reports_section_title = "Team Members"
        
        # Add CEO-specific KPIs if viewing CEO profile (example)
        ceo_kpis = {}
        if user_profile_data.get('Role') == 'CEO':
            # Add any CEO-specific data fetching here
            pass

        return render_template('agency_staff_portal/staff/view_staff_profile.html', 
                               title=f"Profile: {user_profile_data['FirstName']} {user_profile_data['LastName']}", 
                               user_profile=user_profile_data, team_leaders=team_leaders, 
                               points_log=points_log, possible_roles=possible_roles, 
                               direct_reports=direct_reports, 
                               direct_reports_section_title=direct_reports_section_title,
                               ceo_kpis=ceo_kpis)
    except Exception as e:
        current_app.logger.error(f"Could not load profile for user_id {user_id_viewing}: {e}", exc_info=True)
        flash(f"Could not load user profile.", "danger")
        return redirect(url_for('.staff_hub'))
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

# --- Action Routes ---
@employee_mgmt_bp.route('/generate-referral-code/<int:target_staff_id>', methods=['POST'])
@login_required
def generate_referral_code(target_staff_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch target staff profile using StaffID
        cursor.execute("SELECT s.StaffID, u.UserID, u.FirstName, s.ReferralCode, s.ReportsToStaffID FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s", (target_staff_id,))
        target_staff_profile = cursor.fetchone()

        if not target_staff_profile:
            flash("Target staff profile not found.", "warning")
            return redirect(request.referrer or url_for('.staff_hub'))
        
        # Permission check: self or authorized manager
        can_generate = (current_user.specific_role_id == target_staff_id) or \
                       _can_manager_view_profile(current_user, target_staff_profile)
        
        if not can_generate:
            flash("You do not have permission to generate a code for this user.", "danger")
            return redirect(url_for('.staff_hub'))
            
        if target_staff_profile.get('ReferralCode'):
            flash("This user already has a referral code.", "info")
            return redirect(url_for('.view_staff_profile', user_id_viewing=target_staff_profile['UserID']))

        base_name = target_staff_profile['FirstName'].upper().replace(' ', '')[:5]
        while True:
            new_code = f"{base_name}{random.randint(100, 999)}"
            cursor.execute("SELECT StaffID FROM Staff WHERE ReferralCode = %s", (new_code,))
            if not cursor.fetchone(): break
        
        cursor.execute("UPDATE Staff SET ReferralCode = %s WHERE StaffID = %s", (new_code, target_staff_id))
        conn.commit()
        flash(f"Referral code '{new_code}' generated for {target_staff_profile['FirstName']}.", "success")
        return redirect(url_for('.view_staff_profile', user_id_viewing=target_staff_profile['UserID']))
    except Exception as e:
        current_app.logger.error(f"Error generating referral code for StaffID {target_staff_id}: {e}", exc_info=True)
        flash("An error occurred while generating the referral code.", "danger")
        return redirect(request.referrer or url_for('.staff_hub'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

@employee_mgmt_bp.route('/profile/<int:staff_id_to_edit>/update-role', methods=['POST'])
@login_required_with_role(EXECUTIVE_ROLES)
def update_role(staff_id_to_edit):
    new_role = request.form.get('role')
    user_id_of_edited_staff = request.form.get('user_id_redirect') # For redirecting back to the profile
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Staff SET Role = %s WHERE StaffID = %s", (new_role, staff_id_to_edit))
        conn.commit()
        flash("Staff role updated successfully.", "success")
    except Exception as e:
        current_app.logger.error(f"Error updating role for StaffID {staff_id_to_edit}: {e}", exc_info=True)
        flash(f"Error updating role: {str(e)}", "danger")
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_edited_staff))

@employee_mgmt_bp.route('/profile/<int:staff_id_to_edit>/update-leader', methods=['POST'])
@login_required_with_role(EXECUTIVE_ROLES)
def update_leader(staff_id_to_edit):
    new_leader_staff_id_str = request.form.get('leader_id') # This is StaffID of the new leader
    user_id_of_edited_staff = request.form.get('user_id_redirect')
    new_leader_staff_id_db = int(new_leader_staff_id_str) if new_leader_staff_id_str else None

    if new_leader_staff_id_db and not _is_valid_new_leader(staff_id_to_edit, new_leader_staff_id_db):
        flash("Invalid manager assignment: this would create a reporting loop.", "danger")
        return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_edited_staff))
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Staff SET ReportsToStaffID = %s WHERE StaffID = %s", (new_leader_staff_id_db, staff_id_to_edit))
        conn.commit()
        flash("Staff manager updated successfully.", "success")
    except Exception as e:
        current_app.logger.error(f"Error updating manager for StaffID {staff_id_to_edit}: {e}", exc_info=True)
        flash(f"Error updating manager: {str(e)}", "danger")
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_edited_staff))

@employee_mgmt_bp.route('/profile/<int:staff_id_award_points>/add-points', methods=['POST'])
@login_required_with_role(LEADER_ROLES) # LEADER_ROLES can manage points for their subordinates
def add_points(staff_id_award_points):
    user_id_of_staff_getting_points = request.form.get('user_id_redirect')
    conn = None
    try:
        action_type = request.form.get('action_type')
        points_str = request.form.get('points')
        reason = request.form.get('reason', 'Manual adjustment by manager').strip()

        if not action_type or not points_str or not reason: # Reason is now mandatory
            flash("Action type, points value, and reason are required.", "warning")
            return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))
        
        points = abs(int(points_str))
        if points == 0:
             flash("Points value cannot be zero.", "warning")
             return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))

        points_to_apply = -points if action_type == 'deduct' else points
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True) # For fetching profile for permission check
        
        cursor.execute("SELECT StaffID, UserID, ReportsToStaffID FROM Staff WHERE StaffID = %s", (staff_id_award_points,))
        target_staff_for_check = cursor.fetchone()
        if not target_staff_for_check:
            flash("Target staff not found.", "danger")
            return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))

        # Use the permission helper
        if not _can_manager_view_profile(current_user, target_staff_for_check):
             flash("You do not have permission to manage points for this staff member.", "danger")
             return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))
        
        # Switch back to non-dictionary cursor for INSERT/UPDATE
        cursor = conn.cursor() 
        cursor.execute("INSERT INTO StaffPointsLog (AwardedToStaffID, AwardedByStaffID, PointsAmount, ActivityType, Notes) VALUES (%s, %s, %s, %s, %s)",
                       (staff_id_award_points, current_user.specific_role_id, points_to_apply, 'ManualAdjustment', reason))
        cursor.execute("UPDATE Staff SET TotalPoints = TotalPoints + %s WHERE StaffID = %s", (points_to_apply, staff_id_award_points))
        conn.commit()
        
        flash(f"{points} points {'deducted from' if action_type == 'deduct' else 'awarded to'} staff successfully.", "success")
    except ValueError:
        flash("Invalid points value. Please enter a whole number.", "danger")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Error processing points for StaffID {staff_id_award_points}: {e}", exc_info=True)
        flash(f"An error occurred while processing points: {str(e)}", "danger")
    finally:
        if conn and conn.is_connected():
             if 'cursor' in locals() and cursor: cursor.close()
             conn.close()
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))