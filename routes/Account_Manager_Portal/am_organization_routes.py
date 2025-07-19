# routes/Account_Manager_Portal/am_organization_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

# --- [CORRECTED] Define roles that can access this new portal section ---
AM_ORG_MANAGEMENT_ROLES = ['HeadAccountManager', 'CEO', 'Founder']
AM_LEADER_ROLES = ['SeniorAccountManager', 'HeadAccountManager', 'CEO', 'Founder']

am_org_bp = Blueprint('am_org_bp', __name__,
                      url_prefix='/account-manager-portal/organization',
                      template_folder='../../../templates')


# --- Main View ---
@am_org_bp.route('/')
@login_required_with_role(AM_ORG_MANAGEMENT_ROLES)
def organization_management():
    """A central hub for managing Account Manager Units and Teams."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch all AM Units
        cursor.execute("""
            SELECT u.*, s.FirstName, s.LastName
            FROM AccountManagerUnits u
            LEFT JOIN Staff s ON u.UnitManagerStaffID = s.StaffID
            LEFT JOIN Users us ON s.UserID = us.UserID ORDER BY u.UnitName
        """)
        units = cursor.fetchall()

        # Fetch all AM Teams
        cursor.execute("""
            SELECT t.*, lead_user.FirstName as LeadFirstName, lead_user.LastName as LeadLastName, u.UnitName
            FROM AccountManagerTeams t
            LEFT JOIN Staff lead_staff ON t.TeamLeadStaffID = lead_staff.StaffID
            LEFT JOIN Users lead_user ON lead_staff.UserID = lead_user.UserID
            LEFT JOIN AccountManagerUnits u ON t.UnitID = u.UnitID ORDER BY u.UnitName, t.TeamName
        """)
        teams = cursor.fetchall()

        # Fetch all Account Manager staff for assignment
        cursor.execute("""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role, t.TeamName
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            LEFT JOIN AccountManagerTeams t ON s.AMTeamID = t.TeamID
            WHERE s.Role IN ('AccountManager', 'SeniorAccountManager', 'HeadAccountManager') AND u.IsActive = 1
            ORDER BY u.LastName, u.FirstName
        """)
        all_am_staff = cursor.fetchall()

        # [CORRECTED] Fetch potential Unit Managers (only HeadAccountManagers)
        cursor.execute("""
            SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role = 'HeadAccountManager' AND u.IsActive = 1
        """)
        potential_unit_managers = cursor.fetchall()

        # [CORRECTED] Fetch potential Team Leads (only SeniorAccountManagers)
        cursor.execute("""
            SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role = 'SeniorAccountManager' AND u.IsActive = 1
        """)
        potential_team_leads = cursor.fetchall()

    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('account_manager_portal/am_organization_management.html',
                           title="AM Organization Structure",
                           units=units, teams=teams, all_am_staff=all_am_staff,
                           potential_unit_managers=potential_unit_managers,
                           potential_team_leads=potential_team_leads)


# --- Action Routes ---

@am_org_bp.route('/create-unit', methods=['POST'])
@login_required_with_role(AM_ORG_MANAGEMENT_ROLES)
def create_am_unit():
    unit_name = request.form.get('unit_name')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO AccountManagerUnits (UnitName) VALUES (%s)", (unit_name,))
        conn.commit()
        flash(f"Account Manager Unit '{unit_name}' created successfully.", "success")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('.organization_management'))

@am_org_bp.route('/create-team', methods=['POST'])
@login_required_with_role(AM_ORG_MANAGEMENT_ROLES)
def create_am_team():
    team_name = request.form.get('team_name')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO AccountManagerTeams (TeamName) VALUES (%s)", (team_name,))
        conn.commit()
        flash(f"Account Manager Team '{team_name}' created successfully.", "success")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('.organization_management'))

@am_org_bp.route('/assign-unit-manager', methods=['POST'])
@login_required_with_role(AM_ORG_MANAGEMENT_ROLES)
def assign_am_unit_manager():
    unit_id = request.form.get('unit_id')
    manager_staff_id = request.form.get('manager_staff_id')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE AccountManagerUnits SET UnitManagerStaffID = %s WHERE UnitID = %s", (manager_staff_id, unit_id))
        conn.commit()
        flash("AM Unit Manager assigned successfully.", "success")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('.organization_management'))

@am_org_bp.route('/assign-team-lead', methods=['POST'])
@login_required_with_role(AM_ORG_MANAGEMENT_ROLES)
def assign_am_team_lead():
    team_id = request.form.get('team_id')
    lead_staff_id = request.form.get('lead_staff_id')
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("UPDATE AccountManagerTeams SET TeamLeadStaffID = %s WHERE TeamID = %s", (lead_staff_id, team_id))
        
        cursor.execute("SELECT u.UnitManagerStaffID FROM AccountManagerTeams t JOIN AccountManagerUnits u ON t.UnitID = u.UnitID WHERE t.TeamID = %s", (team_id,))
        unit_info = cursor.fetchone()
        if unit_info and unit_info.get('UnitManagerStaffID'):
            cursor.execute("UPDATE Staff SET ReportsToStaffID = %s, AMTeamID = %s WHERE StaffID = %s", (unit_info['UnitManagerStaffID'], team_id, lead_staff_id))
        else:
             cursor.execute("UPDATE Staff SET ReportsToStaffID = NULL, AMTeamID = %s WHERE StaffID = %s", (team_id, lead_staff_id))
        
        conn.commit()
        flash("AM Team Lead assigned successfully.", "success")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('.organization_management'))

@am_org_bp.route('/assign-team-to-unit', methods=['POST'])
@login_required_with_role(AM_ORG_MANAGEMENT_ROLES)
def assign_am_team_to_unit():
    team_id = request.form.get('team_id')
    unit_id = request.form.get('unit_id')
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("UPDATE AccountManagerTeams SET UnitID = %s WHERE TeamID = %s", (unit_id, team_id))
        
        cursor.execute("SELECT u.UnitManagerStaffID, t.TeamLeadStaffID FROM AccountManagerTeams t JOIN AccountManagerUnits u ON t.UnitID = u.UnitID WHERE t.TeamID = %s", (team_id,))
        info = cursor.fetchone()
        if info and info.get('UnitManagerStaffID') and info.get('TeamLeadStaffID'):
             cursor.execute("UPDATE Staff SET ReportsToStaffID = %s WHERE StaffID = %s", (info['UnitManagerStaffID'], info['TeamLeadStaffID']))
        
        conn.commit()
        flash("AM Team assigned to Unit successfully.", "success")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('.organization_management'))

@am_org_bp.route('/assign-am-to-team', methods=['POST'])
@login_required_with_role(AM_LEADER_ROLES)
def assign_am_to_team():
    am_staff_id = request.form.get('am_staff_id')
    team_id = request.form.get('team_id')
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT TeamLeadStaffID FROM AccountManagerTeams WHERE TeamID = %s", (team_id,))
        team = cursor.fetchone()
        if team and team['TeamLeadStaffID']:
            cursor.execute("UPDATE Staff SET AMTeamID = %s, ReportsToStaffID = %s WHERE StaffID = %s", (team_id, team['TeamLeadStaffID'], am_staff_id))
            conn.commit()
            flash("Account Manager assigned to team successfully.", "success")
        else:
            flash("Cannot assign. The selected team does not have a lead.", "warning")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('.organization_management'))