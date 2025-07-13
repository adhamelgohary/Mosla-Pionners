# routes/Account_Manager_Portal/am_portal_routes.py
import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

# --- Roles are defined once for clarity, matching the new schema ---
AM_PORTAL_ACCESS_ROLES = ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 'CEO', 'Founder', 'OperationsManager']
STAFF_MANAGEMENT_ROLES = ['HeadAccountManager', 'CEO', 'Founder', 'OperationsManager']
MANAGEABLE_STAFF_ROLES = ['AccountManager', 'SeniorAccountManager']

account_manager_bp = Blueprint('account_manager_bp', __name__,
                               template_folder='../../../templates',
                               url_prefix='/am-portal')

# --- Helper function remains the same ---
def _is_user_authorized_for_application(staff_id, application_id):
    if not staff_id or not application_id: return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.ManagedByStaffID FROM JobApplications ja
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            WHERE ja.ApplicationID = %s
        """, (application_id,))
        result = cursor.fetchone()
        if not result or not result['ManagedByStaffID']: return False
        
        # Direct manager check
        if result['ManagedByStaffID'] == staff_id: return True

        # Hierarchical check for senior roles
        current_id_in_chain = result['ManagedByStaffID']
        for _ in range(5): # Limit recursion depth
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_id_in_chain,))
            supervisor = cursor.fetchone()
            if not supervisor or not supervisor['ReportsToStaffID']: return False
            current_id_in_chain = supervisor['ReportsToStaffID']
            if current_id_in_chain == staff_id: return True
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@account_manager_bp.route('/')
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def portal_home():
    return redirect(url_for('.dashboard'))

@account_manager_bp.route('/dashboard')
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def dashboard():
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id:
        flash("Your staff profile ID could not be found.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))

    conn = get_db_connection()
    dashboard_data = {}
    try:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT COUNT(*) as count FROM Companies WHERE ManagedByStaffID = %s", (staff_id,))
        dashboard_data['managed_companies_count'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID WHERE c.ManagedByStaffID = %s AND jo.Status = 'Open'", (staff_id,))
        dashboard_data['open_offers_count'] = cursor.fetchone()['count']
        
        # KPI UPDATED: Now counts candidates awaiting scheduling
        cursor.execute("""
            SELECT COUNT(ja.ApplicationID) as count FROM JobApplications ja 
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID 
            JOIN Companies c ON jo.CompanyID = c.CompanyID 
            WHERE c.ManagedByStaffID = %s AND ja.Status = 'Shortlisted'
        """, (staff_id,))
        dashboard_data['pending_interview_scheduling_count'] = cursor.fetchone()['count']

        cursor.execute("SELECT c.CompanyID, c.CompanyName, c.CompanyLogoURL, (SELECT COUNT(*) FROM JobOffers WHERE CompanyID = c.CompanyID AND Status = 'Open') as OpenJobs FROM Companies c WHERE ManagedByStaffID = %s ORDER BY CompanyName", (staff_id,))
        dashboard_data['managed_companies_list'] = cursor.fetchall()
        
        cursor.execute("""
            SELECT u.FirstName, u.LastName, jo.Title as JobTitle, ja.ApplicationDate, c.CandidateID, comp.CompanyName 
            FROM JobApplications ja 
            JOIN Candidates c ON ja.CandidateID = c.CandidateID 
            JOIN Users u ON c.UserID = u.UserID 
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID 
            JOIN Companies comp ON jo.CompanyID = comp.CompanyID 
            WHERE comp.ManagedByStaffID = %s AND ja.Status IN ('Applied', 'Submitted') 
            ORDER BY ja.ApplicationDate DESC LIMIT 5
        """, (staff_id,))
        dashboard_data['recent_applicants'] = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error building AM dashboard for StaffID {staff_id}: {e}", exc_info=True)
        flash("An error occurred while loading your dashboard data.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    return render_template('account_manager_portal/dashboard.html', title="Account Manager Dashboard", dashboard_data=dashboard_data)

# --- NEW INTERVIEW PIPELINE PAGE ---
@account_manager_bp.route('/interview-pipeline')
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def interview_pipeline():
    """Displays a list of all shortlisted and scheduled candidates for the AM's companies."""
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id:
        flash("Your staff profile ID could not be found.", "danger")
        return redirect(url_for('.dashboard'))

    conn = get_db_connection()
    pipeline_apps = []
    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                ja.ApplicationID, ja.ApplicationDate, ja.Status,
                c.CandidateID, u.FirstName, u.LastName,
                jo.Title as OfferTitle,
                comp.CompanyName,
                i.InterviewID, i.ScheduledDateTime, i.Status as InterviewStatus
            FROM JobApplications ja
            JOIN Candidates c ON ja.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies comp ON jo.CompanyID = comp.CompanyID
            LEFT JOIN Interviews i ON ja.ApplicationID = i.ApplicationID
            WHERE ja.Status IN ('Shortlisted', 'Interview Scheduled')
              AND comp.ManagedByStaffID = %s
            ORDER BY 
                CASE WHEN ja.Status = 'Shortlisted' THEN 0 ELSE 1 END ASC,
                i.ScheduledDateTime ASC,
                ja.ApplicationDate DESC;
        """
        cursor.execute(sql, (staff_id,))
        pipeline_apps = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching interview pipeline for StaffID {staff_id}: {e}", exc_info=True)
        flash("An error occurred while loading your interview pipeline.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()
            
    return render_template('account_manager_portal/interview_pipeline.html',
                           title="Interview Pipeline",
                           pipeline_apps=pipeline_apps)

@account_manager_bp.route('/my-staff')
@login_required_with_role(STAFF_MANAGEMENT_ROLES)
def my_staff():
    conn = get_db_connection()
    staff_list = []
    try:
        cursor = conn.cursor(dictionary=True)
        placeholders = ', '.join(['%s'] * len(MANAGEABLE_STAFF_ROLES))
        query = f"""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role, u.ProfilePictureURL,
                   (SELECT COUNT(*) FROM Companies WHERE ManagedByStaffID = s.StaffID) AS AssignedCompanyCount
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role IN ({placeholders}) AND u.IsActive = 1
            ORDER BY u.LastName, u.FirstName
        """
        cursor.execute(query, tuple(MANAGEABLE_STAFF_ROLES))
        staff_list = cursor.fetchall()
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('account_manager_portal/my_staff.html', title="My Staff - Account Managers", staff_list=staff_list)

@account_manager_bp.route('/my-portfolio')
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def my_portfolio():
    if not hasattr(current_user, 'specific_role_id'):
        flash("Your staff profile ID could not be found.", "danger")
        return redirect(url_for('.dashboard'))
    return redirect(url_for('.view_manager_portfolio', manager_staff_id=current_user.specific_role_id))

@account_manager_bp.route('/portfolio/<int:manager_staff_id>')
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def view_manager_portfolio(manager_staff_id):
    is_own_portfolio = hasattr(current_user, 'specific_role_id') and current_user.specific_role_id == manager_staff_id
    if not is_own_portfolio and current_user.role_type not in ['HeadAccountManager', 'CEO', 'OperationsManager', 'Founder']:
        abort(403, "You are not authorized to view this portfolio.")
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT s.StaffID, u.FirstName, u.LastName, s.Role FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.StaffID = %s", (manager_staff_id,))
        manager_details = cursor.fetchone()
        if not manager_details: abort(404, "Account Manager not found.")
        cursor.execute("SELECT CompanyID, CompanyName, Industry FROM Companies WHERE ManagedByStaffID = %s ORDER BY CompanyName", (manager_staff_id,))
        managed_companies = cursor.fetchall()
        companies_with_data = []
        for company in managed_companies:
            company['job_offers'] = []
            cursor.execute("SELECT OfferID, Title, Status, (SELECT COUNT(*) FROM JobApplications WHERE OfferID = jo.OfferID AND Status IN ('Applied', 'Submitted')) as NewApplicantCount FROM JobOffers jo WHERE CompanyID = %s ORDER BY Status, Title", (company['CompanyID'],))
            company['job_offers'] = cursor.fetchall()
            companies_with_data.append(company)
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('account_manager_portal/portfolio_detailed.html', title=f"Portfolio: {manager_details['FirstName']} {manager_details['LastName']}", manager=manager_details, companies_data=companies_with_data)

@account_manager_bp.route('/application/<int:application_id>/update', methods=['POST'])
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def update_application_status(application_id):
    action = request.form.get('action')
    manager_staff_id = request.form.get('manager_staff_id')
    company_id_for_redirect = request.form.get('company_id')
    offer_id_for_redirect = request.form.get('offer_id')
    feedback_notes = request.form.get('feedback_notes', '').strip()
    if not all([action, manager_staff_id]):
        flash("Invalid request. Missing action or manager ID.", "danger")
        return redirect(url_for('.dashboard'))
    if not _is_user_authorized_for_application(current_user.specific_role_id, application_id): abort(403)
    new_status = {'approve': 'Shortlisted', 'reject': 'Rejected'}.get(action)
    if new_status:
        conn = get_db_connection()
        try:
            conn.start_transaction()
            cursor = conn.cursor()
            sql = "UPDATE JobApplications SET Status = %s, NotesByStaff = CONCAT(COALESCE(NotesByStaff, ''), %s) WHERE ApplicationID = %s"
            notes_to_add = f"\n\n--- {new_status} by {current_user.first_name} on {datetime.date.today().strftime('%Y-%m-%d')} ---\n{feedback_notes}"
            cursor.execute(sql, (new_status, notes_to_add, application_id))
            conn.commit()
            flash(f"Application status updated to '{new_status}'.", "success")
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"DB error updating app status for AppID {application_id}: {e}", exc_info=True)
            flash("A database error occurred.", "danger")
        finally:
            if conn and conn.is_connected(): conn.close()
    else: flash("Unknown action specified.", "danger")
    if offer_id_for_redirect:
        return redirect(url_for('.view_offer_applicants', offer_id=offer_id_for_redirect))
    elif company_id_for_redirect:
        return redirect(url_for('.view_single_company', company_id=company_id_for_redirect))
    else:
        return redirect(url_for('.view_manager_portfolio', manager_staff_id=manager_staff_id))

@account_manager_bp.route('/company/<int:company_id>')
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def view_single_company(company_id):
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)
    conn = get_db_connection()
    company_data = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Companies WHERE CompanyID = %s", (company_id,))
        company_info = cursor.fetchone()
        # Authorization check
        if not company_info or company_info['ManagedByStaffID'] != staff_id and current_user.role_type not in STAFF_MANAGEMENT_ROLES:
            flash("You are not authorized to view this company or it does not exist.", "danger")
            return redirect(url_for('.dashboard'))
        company_data['info'] = company_info
        cursor.execute("SELECT OfferID, Title, Status, (SELECT COUNT(*) FROM JobApplications WHERE OfferID = jo.OfferID AND Status IN ('Applied', 'Submitted')) as NewApplicantCount FROM JobOffers jo WHERE CompanyID = %s ORDER BY CASE Status WHEN 'Open' THEN 1 ELSE 2 END, Title", (company_id,))
        company_data['job_offers'] = cursor.fetchall()
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('account_manager_portal/single_company_view.html', title=f"Manage: {company_data['info']['CompanyName']}", company_data=company_data, manager_staff_id=staff_id)

@account_manager_bp.route('/offer/<int:offer_id>/applicants')
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def view_offer_applicants(offer_id):
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)
    conn = get_db_connection()
    offer_data = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT jo.OfferID, jo.Title, jo.Status, c.CompanyID, c.CompanyName, c.ManagedByStaffID FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID WHERE jo.OfferID = %s", (offer_id,))
        offer_info = cursor.fetchone()
        if not offer_info: abort(404, "Job offer not found.")
        if not _is_user_authorized_for_application(staff_id, None): # Simplified check for offer
             abort(403, "You are not authorized to view applicants for this offer.")
        offer_data['info'] = offer_info
        cursor.execute("SELECT ja.ApplicationID, ja.Status, ja.ApplicationDate, c.CandidateID, u.FirstName, u.LastName, u.Email, u.ProfilePictureURL FROM JobApplications ja JOIN Candidates c ON ja.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID WHERE ja.OfferID = %s ORDER BY CASE ja.Status WHEN 'Applied' THEN 1 WHEN 'Submitted' THEN 2 WHEN 'Shortlisted' THEN 3 ELSE 4 END, ja.ApplicationDate DESC", (offer_id,))
        offer_data['applicants'] = cursor.fetchall()
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('account_manager_portal/single_offer_view.html', title=f"Applicants for: {offer_data['info']['Title']}", offer_data=offer_data, manager_staff_id=staff_id)
    
@account_manager_bp.route('/application/<int:application_id>/review-details')
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def review_application_details(application_id):
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id or not _is_user_authorized_for_application(staff_id, application_id): abort(403)
    conn = get_db_connection()
    review_data = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT ja.ApplicationID, ja.NotesByCandidate, ja.ApplicationDate, ja.NotesByStaff, c.CandidateID, jo.OfferID, jo.Title as OfferTitle, comp.CompanyName FROM JobApplications ja JOIN Candidates c ON ja.CandidateID = c.CandidateID JOIN JobOffers jo ON ja.OfferID = jo.OfferID JOIN Companies comp ON jo.CompanyID = comp.CompanyID WHERE ja.ApplicationID = %s", (application_id,))
        app_info = cursor.fetchone()
        if not app_info: abort(404, "Application not found.")
        review_data['application'] = app_info
        candidate_id = app_info['CandidateID']
        cursor.execute("SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL, u.RegistrationDate FROM Candidates c JOIN Users u ON c.UserID = u.UserID WHERE c.CandidateID = %s", (candidate_id,))
        review_data['candidate_profile'] = cursor.fetchone()
        cursor.execute("SELECT CVFileUrl, OriginalFileName, CVTitle FROM CandidateCVs WHERE CandidateID = %s AND UploadedAt <= %s ORDER BY UploadedAt DESC LIMIT 1", (candidate_id, app_info['ApplicationDate']))
        review_data['cv'] = cursor.fetchone()
        cursor.execute("SELECT VoiceNoteURL, Title FROM CandidateVoiceNotes WHERE CandidateID = %s AND UploadedAt <= %s AND Purpose = 'Job Application' ORDER BY UploadedAt DESC LIMIT 1", (candidate_id, app_info['ApplicationDate']))
        review_data['voice_note'] = cursor.fetchone()
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('account_manager_portal/application_review_modal.html', review_data=review_data, manager_staff_id=staff_id)