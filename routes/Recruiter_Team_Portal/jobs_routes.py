# routes/Recruiter_Team_Portal/jobs_routes.py
from flask import Blueprint, abort, render_template, flash, redirect, url_for, current_app, request
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

# --- ROLE CONSTANTS ---
RECRUITER_PORTAL_ROLES = ['SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'CEO', 'Founder']
LEADER_ROLES_IN_PORTAL = ['SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'CEO', 'Founder']

# Define a complete, self-contained blueprint for job-related routes
jobs_bp = Blueprint('jobs_bp', __name__,
                    url_prefix='/recruiter-portal',
                    template_folder='../../../templates')

@jobs_bp.route('/job-offers')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def list_job_offers():
    filter_company_id, filter_category_id = request.args.get('company_id', type=int), request.args.get('category_id', type=int)
    conn = get_db_connection()
    job_offers, all_companies, all_categories = [], [], []
    try:
        cursor = conn.cursor(dictionary=True)
        sql, params = "SELECT jo.OfferID, jo.Title, jo.Location, jo.NetSalary, jo.Status, c.CompanyName, jc.CategoryName FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID WHERE 1=1", []
        if filter_company_id: sql += " AND jo.CompanyID = %s"; params.append(filter_company_id)
        if filter_category_id: sql += " AND jo.CategoryID = %s"; params.append(filter_category_id)
        sql += " ORDER BY jo.DatePosted DESC"
        cursor.execute(sql, tuple(params)); job_offers = cursor.fetchall()
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies ORDER BY CompanyName ASC"); all_companies = cursor.fetchall()
        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName ASC"); all_categories = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching job offers list: {e}", exc_info=True)
        flash("An error occurred while loading the job offers.", "danger")
    finally: conn.close()
    return render_template('recruiter_team_portal/list_job_offers.html', title="Browse Job Offers", job_offers=job_offers, all_companies=all_companies, all_categories=all_categories, filter_company_id=filter_company_id, filter_category_id=filter_category_id)

@jobs_bp.route('/job-offers/<int:offer_id>')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def view_job_offer(offer_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT jo.*, c.CompanyName, c.CompanyLogoURL, jc.CategoryName, u.FirstName as PosterFirstName, u.LastName as PosterLastName FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID LEFT JOIN Staff s ON jo.PostedByStaffID = s.StaffID LEFT JOIN Users u ON s.UserID = u.UserID WHERE jo.OfferID = %s"
        cursor.execute(sql, (offer_id,))
        offer = cursor.fetchone()
        if not offer: abort(404, "Job Offer not found.")
        list_fields = ['RequiredLanguages', 'GraduationStatusRequirement', 'AvailableShifts', 'WorkingDays', 'BenefitsIncluded']
        for field in list_fields:
            if offer.get(field) and isinstance(offer[field], str): offer[field] = [item.strip() for item in offer[field].split(',')]
            elif not offer.get(field): offer[field] = []
    except Exception as e:
        current_app.logger.error(f"Error fetching job offer details for OfferID {offer_id}: {e}", exc_info=True)
        flash("An error occurred while loading the job offer details.", "danger")
        return redirect(url_for('jobs_bp.list_job_offers'))
    finally: conn.close()
    return render_template('recruiter_team_portal/job_offer_detail.html', title=offer['Title'], offer=offer)

@jobs_bp.route('/my-referrals')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def my_referred_applications():
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: flash("Your staff profile ID could not be found.", "danger"); return redirect(url_for('dashboard_bp.dashboard'))
    conn, referred_applications = get_db_connection(), []
    try:
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT ja.ApplicationID, ja.ApplicationDate, ja.Status, c.CandidateID, u.FirstName, u.LastName, u.Email, u.ProfilePictureURL, jo.Title AS JobTitle, comp.CompanyName FROM JobApplications ja JOIN Candidates c ON ja.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID JOIN JobOffers jo ON ja.OfferID = jo.OfferID JOIN Companies comp ON jo.CompanyID = comp.CompanyID WHERE ja.ReferringStaffID = %s ORDER BY ja.ApplicationDate DESC;"
        cursor.execute(sql, (staff_id,)); referred_applications = cursor.fetchall()
    finally: conn.close()
    return render_template('recruiter_team_portal/my_referred_applications.html', title="My Referred Applications", applications=referred_applications)

@jobs_bp.route('/application/<int:application_id>/review')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def review_referred_application(application_id):
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)
    conn, review_data = get_db_connection(), {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT ReferringStaffID FROM JobApplications WHERE ApplicationID = %s", (application_id,)); app_check = cursor.fetchone()
        is_own_referral, is_manager = app_check and app_check.get('ReferringStaffID') == staff_id, current_user.role_type in LEADER_ROLES_IN_PORTAL
        if not (is_own_referral or is_manager): abort(403)
        cursor.execute("SELECT ja.ApplicationID, ja.NotesByCandidate, ja.ApplicationDate, ja.NotesByStaff, c.CandidateID, jo.OfferID, jo.Title as OfferTitle, comp.CompanyName FROM JobApplications ja JOIN Candidates c ON ja.CandidateID = c.CandidateID JOIN JobOffers jo ON ja.OfferID = jo.OfferID JOIN Companies comp ON jo.CompanyID = comp.CompanyID WHERE ja.ApplicationID = %s", (application_id,))
        app_info = cursor.fetchone()
        if not app_info: abort(404, "Application not found.")
        review_data['application'], candidate_id = app_info, app_info['CandidateID']
        cursor.execute("SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL, u.RegistrationDate FROM Candidates c JOIN Users u ON c.UserID = u.UserID WHERE c.CandidateID = %s", (candidate_id,)); review_data['candidate_profile'] = cursor.fetchone()
        if review_data['candidate_profile'] and isinstance(review_data['candidate_profile'].get('Languages'), str): review_data['candidate_profile']['Languages'] = review_data['candidate_profile']['Languages'].split(',')
        cursor.execute("SELECT CVID, CVFileUrl, OriginalFileName, CVTitle FROM CandidateCVs WHERE CandidateID = %s ORDER BY IsPrimary DESC, UploadedAt DESC LIMIT 1", (candidate_id,)); review_data['cv'] = cursor.fetchone()
    finally: conn.close()
    return render_template('account_manager_portal/application_review_modal.html', review_data=review_data, is_recruiter_view=True)