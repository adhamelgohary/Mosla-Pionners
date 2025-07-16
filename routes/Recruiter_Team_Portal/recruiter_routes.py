# routes/Recruiter_Team_Portal/recruiter_routes.py
from flask import Blueprint, abort, render_template, flash, redirect, url_for, current_app, request
from flask_login import login_required, current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

# Define roles that can access this entire portal
RECRUITER_PORTAL_ROLES = [
    'SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 
    'CEO', 'OperationsManager'
]

# Define roles that are considered "Leaders" within this portal and can see the "My Team" page
LEADER_ROLES_IN_PORTAL = [
    'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 'CEO', 'OperationsManager'
]

recruiter_bp = Blueprint('recruiter_bp', __name__,
                         url_prefix='/recruiter-portal',
                         template_folder='../../../templates')

@recruiter_bp.route('/')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def dashboard():
    """ The main dashboard for the Recruiter Portal. """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id:
        flash("Your staff profile could not be found.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))

    kpis = {}
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # KPI: My Referred Applications (This Calendar Month)
        cursor.execute(
            """SELECT COUNT(ApplicationID) AS count 
               FROM JobApplications 
               WHERE ReferringStaffID = %s AND ApplicationDate >= DATE_FORMAT(NOW(), '%Y-%m-01')""",
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

@recruiter_bp.route('/application/<int:application_id>/review')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def review_referred_application(application_id):
    """
    Provides a read-only view of an application's details, specifically for recruiters.
    This ensures recruiters can't perform AM actions but can see the details.
    """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)
    
    conn = get_db_connection()
    review_data = {}
    try:
        cursor = conn.cursor(dictionary=True)
        # Verify this recruiter is authorized to see this application
        cursor.execute("SELECT ReferringStaffID FROM JobApplications WHERE ApplicationID = %s", (application_id,))
        app_check = cursor.fetchone()
        if not app_check or app_check.get('ReferringStaffID') != staff_id:
            abort(403)

        # Fetch all the details for the modal
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

    # We can reuse the AM portal's modal template, but pass a flag to disable actions.
    return render_template('account_manager_portal/application_review_modal.html', 
                           review_data=review_data, 
                           is_recruiter_view=True) # Pass a flag to the template
    
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
    

# --- NEW: `my_team` logic is now moved here ---
@recruiter_bp.route('/my-team')
@login_required_with_role(LEADER_ROLES_IN_PORTAL)
def my_team_performance():
    """ Displays team members for a logged-in sourcing leader. """
    leader_staff_id = getattr(current_user, 'specific_role_id', None)
    if not leader_staff_id:
        flash("Your staff profile ID could not be found.", "warning")
        return redirect(url_for('.dashboard'))

    conn = None
    team_members = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # This query finds everyone who reports directly to this leader
        # and counts their total referrals.
        sql = """
            SELECT 
                u.UserID, u.FirstName, u.LastName, u.ProfilePictureURL, s.Role,
                (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID) as total_referrals
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            WHERE s.ReportsToStaffID = %s
            ORDER BY total_referrals DESC, u.LastName ASC
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
                           title="My Team's Referral Performance",
                           team_members=team_members)