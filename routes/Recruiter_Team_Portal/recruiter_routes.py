# routes/Recruiter_Team_Portal/recruiter_routes.py
from flask import Blueprint, abort, render_template, flash, redirect, url_for, current_app, request, jsonify
from flask_login import login_required, current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

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
    The main dashboard for the Recruiter Portal with advanced, role-aware visualizations.
    The data displayed is aggregated based on the user's role and scope.
    """
    user_staff_id = getattr(current_user, 'specific_role_id', None)
    user_role = getattr(current_user, 'role_type', None)

    if not user_staff_id:
        flash("Your staff profile could not be found.", "danger")
        return redirect(url_for('staff_perf_bp.list_all_staff'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    scoped_staff_ids = []
    dashboard_title = "My Performance"  # Default title
    
    # [FIX] Initialize kpis BEFORE the try block to prevent UnboundLocalError
    kpis = {
        'funnel': {'Applied': 0, 'Shortlisted': 0, 'Interview Scheduled': 0, 'Hired': 0},
        'status_breakdown_for_chart': {},
        'total_referrals': 0,
        'monthly_performance': []
    }

    try:
        # --- Determine the scope of StaffIDs based on the user's role ---
        if user_role in ORG_MANAGEMENT_ROLES:
            dashboard_title = "Overall Sourcing Division Performance"
            cursor.execute("""
                SELECT StaffID FROM Staff
                WHERE Role IN ('SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager') AND status = 'Active'
            """)
            scoped_staff_ids = [row['StaffID'] for row in cursor.fetchall()]

        elif user_role == 'UnitManager':
            dashboard_title = f"{current_user.first_name}'s Unit Performance"
            cursor.execute("""
                SELECT s.StaffID FROM Staff s
                JOIN SourcingTeams st ON s.TeamID = st.TeamID
                WHERE st.UnitID = (
                    SELECT su.UnitID FROM SourcingUnits su WHERE su.UnitManagerStaffID = %s
                ) AND s.status = 'Active'
            """, (user_staff_id,))
            scoped_staff_ids = [row['StaffID'] for row in cursor.fetchall()]

        elif user_role == 'SourcingTeamLead':
            dashboard_title = f"{current_user.first_name}'s Team Performance"
            cursor.execute("""
                SELECT StaffID FROM Staff WHERE TeamID = (
                    SELECT TeamID FROM Staff WHERE StaffID = %s
                ) AND status = 'Active'
            """, (user_staff_id,))
            scoped_staff_ids = [row['StaffID'] for row in cursor.fetchall()]

        # [FIX] The 'AttributeError' is now fixed by the change to the user_loader
        if not scoped_staff_ids and current_user.status == 'Active':
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
        # The log shows the original AttributeError was caught here
        current_app.logger.error(f"Error fetching recruiter dashboard for StaffID {user_staff_id}: {e}", exc_info=True)
        flash("Could not load all dashboard data.", "warning")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/recruiter_dashboard.html',
                           title=dashboard_title, kpis=kpis)

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
    """ Displays a leaderboard for all sourcing staff. """
    sort_by = request.args.get('sort_by', 'referrals_all_time')
    sql = """
        SELECT s.StaffID, u.FirstName, u.LastName, u.ProfilePictureURL, s.Role,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID) as referrals_all_time,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND Status = 'Hired') as hires_all_time,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND ApplicationDate >= DATE_FORMAT(NOW(), '%%Y-%%m-01')) as referrals_monthly,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND Status = 'Hired' AND ApplicationDate >= DATE_FORMAT(NOW(), '%%Y-%%m-01')) as hires_monthly
        FROM Staff s JOIN Users u ON s.UserID = u.UserID
        WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager') AND s.status = 'Active'
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

# --- Helper function for Unit/Team Lead context ---
def _get_manager_context_data(cursor, user):
    """Fetches role-specific management data for the logged-in user."""
    context = {
        "teams_in_unit": [],
        "potential_team_leads": [],
        "unassigned_recruiters": [],
        "assignable_teams": []
    }
    
    if user.role_type == 'UnitManager':
        # Fetch teams within this manager's unit for the management panel
        cursor.execute("""
            SELECT st.*, u.FirstName as LeadFirstName, u.LastName as LeadLastName
            FROM SourcingTeams st
            LEFT JOIN Staff s ON st.TeamLeadStaffID = s.StaffID
            LEFT JOIN Users u ON s.UserID = u.UserID
            WHERE st.UnitID = (SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s)
        """, (user.specific_role_id,))
        context['teams_in_unit'] = cursor.fetchall()
        context['assignable_teams'] = context['teams_in_unit']

        # [MODIFIED QUERY] Fetch potential team leads (only SourcingRecruiter or SourcingTeamLead roles) within the unit's scope.
        cursor.execute("""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead') AND s.status = 'Active' AND (
                s.TeamID IN (
                    SELECT TeamID FROM SourcingTeams WHERE UnitID = (
                        SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s
                    )
                ) OR s.TeamID IS NULL
            )
        """, (user.specific_role_id,))
        context['potential_team_leads'] = cursor.fetchall()
        
        # Fetch all unassigned recruiters
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role = 'SourcingRecruiter' AND s.TeamID IS NULL AND s.status = 'Active'")
        context['unassigned_recruiters'] = cursor.fetchall()

    elif user.role_type == 'SourcingTeamLead':
        # Fetch unassigned recruiters for the assignment panel
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role = 'SourcingRecruiter' AND s.TeamID IS NULL AND s.status = 'Active'")
        context['unassigned_recruiters'] = cursor.fetchall()
        
        # For a Team Lead, the only assignable team is their own
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
        # Get the context data for the logged-in user's role
        manager_context = _get_manager_context_data(cursor, current_user)
        
        # Get the list of direct reports for the current page's subject (in this case, the logged-in user)
        if leader_role in ORG_MANAGEMENT_ROLES:
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.ProfilePictureURL, s.status, su.UnitName
                FROM SourcingUnits su
                JOIN Staff s ON su.UnitManagerStaffID = s.StaffID
                JOIN Users u ON s.UserID = u.UserID
                WHERE s.ReportsToStaffID = %s
            """, (leader_staff_id,))
            team_members = cursor.fetchall()
        elif leader_role == 'UnitManager':
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.ProfilePictureURL, s.status, st.TeamName
                FROM SourcingTeams st
                JOIN SourcingUnits su ON st.UnitID = su.UnitID
                JOIN Staff s ON st.TeamLeadStaffID = s.StaffID
                JOIN Users u ON s.UserID = u.UserID
                WHERE su.UnitManagerStaffID = %s
            """, (leader_staff_id,))
            team_members = cursor.fetchall()
        elif leader_role == 'SourcingTeamLead':
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, s.status, u.ProfilePictureURL
                FROM Staff s JOIN Users u ON s.UserID = u.UserID
                WHERE s.TeamID = (SELECT TeamID FROM Staff WHERE StaffID = %s) AND s.StaffID != %s
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
                           **manager_context) # Unpack all management data into the template

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
        # Fetch details of the leader whose team we are viewing
        cursor.execute("""
            SELECT s.StaffID, s.Role, s.status, u.FirstName, u.LastName, u.UserID
            FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s
        """, (leader_staff_id,))
        current_leader = cursor.fetchone()
        if not current_leader:
            abort(404)

        # Get the management context for the LOGGED-IN user
        manager_context = _get_manager_context_data(cursor, current_user)

        # Get the list of direct reports for the page's subject (the sub-leader)
        leader_role = current_leader['Role']
        if leader_role == 'UnitManager':
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, s.status, u.ProfilePictureURL, st.TeamName
                FROM SourcingTeams st
                JOIN SourcingUnits su ON st.UnitID = su.UnitID
                JOIN Staff s ON st.TeamLeadStaffID = s.StaffID
                JOIN Users u ON s.UserID = u.UserID
                WHERE su.UnitManagerStaffID = %s
            """, (leader_staff_id,))
            team_members = cursor.fetchall()
        elif leader_role == 'SourcingTeamLead':
            cursor.execute("""
                SELECT s.StaffID, u.FirstName, u.LastName, s.Role, s.status, u.ProfilePictureURL
                FROM Staff s
                JOIN Users u ON s.UserID = u.UserID
                WHERE s.TeamID = (SELECT TeamID FROM Staff WHERE StaffID = %s) AND s.StaffID != %s
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
                           **manager_context) # Unpack all management data into the template

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
        # 1. Fetch the profile's main info (no changes to this query)
        cursor.execute("""
            SELECT s.StaffID, s.status, u.UserID, u.FirstName, u.LastName, u.ProfilePictureURL, u.Email, u.RegistrationDate,
                   s.Role, s.ReportsToStaffID, s.TotalPoints, s.ReferralCode
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.StaffID = %s
        """, (staff_id_viewing,))
        profile_info = cursor.fetchone()
        if not profile_info:
            abort(404, "Staff member not found.")
        profile_data['info'] = profile_info

        # Security check (no changes needed here)
        is_manager = (profile_info['ReportsToStaffID'] == viewer_staff_id)
        is_top_level_manager = current_user.role_type in ['HeadUnitManager', 'CEO', 'Founder']
        is_own_profile = (profile_info['StaffID'] == viewer_staff_id)
        if not (is_manager or is_top_level_manager or is_own_profile):
            abort(403)

        # 2. Fetch KPIs for the profile (no changes needed)
        kpis = {}
        kpis['hires_all_time'], kpis['referrals_all_time'] = _get_performance_stats(cursor, staff_id_viewing)
        profile_data['kpis'] = kpis

        # 3. Fetch recent applications (no changes needed)
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
    
    # [MODIFIED] Pass the list of assignable roles to the template
    return render_template('recruiter_team_portal/recruiter_profile.html',
                           title=f"Profile: {profile_data['info']['FirstName']}",
                           profile_data=profile_data,
                           available_roles=ASSIGNABLE_SOURCING_ROLES) # <-- ADD THIS

@recruiter_bp.route('/organization')
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def organization_management():
    """A central hub for managing Units, Teams, their assignments, and staff status."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch all Units with their manager's info (No change)
        cursor.execute("""
            SELECT su.*, u.FirstName, u.LastName
            FROM SourcingUnits su
            LEFT JOIN Staff s ON su.UnitManagerStaffID = s.StaffID
            LEFT JOIN Users u ON s.UserID = u.UserID
            ORDER BY su.UnitName
        """)
        units = cursor.fetchall()

        # Fetch all Teams with their lead's and unit's info (No change)
        cursor.execute("""
            SELECT st.*,
                   lead_user.FirstName as LeadFirstName, lead_user.LastName as LeadLastName,
                   su.UnitName
            FROM SourcingTeams st
            LEFT JOIN Staff lead_staff ON st.TeamLeadStaffID = lead_staff.StaffID
            LEFT JOIN Users lead_user ON lead_staff.UserID = lead_user.UserID
            LEFT JOIN SourcingUnits su ON st.UnitID = su.UnitID
            ORDER BY su.UnitName, st.TeamName
        """)
        teams = cursor.fetchall()
        
        # Fetch ALL Sourcing staff for a comprehensive management view (No change)
        cursor.execute("""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role, s.status, t.TeamName
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            LEFT JOIN SourcingTeams t ON s.TeamID = t.TeamID
            WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'HeadSourcingTeamLead')
            ORDER BY s.status, u.LastName, u.FirstName
        """)
        all_staff = cursor.fetchall()

        # Fetch potential Unit Managers (Active TeamLeads and above) (No change)
        cursor.execute("""
            SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName, s.Role
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role IN ('SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager') AND s.status = 'Active'
        """)
        potential_managers = cursor.fetchall()

        # [MODIFIED QUERY] Fetch potential Team Leads (only SourcingRecruiter or SourcingTeamLead roles)
        cursor.execute("""
            SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName, s.Role
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role IN ('SourcingTeamLead', 'SourcingRecruiter') AND s.status = 'Active'
        """)
        potential_team_leads = cursor.fetchall()

        # Fetch unassigned recruiters to be placed into teams (No change)
        cursor.execute("""
            SELECT s.StaffID, u.FirstName, u.LastName
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role = 'SourcingRecruiter' AND s.TeamID IS NULL AND s.status = 'Active'
        """)
        unassigned_recruiters = cursor.fetchall()

    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/organization_management.html',
                           title="Organization Structure",
                           units=units,
                           teams=teams,
                           all_staff=all_staff,
                           potential_managers=potential_managers,
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
    team_name = request.form.get('team_name')
    if not team_name:
        flash("Team Name is required.", "danger")
        return redirect(request.referrer or url_for('.organization_management'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # If a Unit Manager is creating a team, auto-assign it to their unit
        if current_user.role_type == 'UnitManager':
            cursor.execute("SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s", (current_user.specific_role_id,))
            unit = cursor.fetchone()
            if not unit:
                flash("Could not find your associated unit. Action denied.", "danger")
                return redirect(url_for('.my_team_view'))

            cursor.execute("INSERT INTO SourcingTeams (TeamName, UnitID) VALUES (%s, %s)", (team_name, unit['UnitID']))
        else: # Original logic for org managers
            cursor.execute("INSERT INTO SourcingTeams (TeamName) VALUES (%s)", (team_name,))

        conn.commit()
        flash(f"Team '{team_name}' created successfully.", "success")
    except Exception as e:
        flash(f"Error creating team: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(request.referrer or url_for('.organization_management'))


@recruiter_bp.route('/organization/assign-unit-manager', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def assign_unit_manager():
    unit_id = request.form.get('unit_id')
    manager_staff_id = request.form.get('manager_staff_id')

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Assign manager to the unit
        cursor.execute("UPDATE SourcingUnits SET UnitManagerStaffID = %s WHERE UnitID = %s", (manager_staff_id, unit_id))
        # Update the staff member's role and clear their old team/reporting structure
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

        # Security check for Unit Managers
        if current_user.role_type == 'UnitManager':
            cursor.execute("SELECT su.UnitID FROM SourcingUnits su WHERE su.UnitManagerStaffID = %s", (current_user.specific_role_id,))
            manager_unit = cursor.fetchone()
            cursor.execute("SELECT st.UnitID FROM SourcingTeams st WHERE st.TeamID = %s", (team_id,))
            team_unit = cursor.fetchone()

            if not manager_unit or not team_unit or manager_unit['UnitID'] != team_unit['UnitID']:
                abort(403, "You can only assign leads to teams within your own unit.")

        # Assign lead to the team
        cursor.execute("UPDATE SourcingTeams SET TeamLeadStaffID = %s WHERE TeamID = %s", (lead_staff_id, team_id))
        # Update the staff member's role and make them part of the team they lead
        cursor.execute("UPDATE Staff SET Role = 'SourcingTeamLead', TeamID = %s WHERE StaffID = %s", (team_id, lead_staff_id))
        conn.commit()
        flash("Team Lead assigned successfully.", "success")
    except Exception as e:
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
        # Update the team lead to report to the unit manager
        cursor.execute("""
            UPDATE Staff s
            JOIN SourcingTeams st ON s.StaffID = st.TeamLeadStaffID
            SET s.ReportsToStaffID = %s
            WHERE st.TeamID = %s
        """, (manager_staff_id, team_id))
        conn.commit()
        flash("Team assigned to unit successfully.", "success")
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

        # --- Security check: ensure the user has the right to assign to this specific team ---
        if viewer_role == 'UnitManager':
            # A Unit Manager can only assign to teams within their own unit.
            cursor.execute("SELECT UnitID FROM SourcingUnits WHERE UnitManagerStaffID = %s", (viewer_staff_id,))
            manager_unit = cursor.fetchone()

            cursor.execute("SELECT UnitID FROM SourcingTeams WHERE TeamID = %s", (team_id,))
            target_team_unit = cursor.fetchone()

            if not manager_unit or not target_team_unit or manager_unit['UnitID'] != target_team_unit['UnitID']:
                flash("You can only assign recruiters to teams within your unit.", "danger")
                return redirect(request.referrer or url_for('.organization_management'))

        elif viewer_role == 'SourcingTeamLead':
            # A Team Lead can only assign to their own team.
            cursor.execute("SELECT TeamID FROM Staff WHERE StaffID = %s", (viewer_staff_id,))
            leader_team = cursor.fetchone()

            if not leader_team or str(leader_team['TeamID']) != str(team_id):
                flash("You can only assign recruiters to your own team.", "danger")
                return redirect(request.referrer or url_for('.organization_management'))

        # --- Original logic continues if security checks pass ---
        # Get Team Lead's StaffID to set the reporting line
        cursor.execute("SELECT TeamLeadStaffID FROM SourcingTeams WHERE TeamID = %s", (team_id,))
        team = cursor.fetchone()
        if not team or not team['TeamLeadStaffID']:
            flash("Cannot assign recruiter. The selected team does not have a lead.", "warning")
            return redirect(request.referrer or url_for('.organization_management'))

        team_lead_staff_id = team['TeamLeadStaffID']

        # Assign the recruiter to the team and set their manager
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

# --- [MODIFIED] STAFF ACTIVATION & STATUS MANAGEMENT ---

@recruiter_bp.route('/pending-staff')
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def list_pending_staff():
    """
    [MODIFIED] Displays a list of all staff members whose status is 'Pending'.
    These are users who have registered but not yet been activated by an admin.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    pending_staff = []
    try:
        # [MODIFIED QUERY] Select staff members with 'Pending' status.
        cursor.execute("""
            SELECT u.UserID, s.StaffID, u.FirstName, u.LastName, u.Email, u.RegistrationDate, s.Role
            FROM Users u
            JOIN Staff s ON u.UserID = s.UserID
            WHERE s.status = 'Pending'
            ORDER BY u.RegistrationDate ASC
        """)
        pending_staff = cursor.fetchall()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('recruiter_team_portal/pending_users.html',
                           title="Activate New Staff",
                           pending_users=pending_staff)


@recruiter_bp.route('/activate-staff', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def activate_staff_member():
    """
    [MODIFIED] Activates a staff member by updating their status in the Staff table
    from 'Pending' to 'Active' and confirming their role.
    """
    staff_id = request.form.get('staff_id')
    initial_role = request.form.get('initial_role', 'SourcingRecruiter')

    if not staff_id:
        flash("Staff ID is missing.", "danger")
        return redirect(url_for('.list_pending_staff'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # [MODIFIED LOGIC] Update the existing staff record to 'Active'.
        cursor.execute("""
            UPDATE Staff SET status = 'Active', Role = %s
            WHERE StaffID = %s AND status = 'Pending'
        """, (initial_role, staff_id))
        
        if cursor.rowcount == 0:
            flash("Staff member not found or was already active.", "warning")
        else:
            conn.commit()
            flash("Staff member successfully activated.", "success")
            
    except Exception as e:
        current_app.logger.error(f"Error activating staff for StaffID {staff_id}: {e}")
        flash(f"Error activating staff: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for('.list_pending_staff'))


@recruiter_bp.route('/organization/manage-status', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES)
def manage_staff_status():
    """
    [NEW] A route to change a staff member's status (e.g., to 'Inactive' or 'Active').
    This is intended for use on the main organization management page.
    """
    staff_id = request.form.get('staff_id')
    new_status = request.form.get('new_status')

    if not staff_id or not new_status:
        flash("Missing required information to update status.", "danger")
        return redirect(url_for('.organization_management'))
    
    # Basic validation to ensure only allowed statuses are set
    if new_status not in ['Active', 'Inactive']:
        flash("Invalid status provided.", "danger")
        return redirect(url_for('.organization_management'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Inactivating a user could also involve un-assigning them from teams/units
        if new_status == 'Inactive':
             cursor.execute("""
                UPDATE Staff SET status = 'Inactive', TeamID = NULL, ReportsToStaffID = NULL
                WHERE StaffID = %s
            """, (staff_id,))
        else: # Activating a user
            cursor.execute("UPDATE Staff SET status = 'Active' WHERE StaffID = %s", (staff_id,))

        conn.commit()
        flash(f"Staff member status successfully updated to '{new_status}'.", "success")
    except Exception as e:
        current_app.logger.error(f"Error updating status for StaffID {staff_id}: {e}")
        flash(f"Error updating staff status: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for('.organization_management'))

@recruiter_bp.route('/profile/change-role', methods=['POST'])
@login_required_with_role(ORG_MANAGEMENT_ROLES) # Only org managers can change roles
def change_staff_role():
    """
    Updates the role of a specified staff member.
    """
    staff_id_to_change = request.form.get('staff_id')
    new_role = request.form.get('new_role')

    # --- Validation ---
    if not staff_id_to_change or not new_role:
        flash("Staff ID or new role is missing.", "danger")
        return redirect(url_for('.organization_management'))

    if new_role not in ASSIGNABLE_SOURCING_ROLES:
        flash("Invalid role selected.", "danger")
        return redirect(url_for('.view_recruiter_profile', staff_id_viewing=staff_id_to_change))
        
    # Prevent a manager from accidentally demoting themselves via this form
    if str(staff_id_to_change) == str(getattr(current_user, 'specific_role_id', '')):
        flash("You cannot change your own role from this page.", "warning")
        return redirect(url_for('.view_recruiter_profile', staff_id_viewing=staff_id_to_change))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # --- Database Update ---
        # Note: This just changes the role. Team/Unit assignments for new managers
        # must be handled separately on the organization management page.
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
    filter_status = request.args.get('status', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    recruiters = []
    
    try:
        role_placeholders = ', '.join(['%s'] * len(MANAGEABLE_RECRUITER_ROLES))
        
        # [FIX] Rewritten SQL query using a subquery to prevent JOIN multiplication
        sql = f"""
            SELECT 
                s.StaffID, 
                u.FirstName, 
                u.LastName, 
                s.Role, 
                s.status, 
                u.ProfilePictureURL,
                team_info.TeamName,
                team_info.UnitName
            FROM 
                Staff s
            JOIN 
                Users u ON s.UserID = u.UserID
            LEFT JOIN (
                SELECT 
                    t.TeamID, 
                    t.TeamName, 
                    su.UnitName
                FROM 
                    SourcingTeams t
                LEFT JOIN 
                    SourcingUnits su ON t.UnitID = su.UnitID
            ) AS team_info ON s.TeamID = team_info.TeamID
            WHERE 
                s.Role IN ({role_placeholders})
        """
        params = list(MANAGEABLE_RECRUITER_ROLES)

        # Dynamically add search and filter conditions
        if search_query:
            sql += " AND (u.FirstName LIKE %s OR u.LastName LIKE %s OR u.Email LIKE %s)"
            like_query = f"%{search_query}%"
            params.extend([like_query, like_query, like_query])
        
        if filter_role:
            sql += " AND s.Role = %s"
            params.append(filter_role)
            
        if filter_status:
            sql += " AND s.status = %s"
            params.append(filter_status)
            
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