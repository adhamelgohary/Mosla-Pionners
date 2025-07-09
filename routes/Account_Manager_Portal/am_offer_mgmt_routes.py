# routes/Account_Manager_Portal/am_offer_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import mysql.connector
import decimal

# Roles that can manage offers within the AM portal
AM_OFFER_MANAGEMENT_ROLES = ['HeadAccountManager', 'CEO', 'OperationsManager']

am_offer_mgmt_bp = Blueprint('am_offer_mgmt_bp', __name__,
                             template_folder='../../../templates',
                             url_prefix='/am-portal/offer-management')

def validate_job_offer_data(form_data):
    errors = {}
    if not form_data.get('title', '').strip(): errors['title'] = 'Job title is required.'
    if not form_data.get('company_id'): errors['company_id'] = 'Company is required.'
    if not form_data.get('category_id'): errors['category_id'] = 'Job category is required.'
    # Add more validation as needed...
    return errors

@am_offer_mgmt_bp.route('/')
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def list_companies_for_offers():
    """
    Displays a list of all companies, each with a count of their associated offers.
    This is the new entry point for offer management.
    """
    conn = get_db_connection()
    companies_with_counts = []
    try:
        cursor = conn.cursor(dictionary=True)
        # Query to get companies and the count of their total offers
        cursor.execute("""
            SELECT 
                c.CompanyID, 
                c.CompanyName,
                (SELECT COUNT(*) FROM JobOffers WHERE CompanyID = c.CompanyID) as OfferCount
            FROM Companies c
            ORDER BY c.CompanyName
        """)
        companies_with_counts = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error loading companies for offer management: {e}", exc_info=True)
        flash("Could not load company data.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('account_manager_portal/list_companies.html',
                           title="Job Offer Management",
                           companies=companies_with_counts)


# --- NEW: DEDICATED ROUTE FOR A SINGLE COMPANY'S OFFERS ---
@am_offer_mgmt_bp.route('/company/<int:company_id>/offers')
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def list_offers_for_company(company_id):
    """
    Displays a list of all job offers for a single company, with filtering.
    """
    # Get the status filter from the URL query string (e.g., ?status=Open)
    status_filter = request.args.get('status', 'all')
    
    conn = get_db_connection()
    company = None
    offers = []
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 1. Get Company Details
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE CompanyID = %s", (company_id,))
        company = cursor.fetchone()
        if not company:
            flash("Company not found.", "danger")
            return redirect(url_for('.list_companies_for_offers'))

        # 2. Build the query for offers with an optional status filter
        sql = "SELECT OfferID, Title, Status FROM JobOffers WHERE CompanyID = %s"
        params = [company_id]
        
        if status_filter == 'active':
            sql += " AND Status = 'Open'"
        elif status_filter == 'inactive':
            sql += " AND Status != 'Open'"
            
        sql += " ORDER BY FIELD(Status, 'Open', 'On Hold', 'Closed'), Title"
        
        cursor.execute(sql, tuple(params))
        offers = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error loading offers for company {company_id}: {e}", exc_info=True)
        flash("Could not load offer data.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('account_manager_portal/list_offers_for_company.html',
                           title=f"Offers for {company['CompanyName']}",
                           company=company,
                           offers=offers,
                           current_filter=status_filter)



@am_offer_mgmt_bp.route('/add-offer/for-company/<int:company_id>', methods=['GET', 'POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def add_offer_for_company(company_id):
    """
    Provides a comprehensive form to add a new job offer for a specific company,
    reflecting all the detailed fields in the database schema.
    """
    errors, form_data = {}, {}
    conn = get_db_connection()
    company, categories = None, []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE CompanyID = %s", (company_id,))
        company = cursor.fetchone()
        if not company:
            flash("Company not found.", "danger")
            return redirect(url_for('.list_companies_for_offers'))
        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
        categories = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error loading data for add offer page: {e}", exc_info=True)
        flash("Could not load required data.", "danger")
        return redirect(url_for('.list_companies_for_offers'))
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    if request.method == 'POST':
        form_data = request.form.to_dict()
        # Handle multi-select fields
        form_data['available_shifts'] = request.form.getlist('available_shifts')
        form_data['benefits'] = request.form.getlist('benefits')
        
        # Add company_id for validation
        form_data['company_id'] = company_id
        errors = validate_job_offer_data(form_data)

        if not errors:
            conn_insert = get_db_connection()
            try:
                cursor_insert = conn_insert.cursor()
                sql = """
                    INSERT INTO JobOffers (
                        CompanyID, PostedByStaffID, CategoryID, Title, Location, NetSalary, PaymentTerm, HiringPlan,
                        MaxAge, HasContract, GraduationStatusRequirement, NationalityRequirement, RequiredLanguage, 
                        EnglishLevelRequirement, CandidatesNeeded, HiringCadence, WorkLocationType, ShiftType, 
                        AvailableShifts, Benefits, IsTransportationProvided, TransportationType, Status, ClosingDate
                    ) VALUES (
                        %(company_id)s, %(posted_by_id)s, %(category_id)s, %(title)s, %(location)s, %(net_salary)s, 
                        %(payment_term)s, %(hiring_plan)s, %(max_age)s, %(has_contract)s, %(grad_status)s, 
                        %(nationality_req)s, %(req_lang)s, %(eng_level)s, %(candidates_needed)s, %(hiring_cadence)s, 
                        %(work_location)s, %(shift_type)s, %(available_shifts)s, %(benefits)s, %(transport_provided)s, 
                        %(transport_type)s, 'Open', %(closing_date)s
                    )
                """
                
                params = {
                    "company_id": company_id,
                    "posted_by_id": current_user.specific_role_id,
                    "category_id": form_data.get('category_id'),
                    "title": form_data.get('title').strip(),
                    "location": form_data.get('location'),
                    "net_salary": decimal.Decimal(form_data['net_salary']) if form_data.get('net_salary') else None,
                    "payment_term": form_data.get('payment_term'),
                    "hiring_plan": form_data.get('hiring_plan'),
                    "max_age": int(form_data['max_age']) if form_data.get('max_age') else None,
                    "has_contract": 1 if form_data.get('has_contract') == 'yes' else 0,
                    "grad_status": form_data.get('grad_status'),
                    "nationality_req": form_data.get('nationality_req'),
                    "req_lang": form_data.get('req_lang'),
                    "eng_level": form_data.get('eng_level'),
                    "candidates_needed": int(form_data['candidates_needed']) if form_data.get('candidates_needed') else 1,
                    "hiring_cadence": form_data.get('hiring_cadence'),
                    "work_location": form_data.get('work_location'),
                    "shift_type": form_data.get('shift_type'),
                    "available_shifts": ",".join(form_data.get('available_shifts', [])),
                    "benefits": ",".join(form_data.get('benefits', [])),
                    "transport_provided": 1 if form_data.get('transportation') == 'yes' else 0,
                    "transport_type": form_data.get('transport_type') if form_data.get('transportation') == 'yes' else None,
                    "closing_date": form_data.get('closing_date') or None
                }
                
                cursor_insert.execute(sql, params)
                conn_insert.commit()
                flash(f"New job offer '{form_data.get('title')}' created successfully for {company['CompanyName']}.", "success")
                return redirect(url_for('.list_offers_for_company', company_id=company_id))

            except Exception as e:
                if 'conn_insert' in locals(): conn_insert.rollback()
                current_app.logger.error(f"Error adding new offer for company {company_id}: {e}", exc_info=True)
                flash("An error occurred while adding the offer.", "danger")
            finally:
                if 'conn_insert' in locals() and conn_insert.is_connected():
                    cursor_insert.close()
                    conn_insert.close()
    
    return render_template('account_manager_portal/add_edit_offer.html',
                           title=f"Add Offer for {company['CompanyName']}",
                           form_data=form_data,
                           errors=errors,
                           company=company,
                           categories=categories,
                           action_verb="Create")


# --- ADD THIS NEW, CONSOLIDATED FUNCTION ---
@am_offer_mgmt_bp.route('/offer/<int:offer_id>/action', methods=['POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def handle_offer_action(offer_id):
    """Handles all actions for a job offer: activate, deactivate, and delete."""
    
    action = request.form.get('action')
    # Get company_id from the form for a reliable redirect
    company_id_redirect = request.form.get('company_id')

    if not company_id_redirect:
        flash("An error occurred: Missing company context.", "danger")
        return redirect(url_for('.list_companies_for_offers'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Perform action based on the form value
        if action == 'activate':
            cursor.execute("UPDATE JobOffers SET Status = 'Open', UpdatedAt = NOW() WHERE OfferID = %s", (offer_id,))
            flash("Job offer has been activated.", "success")
        
        elif action == 'deactivate':
            cursor.execute("UPDATE JobOffers SET Status = 'Closed', UpdatedAt = NOW() WHERE OfferID = %s", (offer_id,))
            flash("Job offer has been deactivated.", "info")
        
        elif action == 'delete':
            # Check for related applications first to prevent DB errors
            cursor.execute("SELECT COUNT(*) FROM JobApplications WHERE OfferID = %s", (offer_id,))
            if cursor.fetchone()[0] > 0:
                flash("Cannot delete this offer because it has active applications. Please close the offer instead.", "danger")
            else:
                cursor.execute("DELETE FROM JobOffers WHERE OfferID = %s", (offer_id,))
                if cursor.rowcount > 0:
                    flash("Job offer has been permanently deleted.", "success")
                else:
                    flash("Job offer could not be found.", "warning")
        else:
            flash("Invalid action specified.", "warning")
            
        conn.commit()

    except mysql.connector.Error as e:
        if conn: conn.rollback()
        # Handle foreign key constraint error specifically for delete
        if action == 'delete' and hasattr(e, 'errno') and e.errno == 1451:
             flash('Cannot delete this offer as it is linked to other records.', 'danger')
        else:
            current_app.logger.error(f"DB Error processing offer action '{action}' for OfferID {offer_id}: {e}", exc_info=True)
            flash("A database error occurred.", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error processing offer action '{action}' for OfferID {offer_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return redirect(url_for('.list_offers_for_company', company_id=company_id_redirect))

# --- FULLY IMPLEMENTED `edit_offer` ROUTE ---
@am_offer_mgmt_bp.route('/edit-offer/<int:offer_id>', methods=['GET', 'POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def edit_offer(offer_id):
    errors, form_data = {}, {}
    conn = get_db_connection()
    
    # Fetch existing data for GET request
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM JobOffers WHERE OfferID = %s", (offer_id,))
        offer_data = cursor.fetchone()
        if not offer_data:
            flash("Job offer not found.", "danger")
            return redirect(url_for('.list_companies_for_offers'))

        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE CompanyID = %s", (offer_data['CompanyID'],))
        company = cursor.fetchone()
        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
        categories = cursor.fetchall()
    except Exception as e:
        flash("Error loading offer data for editing.", "danger")
        if conn.is_connected(): conn.close()
        return redirect(url_for('.list_companies_for_offers'))

    if request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['available_shifts'] = request.form.getlist('available_shifts')
        form_data['benefits'] = request.form.getlist('benefits')
        # Here you would call your validation function
        # errors = validate_job_offer_data(form_data)
        
        if not errors:
            try:
                # Use a new connection for the update transaction
                conn_update = get_db_connection()
                cursor_update = conn_update.cursor()
                sql = """
                    UPDATE JobOffers SET
                        CategoryID=%(category_id)s, Title=%(title)s, Location=%(location)s, NetSalary=%(net_salary)s, 
                        PaymentTerm=%(payment_term)s, HiringPlan=%(hiring_plan)s, MaxAge=%(max_age)s, 
                        HasContract=%(has_contract)s, GraduationStatusRequirement=%(grad_status)s, 
                        NationalityRequirement=%(nationality_req)s, RequiredLanguage=%(req_lang)s, 
                        EnglishLevelRequirement=%(eng_level)s, CandidatesNeeded=%(candidates_needed)s, 
                        HiringCadence=%(hiring_cadence)s, WorkLocationType=%(work_location)s, 
                        ShiftType=%(shift_type)s, AvailableShifts=%(available_shifts)s, Benefits=%(benefits)s, 
                        IsTransportationProvided=%(transport_provided)s, TransportationType=%(transport_type)s, 
                        Status=%(status)s, ClosingDate=%(closing_date)s, UpdatedAt=NOW()
                    WHERE OfferID = %(offer_id)s
                """
                params = {
                    "category_id": form_data.get('category_id'),
                    "title": form_data.get('title').strip(),
                    "location": form_data.get('location'),
                    "net_salary": decimal.Decimal(form_data['net_salary']) if form_data.get('net_salary') else None,
                    "payment_term": form_data.get('payment_term'),
                    "hiring_plan": form_data.get('hiring_plan'),
                    "max_age": int(form_data['max_age']) if form_data.get('max_age') else None,
                    "has_contract": 1 if form_data.get('has_contract') == 'yes' else 0,
                    "grad_status": form_data.get('grad_status'),
                    "nationality_req": form_data.get('nationality_req'),
                    "req_lang": form_data.get('req_lang'),
                    "eng_level": form_data.get('eng_level'),
                    "candidates_needed": int(form_data['candidates_needed']) if form_data.get('candidates_needed') else 1,
                    "hiring_cadence": form_data.get('hiring_cadence'),
                    "work_location": form_data.get('work_location'),
                    "shift_type": form_data.get('shift_type'),
                    "available_shifts": ",".join(form_data.get('available_shifts', [])),
                    "benefits": ",".join(form_data.get('benefits', [])),
                    "transport_provided": 1 if form_data.get('transportation') == 'yes' else 0,
                    "transport_type": form_data.get('transport_type') if form_data.get('transportation') == 'yes' else None,
                    "status": form_data.get('status', 'Open'),
                    "closing_date": form_data.get('closing_date') or None,
                    "offer_id": offer_id
                }
                cursor_update.execute(sql, params)
                conn_update.commit()
                flash(f"Job offer '{form_data.get('title')}' updated successfully.", "success")
                return redirect(url_for('.list_offers_for_company', company_id=company['CompanyID']))
            except Exception as e:
                if 'conn_update' in locals(): conn_update.rollback()
                flash("An error occurred while updating the offer.", "danger")
            finally:
                if 'conn_update' in locals() and conn_update.is_connected():
                    cursor_update.close()
                    conn_update.close()
    
    # For GET request, populate form_data from the fetched offer
    if request.method == 'GET':
        form_data = offer_data
        # Convert SET fields to lists for the template checkboxes
        form_data['available_shifts'] = list(offer_data.get('AvailableShifts', [])) if offer_data.get('AvailableShifts') else []
        form_data['benefits'] = list(offer_data.get('Benefits', [])) if offer_data.get('Benefits') else []
        # Format date for the date input
        if offer_data.get('ClosingDate'):
            form_data['closing_date'] = offer_data['ClosingDate'].isoformat()
        
    return render_template('account_manager_portal/add_edit_offer.html',
                           title=f"Edit Offer: {offer_data['Title']}",
                           form_data=form_data, errors=errors, company=company,
                           categories=categories, action_verb="Update", is_editing=True, offer_id=offer_id)