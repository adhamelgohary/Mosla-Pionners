# routes/Recruiter_Team_Portal/recruiter_routes.py
from flask import Blueprint, render_template, flash, redirect, url_for, current_app, request
from flask_login import login_required, current_user
from utils.decorators import login_required_with_role # We still use this for role checks
from db import get_db_connection

# Define roles that can access this entire portal
RECRUITER_PORTAL_ROLES = [
    'SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 
    'CEO', 'OperationsManager'
]

# Define roles that are considered "Leaders" within this portal
LEADER_ROLES_IN_PORTAL = [
    'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 
    'CEO', 'OperationsManager'
]

recruiter_bp = Blueprint('recruiter_bp', __name__,
                         url_prefix='/recruiter-portal',
                         template_folder='../../../templates')

@recruiter_bp.route('/')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def dashboard():
    """
    The main dashboard for the Recruiter Portal.
    """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id:
        flash("Your staff profile could not be found.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard')) # Fallback to main staff dash

    kpis = {}
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # KPI: My Referred Applications (This Month)
        cursor.execute(
            """SELECT COUNT(ApplicationID) AS count 
               FROM JobApplications 
               WHERE ReferringStaffID = %s AND ApplicationDate >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)""",
            (staff_id,)
        )
        res = cursor.fetchone()
        kpis['my_referred_applications_month'] = res['count'] if res else 0

        # KPI: All-time referrals
        cursor.execute("SELECT COUNT(ApplicationID) AS count FROM JobApplications WHERE ReferringStaffID = %s", (staff_id,))
        res = cursor.fetchone()
        kpis['my_referred_applications_all_time'] = res['count'] if res else 0

    except Exception as e:
        current_app.logger.error(f"Error fetching recruiter dashboard for StaffID {staff_id}: {e}", exc_info=True)
        flash("Could not load all dashboard data.", "warning")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()

    return render_template('recruiter_team_portal/recruiter_dashboard.html', 
                           title="Recruiter Dashboard", 
                           kpis=kpis)


@recruiter_bp.route('/my-referrals')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def my_referred_applications():
    """
    Displays a list of all job applications that were submitted
    using the logged-in recruiter's referral code.
    (This is the function moved from team_routes.py)
    """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id:
        flash("Your staff profile ID could not be found.", "danger")
        return redirect(url_for('.dashboard'))

    conn = None
    referred_applications = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT ja.ApplicationID, ja.ApplicationDate, ja.Status, c.CandidateID,
                   u.FirstName, u.LastName, u.Email, jo.Title AS JobTitle, comp.CompanyName
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
    except Exception as e:
        current_app.logger.error(f"Error fetching referred apps for StaffID {staff_id}: {e}", exc_info=True)
        flash("An error occurred while loading your referred applications.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()
    
    return render_template('recruiter_team_portal/my_referred_applications.html',
                           title="My Referred Applications",
                           applications=referred_applications)


@recruiter_bp.route('/my-team')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def my_team_performance():
    """
    Displays team members for a logged-in leader.
    (This is the function moved from team_routes.py)
    """
    leader_staff_id = getattr(current_user, 'specific_role_id', None)
    if not leader_staff_id:
        flash("Your staff profile ID could not be found.", "warning")
        return redirect(url_for('.dashboard'))

    conn = None
    team_members = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # This query is now simpler because we know the user is a leader
        # We find everyone who reports directly to this leader
        sql = """
            SELECT 
                u.UserID, u.FirstName, u.LastName, u.ProfilePictureURL, s.Role,
                (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID) as total_referrals
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            WHERE s.ReportsToStaffID = %s
            ORDER BY u.LastName, u.FirstName
        """
        cursor.execute(sql, (leader_staff_id,))
        team_members = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching team for leader StaffID {leader_staff_id}: {e}", exc_info=True)
        flash("Could not load team information.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()
            
    return render_template('recruiter_team_portal/my_team.html',
                           title="My Team's Referrals",
                           team_members=team_members)