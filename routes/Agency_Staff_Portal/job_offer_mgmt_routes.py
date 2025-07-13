# routes/Agency_Staff_Portal/job_offer_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role, EXECUTIVE_ROLES
from db import get_db_connection
import datetime
import decimal
import mysql.connector

JOB_OFFER_REVIEW_ROLES = ['CEO']
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

    candidates_needed_str = form_data.get('candidates_needed', form_data.get('candidate-count', '')).strip()
    if candidates_needed_str:
        try:
            if int(candidates_needed_str) < 1: errors['candidates_needed'] = 'At least 1 candidate is required.'
        except ValueError: errors['candidates_needed'] = 'Invalid number for candidates needed.'

    max_age_str = form_data.get('max_age', '').strip()
    if max_age_str:
        try:
            if int(max_age_str) < 18: errors['max_age'] = 'Maximum age must be a realistic value (e.g., 18+).'
        except ValueError: errors['max_age'] = 'Invalid number for maximum age.'

    return errors

def _create_automated_announcement(db_cursor, source_type, title, content, audience='AllUsers', priority='Normal', posted_by_user_id=None):
    try:
        sql = "INSERT INTO SystemAnnouncements (Title, Content, Audience, Priority, Source, PostedByUserID, IsActive) VALUES (%s, %s, %s, %s, %s, %s, 1)"
        db_cursor.execute(sql, (title, content, audience, priority, source_type, posted_by_user_id))
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to create automated announcement: {e}", exc_info=True)
        return False

@job_offer_mgmt_bp.route('/submit', methods=['GET', 'POST'])
@login_required_with_role([CLIENT_CONTACT_ROLE_NAME])
def client_submit_job_offer():
    client_company_id = getattr(current_user, 'company_id', None)
    if not client_company_id:
        flash("Your company information could not be found. Please log in again.", "danger")
        return redirect(url_for('login_bp.login'))

    if request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['benefits'] = request.form.getlist('benefits')
        form_data['available_shifts'] = request.form.getlist('available_shifts')
        errors = validate_job_offer_data(form_data, is_client_submission=True)

        if not errors:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                # Note: This table still uses the old column names, which is fine as it's a staging table.
                # The mapping happens when an admin approves it.
                sql = """INSERT INTO ClientSubmittedJobOffers (
                             CompanyID, SubmittedByUserID, Title, Location, MaxAge, ClosingDate, HasContract,
                             RequiredLanguage, EnglishLevelRequirement, CandidatesNeeded, HiringCadence, WorkLocationType,
                             HiringPlan, ShiftType, AvailableShifts, NetSalary, PaymentTerm, GraduationStatusRequirement,
                             NationalityRequirement, Benefits, IsTransportationProvided, TransportationType, ClientNotes
                         ) VALUES (
                             %(company_id)s, %(user_id)s, %(title)s, %(location)s, %(max_age)s, %(closing_date)s, %(has_contract)s,
                             %(required_language)s, %(english_level)s, %(candidates_needed)s, %(hiring_cadence)s, %(work_location)s,
                             %(hiring_plan)s, %(shift_type)s, %(available_shifts)s, %(salary)s, %(payment_term)s, %(grad_status)s,
                             %(nationality)s, %(benefits)s, %(transport_provided)s, %(transport_type)s, %(client_notes)s
                         )"""
                params = {
                    "company_id": client_company_id,
                    "user_id": current_user.id,
                    "title": form_data.get('title'),
                    "location": form_data.get('location'),
                    "max_age": form_data.get('max_age') or None,
                    "closing_date": form_data.get('closing_date') or None,
                    "has_contract": 1 if form_data.get('has_contract') == 'yes' else 0,
                    "required_language": form_data.get('required_language'),
                    "english_level": form_data.get('english_level'),
                    "candidates_needed": int(form_data.get('candidates_needed', 1)) if form_data.get('candidates_needed') else 1,
                    "hiring_cadence": form_data.get('hiring_cadence'),
                    "work_location": form_data.get('work_location'),
                    "hiring_plan": form_data.get('hiring_plan'),
                    "shift_type": form_data.get('shift_type'),
                    "available_shifts": ",".join(form_data['available_shifts']) if form_data['available_shifts'] else None,
                    "salary": decimal.Decimal(form_data['salary']) if form_data.get('salary') else None,
                    "payment_term": form_data.get('payment_term'),
                    "grad_status": form_data.get('grad_status'),
                    "nationality": form_data.get('nationality'),
                    "benefits": ",".join(form_data['benefits']) if form_data['benefits'] else None,
                    "transport_provided": 1 if form_data.get('transportation') == 'yes' else 0,
                    "transport_type": form_data.get('transport_type') if form_data.get('transportation') == 'yes' else None,
                    "client_notes": form_data.get('client_notes')
                }
                cursor.execute(sql, params)
                conn.commit()
                flash("Job offer submitted for review! Thank you.", "success")
                return redirect(url_for('client_portal_bp.dashboard'))
            except Exception as e:
                if conn: conn.rollback()
                current_app.logger.error(f"Error in client_submit_job_offer: {e}", exc_info=True)
                flash("An error occurred while submitting the job offer. Please contact support.", "danger")
            finally:
                if conn and conn.is_connected(): conn.close()
        else:
            flash("Please correct the errors in the form before submitting.", "warning")
    return redirect(url_for('client_portal_bp.dashboard'))


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
@login_required_with_role(EXECUTIVE_ROLES)
def list_all_job_offers():
    offers, conn = [], None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT jo.OfferID, jo.Title, jo.Status, jo.DatePosted, c.CompanyName, jc.CategoryName 
            FROM JobOffers jo 
            JOIN Companies c ON jo.CompanyID = c.CompanyID 
            LEFT JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID 
            ORDER BY jo.DatePosted DESC
        """)
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
    form_data = {
        'work_location': 'site', 'hiring_plan': 'long-term', 'shift_type': 'fixed',
        'nationality': 'any', 'transportation': 'no', 'status': 'Open',
        'has_contract': 'yes', 'hiring_cadence': 'month', 'required_language': 'english',
        'grad-status': 'grad', 'english-level': 'b2',
        'benefits': [], 'available_shifts': []
    }
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
        benefits_list = request.form.getlist('benefits')
        if form_data.get('transportation') == 'yes':
            if form_data.get('transport_type') == 'd2d': benefits_list.append('Transportation (Door to Door)')
            elif form_data.get('transport_type') == 'pickup': benefits_list.append('Transportation (Pickup Points)')
        
        form_data['benefits'] = benefits_list
        form_data['available_shifts'] = request.form.getlist('available_shifts')
        errors = validate_job_offer_data(form_data, is_staff_creation=True)

        if not errors:
            conn_insert = None
            try:
                conn_insert = get_db_connection()
                cursor = conn_insert.cursor()
                sql = """INSERT INTO JobOffers (
                            CompanyID, PostedByStaffID, CategoryID, Title, Location, NetSalary, PaymentTerm, HiringPlan,
                            MaxAge, HasContract, GraduationStatusRequirement, Nationality, RequiredLanguages, RequiredLevel,
                            CandidatesNeeded, HiringCadence, WorkLocationType, ShiftType, AvailableShifts,
                            BenefitsIncluded, Status, ClosingDate, DatePosted
                         ) VALUES (
                            %(company_id)s, %(posted_by_id)s, %(category_id)s, %(title)s, %(location)s, %(salary)s, %(payment_term)s, %(hiring_plan)s,
                            %(max_age)s, %(has_contract)s, %(grad_status)s, %(nationality)s, %(required_languages)s, %(required_level)s,
                            %(candidates_needed)s, %(hiring_cadence)s, %(work_location)s, %(shift_type)s, %(available_shifts)s,
                            %(benefits)s, %(status)s, %(closing_date)s, NOW()
                         )"""
                nationality_mapping = {'egyptian': 'Egyptians Only', 'any': 'Foreigners & Egyptians', 'foreigner': 'Foreigners & Egyptians'}
                params = {
                    "company_id": form_data.get('company_id'), "posted_by_id": current_user.specific_role_id,
                    "category_id": form_data.get('category_id'), "title": form_data.get('position-title'),
                    "location": form_data.get('location'),
                    "salary": decimal.Decimal(form_data['salary']) if form_data.get('salary') else None,
                    "payment_term": form_data.get('payment_term'), "hiring_plan": form_data.get('hiring_plan'),
                    "max_age": form_data.get('max_age') or None,
                    "has_contract": 1 if form_data.get('has_contract') == 'yes' else 0,
                    "grad_status": form_data.get('grad-status'), "nationality": nationality_mapping.get(form_data.get('nationality'), 'Foreigners & Egyptians'),
                    "required_languages": form_data.get('required_language'), "required_level": form_data.get('english-level'),
                    "candidates_needed": form_data.get('candidate-count'), "hiring_cadence": form_data.get('hiring_cadence'),
                    "work_location": form_data.get('work_location'), "shift_type": form_data.get('shift_type'),
                    "available_shifts": ",".join(form_data['available_shifts']) if form_data['available_shifts'] else None,
                    "benefits": ",".join(form_data['benefits']) if form_data['benefits'] else None,
                    "status": "Open", "closing_date": form_data.get('closing_date') or None
                }
                cursor.execute(sql, params)
                conn_insert.commit()
                flash('Job offer created successfully!', 'success')
                return redirect(url_for('.list_all_job_offers'))
            except Exception as e:
                if conn_insert: conn_insert.rollback()
                current_app.logger.error(f"Error creating live job offer: {e}", exc_info=True)
                flash(f'An error occurred: {e}', 'danger')
            finally:
                if conn_insert and conn_insert.is_connected():
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn_insert.close()
        else: flash('Please correct the errors shown in the form.', 'warning')
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
            if conn_dd.is_connected(): conn_dd.close()

    if request.method == 'POST':
        form_data = request.form.to_dict()
        benefits_list = request.form.getlist('benefits')
        if form_data.get('transportation') == 'yes':
            if form_data.get('transport_type') == 'd2d': benefits_list.append('Transportation (Door to Door)')
            elif form_data.get('transport_type') == 'pickup': benefits_list.append('Transportation (Pickup Points)')

        form_data['benefits'] = benefits_list
        form_data['available_shifts'] = request.form.getlist('available_shifts')
        original_title_hidden = request.form.get('original_title_hidden', form_data.get('position-title', 'Job Offer'))
        errors = validate_job_offer_data(form_data, is_staff_creation=True)
        if not errors:
            conn_update = None
            try:
                conn_update = get_db_connection()
                cursor = conn_update.cursor()
                sql = """UPDATE JobOffers SET
                            CompanyID=%(company_id)s, CategoryID=%(category_id)s, Title=%(title)s, Location=%(location)s, NetSalary=%(salary)s, PaymentTerm=%(payment_term)s, HiringPlan=%(hiring_plan)s,
                            MaxAge=%(max_age)s, HasContract=%(has_contract)s, GraduationStatusRequirement=%(grad_status)s, Nationality=%(nationality)s, RequiredLanguages=%(required_languages)s, RequiredLevel=%(required_level)s,
                            CandidatesNeeded=%(candidates_needed)s, HiringCadence=%(hiring_cadence)s, WorkLocationType=%(work_location)s, ShiftType=%(shift_type)s, AvailableShifts=%(available_shifts)s,
                            BenefitsIncluded=%(benefits)s, Status=%(status)s, ClosingDate=%(closing_date)s, UpdatedAt=NOW()
                         WHERE OfferID=%(offer_id)s"""
                nationality_mapping = {'egyptian': 'Egyptians Only', 'any': 'Foreigners & Egyptians', 'foreigner': 'Foreigners & Egyptians'}
                params = {
                    "company_id": form_data.get('company_id'), "category_id": form_data.get('category_id'),
                    "title": form_data.get('position-title'), "location": form_data.get('location'),
                    "salary": decimal.Decimal(form_data['salary']) if form_data.get('salary') else None,
                    "payment_term": form_data.get('payment_term'), "hiring_plan": form_data.get('hiring_plan'),
                    "max_age": form_data.get('max_age') or None,
                    "has_contract": 1 if form_data.get('has_contract') == 'yes' else 0,
                    "grad_status": form_data.get('grad-status'), "nationality": nationality_mapping.get(form_data.get('nationality'), 'Foreigners & Egyptians'),
                    "required_languages": form_data.get('required_language'), "required_level": form_data.get('english-level'),
                    "candidates_needed": form_data.get('candidate-count'), "hiring_cadence": form_data.get('hiring_cadence'),
                    "work_location": form_data.get('work_location'), "shift_type": form_data.get('shift_type'),
                    "available_shifts": ",".join(form_data['available_shifts']) if form_data['available_shifts'] else None,
                    "benefits": ",".join(form_data['benefits']) if form_data['benefits'] else None,
                    "status": form_data.get('status', 'Open'), "closing_date": form_data.get('closing_date') or None,
                    "offer_id": offer_id
                }
                cursor.execute(sql, params)
                conn_update.commit()
                flash('Job offer updated successfully!', 'success')
                return redirect(url_for('.list_all_job_offers'))
            except Exception as e:
                if conn_update: conn_update.rollback()
                current_app.logger.error(f"Error updating offer {offer_id}: {e}", exc_info=True)
                flash(f'An error occurred: {e}', 'danger')
            finally:
                if conn_update and conn_update.is_connected(): 
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn_update.close()
        else: flash('Please correct the form errors.', 'warning')
    else: # GET request
        conn_fetch = get_db_connection()
        if conn_fetch:
            try:
                cursor = conn_fetch.cursor(dictionary=True)
                cursor.execute("SELECT * FROM JobOffers WHERE OfferID = %s", (offer_id,))
                data = cursor.fetchone()
                if data:
                    form_data = data.copy()
                    form_data['company_id'] = data.get('CompanyID')
                    form_data['category_id'] = data.get('CategoryID')
                    form_data['position-title'] = data.get('Title')
                    form_data['location'] = data.get('Location')
                    form_data['max_age'] = data.get('MaxAge')
                    form_data['required_language'] = data.get('RequiredLanguages')
                    form_data['english-level'] = data.get('RequiredLevel')
                    form_data['candidate-count'] = data.get('CandidatesNeeded')
                    form_data['hiring_cadence'] = data.get('HiringCadence')
                    form_data['grad-status'] = data.get('GraduationStatusRequirement')
                    form_data['payment_term'] = data.get('PaymentTerm')
                    form_data['hiring_plan'] = data.get('HiringPlan')
                    form_data['work_location'] = data.get('WorkLocationType')
                    form_data['shift_type'] = data.get('ShiftType')
                    form_data['has_contract'] = 'yes' if data.get('HasContract') else 'no'
                    if data.get('Nationality') == 'Egyptians Only': form_data['nationality'] = 'egyptian'
                    else: form_data['nationality'] = 'any'
                    
                    available_shifts_str = data.get('AvailableShifts', '')
                    form_data['available_shifts'] = available_shifts_str.split(',') if available_shifts_str else []
                    
                    benefits_str = data.get('BenefitsIncluded', '')
                    benefits_list = benefits_str.split(',') if benefits_str else []
                    
                    final_benefits_for_checkboxes = []
                    form_data['transportation'] = 'no'
                    for benefit in benefits_list:
                        if benefit == 'Transportation (Door to Door)':
                            form_data['transportation'] = 'yes'
                            form_data['transport_type'] = 'd2d'
                        elif benefit == 'Transportation (Pickup Points)':
                            form_data['transportation'] = 'yes'
                            form_data['transport_type'] = 'pickup'
                        elif benefit:
                            final_benefits_for_checkboxes.append(benefit)
                    form_data['benefits'] = final_benefits_for_checkboxes
                    
                    form_data['salary'] = str(data['NetSalary']) if data.get('NetSalary') is not None else ''
                    form_data['closing_date'] = data['ClosingDate'].isoformat() if data.get('ClosingDate') and isinstance(data['ClosingDate'], datetime.date) else ''
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
        if cursor.rowcount > 0:
            flash('The job offer has been permanently deleted.', 'success')
        else:
            flash('The job offer could not be found or was already deleted.', 'warning')
    except mysql.connector.Error as e:
        if conn: conn.rollback()
        if e.errno == 1451:
            flash('Cannot delete this offer because it has active job applications. Please close the offer instead.', 'danger')
        else:
            current_app.logger.error(f"Database error deleting offer {offer_id}: {e}", exc_info=True)
            flash(f'A database error occurred. Please contact support.', 'danger')
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Generic error deleting offer {offer_id}: {e}", exc_info=True)
        flash(f'An unexpected error occurred.', 'danger')
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
        cursor.execute("""
            SELECT csjo.*, c.CompanyName, u.FirstName as SubmitterFirstName, u.LastName as SubmitterLastName 
            FROM ClientSubmittedJobOffers csjo 
            JOIN Companies c ON csjo.CompanyID = c.CompanyID 
            JOIN Users u ON csjo.SubmittedByUserID = u.UserID
            WHERE csjo.ReviewStatus IN ('Pending', 'NeedsClarification') 
            ORDER BY csjo.SubmissionDate ASC
        """)
        submissions = cursor.fetchall()
        for sub in submissions: 
            benefits_str = sub.get('Benefits', '')
            sub['Benefits_list'] = benefits_str.split(',') if benefits_str else []
            shifts_str = sub.get('AvailableShifts', '')
            sub['AvailableShifts_list'] = shifts_str.split(',') if shifts_str else []
        
        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
        categories_for_dropdown = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching submissions for review: {e}", exc_info=True)
        flash("Could not load submissions for review.", "danger")
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return render_template('agency_staff_portal/job_offers/review_client_submissions.html', title='Review Client Submissions', submissions=submissions, categories_for_dropdown=categories_for_dropdown)

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
        flash('Comments are required when rejecting or requesting clarification.', 'warning')
        return redirect(url_for('.list_review_client_submissions'))
    if action == 'approve' and not category_id_on_approval:
        flash('A job category must be selected to approve and post an offer.', 'warning')
        return redirect(url_for('.list_review_client_submissions'))

    conn = None
    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT csjo.*, c.CompanyName FROM ClientSubmittedJobOffers csjo JOIN Companies c ON csjo.CompanyID = c.CompanyID WHERE csjo.SubmissionID = %s FOR UPDATE", (submission_id,))
        sub = cursor.fetchone()
        if not sub:
            flash('Submission not found or is being processed by another user.', 'danger')
            conn.rollback()
            return redirect(url_for('.list_review_client_submissions'))

        if action == 'approve':
            sql_live = """INSERT INTO JobOffers (
                            CompanyID, PostedByStaffID, CategoryID, Title, Location, NetSalary, PaymentTerm, HiringPlan,
                            MaxAge, HasContract, GraduationStatusRequirement, Nationality, RequiredLanguages, RequiredLevel,
                            CandidatesNeeded, HiringCadence, WorkLocationType, ShiftType, AvailableShifts,
                            BenefitsIncluded, Status, ClosingDate, DatePosted
                          ) VALUES (
                            %(CompanyID)s, %(PostedByStaffID)s, %(SelectedCategoryID)s, %(Title)s, %(Location)s, %(NetSalary)s, %(PaymentTerm)s, %(HiringPlan)s,
                            %(MaxAge)s, %(HasContract)s, %(GraduationStatusRequirement)s, %(Nationality)s, %(RequiredLanguages)s, %(RequiredLevel)s,
                            %(CandidatesNeeded)s, %(HiringCadence)s, %(WorkLocationType)s, %(ShiftType)s, %(AvailableShifts)s,
                            %(Benefits)s, 'Open', %(ClosingDate)s, NOW()
                          )"""
            params_live = sub.copy()
            # Map old submission columns to new live table columns
            nationality_mapping = {'egyptian': 'Egyptians Only', 'any': 'Foreigners & Egyptians', 'foreigner': 'Foreigners & Egyptians'}
            
            benefits_from_sub = params_live.get('Benefits', '').split(',') if params_live.get('Benefits') else []
            if params_live.get('IsTransportationProvided'):
                if params_live.get('TransportationType') == 'd2d': benefits_from_sub.append('Transportation (Door to Door)')
                elif params_live.get('TransportationType') == 'pickup': benefits_from_sub.append('Transportation (Pickup Points)')

            params_live.update({
                "PostedByStaffID": current_user.specific_role_id, 
                "SelectedCategoryID": category_id_on_approval,
                "Nationality": nationality_mapping.get(sub.get('NationalityRequirement'), 'Foreigners & Egyptians'),
                "RequiredLanguages": sub.get('RequiredLanguage'),
                "RequiredLevel": sub.get('EnglishLevelRequirement'),
                "Benefits": ",".join(filter(None, benefits_from_sub)) # Join final list
            })
            
            cursor.execute(sql_live, params_live)
            live_offer_id = cursor.lastrowid
            
            cursor.execute("UPDATE ClientSubmittedJobOffers SET ReviewStatus='Approved', ReviewerUserID=%s, ReviewDate=NOW(), ReviewerComments=%s, CorrespondingOfferID=%s WHERE SubmissionID=%s", (current_user.id, reviewer_comments, live_offer_id, submission_id))
            _create_automated_announcement(cursor, 'Automated_Offer', f"New Job: {sub['Title']} with {sub['CompanyName']}", "A new job offer has been posted.", posted_by_user_id=current_user.id)
            flash('Submission approved and job offer has been posted live.', 'success')
        
        elif action == 'reject':
            cursor.execute("UPDATE ClientSubmittedJobOffers SET ReviewStatus='Rejected', ReviewerUserID=%s, ReviewDate=NOW(), ReviewerComments=%s WHERE SubmissionID=%s", (current_user.id, reviewer_comments, submission_id))
            flash('Submission has been rejected.', 'info')
        
        elif action == 'needs_clarification':
            cursor.execute("UPDATE ClientSubmittedJobOffers SET ReviewStatus='NeedsClarification', ReviewerUserID=%s, ReviewDate=NOW(), ReviewerComments=%s WHERE SubmissionID=%s", (current_user.id, reviewer_comments, submission_id))
            flash('Submission has been marked as "Needs Clarification". The client will be notified.', 'info')
        
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error processing submission {submission_id}, action {action}: {e}", exc_info=True)
        flash(f'An error occurred: {e}', 'danger')
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return redirect(url_for('.list_review_client_submissions'))

@job_offer_mgmt_bp.route('/view-live/<int:offer_id>')
@login_required_with_role(EXECUTIVE_ROLES)
def view_live_job_offer_detail(offer_id):
    offer, conn = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT jo.*, c.CompanyName, jc.CategoryName, 
                   poster_user.FirstName as PosterFirstName, poster_user.LastName as PosterLastName
            FROM JobOffers jo
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            LEFT JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID
            LEFT JOIN Staff poster_staff ON jo.PostedByStaffID = poster_staff.StaffID
            LEFT JOIN Users poster_user ON poster_staff.UserID = poster_user.UserID
            WHERE jo.OfferID = %s
        """, (offer_id,))
        offer = cursor.fetchone()
        if offer: 
            benefits_str = offer.get('BenefitsIncluded', '')
            offer['Benefits_list'] = benefits_str.split(',') if benefits_str else []
            shifts_str = offer.get('AvailableShifts', '')
            offer['AvailableShifts_list'] = shifts_str.split(',') if shifts_str else []
    except Exception as e:
        current_app.logger.error(f"Error fetching live offer detail {offer_id}: {e}", exc_info=True)
        flash("Could not load offer details.", "danger")
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    if not offer: 
        flash('Job offer not found.', 'danger'); return redirect(url_for('.list_all_job_offers'))
    return render_template('agency_staff_portal/job_offers/view_live_job_offer_detail.html', title=f"Job Offer Details", offer=offer)