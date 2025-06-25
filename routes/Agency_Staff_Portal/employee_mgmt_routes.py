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
    if not manager or not hasattr(manager, 'role_type'): return False
    if manager.role_type in EXECUTIVE_ROLES: return True

    manager_staff_id = getattr(manager, 'specific_role_id', None)
    
    profile_reports_to_staff_id = profile_to_view_staff_data.get('ReportsToStaffID')

    if not manager_staff_id: return False
    if profile_reports_to_staff_id is None: return False 

    if manager_staff_id == profile_reports_to_staff_id:
        return True

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        current_leader_in_chain = profile_reports_to_staff_id
        for _ in range(6): 
            if not current_leader_in_chain:
                return False
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_leader_in_chain,))
            result = cursor.fetchone()
            if not result or not result[0]: 
                return False
            
            parent_of_current_leader = result[0]
            if parent_of_current_leader == manager_staff_id:
                return True 
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
    """Prevents assigning a user to report to one of their own subordinates."""
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

# --- Main Routes ---
@employee_mgmt_bp.route('/')
@login_required
def staff_hub():
    if current_user.role_type in LEADER_ROLES: 
        return redirect(url_for('.my_team'))
    return redirect(url_for('.view_staff_profile', user_id_viewing=current_user.id))

@employee_mgmt_bp.route('/dashboard') 
@login_required_with_role(EXECUTIVE_ROLES) 
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
        return redirect(url_for('staff_dashboard_bp.main_dashboard')) 
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

@employee_mgmt_bp.route('/my-team')
@login_required_with_role(LEADER_ROLES)
def my_team():
    leader_staff_id = getattr(current_user, 'specific_role_id', None) 
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
        page_title = "My Team Performance" 
        where_clause = ""

        if role in EXECUTIVE_ROLES:
            page_title = "All Staff Performance" 
        else: 
            where_clause = """
            WITH RECURSIVE Subordinates AS (
                SELECT StaffID FROM Staff WHERE StaffID = %s 
                UNION ALL
                SELECT s_child.StaffID FROM Staff s_child
                INNER JOIN Subordinates s_parent ON s_child.ReportsToStaffID = s_parent.StaffID
            )
            WHERE s.StaffID IN (SELECT StaffID FROM Subordinates WHERE StaffID != %s) 
            """
            params.extend([leader_staff_id, leader_staff_id]) 
            
            if role == 'UnitManager': page_title = "My Unit's Performance"
            elif role == 'HeadSourcingTeamLead': page_title = "My Division's Performance"
            elif role == 'HeadAccountManager': page_title = "My Account Management Group Performance"
            elif role == 'SeniorAccountManager': page_title = "My Account Managers' Performance"

        final_sql = f"{base_sql} {where_clause} {order_clause}"
        cursor.execute(final_sql, tuple(params))
        team_members = cursor.fetchall()
        
        team_kpis = {
            'member_count': len(team_members),
            'total_points': sum(member.get('TotalPoints', 0) or 0 for member in team_members),
            'monthly_net_points': sum(member.get('NetMonthlyPoints', 0) for member in team_members)
        }
        is_global_view = role in EXECUTIVE_ROLES 

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
    direct_reports_section_title = "Manages Directly" 
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
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

        if user_id_viewing != current_user.id and not _can_manager_view_profile(current_user, user_profile_data):
            flash("You do not have permission to view this profile.", "danger")
            return redirect(url_for('.staff_hub'))
        
        leader_roles_tuple = tuple(LEADER_ROLES)
        placeholders = ', '.join(['%s'] * len(leader_roles_tuple))
        cursor.execute(f"""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role 
            FROM Staff s JOIN Users u ON s.UserID = u.UserID 
            WHERE s.Role IN ({placeholders})
            ORDER BY u.LastName, u.FirstName
        """, leader_roles_tuple)
        team_leaders = cursor.fetchall()
        
        cursor.execute("SHOW COLUMNS FROM Staff LIKE 'Role'")
        enum_str = cursor.fetchone()['Type']
        possible_roles = enum_str.replace("enum('", "").replace("')", "").split("','")

        if user_profile_data.get('StaffID'):
            cursor.execute("SELECT PointsAmount, ActivityType, AwardDate, Notes FROM StaffPointsLog WHERE AwardedToStaffID = %s ORDER BY AwardDate DESC LIMIT 20", (user_profile_data['StaffID'],))
            points_log = cursor.fetchall()

            cursor.execute("""
                SELECT s_report.StaffID, u_report.UserID, u_report.FirstName, u_report.LastName, s_report.Role 
                FROM Staff s_report
                JOIN Users u_report ON s_report.UserID = u_report.UserID
                WHERE s_report.ReportsToStaffID = %s 
                ORDER BY u_report.LastName
            """, (user_profile_data['StaffID'],))
            direct_reports = cursor.fetchall()

            viewed_role = user_profile_data.get('Role')
            if viewed_role == 'CEO': direct_reports_section_title = "Executive Leadership Team"
            elif viewed_role == 'OperationsManager': direct_reports_section_title = "Direct Managerial Reports"
            elif viewed_role == 'UnitManager': direct_reports_section_title = "Head Team Leaders in Unit"
            elif viewed_role == 'HeadSourcingTeamLead' or viewed_role == 'HeadAccountManager': direct_reports_section_title = "Team Leaders / Senior Staff"
            elif viewed_role == 'SourcingTeamLead' or viewed_role == 'SeniorAccountManager': direct_reports_section_title = "Team Members"
        
        ceo_kpis = {}
        if user_profile_data.get('Role') == 'CEO':
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

@employee_mgmt_bp.route('/generate-referral-code/<int:target_staff_id>', methods=['POST'])
@login_required
def generate_referral_code(target_staff_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT s.StaffID, u.UserID, u.FirstName, s.ReferralCode, s.ReportsToStaffID FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s", (target_staff_id,))
        target_staff_profile = cursor.fetchone()

        if not target_staff_profile:
            flash("Target staff profile not found.", "warning")
            return redirect(request.referrer or url_for('.staff_hub'))
        
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
    # user_id_of_edited_staff = request.form.get('user_id_redirect') # OLD, form name is 'user_id'
    user_id_of_edited_staff_str = request.form.get('user_id')
    
    if not user_id_of_edited_staff_str:
        flash("Critical error: User ID for redirect not found.", "danger")
        return redirect(url_for('.staff_hub'))
    try:
        user_id_of_edited_staff = int(user_id_of_edited_staff_str)
    except ValueError:
        flash("Critical error: Invalid User ID format for redirect.", "danger")
        return redirect(url_for('.staff_hub'))

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
    new_leader_staff_id_str = request.form.get('leader_id') 
    # user_id_of_edited_staff = request.form.get('user_id_redirect') # OLD, form name is 'user_id'
    user_id_of_edited_staff_str = request.form.get('user_id')
    new_leader_staff_id_db = int(new_leader_staff_id_str) if new_leader_staff_id_str else None

    if not user_id_of_edited_staff_str:
        flash("Critical error: User ID for redirect not found.", "danger")
        return redirect(url_for('.staff_hub'))
    try:
        user_id_of_edited_staff = int(user_id_of_edited_staff_str)
    except ValueError:
        flash("Critical error: Invalid User ID format for redirect.", "danger")
        return redirect(url_for('.staff_hub'))

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
@login_required_with_role(LEADER_ROLES)
def add_points(staff_id_award_points):
    # CORRECTED: Changed from 'user_id_redirect' to 'user_id' to match the form field name
    user_id_of_staff_getting_points_str = request.form.get('user_id') 
    
    if not user_id_of_staff_getting_points_str:
        flash("Critical error: User ID for redirect not found in form submission.", "danger")
        # Try to get UserID from target_staff_profile if this fails, but it's a fallback.
        # For now, redirecting to a general page if the form is broken.
        conn_temp = get_db_connection()
        if conn_temp:
            cursor_temp = conn_temp.cursor(dictionary=True)
            cursor_temp.execute("SELECT UserID FROM Staff WHERE StaffID = %s", (staff_id_award_points,))
            res_temp = cursor_temp.fetchone()
            if cursor_temp: cursor_temp.close()
            if conn_temp.is_connected(): conn_temp.close()
            if res_temp and res_temp.get('UserID'):
                 current_app.logger.warning(f"Form did not send user_id for redirect. Using UserID {res_temp['UserID']} from StaffID {staff_id_award_points}.")
                 user_id_of_staff_getting_points_str = str(res_temp['UserID']) # Convert to string for consistency
            else:
                current_app.logger.error(f"Form did not send user_id for redirect, and could not look up UserID for StaffID {staff_id_award_points}.")
                return redirect(url_for('.staff_hub')) # Fallback redirect
        else: # DB connection failed
            current_app.logger.error(f"Form did not send user_id for redirect, and DB connection failed to look up UserID for StaffID {staff_id_award_points}.")
            return redirect(url_for('.staff_hub'))


    try:
        user_id_of_staff_getting_points = int(user_id_of_staff_getting_points_str)
    except ValueError:
        flash("Critical error: Invalid User ID format for redirect.", "danger")
        current_app.logger.error(f"Invalid UserID format received: '{user_id_of_staff_getting_points_str}'")
        return redirect(url_for('.staff_hub')) # Fallback redirect

    conn = None
    try:
        action_type = request.form.get('action_type')
        points_str = request.form.get('points')
        reason = request.form.get('reason', 'Manual adjustment by manager').strip()

        if not action_type or not points_str or not reason:
            flash("Action type, points value, and reason are required.", "warning")
            return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))
        
        points = abs(int(points_str)) 
        if points == 0:
             flash("Points value cannot be zero.", "warning")
             return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))

        points_to_apply = -points if action_type == 'deduct' else points
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True) 
        
        cursor.execute("SELECT StaffID, UserID, ReportsToStaffID FROM Staff WHERE StaffID = %s", (staff_id_award_points,))
        target_staff_for_check = cursor.fetchone()

        if not target_staff_for_check:
            flash("Target staff not found.", "danger")
            return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))

        if target_staff_for_check['UserID'] != user_id_of_staff_getting_points:
            flash("Data mismatch: The staff member being awarded points does not match the redirect ID. Please report this issue.", "danger")
            current_app.logger.error(f"Data mismatch in add_points: target UserID {target_staff_for_check['UserID']} vs redirect UserID {user_id_of_staff_getting_points}")
            # Redirect to the profile page based on the ID from the URL to be safe
            return redirect(url_for('.view_staff_profile', user_id_viewing=target_staff_for_check['UserID']))

        if not _can_manager_view_profile(current_user, target_staff_for_check): # _can_manager_view_profile also implies can manage points
             flash("You do not have permission to manage points for this staff member.", "danger")
             return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))
        
        cursor = conn.cursor() # Switch back to non-dictionary cursor for INSERT/UPDATE
        cursor.execute("INSERT INTO StaffPointsLog (AwardedToStaffID, AwardedByStaffID, PointsAmount, ActivityType, Notes) VALUES (%s, %s, %s, %s, %s)",
                       (staff_id_award_points, current_user.specific_role_id, points_to_apply, 'ManualAdjustment', reason))
        cursor.execute("UPDATE Staff SET TotalPoints = COALESCE(TotalPoints, 0) + %s WHERE StaffID = %s", (points_to_apply, staff_id_award_points))
        conn.commit()
        
        flash(f"{abs(points_to_apply)} points {'deducted from' if action_type == 'deduct' else 'awarded to'} staff successfully.", "success")
    except ValueError:
        flash("Invalid points value. Please enter a whole number.", "danger")
    except mysql.connector.Error as db_err: # More specific DB error handling
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Database error processing points for StaffID {staff_id_award_points}: {db_err}", exc_info=True)
        flash(f"A database error occurred while processing points. Please try again.", "danger")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"General error processing points for StaffID {staff_id_award_points}: {e}", exc_info=True)
        flash(f"An unexpected error occurred while processing points: {str(e)}", "danger")
    finally:
        if conn and conn.is_connected():
             if 'cursor' in locals() and cursor: cursor.close()
             conn.close()
    
    # Ensure user_id_of_staff_getting_points is valid before final redirect
    if not user_id_of_staff_getting_points or not isinstance(user_id_of_staff_getting_points, int):
        current_app.logger.error(f"Final redirect attempt in add_points failed: user_id_of_staff_getting_points is invalid ({user_id_of_staff_getting_points}).")
        flash("Error redirecting back to profile. Please navigate manually.", "warning")
        return redirect(url_for('.staff_hub'))
        
    return redirect(url_for('.view_staff_profile', user_id_viewing=user_id_of_staff_getting_points))