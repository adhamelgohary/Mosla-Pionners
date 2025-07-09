# routes/Account_Manager_Portal/am_offer_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import decimal
import datetime

# Roles that can manage offers within the AM portal
AM_OFFER_MANAGEMENT_ROLES = ['HeadAccountManager', 'CEO', 'OperationsManager']

am_offer_mgmt_bp = Blueprint('am_offer_mgmt_bp', __name__,
                             template_folder='../../../templates',
                             url_prefix='/am-portal/offer-management')

def get_form_dependencies(cursor):
    """Fetches companies and categories needed for the form."""
    cursor.execute("SELECT CompanyID, CompanyName FROM Companies ORDER BY CompanyName")
    companies = cursor.fetchall()
    cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
    categories = cursor.fetchall()
    return companies, categories

def validate_job_offer_data(form_data, is_editing=False):
    """A more comprehensive validation helper for the offer form."""
    errors = {}
    if not form_data.get('title', '').strip():
        errors['title'] = 'Job title is required.'
    
    if not is_editing:
        company_selection_mode = form_data.get('company_selection_mode')
        # If a company_id is passed as a hidden field, we don't need to validate the radio buttons
        if not form_data.get('company_id'):
            if company_selection_mode == 'existing' and not form_data.get('selected_company_id'):
                errors['company_id'] = "You must select an existing company."
            elif company_selection_mode == 'new' and not form_data.get('new_company_name', '').strip():
                errors['new_company_name'] = "New company name cannot be empty."
            elif not company_selection_mode:
                errors['company_selection_mode'] = "Please select a company option."
    
    if not form_data.get('category_id'):
        errors['category_id'] = 'Job category is required.'
        
    return errors

@am_offer_mgmt_bp.route('/')
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def list_companies_for_offers():
    """Lists all companies with a count of their job offers."""
    conn = get_db_connection()
    companies_with_counts = []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.CompanyID, c.CompanyName, 
                   (SELECT COUNT(*) FROM JobOffers WHERE CompanyID = c.CompanyID) as OfferCount
            FROM Companies c ORDER BY c.CompanyName
        """)
        companies_with_counts = cursor.fetchall()
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('account_manager_portal/offers/list_companies.html',
                           title="Job Offer Management", companies=companies_with_counts)

@am_offer_mgmt_bp.route('/company/<int:company_id>/offers')
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def list_offers_for_company(company_id):
    """Lists all job offers for a specific company, with status filtering."""
    status_filter = request.args.get('status', 'all')
    conn = get_db_connection()
    company, offers = None, []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE CompanyID = %s", (company_id,))
        company = cursor.fetchone()
        if not company:
            flash("Company not found.", "danger")
            return redirect(url_for('.list_companies_for_offers'))
            
        sql = "SELECT OfferID, Title, Status FROM JobOffers WHERE CompanyID = %s"
        params = [company_id]
        if status_filter == 'active':
            sql += " AND Status = 'Open'"
        elif status_filter == 'inactive':
            sql += " AND Status != 'Open'"
        sql += " ORDER BY FIELD(Status, 'Open', 'On Hold', 'Closed'), Title"
        cursor.execute(sql, tuple(params))
        offers = cursor.fetchall()
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('account_manager_portal/offers/list_offers_for_company.html',
                           title=f"Offers for {company['CompanyName']}", company=company,
                           offers=offers, current_filter=status_filter)

@am_offer_mgmt_bp.route('/add-offer', methods=['GET', 'POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def add_offer():
    """Renders the form to add a new job offer."""
    errors = {}
    form_data = {}
    company = None
    
    # Check if we are adding for a specific company from the list view
    preselected_company_id = request.args.get('company_id', type=int)

    conn_data = get_db_connection()
    try:
        cursor = conn_data.cursor(dictionary=True)
        companies, categories = get_form_dependencies(cursor)
        if preselected_company_id:
            cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE CompanyID = %s", (preselected_company_id,))
            company = cursor.fetchone()
    finally:
        if conn_data and conn_data.is_connected(): conn_data.close()

    if request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['required_languages'] = request.form.getlist('required_languages')
        form_data['benefits_included'] = request.form.getlist('benefits_included')
        form_data['available_shifts'] = request.form.getlist('available_shifts')
        errors = validate_job_offer_data(form_data)
        
        if not errors:
            conn_tx = get_db_connection()
            try:
                cursor = conn_tx.cursor()
                company_id = form_data.get('company_id') # From hidden input if pre-selected
                if not company_id:
                    if form_data.get('company_selection_mode') == 'new':
                        new_company_name = form_data.get('new_company_name').strip()
                        cursor.execute("SELECT CompanyID FROM Companies WHERE CompanyName = %s", (new_company_name,))
                        if cursor.fetchone():
                            errors['new_company_name'] = f"A company named '{new_company_name}' already exists."
                            raise ValueError("Duplicate company name")
                        cursor.execute("INSERT INTO Companies (CompanyName, ManagedByStaffID) VALUES (%s, %s)", 
                                       (new_company_name, current_user.specific_role_id))
                        company_id = cursor.lastrowid
                    else:
                        company_id = form_data.get('selected_company_id')

                # Prepare parameters for SQL, providing defaults for optional fields to avoid IntegrityError
                params = {
                    "company_id": company_id,
                    "posted_by_id": current_user.specific_role_id,
                    "category_id": form_data.get('category_id'),
                    "title": form_data.get('title'),
                    "location": form_data.get('location'),
                    "net_salary": decimal.Decimal(form_data['net_salary']) if form_data.get('net_salary') else None,
                    "payment_term": form_data.get('payment_term', 'Monthly'),
                    "hiring_plan": form_data.get('hiring_plan', 'Ongoing'),
                    "max_age": int(form_data['max_age']) if form_data.get('max_age') else None,
                    "has_contract": 1 if form_data.get('has_contract') == 'yes' else 0,
                    "grad_status": form_data.get('grad_status', 'Any'),
                    "languages_type": form_data.get('languages_type'),
                    "required_languages": ",".join(form_data.get('required_languages', [])),
                    "required_level": form_data.get('required_level'),
                    "candidates_needed": int(form_data.get('candidates_needed', 1)),
                    "hiring_cadence": form_data.get('hiring_cadence', 'As needed'),
                    "work_location": form_data.get('work_location', 'On-site'),
                    "shift_type": form_data.get('shift_type', 'Fixed'),
                    "available_shifts": ",".join(form_data.get('available_shifts', [])),
                    "benefits_included": ",".join(form_data.get('benefits_included', [])),
                    "interview_type": form_data.get('interview_type'),
                    "nationality": form_data.get('nationality'),
                    "closing_date": form_data.get('closing_date') or None
                }
                
                sql = """
                    INSERT INTO JobOffers (
                        CompanyID, PostedByStaffID, CategoryID, Title, Location, NetSalary, PaymentTerm, HiringPlan,
                        MaxAge, HasContract, GraduationStatusRequirement, LanguagesType, RequiredLanguages, RequiredLevel,
                        CandidatesNeeded, HiringCadence, WorkLocationType, ShiftType, AvailableShifts,
                        BenefitsIncluded, InterviewType, Nationality, Status, ClosingDate
                    ) VALUES (
                        %(company_id)s, %(posted_by_id)s, %(category_id)s, %(title)s, %(location)s, %(net_salary)s, 
                        %(payment_term)s, %(hiring_plan)s, %(max_age)s, %(has_contract)s, %(grad_status)s,
                        %(languages_type)s, %(required_languages)s, %(required_level)s, %(candidates_needed)s, 
                        %(hiring_cadence)s, %(work_location)s, %(shift_type)s, %(available_shifts)s, 
                        %(benefits_included)s, %(interview_type)s, %(nationality)s, 'Open', %(closing_date)s
                    )
                """
                cursor.execute(sql, params)
                conn_tx.commit()
                flash(f"New job offer for '{form_data.get('title')}' created successfully!", "success")
                return redirect(url_for('.list_offers_for_company', company_id=company_id))

            except ValueError as ve: # Handles the duplicate company name check
                if conn_tx: conn_tx.rollback()
            except Exception as e:
                if conn_tx: conn_tx.rollback()
                current_app.logger.error(f"Error in add_offer: {e}", exc_info=True)
                flash(f"An error occurred while creating the offer: {e}", "danger")
            finally:
                if conn_tx and conn_tx.is_connected(): conn_tx.close()
    
    # For GET requests, pre-fill company if ID is in URL
    if preselected_company_id:
        form_data['company_id'] = preselected_company_id

    return render_template('account_manager_portal/offers/add_edit_offer.html',
                           title="Create New Job Offer", form_data=form_data, errors=errors,
                           company=company, companies=companies, categories=categories,
                           action_verb="Create", is_editing=False)


@am_offer_mgmt_bp.route('/edit-offer/<int:offer_id>', methods=['GET', 'POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def edit_offer(offer_id):
    """Provides a form to edit an existing job offer."""
    errors = {}
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM JobOffers WHERE OfferID = %s", (offer_id,))
        offer_data = cursor.fetchone()
        if not offer_data:
            flash("Job offer not found.", "danger")
            return redirect(url_for('.list_companies_for_offers'))

        companies, categories = get_form_dependencies(cursor)
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE CompanyID = %s", (offer_data['CompanyID'],))
        company = cursor.fetchone()
    finally:
        if conn and conn.is_connected(): conn.close()

    if request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['required_languages'] = request.form.getlist('required_languages')
        form_data['benefits_included'] = request.form.getlist('benefits_included')
        form_data['available_shifts'] = request.form.getlist('available_shifts')
        errors = validate_job_offer_data(form_data, is_editing=True)

        if not errors:
            conn_update = get_db_connection()
            try:
                cursor_update = conn_update.cursor()
                # Prepare parameters for SQL update
                params = {
                    "category_id": form_data.get('category_id'), "title": form_data.get('title').strip(),
                    "location": form_data.get('location'),
                    "net_salary": decimal.Decimal(form_data['net_salary']) if form_data.get('net_salary') else None,
                    "payment_term": form_data.get('payment_term'), "hiring_plan": form_data.get('hiring_plan'),
                    "max_age": int(form_data['max_age']) if form_data.get('max_age') else None,
                    "has_contract": 1 if form_data.get('has_contract') == 'yes' else 0,
                    "grad_status": form_data.get('grad_status'), "languages_type": form_data.get('languages_type'),
                    "required_languages": ",".join(form_data.get('required_languages', [])),
                    "required_level": form_data.get('required_level'),
                    "candidates_needed": int(form_data.get('candidates_needed', 1)),
                    "hiring_cadence": form_data.get('hiring_cadence'), "work_location": form_data.get('work_location'),
                    "shift_type": form_data.get('shift_type'), "available_shifts": ",".join(form_data.get('available_shifts', [])),
                    "benefits_included": ",".join(form_data.get('benefits_included', [])),
                    "interview_type": form_data.get('interview_type'), "nationality": form_data.get('nationality'),
                    "status": form_data.get('status', 'Open'),
                    "closing_date": form_data.get('closing_date') or None, "offer_id": offer_id
                }
                sql = """
                    UPDATE JobOffers SET
                        CategoryID=%(category_id)s, Title=%(title)s, Location=%(location)s, NetSalary=%(net_salary)s, PaymentTerm=%(payment_term)s, HiringPlan=%(hiring_plan)s,
                        MaxAge=%(max_age)s, HasContract=%(has_contract)s, GraduationStatusRequirement=%(grad_status)s, LanguagesType=%(languages_type)s, 
                        RequiredLanguages=%(required_languages)s, RequiredLevel=%(required_level)s, CandidatesNeeded=%(candidates_needed)s, 
                        HiringCadence=%(hiring_cadence)s, WorkLocationType=%(work_location)s, ShiftType=%(shift_type)s, 
                        AvailableShifts=%(available_shifts)s, BenefitsIncluded=%(benefits_included)s, InterviewType=%(interview_type)s, 
                        Nationality=%(nationality)s, Status=%(status)s, ClosingDate=%(closing_date)s, UpdatedAt=NOW()
                    WHERE OfferID = %(offer_id)s
                """
                cursor_update.execute(sql, params)
                conn_update.commit()
                flash(f"Job offer '{params['title']}' updated successfully.", "success")
                return redirect(url_for('.list_offers_for_company', company_id=company['CompanyID']))
            except Exception as e:
                if conn_update: conn_update.rollback()
                current_app.logger.error(f"Error updating offer {offer_id}: {e}", exc_info=True)
                flash(f"An error occurred while updating the offer: {e}", "danger")
            finally:
                if conn_update and conn_update.is_connected(): conn_update.close()
        
        form_data_for_template = form_data
    
    else: # GET request, populate form from DB
        form_data_for_template = offer_data
        for key in ['RequiredLanguages', 'BenefitsIncluded', 'AvailableShifts']:
            template_key = key.lower().replace('d', '_d', 1) # e.g., RequiredLanguages -> required_languages
            value = offer_data.get(key)
            if isinstance(value, (bytes, str)):
                form_data_for_template[template_key] = value.split(',') if value else []
            elif isinstance(value, set):
                 form_data_for_template[template_key] = list(value)
            else:
                 form_data_for_template[template_key] = []

        if offer_data.get('ClosingDate'):
            form_data_for_template['closing_date'] = offer_data['ClosingDate'].isoformat()
        else:
            form_data_for_template['closing_date'] = ''
        
    return render_template('account_manager_portal/offers/add_edit_offer.html',
                           title=f"Edit Offer: {offer_data.get('Title', 'N/A')}",
                           form_data=form_data_for_template, errors=errors,
                           company=company, categories=categories, 
                           action_verb="Update", is_editing=True, offer_id=offer_id)


@am_offer_mgmt_bp.route('/offer/<int:offer_id>/action', methods=['POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def handle_offer_action(offer_id):
    """Handles actions for a job offer: activate, deactivate, and delete."""
    action = request.form.get('action')
    company_id_redirect = request.form.get('company_id')
    if not company_id_redirect:
        flash("An error occurred: Missing company context.", "danger")
        return redirect(url_for('.list_companies_for_offers'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if action == 'activate':
            cursor.execute("UPDATE JobOffers SET Status = 'Open', UpdatedAt = NOW() WHERE OfferID = %s", (offer_id,))
            flash("Job offer has been activated.", "success")
        elif action == 'deactivate':
            cursor.execute("UPDATE JobOffers SET Status = 'Closed', UpdatedAt = NOW() WHERE OfferID = %s", (offer_id,))
            flash("Job offer has been deactivated.", "info")
        elif action == 'delete':
            cursor.execute("SELECT COUNT(*) FROM JobApplications WHERE OfferID = %s", (offer_id,))
            if cursor.fetchone()[0] > 0:
                flash("Cannot delete this offer because it has associated applications.", "danger")
            else:
                cursor.execute("DELETE FROM JobOffers WHERE OfferID = %s", (offer_id,))
                if cursor.rowcount > 0:
                    flash("Job offer has been permanently deleted.", "success")
                else:
                    flash("Job offer could not be found to delete.", "warning")
        else:
            flash("Invalid action specified.", "warning")
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error processing offer action '{action}' for OfferID {offer_id}: {e}", exc_info=True)
        flash("A database error occurred while processing the action.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_offers_for_company', company_id=company_id_redirect))