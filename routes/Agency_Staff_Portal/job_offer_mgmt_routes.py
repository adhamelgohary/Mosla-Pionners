# routes/Agency_Staff_Portal/job_offer_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role, EXECUTIVE_ROLES
from db import get_db_connection
import datetime
import decimal
import mysql.connector

JOB_OFFER_REVIEW_ROLES = ['CEO', 'OperationsManager']
CLIENT_CONTACT_ROLE_NAME = 'ClientContact'

job_offer_mgmt_bp = Blueprint('job_offer_mgmt_bp', __name__,
                              template_folder='../../../templates',
                              url_prefix='/job-offers')

def validate_job_offer_data(form_data, is_client_submission=False, is_staff_creation=False):
    errors = {}
    title_key = 'position-title' if is_staff_creation else 'title'
    title = form_data.get(title_key, '').strip()
    if not title: errors[title_key] = 'Job title is required.'
    elif len(title) > 255: errors[title_key] = 'Job title is too long.'
    if is_staff_creation:
        if not form_data.get('company_id'): errors['company_id'] = 'Company is required.'
    if not form_data.get('category_id'): errors['category_id'] = 'Job category is required.'
    net_salary_str = form_data.get('salary', '').strip()
    if net_salary_str:
        try:
            net_salary = decimal.Decimal(net_salary_str)
            if net_salary < 0: errors['salary'] = 'Net salary cannot be negative.'
        except decimal.InvalidOperation: errors['salary'] = 'Invalid net salary format.'
    candidates_needed_str = form_data.get('candidates_needed', form_data.get('candidate-count', ''))
    if candidates_needed_str:
        try:
            if int(candidates_needed_str) < 1: errors['candidates_needed'] = 'At least 1 candidate needed.'
        except ValueError: errors['candidates_needed'] = 'Invalid number for candidates.'
    return errors

def _create_automated_announcement(db_cursor, source_type, title, content, audience='AllUsers', priority='Normal', posted_by_user_id=None):
    try:
        sql = "INSERT INTO SystemAnnouncements (Title, Content, Audience, Priority, Source, PostedByUserID, IsActive) VALUES (%s, %s, %s, %s, %s, %s, 1)"
        db_cursor.execute(sql, (title, content, audience, priority, source_type, posted_by_user_id))
        return True
    except Exception: return False

@job_offer_mgmt_bp.route('/submit', methods=['GET', 'POST'])
@login_required_with_role([CLIENT_CONTACT_ROLE_NAME])
def client_submit_job_offer():
    client_company_id = getattr(current_user, 'company_id', None)
    if not client_company_id:
        flash("Your company information could not be found. Please log in again.", "danger")
        return redirect(url_for('login_bp.login'))
    form_data, errors, categories = {}, {}, []
    conn_cat = get_db_connection()
    if conn_cat:
        try:
            cursor_cat = conn_cat.cursor(dictionary=True)
            cursor_cat.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
            categories = cursor_cat.fetchall()
        finally:
            if conn_cat.is_connected(): conn_cat.close()
    if request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['benefits'] = request.form.getlist('benefits')
        errors = validate_job_offer_data(form_data, is_client_submission=True)
        if not errors:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                sql = """INSERT INTO ClientSubmittedJobOffers (CompanyID, SubmittedByUserID, Title, CandidatesNeeded, Description, Requirements, EnglishLevelRequirement, GraduationStatusRequirement, NationalityRequirement, Location, WorkLocationType, NetSalary, Currency, JobType, ShiftType, Benefits, IsTransportationProvided, TransportationType, ClientNotes, CategoryID)
                         VALUES (%(company_id)s, %(user_id)s, %(title)s, %(candidates_needed)s, %(description)s, %(requirements)s, %(english_level)s, %(grad_status)s, %(nationality)s, %(location)s, %(work_location)s, %(salary)s, %(currency)s, %(job_type)s, %(shift_type)s, %(benefits)s, %(transport_provided)s, %(transport_type)s, %(client_notes)s, %(category_id)s)"""
                params = {
                    "company_id": client_company_id, "user_id": current_user.id, "title": form_data.get('title'),
                    "candidates_needed": int(form_data.get('candidates_needed', 1)) if form_data.get('candidates_needed') else 1,
                    "description": form_data.get('description'), "requirements": form_data.get('requirements'),
                    "english_level": form_data.get('english_level'), "grad_status": form_data.get('grad_status'),
                    "nationality": form_data.get('nationality', 'Any'), "location": form_data.get('location'),
                    "work_location": form_data.get('work_location', 'On-site'),
                    "salary": decimal.Decimal(form_data['salary']) if form_data.get('salary') else None,
                    "currency": form_data.get('currency', 'EGP'), "job_type": form_data.get('job_type'),
                    "shift_type": form_data.get('shift_type', 'Fixed'),
                    "benefits": ",".join(form_data['benefits']) if form_data['benefits'] else None,
                    "transport_provided": 1 if form_data.get('transportation') == 'yes' else 0,
                    "transport_type": form_data.get('transport_type') if form_data.get('transportation') == 'yes' else None,
                    "client_notes": form_data.get('client_notes'), "category_id": form_data.get('category_id')}
                cursor.execute(sql, params)
                conn.commit()
                flash("Job offer submitted for review!", "success")
                return redirect(url_for('client_portal_bp.dashboard'))
            except Exception as e:
                if conn: conn.rollback()
                current_app.logger.error(f"Error in client_submit_job_offer: {e}", exc_info=True)
                flash("Error submitting job offer.", "danger")
            finally:
                if conn and conn.is_connected(): conn.close()
        else:
            flash("Please correct form errors.", "warning")
    return render_template('client_portal/submit_offer_form.html', title="Submit Job Offer", form_data=form_data, errors=errors, categories=categories)

@job_offer_mgmt_bp.route('/dashboard')
@login_required_with_role(JOB_OFFER_REVIEW_ROLES)
def dashboard():
    conn, kpis = None, {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        queries = {
            'total_open_offers': "SELECT COUNT(OfferID) as count FROM JobOffers WHERE Status = 'Open'",
            'total_candidates_needed': "SELECT SUM(CandidatesNeeded) as sum FROM JobOffers WHERE Status = 'Open'",
            'avg_time_to_fill': "SELECT AVG(DATEDIFF(FilledDate, DatePosted)) as avg_days FROM JobOffers WHERE Status = 'Filled' AND FilledDate IS NOT NULL AND DatePosted IS NOT NULL",
            'approval_rate': "SELECT (SUM(CASE WHEN ReviewStatus = 'Approved' THEN 1 ELSE 0 END) / COUNT(SubmissionID)) * 100 as approval_rate FROM ClientSubmittedJobOffers WHERE SubmissionDate >= DATE_SUB(NOW(), INTERVAL 90 DAY) AND ReviewStatus IN ('Approved', 'Rejected')",
            'pending_submissions': "SELECT COUNT(SubmissionID) as count FROM ClientSubmittedJobOffers WHERE ReviewStatus = 'Pending'",
            'new_offers_this_month': "SELECT COUNT(OfferID) as count FROM JobOffers WHERE DatePosted >= DATE_FORMAT(NOW(), '%Y-%m-01')"
        }
        for key, sql in queries.items():
            cursor.execute(sql)
            res = cursor.fetchone()
            if key == 'total_candidates_needed': kpis[key] = int(res['sum'] or 0) if res else 0
            elif key == 'avg_time_to_fill': kpis[key] = round(res['avg_days'], 1) if res and res['avg_days'] is not None else 'N/A'
            elif key == 'approval_rate': kpis[key] = f"{round(res['approval_rate'], 1)}%" if res and res['approval_rate'] is not None else 'N/A'
            else: kpis[key] = res['count'] if res else 0
        cursor.execute("SELECT jo.Title, c.CompanyName, DATEDIFF(NOW(), jo.DatePosted) as oldest_days FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID WHERE jo.Status = 'Open' ORDER BY jo.DatePosted ASC LIMIT 1")
        oldest = cursor.fetchone()
        kpis.update({'age_of_oldest_offer': oldest['oldest_days'], 'oldest_offer_title': oldest['Title'], 'oldest_offer_company': oldest['CompanyName']} if oldest else {'age_of_oldest_offer': 'N/A', 'oldest_offer_title': 'No open offers', 'oldest_offer_company': ''})
        return render_template('agency_staff_portal/job_offers/dashboard.html', title="Job Offer Dashboard", kpis=kpis)
    except Exception as e:
        current_app.logger.error(f"Error building KPI dashboard: {e}", exc_info=True)
        flash("Could not load dashboard data.", "danger")
        return render_template('agency_staff_portal/job_offers/dashboard.html', title="Error", kpis={}, error=True)
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

@job_offer_mgmt_bp.route('/')
@login_required_with_role(JOB_OFFER_REVIEW_ROLES)
def list_all_job_offers():
    offers, conn = [], None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT jo.OfferID, jo.Title, jo.Status, jo.DatePosted, c.CompanyName, jc.CategoryName FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID ORDER BY jo.DatePosted DESC")
        offers = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching all job offers: {e}", exc_info=True)
        flash("Could not load job offers list.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return render_template('agency_staff_portal/job_offers/list_all_job_offers.html', title='Manage Live Offers', offers=offers)

@job_offer_mgmt_bp.route('/create-live', methods=['GET', 'POST'])
@login_required_with_role(JOB_OFFER_REVIEW_ROLES)
def staff_direct_create_job_offer():
    form_data = { 'work_location': 'On-site', 'work_time': 'Full-time', 'shifts': 'Fixed', 'nationality': 'Any', 'transportation': 'no', 'status': 'Open', 'is_featured': False, 'benefits': [] }
    errors, companies, categories = {}, [], []
    conn_data = get_db_connection()
    if conn_data:
        try:
            cursor_data = conn_data.cursor(dictionary=True)
            cursor_data.execute("SELECT CompanyID, CompanyName FROM Companies ORDER BY CompanyName")
            companies = cursor_data.fetchall()
            cursor_data.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
            categories = cursor_data.fetchall()
        except Exception as e_data:
            current_app.logger.error(f"Error fetching form data for staff create offer: {e_data}", exc_info=True)
            flash("Error loading form support data.", "danger")
        finally:
            if 'cursor_data' in locals() and cursor_data: cursor_data.close()
            if conn_data.is_connected(): conn_data.close()

    if request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['is_featured'] = request.form.get('is_featured') == 'on'
        form_data['benefits'] = request.form.getlist('benefits')
        errors = validate_job_offer_data(form_data, is_staff_creation=True)
        if not errors:
            conn_insert = None
            try:
                conn_insert = get_db_connection()
                cursor = conn_insert.cursor()
                sql = """INSERT INTO JobOffers (CompanyID, PostedByStaffID, CategoryID, Title, CandidatesNeeded, EnglishLevelRequirement, GraduationStatusRequirement, NationalityRequirement, Location, WorkLocationType, NetSalary, Currency, JobType, ShiftType, Benefits, IsTransportationProvided, TransportationType, Status, DatePosted, IsFeatured, ClosingDate)
                         VALUES (%(company_id)s, %(posted_by_id)s, %(category_id)s, %(title)s, %(candidates_needed)s, %(english_level)s, %(grad_status)s, %(nationality)s, %(location)s, %(work_location)s, %(salary)s, %(currency)s, %(job_type)s, %(shift_type)s, %(benefits)s, %(transport_provided)s, %(transport_type)s, %(status)s, NOW(), %(is_featured)s, %(closing_date)s)"""
                params = {
                    "company_id": form_data['company_id'], "posted_by_id": current_user.specific_role_id, "category_id": form_data['category_id'],
                    "title": form_data['position-title'], "candidates_needed": form_data.get('candidate-count'),
                    "english_level": form_data.get('english-level'), "grad_status": form_data.get('grad-status'),
                    "nationality": form_data.get('nationality'), "location": form_data.get('location'),
                    "work_location": form_data.get('work_location'), "salary": decimal.Decimal(form_data['salary']) if form_data.get('salary') else None,
                    "currency": form_data.get('currency', 'EGP'), "job_type": form_data.get('work_time'),
                    "shift_type": form_data.get('shifts'), "benefits": ",".join(form_data['benefits']) if form_data['benefits'] else None,
                    "transport_provided": 1 if form_data.get('transportation') == 'yes' else 0,
                    "transport_type": form_data.get('transport_type') if form_data.get('transportation') == 'yes' else None,
                    "status": form_data.get('status', 'Open'), "is_featured": 1 if form_data.get('is_featured') else 0,
                    "closing_date": form_data.get('closing_date') if form_data.get('closing_date') else None
                }
                cursor.execute(sql, params)
                offer_id = cursor.lastrowid
                # _create_automated_announcement(cursor, 'Automated_Offer', f"New Job: {params['title']}", "A new job offer is available.")
                conn_insert.commit()
                flash('Job offer created!', 'success')
                return redirect(url_for('.list_all_job_offers'))
            except Exception as e:
                if conn_insert: conn_insert.rollback()
                current_app.logger.error(f"Error creating live job offer: {e}", exc_info=True)
                flash(f'Error: {e}', 'danger')
            finally:
                if conn_insert and conn_insert.is_connected():
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn_insert.close()
        else: flash('Please correct form errors.', 'warning')
    return render_template('agency_staff_portal/job_offers/add_edit_job_offer.html', title='Create Job Offer', form_data=form_data, errors=errors, companies=companies, categories=categories, is_staff_direct_creation=True, action_verb="Post Live")

@job_offer_mgmt_bp.route('/edit-live/<int:offer_id>', methods=['GET', 'POST'])
@login_required_with_role(JOB_OFFER_REVIEW_ROLES)
def edit_live_job_offer(offer_id):
    form_data, errors, companies, categories = {}, {}, [], []
    original_title_hidden = "Job Offer"
    conn_dd = get_db_connection()
    if conn_dd:
        try:
            cursor_dd = conn_dd.cursor(dictionary=True)
            cursor_dd.execute("SELECT CompanyID, CompanyName FROM Companies ORDER BY CompanyName")
            companies = cursor_dd.fetchall()
            cursor_dd.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
            categories = cursor_dd.fetchall()
        finally: 
            if 'cursor_dd' in locals() and cursor_dd: cursor_dd.close()
            conn_dd.close()

    if request.method == 'GET':
        conn_fetch = get_db_connection()
        if conn_fetch:
            try:
                cursor = conn_fetch.cursor(dictionary=True)
                cursor.execute("SELECT * FROM JobOffers WHERE OfferID = %s", (offer_id,))
                data = cursor.fetchone()
                if data:
                    form_data = data.copy() # Use copy to avoid modifying original dict from cursor
                    form_data['position-title'] = data.get('Title')
                    form_data['candidate-count'] = data.get('CandidatesNeeded')
                    form_data['english-level'] = data.get('EnglishLevelRequirement')
                    form_data['grad-status'] = data.get('GraduationStatusRequirement')
                    form_data['nationality'] = data.get('NationalityRequirement')
                    form_data['work_location'] = data.get('WorkLocationType')
                    form_data['work_time'] = data.get('JobType')
                    form_data['shifts'] = data.get('ShiftType')
                    form_data['salary'] = str(data['NetSalary']) if data.get('NetSalary') is not None else ''
                    form_data['currency'] = data.get('Currency', 'EGP')
                    form_data['benefits'] = data.get('Benefits', '').split(',') if data.get('Benefits') else []
                    form_data['transportation'] = 'yes' if data.get('IsTransportationProvided') else 'no'
                    form_data['transport_type'] = data.get('TransportationType')
                    form_data['closing_date'] = data['ClosingDate'].isoformat() if data.get('ClosingDate') and isinstance(data['ClosingDate'], datetime.date) else ''
                    form_data['is_featured'] = bool(data.get('IsFeatured'))
                    original_title_hidden = data.get('Title', "Job Offer")
                else:
                    flash('Job offer not found.', 'danger')
                    return redirect(url_for('.list_all_job_offers'))
            except Exception as e:
                current_app.logger.error(f"Error fetching offer {offer_id} for edit: {e}", exc_info=True)
                flash('Error fetching offer details.', 'danger')
            finally: 
                if 'cursor' in locals() and cursor: cursor.close()
                if conn_fetch.is_connected(): conn_fetch.close()
    elif request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['is_featured'] = request.form.get('is_featured') == 'on'
        form_data['benefits'] = request.form.getlist('benefits')
        original_title_hidden = request.form.get('original_title_hidden', form_data.get('position-title', 'Job Offer'))
        errors = validate_job_offer_data(form_data, is_staff_creation=True) # is_staff_creation implies company_id and category_id are required
        if not errors:
            conn_update = None
            try:
                conn_update = get_db_connection()
                cursor = conn_update.cursor()
                sql = """UPDATE JobOffers SET CompanyID=%(company_id)s, CategoryID=%(category_id)s, Title=%(title)s, CandidatesNeeded=%(candidates_needed)s, EnglishLevelRequirement=%(english_level)s, GraduationStatusRequirement=%(grad_status)s, NationalityRequirement=%(nationality)s, Location=%(location)s, WorkLocationType=%(work_location)s, NetSalary=%(salary)s, Currency=%(currency)s, JobType=%(job_type)s, ShiftType=%(shift_type)s, Benefits=%(benefits)s, IsTransportationProvided=%(transport_provided)s, TransportationType=%(transport_type)s, Status=%(status)s, IsFeatured=%(is_featured)s, ClosingDate=%(closing_date)s, UpdatedAt=NOW() WHERE OfferID=%(offer_id)s"""
                params = {
                    "company_id": form_data['company_id'], "category_id": form_data['category_id'], "title": form_data['position-title'],
                    "candidates_needed": form_data.get('candidate-count'), "english_level": form_data.get('english-level'),
                    "grad_status": form_data.get('grad-status'), "nationality": form_data.get('nationality'),
                    "location": form_data.get('location'), "work_location": form_data.get('work_location'),
                    "salary": decimal.Decimal(form_data['salary']) if form_data.get('salary') else None,
                    "currency": form_data.get('currency', 'EGP'), "job_type": form_data.get('work_time'),
                    "shift_type": form_data.get('shifts'), "benefits": ",".join(form_data['benefits']) if form_data['benefits'] else None,
                    "transport_provided": 1 if form_data.get('transportation') == 'yes' else 0,
                    "transport_type": form_data.get('transport_type') if form_data.get('transportation') == 'yes' else None,
                    "status": form_data.get('status', 'Open'), "is_featured": 1 if form_data.get('is_featured') else 0,
                    "closing_date": form_data.get('closing_date') if form_data.get('closing_date') else None, "offer_id": offer_id}
                cursor.execute(sql, params)
                conn_update.commit()
                flash('Job offer updated!', 'success')
                return redirect(url_for('.list_all_job_offers'))
            except Exception as e:
                if conn_update: conn_update.rollback()
                current_app.logger.error(f"Error updating offer {offer_id}: {e}", exc_info=True)
                flash(f'Error: {e}', 'danger')
            finally:
                if conn_update and conn_update.is_connected(): 
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn_update.close()
        else: flash('Correct errors.', 'warning')
    return render_template('agency_staff_portal/job_offers/add_edit_job_offer.html', title=f'Edit: {original_title_hidden}', form_data=form_data, errors=errors, companies=companies, categories=categories, offer_id=offer_id, original_title_hidden=original_title_hidden, is_editing_live=True, action_verb="Update Live")

@job_offer_mgmt_bp.route('/delete-live/<int:offer_id>', methods=['POST'])
@login_required_with_role(JOB_OFFER_REVIEW_ROLES)
def delete_live_job_offer(offer_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM JobOffers WHERE OfferID = %s", (offer_id,))
        conn.commit()
        flash('Offer deleted!', 'success' if cursor.rowcount > 0 else 'warning')
    except mysql.connector.Error as e:
        if conn: conn.rollback()
        if e.errno == 1451: flash('Cannot delete: offer has related records.', 'danger')
        else: flash(f'DB Error: {e}', 'danger')
    except Exception as e:
        if conn: conn.rollback()
        flash(f'Error: {e}', 'danger')
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return redirect(url_for('.list_all_job_offers'))

@job_offer_mgmt_bp.route('/review-client-submissions')
@login_required_with_role(JOB_OFFER_REVIEW_ROLES)
def list_review_client_submissions():
    conn, submissions, categories_for_dropdown = None, [], []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT csjo.*, c.CompanyName, u.FirstName as SubmitterFirstName, u.LastName as SubmitterLastName, cat.CategoryName FROM ClientSubmittedJobOffers csjo JOIN Companies c ON csjo.CompanyID = c.CompanyID JOIN Users u ON csjo.SubmittedByUserID = u.UserID LEFT JOIN JobCategories cat ON csjo.CategoryID = cat.CategoryID WHERE csjo.ReviewStatus IN ('Pending', 'NeedsClarification') ORDER BY csjo.SubmissionDate ASC")
        submissions = cursor.fetchall()
        for sub in submissions: sub['Benefits_list'] = sub.get('Benefits', '').split(',') if sub.get('Benefits') else []
        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
        categories_for_dropdown = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching submissions for review: {e}", exc_info=True)
        flash("Could not load submissions for review.", "danger")
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return render_template('agency_staff_portal/job_offers/review_client_submissions.html', title='Review Submissions', submissions=submissions, categories_for_dropdown=categories_for_dropdown)

@job_offer_mgmt_bp.route('/review-client-submission/<int:submission_id>/action', methods=['POST'])
@login_required_with_role(JOB_OFFER_REVIEW_ROLES)
def review_client_submission_action(submission_id):
    action = request.form.get('action')
    reviewer_comments = request.form.get('reviewer_comments', '').strip()
    category_id_on_approval = request.form.get('category_id_on_approval')

    if action not in ['approve', 'reject', 'needs_clarification']:
        flash('Invalid action.', 'danger')
        return redirect(url_for('.list_review_client_submissions'))
    if (action == 'reject' or action == 'needs_clarification') and not reviewer_comments:
        flash('Comments are required for this action.', 'warning')
        return redirect(url_for('.list_review_client_submissions'))
    if action == 'approve' and not category_id_on_approval:
        flash('A job category must be selected for approval.', 'warning')
        return redirect(url_for('.list_review_client_submissions'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT csjo.*, c.CompanyName FROM ClientSubmittedJobOffers csjo JOIN Companies c ON csjo.CompanyID = c.CompanyID WHERE csjo.SubmissionID = %s", (submission_id,))
        sub = cursor.fetchone()
        if not sub: flash('Submission not found.', 'danger'); return redirect(url_for('.list_review_client_submissions'))

        if action == 'approve':
            sql_live = """INSERT INTO JobOffers (CompanyID, PostedByStaffID, CategoryID, Title, CandidatesNeeded, Description, Requirements, EnglishLevelRequirement, GraduationStatusRequirement, NationalityRequirement, Location, WorkLocationType, NetSalary, Currency, JobType, ShiftType, Benefits, IsTransportationProvided, TransportationType, Status, DatePosted)
                          VALUES (%(CompanyID)s, %(PostedByStaffID)s, %(SelectedCategoryID)s, %(Title)s, %(CandidatesNeeded)s, %(Description)s, %(Requirements)s, %(EnglishLevelRequirement)s, %(GraduationStatusRequirement)s, %(NationalityRequirement)s, %(Location)s, %(WorkLocationType)s, %(NetSalary)s, %(Currency)s, %(JobType)s, %(ShiftType)s, %(Benefits)s, %(IsTransportationProvided)s, %(TransportationType)s, 'Open', NOW())"""
            params_live = sub.copy()
            params_live.update({"PostedByStaffID": current_user.specific_role_id, "SelectedCategoryID": category_id_on_approval})
            
            cursor.execute(sql_live, params_live)
            live_offer_id = cursor.lastrowid
            
            cursor.execute("UPDATE ClientSubmittedJobOffers SET ReviewStatus='Approved', ReviewerUserID=%s, ReviewDate=NOW(), ReviewerComments=%s, CorrespondingOfferID=%s WHERE SubmissionID=%s", (current_user.id, reviewer_comments, live_offer_id, submission_id))
            _create_automated_announcement(cursor, 'Automated_Offer', f"New Job: {sub['Title']} with {sub['CompanyName']}", "A new job offer has been posted.", posted_by_user_id=current_user.id)
            flash('Approved & job offer posted live.', 'success')
        elif action == 'reject':
            cursor.execute("UPDATE ClientSubmittedJobOffers SET ReviewStatus='Rejected', ReviewerUserID=%s, ReviewDate=NOW(), ReviewerComments=%s WHERE SubmissionID=%s", (current_user.id, reviewer_comments, submission_id))
            flash('Submission rejected.', 'info')
        elif action == 'needs_clarification':
            cursor.execute("UPDATE ClientSubmittedJobOffers SET ReviewStatus='NeedsClarification', ReviewerUserID=%s, ReviewDate=NOW(), ReviewerComments=%s WHERE SubmissionID=%s", (current_user.id, reviewer_comments, submission_id))
            flash('Submission marked as "Needs Clarification".', 'info')
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error processing submission {submission_id}, action {action}: {e}", exc_info=True)
        flash(f'Error: {e}', 'danger')
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return redirect(url_for('.list_review_client_submissions'))

@job_offer_mgmt_bp.route('/view-live/<int:offer_id>')
@login_required_with_role(JOB_OFFER_REVIEW_ROLES)
def view_live_job_offer_detail(offer_id):
    offer, conn = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Updated to join with Staff and Users for Poster info
        cursor.execute("""
            SELECT jo.*, c.CompanyName, jc.CategoryName, 
                   poster_user.FirstName as PosterFirstName, poster_user.LastName as PosterLastName
            FROM JobOffers jo
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID
            LEFT JOIN Staff poster_staff ON jo.PostedByStaffID = poster_staff.StaffID
            LEFT JOIN Users poster_user ON poster_staff.UserID = poster_user.UserID
            WHERE jo.OfferID = %s
        """, (offer_id,))
        offer = cursor.fetchone()
        if offer: 
            offer['Benefits_list'] = offer.get('Benefits', '').split(',') if offer.get('Benefits') else []
    except Exception as e:
        current_app.logger.error(f"Error fetching live offer detail {offer_id}: {e}", exc_info=True)
        flash("Could not load offer details.", "danger")
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    if not offer: 
        flash('Job offer not found.', 'danger'); return redirect(url_for('.list_all_job_offers'))
    return render_template('agency_staff_portal/job_offers/view_live_job_offer_detail.html', title=f"Job Offer Details: {offer['Title']}", offer=offer)