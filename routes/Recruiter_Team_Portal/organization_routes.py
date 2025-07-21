# routes/Recruiter_Team_Portal/organization_routes.py
from flask import Blueprint, abort, render_template, flash, redirect, url_for, current_app, request
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

# --- ROLE CONSTANTS ---
RECRUITER_PORTAL_ROLES = ['SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'CEO', 'Founder']
LEADER_ROLES_IN_PORTAL = ['SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'CEO', 'Founder']
ORG_MANAGEMENT_ROLES = ['HeadUnitManager', 'CEO', 'Founder']
TEAM_ASSIGNMENT_ROLES = ['SourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'CEO', 'Founder']
UNIT_AND_ORG_MANAGEMENT_ROLES = ['UnitManager', 'HeadUnitManager', 'CEO', 'Founder']

# Define a complete, self-contained blueprint for organization-related routes
organization_bp = Blueprint('organization_bp', __name__,
                              url_prefix='/recruiter-portal/organization',
                              template_folder='../../../templates')

# --- Helper Functions (can be moved to a utils file later if needed) ---
def _get_performance_stats(cursor, staff_id):
    cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s AND Status = 'Hired'", (staff_id,))
    hires = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s", (staff_id,))
    referrals = cursor.fetchone()['count']
    return hires, referrals

def _get_manager_context_data(cursor, user):
    context = {"teams_in_unit": [], "potential_team_leads": [], "unassigned_recruiters": [], "assignable_teams": []}
    if user.role_type == 'UnitManager':
        cursor.execute("SELECT st.*, u.FirstName as LeadFirstName, u.LastName as LeadLastName FROM SourcingTeams st LEFT JOIN Staff s ON st.TeamLeadStaffID = s.StaffID LEFT JOIN Users u ON s.UserID = u.UserID WHERE st.UnitID = (SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s)", (user.specific_role_id,))
        context['teams_in_unit'] = cursor.fetchall()
        context['assignable_teams'] = context['teams_in_unit']
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName, s.Role FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead') AND u.IsActive = 1 AND (s.TeamID IN (SELECT TeamID FROM SourcingTeams WHERE UnitID = (SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s)) OR s.TeamID IS NULL)", (user.specific_role_id,))
        context['potential_team_leads'] = cursor.fetchall()
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role = 'SourcingRecruiter' AND s.TeamID IS NULL AND u.IsActive = 1")
        context['unassigned_recruiters'] = cursor.fetchall()
    elif user.role_type == 'SourcingTeamLead':
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role = 'SourcingRecruiter' AND s.TeamID IS NULL AND u.IsActive = 1")
        context['unassigned_recruiters'] = cursor.fetchall()
        cursor.execute("SELECT * FROM SourcingTeams WHERE TeamLeadStaffID = %s", (user.specific_role_id,))
        context['assignable_teams'] = cursor.fetchall()
    return context

# --- Smart Entry Route ---
@organization_bp.route('/my-organization')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def manage_organization_entry():
    role, staff_id = current_user.role_type, current_user.specific_role_id
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if role in ORG_MANAGEMENT_ROLES:
            return redirect(url_for('organization_bp.list_units'))
        elif role == 'UnitManager':
            cursor.execute("SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s", (staff_id,))
            unit = cursor.fetchone()
            if unit: return redirect(url_for('organization_bp.manage_unit', unit_id=unit['UnitID']))
            else: flash("You are not assigned to manage a unit.", "warning"); return redirect(url_for('dashboard_bp.dashboard'))
        elif role == 'SourcingTeamLead':
            cursor.execute("SELECT TeamID FROM SourcingTeams WHERE TeamLeadStaffID = %s", (staff_id,))
            team = cursor.fetchone()
            if team: return redirect(url_for('organization_bp.manage_team', team_id=team['TeamID']))
            else: flash("You are not assigned to lead a team.", "warning"); return redirect(url_for('dashboard_bp.dashboard'))
        elif role == 'SourcingRecruiter':
            cursor.execute("SELECT TeamID FROM Staff WHERE StaffID = %s", (staff_id,))
            staff_info = cursor.fetchone()
            if staff_info and staff_info['TeamID']: return redirect(url_for('organization_bp.manage_team', team_id=staff_info['TeamID']))
            else: flash("You are not currently assigned to a team.", "info"); return redirect(url_for('dashboard_bp.dashboard'))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    flash("Could not determine your organizational view.", "danger")
    return redirect(url_for('dashboard_bp.dashboard'))

# --- Hierarchy Viewing Routes ---
@organization_bp.route('/my-team')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def my_team_view():
    leader_staff_id, leader_role = getattr(current_user, 'specific_role_id', None), getattr(current_user, 'role_type', None)
    if not leader_staff_id or not leader_role:
        flash("Your staff profile could not be found.", "warning")
        return redirect(url_for('dashboard_bp.dashboard'))
    conn, team_members, manager_context = get_db_connection(), [], {}
    cursor = conn.cursor(dictionary=True)
    try:
        manager_context = _get_manager_context_data(cursor, current_user)
        if leader_role in ORG_MANAGEMENT_ROLES:
            cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.ProfilePictureURL, u.IsActive, su.UnitName FROM SourcingUnits su JOIN Staff s ON su.UnitManagerStaffID = s.StaffID JOIN Users u ON s.UserID = u.UserID WHERE s.ReportsToStaffID = %s AND u.IsActive = 1", (leader_staff_id,))
        elif leader_role == 'UnitManager':
            cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.ProfilePictureURL, u.IsActive, st.TeamName FROM SourcingTeams st JOIN SourcingUnits su ON st.UnitID = su.UnitID JOIN Staff s ON st.TeamLeadStaffID = s.StaffID JOIN Users u ON s.UserID = u.UserID WHERE su.UnitManagerStaffID = %s AND u.IsActive = 1", (leader_staff_id,))
        elif leader_role == 'SourcingTeamLead':
            cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.IsActive, u.ProfilePictureURL FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.TeamID = (SELECT TeamID FROM Staff WHERE StaffID = %s) AND s.StaffID != %s AND u.IsActive = 1", (leader_staff_id, leader_staff_id))
        team_members = cursor.fetchall()
        for member in team_members:
            member['total_hires'], member['total_referrals'] = _get_performance_stats(cursor, member['StaffID'])
            member['direct_reports_count'] = 1 if member['Role'] in ['UnitManager', 'SourcingTeamLead'] else 0
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return render_template('recruiter_team_portal/team_hierarchy_view.html', title="My Team", team_members=team_members, current_leader=current_user, breadcrumbs=[], **manager_context)

@organization_bp.route('/team-view/<int:leader_staff_id>')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def team_view(leader_staff_id):
    conn, team_members, manager_context, current_leader = get_db_connection(), [], {}, None
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT s.StaffID, s.Role, u.IsActive, u.FirstName, u.LastName, u.UserID FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s", (leader_staff_id,))
        current_leader = cursor.fetchone()
        if not current_leader: abort(404)
        manager_context, leader_role = _get_manager_context_data(cursor, current_user), current_leader['Role']
        if leader_role == 'UnitManager':
            cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.IsActive, u.ProfilePictureURL, st.TeamName FROM SourcingTeams st JOIN SourcingUnits su ON st.UnitID = su.UnitID JOIN Staff s ON st.TeamLeadStaffID = s.StaffID JOIN Users u ON s.UserID = u.UserID WHERE su.UnitManagerStaffID = %s AND u.IsActive = 1", (leader_staff_id,))
        elif leader_role == 'SourcingTeamLead':
            cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.IsActive, u.ProfilePictureURL FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.TeamID = (SELECT TeamID FROM Staff WHERE StaffID = %s) AND s.StaffID != %s AND u.IsActive = 1", (leader_staff_id, leader_staff_id))
        team_members = cursor.fetchall()
        for member in team_members:
            member['total_hires'], member['total_referrals'] = _get_performance_stats(cursor, member['StaffID'])
            member['direct_reports_count'] = 1 if member['Role'] in ['UnitManager', 'SourcingTeamLead'] else 0
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    breadcrumbs = [{'name': 'My Team', 'url': url_for('organization_bp.my_team_view')}, {'name': f"{current_leader['FirstName']} {current_leader['LastName']}", 'url': None}]
    return render_template('recruiter_team_portal/team_hierarchy_view.html', title=f"Team: {current_leader['FirstName']} {current_leader['LastName']}", team_members=team_members, current_leader=current_leader, breadcrumbs=breadcrumbs, **manager_context)

# --- Unit & Team Management Routes ---
@organization_bp.route('/units')
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def list_units():
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = "SELECT su.*, u.FirstName, u.LastName FROM SourcingUnits su LEFT JOIN Staff s ON su.UnitManagerStaffID = s.StaffID LEFT JOIN Users u ON s.UserID = u.UserID"
        if not show_all: sql += " WHERE su.IsActive = 1"
        sql += " ORDER BY su.IsActive DESC, su.UnitName"
        cursor.execute(sql)
        units = cursor.fetchall()
        cursor.execute("SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName, s.Role FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role IN ('SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager') AND u.IsActive = 1")
        potential_managers = cursor.fetchall()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return render_template('recruiter_team_portal/list_units.html', title="Organization Management: Units", units=units, potential_managers=potential_managers, show_all=show_all)

@organization_bp.route('/unit/<int:unit_id>')
@login_required_with_role(UNIT_AND_ORG_MANAGEMENT_ROLES)
def manage_unit(unit_id):
    if current_user.role_type == 'UnitManager':
        conn_check = get_db_connection()
        cursor_check = conn_check.cursor(dictionary=True)
        cursor_check.execute("SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s", (current_user.specific_role_id,))
        managed_unit = cursor_check.fetchone()
        cursor_check.close(); conn_check.close()
        if not managed_unit or managed_unit['UnitID'] != unit_id: abort(403, "You are not authorized to manage this unit.")
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM SourcingUnits WHERE UnitID = %s", (unit_id,))
        unit = cursor.fetchone();
        if not unit: abort(404, "Unit not found.")
        team_sql = "SELECT st.*, lead_user.FirstName as LeadFirstName, lead_user.LastName as LeadLastName FROM SourcingTeams st LEFT JOIN Staff lead_staff ON st.TeamLeadStaffID = lead_staff.StaffID LEFT JOIN Users lead_user ON lead_staff.UserID = lead_user.UserID WHERE st.UnitID = %s"
        if not show_all: team_sql += " AND st.IsActive = 1"
        team_sql += " ORDER BY st.IsActive DESC, st.TeamName"
        cursor.execute(team_sql, (unit_id,))
        teams_in_unit = cursor.fetchall()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return render_template('recruiter_team_portal/manage_unit.html', title=f"Manage Unit: {unit['UnitName']}", unit=unit, teams_in_unit=teams_in_unit, show_all=show_all)

@organization_bp.route('/team/<int:team_id>')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def manage_team(team_id):
    user_role, staff_id = current_user.role_type, current_user.specific_role_id
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT UnitID FROM SourcingTeams WHERE TeamID = %s", (team_id,))
        team_info = cursor.fetchone();
        if not team_info: abort(404, "Team not found.")
        is_authorized = False
        if user_role in ORG_MANAGEMENT_ROLES: is_authorized = True
        elif user_role == 'UnitManager':
            cursor.execute("SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s", (staff_id,)); managed_unit = cursor.fetchone()
            if managed_unit and managed_unit['UnitID'] == team_info['UnitID']: is_authorized = True
        elif user_role == 'SourcingTeamLead':
            cursor.execute("SELECT TeamID FROM SourcingTeams WHERE TeamLeadStaffID = %s", (staff_id,)); led_team = cursor.fetchone()
            if led_team and led_team['TeamID'] == team_id: is_authorized = True
        elif user_role == 'SourcingRecruiter':
            cursor.execute("SELECT TeamID FROM Staff WHERE StaffID = %s", (staff_id,)); member_team = cursor.fetchone()
            if member_team and member_team['TeamID'] == team_id: is_authorized = True
        if not is_authorized: abort(403, "You are not authorized to view this team.")
        
        cursor.execute("SELECT st.*, lead_user.FirstName as LeadFirstName, lead_user.LastName as LeadLastName, su.UnitName FROM SourcingTeams st LEFT JOIN Staff lead_staff ON st.TeamLeadStaffID = lead_staff.StaffID LEFT JOIN Users lead_user ON lead_staff.UserID = lead_user.UserID LEFT JOIN SourcingUnits su ON st.UnitID = su.UnitID WHERE st.TeamID = %s", (team_id,))
        team = cursor.fetchone()
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName, s.Role FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.TeamID = %s AND u.IsActive = 1 ORDER BY s.Role, u.FirstName", (team_id,))
        team_members = cursor.fetchall()
        cursor.execute("SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role IN ('SourcingTeamLead', 'SourcingRecruiter') AND u.IsActive = 1")
        potential_team_leads = cursor.fetchall()
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role = 'SourcingRecruiter' AND s.TeamID IS NULL AND u.IsActive = 1")
        unassigned_recruiters = cursor.fetchall()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return render_template('recruiter_team_portal/manage_team.html', title=f"Manage Team: {team['TeamName']}", team=team, team_members=team_members, potential_team_leads=potential_team_leads, unassigned_recruiters=unassigned_recruiters)


# --- POST Actions for Organization Management ---
@organization_bp.route('/create-unit', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def create_unit():
    unit_name = request.form.get('unit_name')
    if not unit_name: flash("Unit Name is required.", "danger"); return redirect(url_for('organization_bp.list_units'))
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO SourcingUnits (UnitName) VALUES (%s)", (unit_name,))
        conn.commit(); flash(f"Unit '{unit_name}' created successfully.", "success")
    except Exception as e: flash(f"Error creating unit: {e}", "danger")
    finally: conn.close()
    return redirect(url_for('organization_bp.list_units'))

@organization_bp.route('/create-team', methods=['POST'])
@login_required_with_role(UNIT_AND_ORG_MANAGEMENT_ROLES)
def create_team():
    team_name, unit_id = request.form.get('team_name'), request.form.get('unit_id')
    if not team_name or not unit_id:
        flash("A Team Name and Unit context are required to create a team.", "danger")
        return redirect(url_for('organization_bp.list_units'))
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO SourcingTeams (TeamName, UnitID) VALUES (%s, %s)", (team_name, unit_id))
        conn.commit(); flash(f"Team '{team_name}' was created successfully.", "success")
    except Exception as e:
        current_app.logger.error(f"Error creating team '{team_name}' for unit {unit_id}: {e}")
        flash(f"An error occurred while creating the team: {e}", "danger")
    finally: conn.close()
    return redirect(url_for('organization_bp.manage_unit', unit_id=unit_id))

@organization_bp.route('/assign-unit-manager', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def assign_unit_manager():
    unit_id, manager_staff_id = request.form.get('unit_id'), request.form.get('manager_staff_id')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE SourcingUnits SET UnitManagerStaffID = %s WHERE UnitID = %s", (manager_staff_id, unit_id))
        cursor.execute("UPDATE Staff SET Role = 'UnitManager', TeamID = NULL, ReportsToStaffID = %s WHERE StaffID = %s", (current_user.specific_role_id, manager_staff_id))
        conn.commit(); flash("Unit Manager assigned successfully.", "success")
    except Exception as e: flash(f"Error assigning manager: {e}", "danger")
    finally: conn.close()
    return redirect(url_for('organization_bp.list_units'))

@organization_bp.route('/assign-team-lead', methods=['POST'])
@login_required_with_role(UNIT_AND_ORG_MANAGEMENT_ROLES)
def assign_team_lead():
    team_id, lead_staff_id = request.form.get('team_id'), request.form.get('lead_staff_id')
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        if current_user.role_type == 'UnitManager':
            cursor.execute("SELECT su.UnitID FROM SourcingUnits su WHERE su.UnitManagerStaffID = %s", (current_user.specific_role_id,)); manager_unit = cursor.fetchone()
            cursor.execute("SELECT st.UnitID FROM SourcingTeams st WHERE st.TeamID = %s", (team_id,)); team_unit = cursor.fetchone()
            if not manager_unit or not team_unit or manager_unit['UnitID'] != team_unit['UnitID']: abort(403, "You can only assign leads to teams within your own unit.")
        cursor.execute("UPDATE SourcingTeams SET TeamLeadStaffID = %s WHERE TeamID = %s", (lead_staff_id, team_id))
        cursor.execute("UPDATE Staff SET Role = 'SourcingTeamLead', TeamID = %s WHERE StaffID = %s", (team_id, lead_staff_id))
        cursor.execute("SELECT su.UnitManagerStaffID FROM SourcingTeams st JOIN SourcingUnits su ON st.UnitID = su.UnitID WHERE st.TeamID = %s", (team_id,))
        unit_info = cursor.fetchone()
        if unit_info and unit_info.get('UnitManagerStaffID'):
            cursor.execute("UPDATE Staff SET ReportsToStaffID = %s WHERE StaffID = %s", (unit_info['UnitManagerStaffID'], lead_staff_id))
            flash("Team Lead assigned successfully and now reports to the Unit Manager.", "success")
        else:
            cursor.execute("UPDATE Staff SET ReportsToStaffID = NULL WHERE StaffID = %s", (lead_staff_id,))
            flash("Team Lead assigned successfully. Note: The team is not in a managed unit, so no manager was set.", "info")
        conn.commit()
    except Exception as e:
        conn.rollback(); current_app.logger.error(f"Error assigning team lead: {e}"); flash(f"Error assigning team lead: {e}", "danger")
    finally: conn.close()
    return redirect(request.referrer or url_for('organization_bp.list_units'))

@organization_bp.route('/assign-recruiter-to-team', methods=['POST'])
@login_required_with_role(TEAM_ASSIGNMENT_ROLES)
def assign_recruiter_to_team():
    recruiter_staff_id, team_id = request.form.get('recruiter_staff_id'), request.form.get('team_id')
    viewer_staff_id, viewer_role = getattr(current_user, 'specific_role_id', None), getattr(current_user, 'role_type', None)
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        if viewer_role == 'UnitManager':
            cursor.execute("SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s", (viewer_staff_id,)); manager_unit = cursor.fetchone()
            cursor.execute("SELECT UnitID FROM SourcingTeams WHERE TeamID = %s", (team_id,)); target_team_unit = cursor.fetchone()
            if not manager_unit or not target_team_unit or manager_unit['UnitID'] != target_team_unit['UnitID']: flash("You can only assign recruiters to teams within your unit.", "danger"); return redirect(request.referrer)
        elif viewer_role == 'SourcingTeamLead':
            cursor.execute("SELECT TeamID FROM Staff WHERE StaffID = %s", (viewer_staff_id,)); leader_team = cursor.fetchone()
            if not leader_team or str(leader_team['TeamID']) != str(team_id): flash("You can only assign recruiters to your own team.", "danger"); return redirect(request.referrer)
        cursor.execute("SELECT TeamLeadStaffID FROM SourcingTeams WHERE TeamID = %s", (team_id,))
        team = cursor.fetchone()
        if not team or not team['TeamLeadStaffID']: flash("Cannot assign recruiter. The selected team does not have a lead.", "warning"); return redirect(request.referrer)
        cursor.execute("UPDATE Staff SET TeamID = %s, ReportsToStaffID = %s WHERE StaffID = %s", (team_id, team['TeamLeadStaffID'], recruiter_staff_id))
        conn.commit(); flash("Recruiter successfully assigned to team.", "success")
    except Exception as e:
        current_app.logger.error(f"Error assigning recruiter to team: {e}"); flash(f"Error assigning recruiter: {e}", "danger")
    finally: conn.close()
    return redirect(request.referrer or url_for('organization_bp.list_units'))

@organization_bp.route('/unit/<int:unit_id>/deactivate', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def deactivate_unit(unit_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("UPDATE SourcingUnits SET UnitManagerStaffID = NULL, IsActive = 0 WHERE UnitID = %s", (unit_id,))
        cursor.execute("SELECT TeamID FROM SourcingTeams WHERE UnitID = %s", (unit_id,))
        team_ids = [team['TeamID'] for team in cursor.fetchall()]
        if team_ids:
            placeholders = ', '.join(['%s'] * len(team_ids))
            cursor.execute(f"UPDATE SourcingTeams SET TeamLeadStaffID = NULL, IsActive = 0 WHERE TeamID IN ({placeholders})", tuple(team_ids))
            cursor.execute(f"UPDATE Staff SET TeamID = NULL, ReportsToStaffID = NULL WHERE TeamID IN ({placeholders})", tuple(team_ids))
        conn.commit()
        flash("Unit has been deactivated. All associated teams and staff assignments have been cleared.", "success")
    except Exception as e:
        conn.rollback(); current_app.logger.error(f"Error deactivating unit {unit_id}: {e}", exc_info=True); flash(f"Error deactivating unit: {e}", "danger")
    finally: conn.close()
    return redirect(url_for('organization_bp.list_units'))

@organization_bp.route('/team/<int:team_id>/deactivate', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def deactivate_team(team_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE SourcingTeams SET TeamLeadStaffID = NULL, IsActive = 0 WHERE TeamID = %s", (team_id,))
        cursor.execute("UPDATE Staff SET TeamID = NULL, ReportsToStaffID = NULL WHERE TeamID = %s", (team_id,))
        conn.commit(); flash("Team has been deactivated. All staff assignments have been cleared.", "success")
    except Exception as e:
        conn.rollback(); current_app.logger.error(f"Error deactivating team {team_id}: {e}", exc_info=True); flash(f"Error deactivating team: {e}", "danger")
    finally: conn.close()
    return redirect(request.referrer or url_for('organization_bp.list_units'))