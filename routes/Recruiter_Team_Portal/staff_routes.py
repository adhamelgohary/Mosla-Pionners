# routes/Recruiter_Team_Portal/staff_routes.py
from flask import Blueprint, abort, render_template, flash, redirect, url_for, current_app, request
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

# --- ROLE CONSTANTS ---
LEADER_ROLES_IN_PORTAL = ['SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'CEO', 'Founder']
ORG_MANAGEMENT_ROLES = ['HeadUnitManager', 'CEO', 'Founder']
ASSIGNABLE_SOURCING_ROLES = ['SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager']
MANAGEABLE_RECRUITER_ROLES = ['SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager']

# Define a complete, self-contained blueprint for staff-related routes
staff_bp = Blueprint('staff_bp', __name__,
                     url_prefix='/recruiter-portal',
                     template_folder='../../../templates')

def _get_performance_stats(cursor, staff_id):
    cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s AND Status = 'Hired'", (staff_id,))
    hires = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s", (staff_id,))
    referrals = cursor.fetchone()['count']
    return hires, referrals

@staff_bp.route('/manage-recruiters')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def manage_recruiters():
    search_query, filter_role, filter_status = request.args.get('search', '').strip(), request.args.get('role', ''), request.args.get('status', '')
    conn, recruiters = get_db_connection(), []
    try:
        cursor = conn.cursor(dictionary=True)
        role_placeholders = ', '.join(['%s'] * len(MANAGEABLE_RECRUITER_ROLES))
        sql = f"SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.IsActive, u.ProfilePictureURL, team_info.TeamName, team_info.UnitName FROM Staff s JOIN Users u ON s.UserID = u.UserID LEFT JOIN (SELECT t.TeamID, t.TeamName, su.UnitName FROM SourcingTeams t LEFT JOIN SourcingUnits su ON t.UnitID = su.UnitID) AS team_info ON s.TeamID = team_info.TeamID WHERE s.Role IN ({role_placeholders})"
        params = list(MANAGEABLE_RECRUITER_ROLES)
        if search_query: sql += " AND (u.FirstName LIKE %s OR u.LastName LIKE %s OR u.Email LIKE %s)"; like_query = f"%{search_query}%"; params.extend([like_query, like_query, like_query])
        if filter_role: sql += " AND s.Role = %s"; params.append(filter_role)
        if filter_status.lower() == 'active': sql += " AND u.IsActive = 1"
        elif filter_status.lower() == 'inactive': sql += " AND u.IsActive = 0"
        sql += " ORDER BY u.FirstName, u.LastName"
        cursor.execute(sql, tuple(params)); recruiters = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching recruiters list: {e}", exc_info=True); flash("Could not load the list of recruiters.", "danger")
    finally: conn.close()
    return render_template('recruiter_team_portal/manage_recruiters.html', title="Manage Recruiters", recruiters=recruiters, search_query=search_query, filter_role=filter_role, filter_status=filter_status, available_roles=MANAGEABLE_RECRUITER_ROLES)

@staff_bp.route('/profile/<int:staff_id_viewing>')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def view_recruiter_profile(staff_id_viewing):
    viewer_staff_id, profile_data = getattr(current_user, 'specific_role_id', None), {}
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT s.StaffID, u.IsActive, u.UserID, u.FirstName, u.LastName, u.ProfilePictureURL, u.Email, u.RegistrationDate, s.Role, s.ReportsToStaffID, s.TotalPoints, s.ReferralCode FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s", (staff_id_viewing,))
        profile_info = cursor.fetchone()
        if not profile_info: abort(404, "Staff member not found.")
        profile_data['info'] = profile_info
        is_manager, is_top_level_manager, is_own_profile = (profile_info['ReportsToStaffID'] == viewer_staff_id), current_user.role_type in ['HeadUnitManager', 'CEO', 'Founder'], (profile_info['StaffID'] == viewer_staff_id)
        if not (is_manager or is_top_level_manager or is_own_profile): abort(403)
        profile_data['kpis'] = {}; profile_data['kpis']['hires_all_time'], profile_data['kpis']['referrals_all_time'] = _get_performance_stats(cursor, staff_id_viewing)
        cursor.execute("SELECT ja.ApplicationID, ja.Status, u.FirstName, u.LastName, jo.Title as JobTitle FROM JobApplications ja JOIN Candidates c ON ja.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID JOIN JobOffers jo ON ja.OfferID = jo.OfferID WHERE ja.ReferringStaffID = %s ORDER BY ja.ApplicationDate DESC LIMIT 10", (staff_id_viewing,))
        profile_data['recent_applications'] = cursor.fetchall()
    finally: conn.close()
    return render_template('recruiter_team_portal/recruiter_profile.html', title=f"Profile: {profile_data['info']['FirstName']}", profile_data=profile_data, available_roles=ASSIGNABLE_SOURCING_ROLES)

@staff_bp.route('/pending-staff')
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def list_pending_staff():
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT u.UserID, s.StaffID, u.FirstName, u.LastName, u.Email, u.RegistrationDate, s.Role FROM Users u JOIN Staff s ON u.UserID = s.UserID WHERE u.IsActive = 0 ORDER BY u.RegistrationDate ASC")
        pending_staff = cursor.fetchall()
    finally: conn.close()
    return render_template('recruiter_team_portal/pending_users.html', title="Activate New Staff", pending_users=pending_staff)

@staff_bp.route('/activate-staff', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def activate_staff_member():
    staff_id, initial_role = request.form.get('staff_id'), request.form.get('initial_role')
    if not staff_id: flash("Staff ID is missing.", "danger"); return redirect(url_for('staff_bp.list_pending_staff'))
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users u JOIN Staff s ON u.UserID = s.UserID SET u.IsActive = 1 WHERE s.StaffID = %s", (staff_id,))
        if cursor.rowcount == 0: flash("User not found.", "warning")
        else:
            if initial_role: cursor.execute("UPDATE Staff SET Role = %s WHERE StaffID = %s", (initial_role, staff_id))
            conn.commit(); flash("Staff member successfully activated.", "success")
    except Exception as e: current_app.logger.error(f"Error activating staff for StaffID {staff_id}: {e}"); flash(f"Error activating staff: {e}", "danger")
    finally: conn.close()
    return redirect(request.referrer or url_for('staff_bp.list_pending_staff'))

@staff_bp.route('/deactivate-staff', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def deactivate_staff():
    staff_id = request.form.get('staff_id')
    if not staff_id: flash("Staff ID is missing.", "danger"); return redirect(request.referrer)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Users u JOIN Staff s ON u.UserID = s.UserID SET u.IsActive = 0 WHERE s.StaffID = %s", (staff_id,))
        cursor.execute("UPDATE Staff SET TeamID = NULL, ReportsToStaffID = NULL WHERE StaffID = %s", (staff_id,))
        conn.commit(); flash("Staff member has been deactivated.", "success")
    except Exception as e: current_app.logger.error(f"Error deactivating staff for StaffID {staff_id}: {e}"); flash(f"Error deactivating staff member: {e}", "danger")
    finally: conn.close()
    return redirect(request.referrer or url_for('organization_bp.list_units'))

@staff_bp.route('/profile/change-role', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def change_staff_role():
    staff_id_to_change, new_role = request.form.get('staff_id'), request.form.get('new_role')
    redirect_url = url_for('staff_bp.view_recruiter_profile', staff_id_viewing=staff_id_to_change)
    if not staff_id_to_change or not new_role: flash("Staff ID or new role is missing.", "danger"); return redirect(request.referrer or redirect_url)
    if new_role not in ASSIGNABLE_SOURCING_ROLES: flash("Invalid role selected.", "danger"); return redirect(redirect_url)
    if str(staff_id_to_change) == str(getattr(current_user, 'specific_role_id', '')): flash("You cannot change your own role from this page.", "warning"); return redirect(redirect_url)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Staff SET Role = %s WHERE StaffID = %s", (new_role, staff_id_to_change))
        conn.commit(); flash(f"Role successfully updated to '{new_role}'. Any necessary team or unit re-assignments should be done on the Organization Management page.", "success")
    except Exception as e: current_app.logger.error(f"Error changing role for StaffID {staff_id_to_change}: {e}"); flash(f"Error updating role: {e}", "danger")
    finally: conn.close()
    return redirect(redirect_url)