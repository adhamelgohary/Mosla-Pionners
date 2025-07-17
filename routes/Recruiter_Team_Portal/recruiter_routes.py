# routes/Recruiter_Team_Portal/recruiter_routes.py
from flask import Blueprint, abort, render_template, flash, redirect, url_for, current_app, request, jsonify
from flask_login import login_required, current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

# All roles that can access this portal.
RECRUITER_PORTAL_ROLES = [
    'SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 
    'HeadUnitManager', 'CEO', 'Founder' # Top-level execs can also view
]

# Roles that can see a "Team" view.
LEADER_ROLES_IN_PORTAL = [
    'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 
    'HeadUnitManager', 'CEO', 'Founder'
]

# Roles that see the top-level "All Teams" view by default.
DIVISION_LEADER_ROLES = ['HeadUnitManager', 'UnitManager', 'CEO', 'Founder']

# Roles that can promote Team Leads to Unit Managers.
PROMOTION_ROLES = ['HeadUnitManager', 'CEO', 'Founder']
recruiter_bp = Blueprint('recruiter_bp', __name__,
                         url_prefix='/recruiter-portal',
                         template_folder='../../../templates')

@recruiter_bp.route('/')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def dashboard():
    """ The main dashboard for the Recruiter Portal with advanced visualizations. """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id:
        flash("Your staff profile could not be found.", "danger")
        return redirect(url_for('staff_perf_bp.list_all_staff'))

    kpis = {}
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        funnel_sql = "SELECT Status, COUNT(ApplicationID) as count FROM JobApplications WHERE ReferringStaffID = %s GROUP BY Status"
        cursor.execute(funnel_sql, (staff_id,))
        funnel_data = {row['Status']: row['count'] for row in cursor.fetchall()}
        
        kpis['funnel'] = {
            'Applied': funnel_data.get('Applied', 0) + funnel_data.get('Submitted', 0),
            'Shortlisted': funnel_data.get('Shortlisted', 0),
            'Interview Scheduled': funnel_data.get('Interview Scheduled', 0),
            'Hired': funnel_data.get('Hired', 0)
        }
        kpis['status_breakdown_for_chart'] = funnel_data
        kpis['total_referrals'] = sum(funnel_data.values())
        
        monthly_sql = """
            SELECT 
                DATE_FORMAT(ApplicationDate, '%%Y-%%m') AS month,
                COUNT(ApplicationID) as total_referrals,
                SUM(CASE WHEN Status = 'Hired' THEN 1 ELSE 0 END) as total_hires
            FROM JobApplications
            WHERE ReferringStaffID = %s AND ApplicationDate >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
            GROUP BY month ORDER BY month ASC
        """
        cursor.execute(monthly_sql, (staff_id,))
        kpis['monthly_performance'] = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching recruiter dashboard for StaffID {staff_id}: {e}", exc_info=True)
        flash("Could not load all dashboard data.", "warning")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()

    return render_template('recruiter_team_portal/recruiter_dashboard.html', 
                           title="Recruiter Dashboard", kpis=kpis)

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
        if not app_check or app_check.get('ReferringStaffID') != staff_id:
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
        WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager')
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

def _get_team_members(leader_staff_id, leader_role):
    """
    A helper function to fetch team members based on the leader's specific role.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    stats_subquery = """
        (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID) as total_referrals,
        (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND Status = 'Hired') as total_hires,
        (SELECT COUNT(*) FROM Staff WHERE ReportsToStaffID = s.StaffID) as direct_reports_count
    """
    
    # --- NEW HIERARCHICAL LOGIC ---
    # Determine which roles to look for based on the manager's role.
    roles_to_find = []
    if leader_role in ['HeadUnitManager', 'CEO', 'Founder']:
        roles_to_find = ['UnitManager']
    elif leader_role == 'UnitManager':
        roles_to_find = ['HeadSourcingTeamLead', 'SourcingTeamLead']
    elif leader_role == 'HeadSourcingTeamLead':
        roles_to_find = ['SourcingTeamLead']
    elif leader_role == 'SourcingTeamLead':
        roles_to_find = ['SourcingRecruiter']

    if roles_to_find:
        placeholders = ', '.join(['%s'] * len(roles_to_find))
        sql = f"""
            SELECT u.UserID, s.StaffID, u.FirstName, u.LastName, u.ProfilePictureURL, s.Role, {stats_subquery}
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.ReportsToStaffID = %s AND s.Role IN ({placeholders})
            ORDER BY s.Role, u.LastName
        """
        params = [leader_staff_id] + roles_to_find
    else:
        # Fallback for roles at the bottom of the hierarchy (or undefined)
        sql = f"""
            SELECT u.UserID, s.StaffID, u.FirstName, u.LastName, u.ProfilePictureURL, s.Role, {stats_subquery}
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.ReportsToStaffID = %s
            ORDER BY u.LastName
        """
        params = [leader_staff_id]
        
    cursor.execute(sql, tuple(params))
    team_members = cursor.fetchall()
    conn.close()
    return team_members

@recruiter_bp.route('/my-team')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def my_team_view():
    """ Acts as the main entry point for team views, now using role-based fetching. """
    leader_staff_id = getattr(current_user, 'specific_role_id', None)
    leader_role = getattr(current_user, 'role_type', None)

    if not leader_staff_id or not leader_role:
        flash("Your staff profile could not be found.", "warning")
        return redirect(url_for('.dashboard'))
    
    # The helper function now intelligently gets the right team members
    team_members = _get_team_members(leader_staff_id, leader_role)
    
    return render_template('recruiter_team_portal/team_hierarchy_view.html',
                           title="My Team",
                           team_members=team_members,
                           current_leader=current_user,
                           breadcrumbs=[])


@recruiter_bp.route('/team-view/<int:leader_staff_id>')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def team_view(leader_staff_id):
    """Shows the team of a specific sub-leader."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (leader_staff_id,))
    leader_info = cursor.fetchone()
    if not (current_user.role_type in DIVISION_LEADER_ROLES or (leader_info and leader_info['ReportsToStaffID'] == current_user.specific_role_id)):
        abort(403)

    cursor.execute("SELECT u.FirstName, u.LastName, s.Role, s.StaffID FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s", (leader_staff_id,))
    current_leader = cursor.fetchone()
    if not current_leader: abort(404)
    conn.close()
    
    team_members = _get_team_members(leader_staff_id)
    
    breadcrumbs = [
        {'name': 'My Team', 'url': url_for('.my_team_view')},
        {'name': f"{current_leader['FirstName']} {current_leader['LastName']}", 'url': None}
    ]
    
    return render_template('recruiter_team_portal/team_hierarchy_view.html',
                           title=f"Team: {current_leader['FirstName']} {current_leader['LastName']}",
                           team_members=team_members, current_leader=current_leader,
                           breadcrumbs=breadcrumbs)


@recruiter_bp.route('/manage/promote-to-unit-manager/<int:staff_id_to_promote>', methods=['POST'])
@login_required_with_role(PROMOTION_ROLES)
def promote_to_unit_manager(staff_id_to_promote):
    """Promotes a SourcingTeamLead to a UnitManager."""
    # Redirect back to the team view after the action
    redirect_url = url_for('.my_team_view')
    head_unit_manager_staff_id = getattr(current_user, 'specific_role_id', None)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Promote the user and assign them to report to the current HeadUnitManager
        cursor.execute("""
            UPDATE Staff SET 
                Role = 'UnitManager',
                ReportsToStaffID = %s 
            WHERE StaffID = %s AND Role = 'SourcingTeamLead'
        """, (head_unit_manager_staff_id, staff_id_to_promote))
        conn.commit()

        if cursor.rowcount > 0:
            flash("Staff member successfully promoted to Unit Manager.", "success")
        else:
            flash("Promotion failed. The user might not be a SourcingTeamLead.", "warning")

    except Exception as e:
        current_app.logger.error(f"Error promoting staff {staff_id_to_promote}: {e}", exc_info=True)
        flash(f"An error occurred: {e}", "danger")
    finally:
        if conn.is_connected(): conn.close()
        
    return redirect(redirect_url)

@recruiter_bp.route('/manage/transfer-recruiter/<int:recruiter_staff_id>', methods=['POST'])
@login_required_with_role(LEADER_ROLES_IN_PORTAL) # Any leader in the portal can transfer
def transfer_recruiter(recruiter_staff_id):
    """Transfers a SourcingRecruiter to a new SourcingTeamLead."""
    new_leader_staff_id = request.form.get('new_leader_id')
    # Redirect back to the team view of the recruiter's FORMER manager for context
    redirect_url = request.form.get('redirect_url', url_for('.my_team_view'))

    if not new_leader_staff_id:
        flash("You must select a new Team Leader.", "warning")
        return redirect(redirect_url)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Staff SET ReportsToStaffID = %s 
            WHERE StaffID = %s AND Role = 'SourcingRecruiter'
        """, (new_leader_staff_id, recruiter_staff_id))
        conn.commit()

        if cursor.rowcount > 0:
            flash("Recruiter successfully transferred to the new team.", "success")
        else:
            flash("Transfer failed. The user might not be a Sourcing Recruiter.", "warning")
            
    except Exception as e:
        current_app.logger.error(f"Error transferring staff {recruiter_staff_id}: {e}", exc_info=True)
        flash(f"An error occurred: {e}", "danger")
    finally:
        if conn.is_connected(): conn.close()
        
    return redirect(redirect_url)


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
        # 1. Fetch the profile's main info
        cursor.execute("""
            SELECT s.StaffID, u.UserID, u.FirstName, u.LastName, u.ProfilePictureURL, s.Role, s.ReportsToStaffID
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.StaffID = %s
        """, (staff_id_viewing,))
        profile_info = cursor.fetchone()
        if not profile_info:
            abort(404, "Staff member not found.")
        profile_data['info'] = profile_info

        # Security check: Make sure viewer is a manager of the person being viewed
        # (This is simplified; a full recursive check would be more robust but this covers most cases)
        is_manager = (profile_info['ReportsToStaffID'] == viewer_staff_id)
        is_top_level_manager = current_user.role_type in DIVISION_LEADER_ROLES
        if not (is_manager or is_top_level_manager or profile_info['StaffID'] == viewer_staff_id):
            abort(403)

        # 2. Fetch KPIs for the profile
        kpis = {}
        cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s", (staff_id_viewing,))
        kpis['referrals_all_time'] = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ReferringStaffID = %s AND Status = 'Hired'", (staff_id_viewing,))
        kpis['hires_all_time'] = cursor.fetchone()['count']
        profile_data['kpis'] = kpis

        # 3. Fetch recent applications
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
        
        # 4. Fetch list of other SourcingTeamLeads for the transfer modal
        cursor.execute("""
            SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) as FullName
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role = 'SourcingTeamLead' AND s.StaffID != %s
        """, (staff_id_viewing,))
        profile_data['sourcing_team_leads'] = cursor.fetchall()

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            
    return render_template('recruiter_team_portal/recruiter_profile.html',
                           title=f"Profile: {profile_data['info']['FirstName']}",
                           profile_data=profile_data)