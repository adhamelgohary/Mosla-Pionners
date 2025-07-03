# routes/Account_Manager_Portal/am_portal_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import mysql.connector

# --- Roles are defined once for clarity ---
AM_PORTAL_ACCESS_ROLES = ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 'CEO', 'Founder', 'OperationsManager']
STAFF_MANAGEMENT_ROLES = ['HeadAccountManager', 'CEO', 'Founder', 'OperationsManager']
MANAGEABLE_STAFF_ROLES = ['AccountManager', 'SeniorAccountManager']

# --- BLUEPRINT UPDATED for a cleaner template path ---
account_manager_bp = Blueprint('account_manager_bp', __name__,
                               template_folder='../../../templates',
                               url_prefix='/am-portal')

# --- HELPER FUNCTION (No Changes) ---
def _is_user_authorized_for_application(staff_id, application_id):
    """Checks if a staff member can action a specific application."""
    if not staff_id or not application_id: return False
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT c.ManagedByStaffID FROM JobApplications ja
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            WHERE ja.ApplicationID = %s
        """, (application_id,))
        result = cursor.fetchone()
        if not result or not result['ManagedByStaffID']: return False
        company_manager_staff_id = result['ManagedByStaffID']
        if company_manager_staff_id == staff_id: return True
        current_id_in_chain = company_manager_staff_id
        for _ in range(5):
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_id_in_chain,))
            supervisor = cursor.fetchone()
            if not supervisor or not supervisor['ReportsToStaffID']: return False
            current_id_in_chain = supervisor['ReportsToStaffID']
            if current_id_in_chain == staff_id: return True
        return False
    finally:
        cursor.close()
        conn.close()

# --- ROUTES ---

@account_manager_bp.route('/')
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def portal_home():
    """Redirects AM portal users to their dashboard."""
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
        cursor.execute("SELECT COUNT(ja.ApplicationID) as count FROM JobApplications ja JOIN JobOffers jo ON ja.OfferID = jo.OfferID JOIN Companies c ON jo.CompanyID = c.CompanyID WHERE c.ManagedByStaffID = %s AND ja.Status = 'Applied'", (staff_id,))
        dashboard_data['pending_applicants_count'] = cursor.fetchone()['count']
        cursor.execute("SELECT CompanyID, CompanyName, CompanyLogoURL, (SELECT COUNT(*) FROM JobOffers WHERE CompanyID = c.CompanyID AND Status = 'Open') as OpenJobs FROM Companies c WHERE ManagedByStaffID = %s ORDER BY CompanyName", (staff_id,))
        dashboard_data['managed_companies_list'] = cursor.fetchall()
        cursor.execute("SELECT u.FirstName, u.LastName, jo.Title as JobTitle, ja.ApplicationDate, c.CandidateID FROM JobApplications ja JOIN Candidates c ON ja.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID JOIN JobOffers jo ON ja.OfferID = jo.OfferID JOIN Companies comp ON jo.CompanyID = comp.CompanyID WHERE comp.ManagedByStaffID = %s AND ja.Status = 'Applied' ORDER BY ja.ApplicationDate DESC LIMIT 5", (staff_id,))
        dashboard_data['recent_applicants'] = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error building AM dashboard for StaffID {staff_id}: {e}", exc_info=True)
        flash("An error occurred while loading your dashboard data.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    return render_template('account_manager_portal/dashboard.html', title="Account Manager Dashboard", dashboard_data=dashboard_data)

@account_manager_bp.route('/my-staff')
@login_required_with_role(STAFF_MANAGEMENT_ROLES)
def my_staff():
    """For Head AMs and above, this is the single entry point for viewing staff members."""
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
    except Exception as e:
        current_app.logger.error(f"Error fetching staff list for 'My Staff' page: {e}", exc_info=True)
        flash("An error occurred while loading the staff list.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
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
            cursor.execute("SELECT OfferID, Title, Status FROM JobOffers WHERE CompanyID = %s ORDER BY Status, Title", (company['CompanyID'],))
            offers = cursor.fetchall()
            for offer in offers:
                cursor.execute("SELECT ja.ApplicationID, ja.Status AS ApplicationStatus, c.CandidateID, u.FirstName, u.LastName FROM JobApplications ja JOIN Candidates c ON ja.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID WHERE ja.OfferID = %s ORDER BY ja.ApplicationDate DESC LIMIT 20", (offer['OfferID'],))
                offer['applicants'] = cursor.fetchall()
                company['job_offers'].append(offer)
            companies_with_data.append(company)
    except Exception as e:
        current_app.logger.error(f"Error fetching portfolio for manager {manager_staff_id}: {e}", exc_info=True)
        flash("An error occurred while loading the portfolio.", "danger")
        return redirect(url_for('.dashboard'))
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    return render_template('account_manager_portal/portfolio_detailed.html', title=f"Portfolio: {manager_details['FirstName']} {manager_details['LastName']}", manager=manager_details, companies_data=companies_with_data)

@account_manager_bp.route('/application/<int:application_id>/update', methods=['POST'])
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def update_application_status(application_id):
    action, manager_staff_id = request.form.get('action'), request.form.get('manager_staff_id')
    if not all([action, manager_staff_id]):
        flash("Invalid request. Missing action or manager ID.", "danger")
        return redirect(url_for('.dashboard'))
    if not _is_user_authorized_for_application(current_user.specific_role_id, application_id): abort(403)
    new_status = {'approve': 'Shortlisted', 'reject': 'Rejected'}.get(action)
    if new_status:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE JobApplications SET Status = %s, UpdatedAt = NOW() WHERE ApplicationID = %s", (new_status, application_id))
            conn.commit()
            flash(f"Application status updated to '{new_status}'.", "success")
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"DB error updating app status for AppID {application_id}: {e}")
            flash("A database error occurred.", "danger")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    else: flash("Unknown action specified.", "danger")
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
        cursor.execute("SELECT CompanyID, CompanyName, Industry, CompanyWebsite, CompanyLogoURL FROM Companies WHERE CompanyID = %s AND ManagedByStaffID = %s", (company_id, staff_id))
        company_info = cursor.fetchone()
        if not company_info:
            flash("You are not authorized to view this company or it does not exist.", "danger")
            return redirect(url_for('.dashboard'))
        company_data['info'] = company_info
        company_data['job_offers'] = []
        cursor.execute("SELECT OfferID, Title, Status FROM JobOffers WHERE CompanyID = %s ORDER BY CASE Status WHEN 'Open' THEN 1 WHEN 'On Hold' THEN 2 ELSE 3 END, Title", (company_id,))
        job_offers = cursor.fetchall()
        for offer in job_offers:
            cursor.execute("SELECT ja.ApplicationID, ja.Status AS ApplicationStatus, c.CandidateID, u.FirstName, u.LastName FROM JobApplications ja JOIN Candidates c ON ja.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID WHERE ja.OfferID = %s ORDER BY ja.ApplicationDate DESC LIMIT 20", (offer['OfferID'],))
            offer['applicants'] = cursor.fetchall()
            company_data['job_offers'].append(offer)
    except Exception as e:
        current_app.logger.error(f"Error fetching single company view (CompanyID: {company_id}) for StaffID {staff_id}: {e}", exc_info=True)
        flash("An error occurred while loading the company details.", "danger")
        return redirect(url_for('.dashboard'))
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    return render_template('account_manager_portal/single_company_view.html', title=f"Manage: {company_data['info']['CompanyName']}", company_data=company_data, manager_staff_id=staff_id)