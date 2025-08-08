# routes/Recruiter_Team_Portal/staff_routes.py

from flask import Blueprint, abort, render_template, flash, redirect, url_for, current_app, request
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

# --- ROLE CONSTANTS ---
LEADER_ROLES_IN_PORTAL = ['SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'CEO', 'Founder']
TOP_LEVEL_MANAGEMENT = ['HeadUnitManager', 'CEO', 'Founder']
ORG_MANAGEMENT_ROLES = ['HeadUnitManager', 'CEO', 'Founder']
ASSIGNABLE_SOURCING_ROLES = ['SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager']
MANAGEABLE_RECRUITER_ROLES = ['SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager']

staff_bp = Blueprint('staff_bp', __name__,
                     url_prefix='/recruiter-portal',
                     template_folder='../../../templates')

def _get_performance_stats(cursor, staff_id):
    """Fetches all-time hires and referrals for a staff member."""
    cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s AND Status = 'Hired'", (staff_id,))
    hires = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s", (staff_id,))
    referrals = cursor.fetchone()['count']
    return {
        'hires_all_time': hires,
        'referrals_all_time': referrals
    }

def _is_subordinate(cursor, manager_staff_id, subordinate_staff_id):
    """
    Checks if a staff member is a subordinate of a manager by traversing the reporting hierarchy.
    """
    if not manager_staff_id or not subordinate_staff_id or str(manager_staff_id) == str(subordinate_staff_id):
        return False
    query = """
        WITH RECURSIVE SubordinateHierarchy AS (
            SELECT StaffID FROM Staff WHERE ReportsToStaffID = %s
            UNION ALL
            SELECT s.StaffID FROM Staff s INNER JOIN SubordinateHierarchy sh ON s.ReportsToStaffID = sh.StaffID
        )
        SELECT 1 FROM SubordinateHierarchy WHERE StaffID = %s;
    """
    cursor.execute(query, (manager_staff_id, subordinate_staff_id))
    return cursor.fetchone() is not None

@staff_bp.route('/manage-recruiters')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def manage_recruiters():
    search_query = request.args.get('search', '').strip()
    filter_role = request.args.get('role', '')
    filter_status = request.args.get('status', '') # e.g., 'Active', 'Inactive'
    
    conn = get_db_connection()
    recruiters = []
    try:
        cursor = conn.cursor(dictionary=True)
        role_placeholders = ', '.join(['%s'] * len(MANAGEABLE_RECRUITER_ROLES))
        
        # [MODIFIED] Query now uses u.AccountStatus instead of u.IsActive
        sql = f"""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.AccountStatus, u.ProfilePictureURL, 
                   team_info.TeamName, team_info.UnitName 
            FROM Staff s 
            JOIN Users u ON s.UserID = u.UserID 
            LEFT JOIN (
                SELECT t.TeamID, t.TeamName, su.UnitName 
                FROM SourcingTeams t LEFT JOIN SourcingUnits su ON t.UnitID = su.UnitID
            ) AS team_info ON s.TeamID = team_info.TeamID 
            WHERE s.Role IN ({role_placeholders})
        """
        params = list(MANAGEABLE_RECRUITER_ROLES)
        
        if search_query:
            sql += " AND (u.FirstName LIKE %s OR u.LastName LIKE %s OR u.Email LIKE %s)"
            like_query = f"%{search_query}%"
            params.extend([like_query, like_query, like_query])
        
        if filter_role:
            sql += " AND s.Role = %s"
            params.append(filter_role)
            
        # [MODIFIED] Filtering logic now uses the AccountStatus string values
        if filter_status and filter_status in ['Active', 'Inactive']:
            sql += " AND u.AccountStatus = %s"
            params.append(filter_status)

        sql += " ORDER BY u.FirstName, u.LastName"
        cursor.execute(sql, tuple(params))
        recruiters = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching recruiters list: {e}", exc_info=True)
        flash("Could not load the list of recruiters.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('recruiter_team_portal/manage_recruiters.html', 
                           title="Manage Recruiters", 
                           recruiters=recruiters, 
                           search_query=search_query, 
                           filter_role=filter_role, 
                           filter_status=filter_status, 
                           available_roles=MANAGEABLE_RECRUITER_ROLES)

@staff_bp.route('/profile/<int:staff_id_viewing>')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def view_recruiter_profile(staff_id_viewing):
    viewer_staff_id = getattr(current_user, 'specific_role_id', None)
    profile_data = {}
    can_manage_profile, can_assign_points = False, False
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # [MODIFIED] Query now uses u.AccountStatus instead of u.IsActive
        cursor.execute("""
            SELECT s.StaffID, u.AccountStatus, u.UserID, u.FirstName, u.LastName, 
                   u.ProfilePictureURL, u.Email, u.RegistrationDate, s.Role, 
                   s.ReportsToStaffID, s.TotalPoints, s.ReferralCode 
            FROM Staff s 
            JOIN Users u ON s.UserID = u.UserID 
            WHERE s.StaffID = %s
        """, (staff_id_viewing,))
        profile_info = cursor.fetchone()
        
        if not profile_info:
            abort(404, "Staff member not found.")

        is_top_level = current_user.role_type in TOP_LEVEL_MANAGEMENT
        is_own_profile = (str(staff_id_viewing) == str(viewer_staff_id))
        is_direct_manager = (str(profile_info['ReportsToStaffID']) == str(viewer_staff_id))
        is_indirect_manager = not is_direct_manager and _is_subordinate(cursor, viewer_staff_id, staff_id_viewing)
        
        if not (is_own_profile or is_direct_manager or is_indirect_manager or is_top_level):
            abort(403)
        
        can_manage_profile = is_direct_manager or is_indirect_manager or is_top_level
        
        manager_role = current_user.role_type
        if manager_role in TOP_LEVEL_MANAGEMENT or (manager_role == 'UnitManager' and (is_direct_manager or is_indirect_manager)) or (manager_role == 'SourcingTeamLead' and is_direct_manager and profile_info['Role'] == 'SourcingRecruiter'):
            can_assign_points = True
        if is_own_profile:
            can_assign_points = False
        
        # This uses the Staff.TotalPoints, which is now the correct central value
        profile_data['total_points'] = profile_info.get('TotalPoints', 0)

        log_query = """
            SELECT pl.*, u_assigner.FirstName as AssignerFirstName, u_assigner.LastName as AssignerLastName
            FROM StaffPointsLog pl
            JOIN Staff s_assigner ON pl.AwardedByStaffID = s_assigner.StaffID
            JOIN Users u_assigner ON s_assigner.UserID = u_assigner.UserID
            WHERE pl.AwardedToStaffID = %s ORDER BY pl.AwardDate DESC LIMIT 50
        """
        cursor.execute(log_query, (staff_id_viewing,))
        profile_data['point_transactions'] = cursor.fetchall()

        profile_data['info'] = profile_info
        profile_data['kpis'] = _get_performance_stats(cursor, staff_id_viewing)

    finally:
        if conn and conn.is_connected(): conn.close()
    
    return render_template('recruiter_team_portal/recruiter_profile.html', 
                           title=f"Profile: {profile_data['info']['FirstName']}", 
                           profile_data=profile_data, 
                           available_roles=ASSIGNABLE_SOURCING_ROLES,
                           can_manage_profile=can_manage_profile,
                           can_assign_points=can_assign_points)

@staff_bp.route('/profile/assign-points', methods=['POST'])
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def assign_points():
    staff_id_to_reward = request.form.get('staff_id')
    points_str = request.form.get('points')
    reason = request.form.get('reason', '').strip()
    manager_staff_id = getattr(current_user, 'specific_role_id', None)
    manager_role = current_user.role_type
    redirect_url = url_for('staff_bp.view_recruiter_profile', staff_id_viewing=staff_id_to_reward)

    if not all([staff_id_to_reward, points_str, reason]):
        flash("Points and reason are required.", "danger")
        return redirect(redirect_url)
    try:
        points = int(points_str)
        if points == 0: flash("Points value cannot be zero.", "warning"); return redirect(redirect_url)
    except (ValueError, TypeError):
        flash("Invalid number of points provided.", "danger"); return redirect(redirect_url)
    
    if str(staff_id_to_reward) == str(manager_staff_id):
        flash("You cannot make a point transaction for yourself.", "warning"); return redirect(redirect_url)

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT Role, ReportsToStaffID FROM Staff WHERE StaffID = %s", (staff_id_to_reward,))
        subordinate = cursor.fetchone()
        if not subordinate: flash("Staff member not found.", "danger"); return redirect(url_for('staff_bp.manage_recruiters'))
        
        is_authorized = (manager_role in TOP_LEVEL_MANAGEMENT) or \
                        (manager_role == 'UnitManager' and _is_subordinate(cursor, manager_staff_id, staff_id_to_reward)) or \
                        (manager_role == 'SourcingTeamLead' and str(subordinate['ReportsToStaffID']) == str(manager_staff_id) and subordinate['Role'] == 'SourcingRecruiter')
        
        if not is_authorized:
            flash("You do not have permission to manage points for this staff member.", "danger")
            return redirect(redirect_url)
        
        # [MODIFIED] Logic uses StaffPointsLog and updates Staff.TotalPoints
        cursor.execute("INSERT INTO StaffPointsLog (AwardedToStaffID, AwardedByStaffID, PointsAmount, ActivityType, Notes) VALUES (%s, %s, %s, %s, %s)",
                       (staff_id_to_reward, manager_staff_id, points, 'ManualAdjustment', reason))
        cursor.execute("UPDATE Staff SET TotalPoints = COALESCE(TotalPoints, 0) + %s WHERE StaffID = %s", (points, staff_id_to_reward))
        conn.commit()
        flash("Point transaction successfully logged.", "success")
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Error logging point transaction for StaffID {staff_id_to_reward}: {e}")
        flash("An error occurred while logging the transaction.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    return redirect(redirect_url)

@staff_bp.route('/pending-staff')
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def list_pending_staff():
    """
    [RESTORED & UPDATED] This route is now fully functional and queries the StaffApplications table.
    It provides a view of pending applications specifically for this portal.
    """
    conn = get_db_connection()
    pending_applications = []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                sa.ApplicationID, u.UserID, u.FirstName, u.LastName, u.Email, 
                u.RegistrationDate, sa.DesiredRole, sa.CVFilePath
            FROM StaffApplications sa
            JOIN Users u ON sa.UserID = u.UserID
            WHERE sa.Status = 'Pending' 
            ORDER BY sa.CreatedAt ASC
        """)
        pending_applications = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching pending staff applications: {e}")
        flash("An error occurred while fetching pending applications.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    # Note: This route renders 'pending_users.html'. Ensure this template is updated
    # to handle 'pending_applications' data and has forms pointing to the central
    # 'staff_perf_bp.approve_application' and 'staff_perf_bp.reject_application' routes.
    return render_template('recruiter_team_portal/pending_users.html', 
                           title="Review Staff Applications", 
                           pending_users=pending_applications)

@staff_bp.route('/activate-staff', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def activate_staff_member():
    """Activates an INACTIVE staff member. New staff are approved via the application review flow."""
    staff_id = request.form.get('staff_id')
    if not staff_id:
        flash("Staff ID is missing.", "danger")
        return redirect(request.referrer or url_for('staff_bp.manage_recruiters'))
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users u JOIN Staff s ON u.UserID = s.UserID SET u.AccountStatus = 'Active' WHERE s.StaffID = %s", (staff_id,))
        if cursor.rowcount > 0:
            conn.commit()
            flash("Staff member has been activated.", "success")
        else:
            flash("Staff member not found or no change was needed.", "warning")
    except Exception as e:
        flash(f"Error activating staff: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return redirect(request.referrer or url_for('staff_bp.manage_recruiters'))

@staff_bp.route('/deactivate-staff', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def deactivate_staff():
    """Deactivates an ACTIVE staff member."""
    staff_id = request.form.get('staff_id')
    if not staff_id:
        flash("Staff ID is missing.", "danger")
        return redirect(request.referrer)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users u JOIN Staff s ON u.UserID = s.UserID SET u.AccountStatus = 'Inactive' WHERE s.StaffID = %s", (staff_id,))
        cursor.execute("UPDATE Staff SET TeamID = NULL, ReportsToStaffID = NULL WHERE StaffID = %s", (staff_id,))
        conn.commit()
        flash("Staff member has been deactivated.", "success")
    except Exception as e:
        flash(f"Error deactivating staff member: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return redirect(request.referrer or url_for('organization_bp.list_units'))

@staff_bp.route('/profile/change-role', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def change_staff_role():
    staff_id_to_change = request.form.get('staff_id')
    new_role = request.form.get('new_role')
    manager_staff_id = getattr(current_user, 'specific_role_id', None)
    redirect_url = url_for('staff_bp.view_recruiter_profile', staff_id_viewing=staff_id_to_change)
    
    if not staff_id_to_change or not new_role:
        flash("Staff ID or new role is missing.", "danger"); return redirect(request.referrer or redirect_url)
    if new_role not in ASSIGNABLE_SOURCING_ROLES:
        flash("Invalid role selected.", "danger"); return redirect(redirect_url)
    if str(staff_id_to_change) == str(manager_staff_id):
        flash("You cannot change your own role.", "warning"); return redirect(redirect_url)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        is_authorized = (current_user.role_type in TOP_LEVEL_MANAGEMENT) or \
                        (manager_staff_id and _is_subordinate(cursor, manager_staff_id, staff_id_to_change))
        
        if not is_authorized:
            flash("You are not authorized to modify this staff member's role.", "danger")
            return redirect(redirect_url)

        cursor.execute("UPDATE Staff SET Role = %s WHERE StaffID = %s", (new_role, staff_id_to_change))
        conn.commit()
        flash(f"Role successfully updated to '{new_role}'.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error updating role: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return redirect(redirect_url)