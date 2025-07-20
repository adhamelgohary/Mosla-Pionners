# routes/Recruiter_Team_Portal/recruiter_routes.py
from flask import Blueprint, abort, render_template, flash, redirect, url_for, current_app, request, jsonify
from flask_login import login_required, current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import secrets # <--- ADD THIS IMPORT AT THE TOP OF THE FILE
from werkzeug.security import generate_password_hash, check_password_hash # Ensure this is imported
from werkzeug.utils import secure_filename # Ensure this is imported
import os # Ensure this is imported


# --- ROLE CONSTANTS ---
RECRUITER_PORTAL_ROLES = [
    'SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager',
    'HeadUnitManager', 'CEO', 'Founder'
]
LEADER_ROLES_IN_PORTAL = [
    'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager',
    'HeadUnitManager', 'CEO', 'Founder'
]
ORG_MANAGEMENT_ROLES = ['HeadUnitManager', 'CEO', 'Founder']
TEAM_ASSIGNMENT_ROLES = ['SourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'CEO', 'Founder']
UNIT_AND_ORG_MANAGEMENT_ROLES = ['UnitManager', 'HeadUnitManager', 'CEO', 'Founder']

ASSIGNABLE_SOURCING_ROLES = [
    'SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager'
]

MANAGEABLE_RECRUITER_ROLES = ['SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager']


recruiter_bp = Blueprint('recruiter_bp', __name__,
                         url_prefix='/recruiter-portal',
                         template_folder='../../../templates')


@recruiter_bp.route('/')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def dashboard():
    """
    The main dashboard for the Recruiter Portal with advanced, role-aware visualizations and announcements.
    """
    user_staff_id = getattr(current_user, 'specific_role_id', None)
    user_role = getattr(current_user, 'role_type', None)

    if not user_staff_id:
        flash("Your staff profile could not be found.", "danger")
        return redirect(url_for('staff_perf_bp.list_all_staff'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    scoped_staff_ids = []
    dashboard_title = "My Performance"
    
    kpis = {
        'funnel': {'Applied': 0, 'Shortlisted': 0, 'Interview Scheduled': 0, 'Hired': 0},
        'status_breakdown_for_chart': {},
        'total_referrals': 0,
        'monthly_performance': []
    }
    
    announcements = []

    try:
        cursor.execute("""
            SELECT Title, Content, CreatedAt, Priority
            FROM SystemAnnouncements
            WHERE IsActive = 1 AND (DisplayUntil IS NULL OR DisplayUntil > NOW())
            ORDER BY Priority DESC, CreatedAt DESC LIMIT 5
        """)
        announcements = cursor.fetchall()

        # --- Determine the scope of StaffIDs based on the user's role, ensuring they are active ---
        if user_role in ORG_MANAGEMENT_ROLES:
            dashboard_title = "Overall Sourcing Division Performance"
            cursor.execute("""
                SELECT s.StaffID FROM Staff s
                JOIN Users u ON s.UserID = u.UserID
                WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager') AND u.IsActive = 1
            """)
            scoped_staff_ids = [row['StaffID'] for row in cursor.fetchall()]

        elif user_role == 'UnitManager':
            dashboard_title = f"{current_user.first_name}'s Unit Performance"
            cursor.execute("""
                SELECT s.StaffID FROM Staff s
                JOIN SourcingTeams st ON s.TeamID = st.TeamID
                JOIN Users u ON s.UserID = u.UserID
                WHERE st.UnitID = (
                    SELECT su.UnitID FROM SourcingUnits su WHERE su.UnitManagerStaffID = %s
                ) AND u.IsActive = 1
            """, (user_staff_id,))
            scoped_staff_ids = [row['StaffID'] for row in cursor.fetchall()]

        elif user_role == 'SourcingTeamLead':
            dashboard_title = f"{current_user.first_name}'s Team Performance"
            cursor.execute("""
                SELECT s.StaffID FROM Staff s
                JOIN Users u ON s.UserID = u.UserID
                WHERE s.TeamID = (
                    SELECT TeamID FROM Staff WHERE StaffID = %s
                ) AND u.IsActive = 1
            """, (user_staff_id,))
            scoped_staff_ids = [row['StaffID'] for row in cursor.fetchall()]

        if not scoped_staff_ids and current_user.is_active:
            scoped_staff_ids.append(user_staff_id)

        # --- Fetch KPIs using the determined scope of StaffIDs ---
        if scoped_staff_ids:
            placeholders = ', '.join(['%s'] * len(scoped_staff_ids))

            funnel_sql = f"SELECT Status, COUNT(ApplicationID) as count FROM JobApplications WHERE ReferringStaffID IN ({placeholders}) GROUP BY Status"
            cursor.execute(funnel_sql, tuple(scoped_staff_ids))
            funnel_data = {row['Status']: row['count'] for row in cursor.fetchall()}

            kpis['funnel'] = {
                'Applied': funnel_data.get('Applied', 0) + funnel_data.get('Submitted', 0),
                'Shortlisted': funnel_data.get('Shortlisted', 0),
                'Interview Scheduled': funnel_data.get('Interview Scheduled', 0),
                'Hired': funnel_data.get('Hired', 0)
            }
            kpis['status_breakdown_for_chart'] = funnel_data
            kpis['total_referrals'] = sum(funnel_data.values())

            monthly_sql = f"""
                SELECT
                    DATE_FORMAT(ApplicationDate, '%%Y-%%m') AS month,
                    COUNT(ApplicationID) as total_referrals,
                    SUM(CASE WHEN Status = 'Hired' THEN 1 ELSE 0 END) as total_hires
                FROM JobApplications
                WHERE ReferringStaffID IN ({placeholders}) AND ApplicationDate >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
                GROUP BY month ORDER BY month ASC
            """
            cursor.execute(monthly_sql, tuple(scoped_staff_ids))
            kpis['monthly_performance'] = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error fetching recruiter dashboard for StaffID {user_staff_id}: {e}", exc_info=True)
        flash("Could not load all dashboard data.", "warning")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    
    return render_template('recruiter_team_portal/recruiter_dashboard.html',
                           title=dashboard_title, 
                           kpis=kpis,
                           announcements=announcements)

@recruiter_bp.route('/application/<int:application_id>/review')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def review_referred_application(application_id):
    """ Provides a read-only view of an application's details for recruiters. """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)

    conn = get_db_connection()
    review_data = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT ReferringStaffID FROM JobApplications WHERE ApplicationID = %s", (application_id,))
        app_check = cursor.fetchone()
        
        # Security Check: allow viewing if it's the recruiter's referral, or if the viewer is a manager
        is_own_referral = app_check and app_check.get('ReferringStaffID') == staff_id
        is_manager = current_user.role_type in LEADER_ROLES_IN_PORTAL

        if not (is_own_referral or is_manager):
            abort(403)

        cursor.execute("""
            SELECT ja.ApplicationID, ja.NotesByCandidate, ja.ApplicationDate, ja.NotesByStaff,
                   c.CandidateID, jo.OfferID, jo.Title as OfferTitle, comp.CompanyName
            FROM JobApplications ja
            JOIN Candidates c ON ja.CandidateID = c.CandidateID
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies comp ON jo.CompanyID = comp.CompanyID
            WHERE ja.ApplicationID = %s
        """, (application_id,))
        app_info = cursor.fetchone()
        if not app_info: abort(404, "Application not found.")

        review_data['application'] = app_info
        candidate_id = app_info['CandidateID']

        cursor.execute("SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL, u.RegistrationDate FROM Candidates c JOIN Users u ON c.UserID = u.UserID WHERE c.CandidateID = %s", (candidate_id,))
        review_data['candidate_profile'] = cursor.fetchone()

        if review_data['candidate_profile'] and isinstance(review_data['candidate_profile'].get('Languages'), str):
            review_data['candidate_profile']['Languages'] = review_data['candidate_profile']['Languages'].split(',')

        cursor.execute("SELECT CVID, CVFileUrl, OriginalFileName, CVTitle FROM CandidateCVs WHERE CandidateID = %s ORDER BY IsPrimary DESC, UploadedAt DESC LIMIT 1", (candidate_id,))
        review_data['cv'] = cursor.fetchone()

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('account_manager_portal/application_review_modal.html',
                           review_data=review_data, is_recruiter_view=True)


@recruiter_bp.route('/my-referrals')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def my_referred_applications():
    """ Displays a list of all job applications submitted using the recruiter's referral code. """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id:
        flash("Your staff profile ID could not be found.", "danger")
        return redirect(url_for('.dashboard'))

    conn = get_db_connection()
    referred_applications = []
    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT ja.ApplicationID, ja.ApplicationDate, ja.Status, c.CandidateID,
                   u.FirstName, u.LastName, u.Email, u.ProfilePictureURL, jo.Title AS JobTitle, comp.CompanyName
            FROM JobApplications ja
            JOIN Candidates c ON ja.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies comp ON jo.CompanyID = comp.CompanyID
            WHERE ja.ReferringStaffID = %s
            ORDER BY ja.ApplicationDate DESC;
        """
        cursor.execute(sql, (staff_id,))
        referred_applications = cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()

    return render_template('recruiter_team_portal/my_referred_applications.html',
                           title="My Referred Applications", applications=referred_applications)


@recruiter_bp.route('/leaderboard')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def team_leaderboard():
    """ Displays a leaderboard for all active sourcing staff. """
    sort_by = request.args.get('sort_by', 'referrals_all_time')
    sql = """
        SELECT s.StaffID, u.FirstName, u.LastName, u.ProfilePictureURL, s.Role,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID) as referrals_all_time,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND Status = 'Hired') as hires_all_time,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND ApplicationDate >= DATE_FORMAT(NOW(), '%%Y-%%m-01')) as referrals_monthly,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND Status = 'Hired' AND ApplicationDate >= DATE_FORMAT(NOW(), '%%Y-%%m-01')) as hires_monthly
        FROM Staff s 
        JOIN Users u ON s.UserID = u.UserID
        WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager') AND u.IsActive = 1
    """
    if sort_by == 'hires_all_time':
        sql += " ORDER BY hires_all_time DESC, referrals_all_time DESC"; title = "Leaderboard: All-Time Hires"
    elif sort_by == 'referrals_monthly':
        sql += " ORDER BY referrals_monthly DESC, hires_monthly DESC"; title = "Leaderboard: Referrals This Month"
    elif sort_by == 'hires_monthly':
        sql += " ORDER BY hires_monthly DESC, referrals_monthly DESC"; title = "Leaderboard: Hires This Month"
    else:
        sort_by = 'referrals_all_time'; sql += " ORDER BY referrals_all_time DESC, hires_all_time DESC"; title = "Leaderboard: All-Time Referrals"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    leaderboard_data = cursor.fetchall()
    conn.close()
    return render_template('recruiter_team_portal/team_leaderboard.html',
                           title=title, leaderboard_data=leaderboard_data, current_sort=sort_by)


# --- REWRITTEN & COMPATIBLE TEAM VIEWING LOGIC ---

def _get_performance_stats(cursor, staff_id):
    """Helper to fetch hire/referral counts for a staff member."""
    cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s AND Status = 'Hired'", (staff_id,))
    hires = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s", (staff_id,))
    referrals = cursor.fetchone()['count']
    return hires, referrals

def _get_manager_context_data(cursor, user):
    """Fetches role-specific management data for the logged-in user."""
    context = {
        "teams_in_unit": [],
        "potential_team_leads": [],
        "unassigned_recruiters": [],
        "assignable_teams": []
    }
    
    if user.role_type == 'UnitManager':
        cursor.execute("""
            SELECT st.*, u.FirstName as LeadFirstName, u.LastName as LeadLastName
            FROM SourcingTeams st
            LEFT JOIN Staff s ON st.TeamLeadStaffID = s.StaffID
            LEFT JOIN Users u ON s.UserID = u.UserID
            WHERE st.UnitID = (SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s)
        """, (user.specific_role_id,))
        context['teams_in_unit'] = cursor.fetchall()
        context['assignable_teams'] = context['teams_in_unit']

        cursor.execute("""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role
            FROM Staff s 
            JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead') AND u.IsActive = 1 AND (
                s.TeamID IN (
                    SELECT TeamID FROM SourcingTeams WHERE UnitID = (
                        SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s
                    )
                ) OR s.TeamID IS NULL
            )
        """, (user.specific_role_id,))
        context['potential_team_leads'] = cursor.fetchall()
        
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role = 'SourcingRecruiter' AND s.TeamID IS NULL AND u.IsActive = 1")
        context['unassigned_recruiters'] = cursor.fetchall()

    elif user.role_type == 'SourcingTeamLead':
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role = 'SourcingRecruiter' AND s.TeamID IS NULL AND u.IsActive = 1")
        context['unassigned_recruiters'] = cursor.fetchall()
        
        cursor.execute("SELECT * FROM SourcingTeams WHERE TeamLeadStaffID = %s", (user.specific_role_id,))
        context['assignable_teams'] = cursor.fetchall()
        
    return context

@recruiter_bp.route('/my-team')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def my_team_view():
    """Acts as the main entry point for team views."""
    leader_staff_id = getattr(current_user, 'specific_role_id', None)
    leader_role = getattr(current_user, 'role_type', None)

    if not leader_staff_id or not leader_role:
        flash("Your staff profile could not be found.", "warning")
        return redirect(url_for('.dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    team_members = []
    manager_context = {}
    
    try:
        manager_context = _get_manager_context_data(cursor, current_user)
        
        if leader_role in ORG_MANAGEMENT_ROLES:
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.ProfilePictureURL, u.IsActive, su.UnitName
                FROM SourcingUnits su
                JOIN Staff s ON su.UnitManagerStaffID = s.StaffID
                JOIN Users u ON s.UserID = u.UserID
                WHERE s.ReportsToStaffID = %s AND u.IsActive = 1
            """, (leader_staff_id,))
            team_members = cursor.fetchall()
        elif leader_role == 'UnitManager':
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.ProfilePictureURL, u.IsActive, st.TeamName
                FROM SourcingTeams st
                JOIN SourcingUnits su ON st.UnitID = su.UnitID
                JOIN Staff s ON st.TeamLeadStaffID = s.StaffID
                JOIN Users u ON s.UserID = u.UserID
                WHERE su.UnitManagerStaffID = %s AND u.IsActive = 1
            """, (leader_staff_id,))
            team_members = cursor.fetchall()
        elif leader_role == 'SourcingTeamLead':
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.IsActive, u.ProfilePictureURL
                FROM Staff s JOIN Users u ON s.UserID = u.UserID
                WHERE s.TeamID = (SELECT TeamID FROM Staff WHERE StaffID = %s) AND s.StaffID != %s AND u.IsActive = 1
            """, (leader_staff_id, leader_staff_id))
            team_members = cursor.fetchall()

        for member in team_members:
            member['total_hires'], member['total_referrals'] = _get_performance_stats(cursor, member['StaffID'])
            member['direct_reports_count'] = 1 if member['Role'] in ['UnitManager', 'SourcingTeamLead'] else 0

    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/team_hierarchy_view.html',
                           title="My Team",
                           team_members=team_members,
                           current_leader=current_user,
                           breadcrumbs=[],
                           **manager_context)

@recruiter_bp.route('/team-view/<int:leader_staff_id>')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def team_view(leader_staff_id):
    """Shows the team of a specific sub-leader."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    team_members = []
    manager_context = {}
    current_leader = None

    try:
        cursor.execute("""
            SELECT s.StaffID, s.Role, u.IsActive, u.FirstName, u.LastName, u.UserID
            FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s
        """, (leader_staff_id,))
        current_leader = cursor.fetchone()
        if not current_leader:
            abort(404)

        manager_context = _get_manager_context_data(cursor, current_user)
        leader_role = current_leader['Role']

        if leader_role == 'UnitManager':
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.IsActive, u.ProfilePictureURL, st.TeamName
                FROM SourcingTeams st
                JOIN SourcingUnits su ON st.UnitID = su.UnitID
                JOIN Staff s ON st.TeamLeadStaffID = s.StaffID
                JOIN Users u ON s.UserID = u.UserID
                WHERE su.UnitManagerStaffID = %s AND u.IsActive = 1
            """, (leader_staff_id,))
            team_members = cursor.fetchall()
        elif leader_role == 'SourcingTeamLead':
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.IsActive, u.ProfilePictureURL
                FROM Staff s
                JOIN Users u ON s.UserID = u.UserID
                WHERE s.TeamID = (SELECT TeamID FROM Staff WHERE StaffID = %s) AND s.StaffID != %s AND u.IsActive = 1
            """, (leader_staff_id, leader_staff_id))
            team_members = cursor.fetchall()
        
        for member in team_members:
            member['total_hires'], member['total_referrals'] = _get_performance_stats(cursor, member['StaffID'])
            member['direct_reports_count'] = 1 if member['Role'] in ['UnitManager', 'SourcingTeamLead'] else 0

    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    breadcrumbs = [
        {'name': 'My Team', 'url': url_for('.my_team_view')},
        {'name': f"{current_leader['FirstName']} {current_leader['LastName']}", 'url': None}
    ]
    
    return render_template('recruiter_team_portal/team_hierarchy_view.html',
                           title=f"Team: {current_leader['FirstName']} {current_leader['LastName']}",
                           team_members=team_members, 
                           current_leader=current_leader,
                           breadcrumbs=breadcrumbs,
                           **manager_context)

@recruiter_bp.route('/profile/<int:staff_id_viewing>')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def view_recruiter_profile(staff_id_viewing):
    """
    Displays a dedicated performance and management profile for a member of the sourcing division.
    """
    viewer_staff_id = getattr(current_user, 'specific_role_id', None)
    profile_data = {}
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT s.StaffID, u.IsActive, u.UserID, u.FirstName, u.LastName, u.ProfilePictureURL, u.Email, u.RegistrationDate,
                   s.Role, s.ReportsToStaffID, s.TotalPoints, s.ReferralCode
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.StaffID = %s
        """, (staff_id_viewing,))
        profile_info = cursor.fetchone()
        if not profile_info:
            abort(404, "Staff member not found.")
        profile_data['info'] = profile_info

        is_manager = (profile_info['ReportsToStaffID'] == viewer_staff_id)
        is_top_level_manager = current_user.role_type in ['HeadUnitManager', 'CEO', 'Founder']
        is_own_profile = (profile_info['StaffID'] == viewer_staff_id)
        if not (is_manager or is_top_level_manager or is_own_profile):
            abort(403)

        kpis = {}
        kpis['hires_all_time'], kpis['referrals_all_time'] = _get_performance_stats(cursor, staff_id_viewing)
        profile_data['kpis'] = kpis

        cursor.execute("""
            SELECT ja.ApplicationID, ja.Status, u.FirstName, u.LastName, jo.Title as JobTitle
            FROM JobApplications ja
            JOIN Candidates c ON ja.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            WHERE ja.ReferringStaffID = %s
            ORDER BY ja.ApplicationDate DESC LIMIT 10
        """, (staff_id_viewing,))
        profile_data['recent_applications'] = cursor.fetchall()

    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    
    return render_template('recruiter_team_portal/recruiter_profile.html',
                           title=f"Profile: {profile_data['info']['FirstName']}",
                           profile_data=profile_data,
                           available_roles=ASSIGNABLE_SOURCING_ROLES)

@recruiter_bp.route('/organization/units')
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def list_units():
    """ [STEP 1] A central hub for managing Units and assigning their managers. """
    # [NEW] Add a filter to show active or all units
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = """
            SELECT su.*, u.FirstName, u.LastName
            FROM SourcingUnits su
            LEFT JOIN Staff s ON su.UnitManagerStaffID = s.StaffID
            LEFT JOIN Users u ON s.UserID = u.UserID
        """
        if not show_all:
            sql += " WHERE su.IsActive = 1" # Default to showing only active units
            
        sql += " ORDER BY su.IsActive DESC, su.UnitName"
        
        cursor.execute(sql)
        units = cursor.fetchall()
        # ... (rest of the function is the same)
        cursor.execute("""
            SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName, s.Role
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role IN ('SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager') AND u.IsActive = 1
        """)
        potential_managers = cursor.fetchall()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/list_units.html',
                           title="Organization Management: Units",
                           units=units,
                           potential_managers=potential_managers,
                           show_all=show_all) # Pass show_all to the template


@recruiter_bp.route('/organization/unit/<int:unit_id>')
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def manage_unit(unit_id):
    """ [STEP 2] Manages a specific Unit, including its teams. """
    # [NEW] Add a filter to show active or all teams
    show_all = request.args.get('show_all', 'false').lower() == 'true'

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM SourcingUnits WHERE UnitID = %s", (unit_id,))
        unit = cursor.fetchone()
        if not unit:
            abort(404, "Unit not found.")

        team_sql = """
            SELECT st.*, lead_user.FirstName as LeadFirstName, lead_user.LastName as LeadLastName
            FROM SourcingTeams st
            LEFT JOIN Staff lead_staff ON st.TeamLeadStaffID = lead_staff.StaffID
            LEFT JOIN Users lead_user ON lead_staff.UserID = lead_user.UserID
            WHERE st.UnitID = %s
        """
        params = [unit_id]
        
        if not show_all:
            team_sql += " AND st.IsActive = 1" # Default to showing only active teams

        team_sql += " ORDER BY st.IsActive DESC, st.TeamName"
        
        cursor.execute(team_sql, tuple(params))
        teams_in_unit = cursor.fetchall()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/manage_unit.html',
                           title=f"Manage Unit: {unit['UnitName']}",
                           unit=unit,
                           teams_in_unit=teams_in_unit,
                           show_all=show_all) # Pass show_all to the template


@recruiter_bp.route('/organization/team/<int:team_id>')
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def manage_team(team_id):
    """ [STEP 3] Manages a specific Team: assigning lead and recruiters. """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT st.*, lead_user.FirstName as LeadFirstName, lead_user.LastName as LeadLastName, su.UnitName
            FROM SourcingTeams st
            LEFT JOIN Staff lead_staff ON st.TeamLeadStaffID = lead_staff.StaffID
            LEFT JOIN Users lead_user ON lead_staff.UserID = lead_user.UserID
            LEFT JOIN SourcingUnits su ON st.UnitID = su.UnitID
            WHERE st.TeamID = %s
        """, (team_id,))
        team = cursor.fetchone()
        if not team:
            abort(404, "Team not found.")

        cursor.execute("""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.TeamID = %s AND u.IsActive = 1
            ORDER BY s.Role, u.FirstName
        """, (team_id,))
        team_members = cursor.fetchall()

        cursor.execute("""
            SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role IN ('SourcingTeamLead', 'SourcingRecruiter') AND u.IsActive = 1
        """)
        potential_team_leads = cursor.fetchall()
        
        cursor.execute("""
            SELECT s.StaffID, u.FirstName, u.LastName
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role = 'SourcingRecruiter' AND s.TeamID IS NULL AND u.IsActive = 1
        """)
        unassigned_recruiters = cursor.fetchall()

    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/manage_team.html',
                           title=f"Manage Team: {team['TeamName']}",
                           team=team,
                           team_members=team_members,
                           potential_team_leads=potential_team_leads,
                           unassigned_recruiters=unassigned_recruiters)



@recruiter_bp.route('/organization/create-unit', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def create_unit():
    unit_name = request.form.get('unit_name')
    if not unit_name:
        flash("Unit Name is required.", "danger")
        return redirect(url_for('.organization_management'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO SourcingUnits (UnitName) VALUES (%s)", (unit_name,))
        conn.commit()
        flash(f"Unit '{unit_name}' created successfully.", "success")
    except Exception as e:
        flash(f"Error creating unit: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('.organization_management'))


@recruiter_bp.route('/organization/create-team', methods=['POST'])
@login_required_with_role(UNIT_AND_ORG_MANAGEMENT_ROLES)
def create_team():
    """
    Creates a new team and assigns it to the specified unit.
    This corrected version ALWAYS uses the unit_id from the form.
    """
    team_name = request.form.get('team_name')
    unit_id = request.form.get('unit_id')

    # Validate that we received both required pieces of data from the form.
    if not team_name or not unit_id:
        flash("A Team Name and Unit context are required to create a team.", "danger")
        return redirect(url_for('.list_units')) # Safe fallback

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Directly insert the team with the provided unit_id. This is the key fix.
        cursor.execute("INSERT INTO SourcingTeams (TeamName, UnitID) VALUES (%s, %s)", (team_name, unit_id))
        
        conn.commit()
        flash(f"Team '{team_name}' was created successfully.", "success")
    except Exception as e:
        current_app.logger.error(f"Error creating team '{team_name}' for unit {unit_id}: {e}")
        flash(f"An error occurred while creating the team: {e}", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()

    # Redirect the user back to the "Manage Unit" page they were just on.
    return redirect(url_for('.manage_unit', unit_id=unit_id))


@recruiter_bp.route('/organization/assign-unit-manager', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def assign_unit_manager():
    unit_id = request.form.get('unit_id')
    manager_staff_id = request.form.get('manager_staff_id')

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE SourcingUnits SET UnitManagerStaffID = %s WHERE UnitID = %s", (manager_staff_id, unit_id))
        cursor.execute("UPDATE Staff SET Role = 'UnitManager', TeamID = NULL, ReportsToStaffID = %s WHERE StaffID = %s", (current_user.specific_role_id, manager_staff_id))
        conn.commit()
        flash("Unit Manager assigned successfully.", "success")
    except Exception as e:
        flash(f"Error assigning manager: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('.organization_management'))


@recruiter_bp.route('/organization/assign-team-lead', methods=['POST'])
@login_required_with_role(UNIT_AND_ORG_MANAGEMENT_ROLES)
def assign_team_lead():
    team_id = request.form.get('team_id')
    lead_staff_id = request.form.get('lead_staff_id')

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        # Security check for Unit Managers (remains unchanged)
        if current_user.role_type == 'UnitManager':
            cursor.execute("SELECT su.UnitID FROM SourcingUnits su WHERE su.UnitManagerStaffID = %s", (current_user.specific_role_id,))
            manager_unit = cursor.fetchone()
            cursor.execute("SELECT st.UnitID FROM SourcingTeams st WHERE st.TeamID = %s", (team_id,))
            team_unit = cursor.fetchone()

            if not manager_unit or not team_unit or manager_unit['UnitID'] != team_unit['UnitID']:
                abort(403, "You can only assign leads to teams within your own unit.")

        # Step 1: Assign lead to the team
        cursor.execute("UPDATE SourcingTeams SET TeamLeadStaffID = %s WHERE TeamID = %s", (lead_staff_id, team_id))
        
        # Step 2: Update the staff member's role and make them part of the team they lead
        cursor.execute("UPDATE Staff SET Role = 'SourcingTeamLead', TeamID = %s WHERE StaffID = %s", (team_id, lead_staff_id))
        
        # --- [NEW LOGIC] ---
        # Step 3: Automatically set the reporting line to the Unit Manager.
        
        # First, find the UnitID and UnitManagerStaffID for the team's unit.
        cursor.execute("""
            SELECT su.UnitManagerStaffID
            FROM SourcingTeams st
            JOIN SourcingUnits su ON st.UnitID = su.UnitID
            WHERE st.TeamID = %s
        """, (team_id,))
        
        unit_info = cursor.fetchone()
        
        # If the team is in a unit and that unit has a manager...
        if unit_info and unit_info.get('UnitManagerStaffID'):
            unit_manager_staff_id = unit_info['UnitManagerStaffID']
            # ...update the new team lead to report to that unit manager.
            cursor.execute("UPDATE Staff SET ReportsToStaffID = %s WHERE StaffID = %s", (unit_manager_staff_id, lead_staff_id))
            flash("Team Lead assigned successfully and now reports to the Unit Manager.", "success")
        else:
            # If the team is not in a unit, or the unit has no manager, clear the reporting line.
            cursor.execute("UPDATE Staff SET ReportsToStaffID = NULL WHERE StaffID = %s", (lead_staff_id,))
            flash("Team Lead assigned successfully. Note: The team is not in a managed unit, so no manager was set.", "info")

        conn.commit()
        
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Error assigning team lead: {e}")
        flash(f"Error assigning team lead: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        
    return redirect(request.referrer or url_for('.organization_management'))


@recruiter_bp.route('/organization/assign-team-to-unit', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def assign_team_to_unit():
    team_id = request.form.get('team_id')
    unit_id = request.form.get('unit_id')

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Get the Unit Manager's StaffID
        cursor.execute("SELECT UnitManagerStaffID FROM SourcingUnits WHERE UnitID = %s", (unit_id,))
        unit = cursor.fetchone()
        if not unit or not unit['UnitManagerStaffID']:
            flash("Cannot assign team. The selected unit does not have a manager.", "warning")
            return redirect(url_for('.organization_management'))

        manager_staff_id = unit['UnitManagerStaffID']

        # Assign team to unit
        cursor.execute("UPDATE SourcingTeams SET UnitID = %s WHERE TeamID = %s", (unit_id, team_id))
        
        # --- [MODIFIED LOGIC] ---
        # Update the team lead to report to the unit manager ONLY IF they don't already have a manager.
        cursor.execute("""
            UPDATE Staff s
            JOIN SourcingTeams st ON s.StaffID = st.TeamLeadStaffID
            SET s.ReportsToStaffID = %s
            WHERE st.TeamID = %s AND s.ReportsToStaffID IS NULL
        """, (manager_staff_id, team_id))
        
        # Check if the row was updated. If not, it means a manager was already assigned.
        if cursor.rowcount == 0:
            flash("Team assigned to unit. The Team Lead's existing manager was preserved.", "info")
        else:
            flash("Team assigned to unit and Team Lead now reports to the Unit Manager.", "success")

        conn.commit()
    except Exception as e:
        current_app.logger.error(f"Error assigning team to unit: {e}")
        flash(f"Error assigning team to unit: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('.organization_management'))


@recruiter_bp.route('/organization/assign-recruiter-to-team', methods=['POST'])
@login_required_with_role(TEAM_ASSIGNMENT_ROLES)
def assign_recruiter_to_team():
    recruiter_staff_id = request.form.get('recruiter_staff_id')
    team_id = request.form.get('team_id')

    viewer_staff_id = getattr(current_user, 'specific_role_id', None)
    viewer_role = getattr(current_user, 'role_type', None)

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        if viewer_role == 'UnitManager':
            cursor.execute("SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s", (viewer_staff_id,))
            manager_unit = cursor.fetchone()
            cursor.execute("SELECT UnitID FROM SourcingTeams WHERE TeamID = %s", (team_id,))
            target_team_unit = cursor.fetchone()
            if not manager_unit or not target_team_unit or manager_unit['UnitID'] != target_team_unit['UnitID']:
                flash("You can only assign recruiters to teams within your unit.", "danger")
                return redirect(request.referrer or url_for('.organization_management'))

        elif viewer_role == 'SourcingTeamLead':
            cursor.execute("SELECT TeamID FROM Staff WHERE StaffID = %s", (viewer_staff_id,))
            leader_team = cursor.fetchone()
            if not leader_team or str(leader_team['TeamID']) != str(team_id):
                flash("You can only assign recruiters to your own team.", "danger")
                return redirect(request.referrer or url_for('.organization_management'))

        cursor.execute("SELECT TeamLeadStaffID FROM SourcingTeams WHERE TeamID = %s", (team_id,))
        team = cursor.fetchone()
        if not team or not team['TeamLeadStaffID']:
            flash("Cannot assign recruiter. The selected team does not have a lead.", "warning")
            return redirect(request.referrer or url_for('.organization_management'))

        team_lead_staff_id = team['TeamLeadStaffID']
        cursor.execute("UPDATE Staff SET TeamID = %s, ReportsToStaffID = %s WHERE StaffID = %s", (team_id, team_lead_staff_id, recruiter_staff_id))
        conn.commit()
        flash("Recruiter successfully assigned to team.", "success")
    except Exception as e:
        current_app.logger.error(f"Error assigning recruiter to team: {e}")
        flash(f"Error assigning recruiter: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(request.referrer or url_for('.organization_management'))


# --- [REFACTORED] STAFF ACTIVATION & STATUS MANAGEMENT ---

@recruiter_bp.route('/pending-staff')
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def list_pending_staff():
    """
    Displays a list of all staff members who are awaiting activation (u.IsActive = 0).
    These are users who have registered but not yet been activated by an admin.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    pending_staff = []
    try:
        # Fetch staff members whose corresponding user account is not yet active.
        cursor.execute("""
            SELECT u.UserID, s.StaffID, u.FirstName, u.LastName, u.Email, u.RegistrationDate, s.Role
            FROM Users u
            JOIN Staff s ON u.UserID = s.UserID
            WHERE u.IsActive = 0
            ORDER BY u.RegistrationDate ASC
        """)
        pending_staff = cursor.fetchall()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/pending_users.html',
                           title="Activate New Staff",
                           pending_users=pending_staff)


# in routes/Recruiter_Team_Portal/recruiter_routes.py

@recruiter_bp.route('/activate-staff', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def activate_staff_member():
    """
    Activates a staff member by setting IsActive = 1 in the Users table
    and can optionally set an initial role if one is provided.
    """
    staff_id = request.form.get('staff_id')
    # [MODIFIED] The initial_role is now optional.
    initial_role = request.form.get('initial_role') 

    if not staff_id:
        flash("Staff ID is missing.", "danger")
        return redirect(url_for('.list_pending_staff'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE Users u
            JOIN Staff s ON u.UserID = s.UserID
            SET u.IsActive = 1
            WHERE s.StaffID = %s
        """, (staff_id,))
        
        if cursor.rowcount == 0:
            flash("User not found.", "warning")
        else:
            # [MODIFIED] Only update the role if an initial_role was passed in the form.
            # This makes the function safe for re-activating users from the org page
            # without resetting their role.
            if initial_role:
                cursor.execute("UPDATE Staff SET Role = %s WHERE StaffID = %s", (initial_role, staff_id))
            
            conn.commit()
            flash("Staff member successfully activated.", "success")
            
    except Exception as e:
        current_app.logger.error(f"Error activating staff for StaffID {staff_id}: {e}")
        flash(f"Error activating staff: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    # [MODIFIED] Redirect back to the referrer (e.g., org page or pending users page)
    return redirect(request.referrer or url_for('.list_pending_staff'))


@recruiter_bp.route('/organization/deactivate-staff', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def deactivate_staff():
    """
    [NEW] Deactivates a staff member's account by setting IsActive = 0 in the Users table.
    This will also un-assign them from any teams or reporting lines.
    """
    staff_id = request.form.get('staff_id')
    if not staff_id:
        flash("Staff ID is missing.", "danger")
        return redirect(url_for('.organization_management'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Step 1: Deactivate the user in the Users table.
        cursor.execute("""
            UPDATE Users u
            JOIN Staff s ON u.UserID = s.UserID
            SET u.IsActive = 0
            WHERE s.StaffID = %s
        """, (staff_id,))

        # Step 2: Clear their team and reporting assignments.
        cursor.execute("""
            UPDATE Staff SET TeamID = NULL, ReportsToStaffID = NULL
            WHERE StaffID = %s
        """, (staff_id,))

        conn.commit()
        flash("Staff member has been deactivated.", "success")
    except Exception as e:
        current_app.logger.error(f"Error deactivating staff for StaffID {staff_id}: {e}")
        flash(f"Error deactivating staff member: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(request.referrer or url_for('.organization_management'))

@recruiter_bp.route('/profile/change-role', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def change_staff_role():
    """
    Updates the role of a specified staff member.
    """
    staff_id_to_change = request.form.get('staff_id')
    new_role = request.form.get('new_role')

    if not staff_id_to_change or not new_role:
        flash("Staff ID or new role is missing.", "danger")
        return redirect(url_for('.organization_management'))

    if new_role not in ASSIGNABLE_SOURCING_ROLES:
        flash("Invalid role selected.", "danger")
        return redirect(url_for('.view_recruiter_profile', staff_id_viewing=staff_id_to_change))
        
    if str(staff_id_to_change) == str(getattr(current_user, 'specific_role_id', '')):
        flash("You cannot change your own role from this page.", "warning")
        return redirect(url_for('.view_recruiter_profile', staff_id_viewing=staff_id_to_change))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Staff SET Role = %s WHERE StaffID = %s", (new_role, staff_id_to_change))
        conn.commit()
        flash(f"Role successfully updated to '{new_role}'. Any necessary team or unit re-assignments should be done on the Organization Management page.", "success")
    except Exception as e:
        current_app.logger.error(f"Error changing role for StaffID {staff_id_to_change}: {e}")
        flash(f"Error updating role: {e}", "danger")
    finally:
        if conn: conn.close()

    return redirect(url_for('.view_recruiter_profile', staff_id_viewing=staff_id_to_change))


@recruiter_bp.route('/manage-recruiters')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def manage_recruiters():
    """
    Provides a searchable and filterable list of all staff in the sourcing division.
    """
    search_query = request.args.get('search', '').strip()
    filter_role = request.args.get('role', '')
    filter_status = request.args.get('status', '') # expecting 'active' or 'inactive'

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    recruiters = []
    
    try:
        role_placeholders = ', '.join(['%s'] * len(MANAGEABLE_RECRUITER_ROLES))
        
        sql = f"""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.IsActive, u.ProfilePictureURL,
                   team_info.TeamName, team_info.UnitName
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            LEFT JOIN (
                SELECT t.TeamID, t.TeamName, su.UnitName
                FROM SourcingTeams t
                LEFT JOIN SourcingUnits su ON t.UnitID = su.UnitID
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
            
        if filter_status.lower() == 'active':
            sql += " AND u.IsActive = 1"
        elif filter_status.lower() == 'inactive':
            sql += " AND u.IsActive = 0"
            
        sql += " ORDER BY u.FirstName, u.LastName"

        cursor.execute(sql, tuple(params))
        recruiters = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error fetching recruiters list: {e}", exc_info=True)
        flash("Could not load the list of recruiters.", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/manage_recruiters.html',
                           title="Manage Recruiters",
                           recruiters=recruiters,
                           search_query=search_query,
                           filter_role=filter_role,
                           filter_status=filter_status,
                           available_roles=MANAGEABLE_RECRUITER_ROLES)
    
@recruiter_bp.route('/announcements')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def announcements_history():
    """
    Displays a full, searchable, and filterable history of all system announcements
    relevant to the recruiter portal audience.
    """
    search_query = request.args.get('search', '').strip()
    filter_priority = request.args.get('priority', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    all_announcements = []
    
    try:
        sql = """
            SELECT Title, Content, CreatedAt, Priority, Audience
            FROM SystemAnnouncements
            WHERE IsActive = 1
        """
        params = []

        if search_query:
            sql += " AND (Title LIKE %s OR Content LIKE %s)"
            like_query = f"%{search_query}%"
            params.extend([like_query, like_query])
        
        if filter_priority:
            sql += " AND Priority = %s"
            params.append(filter_priority)
            
        sql += " ORDER BY CreatedAt DESC"

        cursor.execute(sql, tuple(params))
        all_announcements = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error fetching announcements history: {e}", exc_info=True)
        flash("Could not load the announcements history.", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/announcements_history.html',
                           title="Announcements History",
                           announcements=all_announcements,
                           search_query=search_query,
                           filter_priority=filter_priority)
    
@recruiter_bp.route('/organization/unit/<int:unit_id>/deactivate', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def deactivate_unit(unit_id):
    """
    Deactivates a Sourcing Unit and all associated teams.
    Also un-assigns the unit manager and all team leads/members.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Un-assign the manager from the unit
        cursor.execute("UPDATE SourcingUnits SET UnitManagerStaffID = NULL, IsActive = 0 WHERE UnitID = %s", (unit_id,))

        # 2. Get all teams within this unit
        cursor.execute("SELECT TeamID FROM SourcingTeams WHERE UnitID = %s", (unit_id,))
        teams_in_unit = cursor.fetchall()
        team_ids = [team['TeamID'] for team in teams_in_unit]

        if team_ids:
            placeholders = ', '.join(['%s'] * len(team_ids))
            
            # 3. Deactivate all teams in the unit and un-assign their leads
            cursor.execute(f"UPDATE SourcingTeams SET TeamLeadStaffID = NULL, IsActive = 0 WHERE TeamID IN ({placeholders})", tuple(team_ids))

            # 4. Un-assign all staff members from these teams
            cursor.execute(f"UPDATE Staff SET TeamID = NULL, ReportsToStaffID = NULL WHERE TeamID IN ({placeholders})", tuple(team_ids))

        conn.commit()
        flash("Unit has been deactivated. All associated teams and staff assignments have been cleared.", "success")
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Error deactivating unit {unit_id}: {e}", exc_info=True)
        flash(f"Error deactivating unit: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    
    return redirect(url_for('.list_units'))


@recruiter_bp.route('/organization/team/<int:team_id>/deactivate', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def deactivate_team(team_id):
    """
    Deactivates a Sourcing Team.
    Also un-assigns the team lead and all members.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Deactivate the team and un-assign its lead
        cursor.execute("UPDATE SourcingTeams SET TeamLeadStaffID = NULL, IsActive = 0 WHERE TeamID = %s", (team_id,))

        # 2. Un-assign all staff members from this team
        cursor.execute("UPDATE Staff SET TeamID = NULL, ReportsToStaffID = NULL WHERE TeamID = %s", (team_id,))
        
        conn.commit()
        flash("Team has been deactivated. All staff assignments have been cleared.", "success")
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Error deactivating team {team_id}: {e}", exc_info=True)
        flash(f"Error deactivating team: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    
    # Redirect back to the referrer (the unit management page)
    return redirect(request.referrer or url_for('.list_units'))

# [NEW] SELF-SERVICE PROFILE MANAGEMENT ROUTE
@recruiter_bp.route('/my-profile', methods=['GET', 'POST'])
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def my_profile():
    """
    Allows a logged-in user to view and manage their own profile details,
    change their password, and generate their referral code.
    """
    user_id = current_user.id
    staff_id = current_user.specific_role_id
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # --- HANDLE FORM SUBMISSIONS ---
    if request.method == 'POST':
        action = request.form.get('action')

        # --- Action 1: Update Personal Details ---
        if action == 'update_details':
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            phone_number = request.form.get('phone_number')
            
            # Handle profile picture upload
            profile_pic_url = current_user.profile_picture_url
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file.filename != '':
                    # Ensure the filename is safe
                    filename = secure_filename(f"user_{user_id}_{file.filename}")
                    # Define the path to save the image
                    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profile_pics')
                    os.makedirs(upload_path, exist_ok=True) # Create directory if it doesn't exist
                    file.save(os.path.join(upload_path, filename))
                    profile_pic_url = url_for('static', filename=f'uploads/profile_pics/{filename}', _external=False)

            cursor.execute("""
                UPDATE Users 
                SET FirstName = %s, LastName = %s, Email = %s, PhoneNumber = %s, ProfilePictureURL = %s
                WHERE UserID = %s
            """, (first_name, last_name, email, phone_number, profile_pic_url, user_id))
            conn.commit()

            # Update the session object so changes are reflected immediately
            current_user.first_name = first_name
            current_user.last_name = last_name
            current_user.profile_picture_url = profile_pic_url
            flash("Your profile details have been updated successfully.", "success")
        
        # --- Action 2: Change Password ---
        elif action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            if not check_password_hash(current_user.password_hash, current_password):
                flash("Your current password was incorrect.", "danger")
            elif new_password != confirm_password:
                flash("The new passwords do not match.", "danger")
            else:
                hashed_password = generate_password_hash(new_password)
                cursor.execute("UPDATE Users SET PasswordHash = %s WHERE UserID = %s", (hashed_password, user_id))
                conn.commit()
                flash("Your password has been changed successfully.", "success")
        
        # --- Action 3: Generate Referral Code ---
        elif action == 'generate_code':
            # Check if a code already exists to prevent accidental overwrites
            cursor.execute("SELECT ReferralCode FROM Staff WHERE StaffID = %s", (staff_id,))
            existing_code = cursor.fetchone()
            if not existing_code or not existing_code['ReferralCode']:
                # Generate a unique 8-character code
                new_code = secrets.token_hex(4).upper()
                cursor.execute("UPDATE Staff SET ReferralCode = %s WHERE StaffID = %s", (new_code, staff_id))
                conn.commit()
                current_user.referral_code = new_code
                flash(f"Your new referral code has been generated: {new_code}", "success")
            else:
                flash("A referral code already exists for your account.", "info")

        cursor.close()
        conn.close()
        return redirect(url_for('.my_profile'))

    # --- HANDLE PAGE LOAD (GET REQUEST) ---
    try:
        # Fetch comprehensive user data for display
        cursor.execute("""
            SELECT u.UserID, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL,
                   s.Role, s.ReferralCode
            FROM Users u
            LEFT JOIN Staff s ON u.UserID = s.UserID
            WHERE u.UserID = %s
        """, (user_id,))
        user_data = cursor.fetchone()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    if not user_data:
        abort(404, "User profile not found.")

    return render_template('recruiter_team_portal/my_profile.html',
                           title="My Profile",
                           user_data=user_data)