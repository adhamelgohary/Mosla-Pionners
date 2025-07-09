# routes/Account_Manager_Portal/am_offer_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import decimal

# Roles that can manage offers within the AM portal (e.g., create, edit)
AM_OFFER_MANAGEMENT_ROLES = ['HeadAccountManager', 'CEO', 'OperationsManager']

am_offer_mgmt_bp = Blueprint('am_offer_mgmt_bp', __name__,
                             template_folder='../../../templates',
                             url_prefix='/am-portal/offer-management')

@am_offer_mgmt_bp.route('/')
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def list_company_offers():
    """
    Shows a list of all companies and their offers, primarily for Head AMs to get an overview
    and to select a company for which to add a new offer.
    """
    conn = get_db_connection()
    companies_data = []
    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch all companies, as executives can see everything.
        # A HeadAccountManager would see companies managed by their team.
        # For simplicity, we'll show all for now. A hierarchical filter can be added.
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies ORDER BY CompanyName")
        companies = cursor.fetchall()
        
        for company in companies:
            cursor.execute("SELECT OfferID, Title, Status FROM JobOffers WHERE CompanyID = %s", (company['CompanyID'],))
            company['offers'] = cursor.fetchall()
            companies_data.append(company)
            
    except Exception as e:
        current_app.logger.error(f"Error loading companies for offer management: {e}", exc_info=True)
        flash("Could not load company and offer data.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('account_manager_portal/list_company_offers.html',
                           title="Job Offer Management",
                           companies_data=companies_data)


@am_offer_mgmt_bp.route('/add-offer/for-company/<int:company_id>', methods=['GET', 'POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def add_offer_for_company(company_id):
    """
    Provides a form to add a new job offer for a specific company.
    """
    errors = {}
    form_data = {}
    conn = get_db_connection()
    company = None
    categories = []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE CompanyID = %s", (company_id,))
        company = cursor.fetchone()
        if not company:
            flash("Company not found.", "danger")
            return redirect(url_for('.list_company_offers'))

        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
        categories = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error loading data for add offer page: {e}", exc_info=True)
        flash("Could not load required data.", "danger")
        return redirect(url_for('.list_company_offers'))
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    if request.method == 'POST':
        form_data = request.form.to_dict()
        # Basic validation (can be expanded)
        if not form_data.get('title').strip(): errors['title'] = "Job title is required."
        if not form_data.get('category_id'): errors['category_id'] = "Category is required."

        if not errors:
            conn_insert = get_db_connection()
            try:
                cursor_insert = conn_insert.cursor()
                sql = """
                    INSERT INTO JobOffers (
                        CompanyID, PostedByStaffID, CategoryID, Title, Location, NetSalary, Status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                salary = decimal.Decimal(form_data['net_salary']) if form_data.get('net_salary') else None
                params = (
                    company_id,
                    current_user.specific_role_id,
                    form_data.get('category_id'),
                    form_data.get('title').strip(),
                    form_data.get('location'),
                    salary,
                    form_data.get('status', 'Open')
                )
                cursor_insert.execute(sql, params)
                conn_insert.commit()
                flash(f"New job offer '{form_data.get('title')}' created successfully for {company['CompanyName']}.", "success")
                return redirect(url_for('account_manager_bp.view_single_company', company_id=company_id))

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


@am_offer_mgmt_bp.route('/delete-offer/<int:offer_id>', methods=['POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def delete_offer(offer_id):
    """ Deletes a job offer. """
    company_id_redirect = request.form.get('company_id')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Check for related applications first to prevent DB errors
        cursor.execute("SELECT COUNT(*) FROM JobApplications WHERE OfferID = %s", (offer_id,))
        if cursor.fetchone()[0] > 0:
            flash("Cannot delete this offer because it has active applications. Please close or put the offer on hold instead.", "danger")
        else:
            cursor.execute("DELETE FROM JobOffers WHERE OfferID = %s", (offer_id,))
            conn.commit()
            if cursor.rowcount > 0:
                flash("Job offer has been permanently deleted.", "success")
            else:
                flash("Job offer could not be found.", "warning")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deleting offer {offer_id}: {e}", exc_info=True)
        flash("An error occurred while deleting the offer.", "danger")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

    if company_id_redirect:
        return redirect(url_for('account_manager_bp.view_single_company', company_id=company_id_redirect))
    return redirect(url_for('.list_company_offers'))

# In am_offer_mgmt_routes.py, add these two new routes.

@am_offer_mgmt_bp.route('/offer/<int:offer_id>/activate', methods=['POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def activate_offer(offer_id):
    """Sets a job offer's status to 'Open'."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE JobOffers SET Status = 'Open', UpdatedAt = NOW() WHERE OfferID = %s", (offer_id,))
        conn.commit()
        flash("Job offer has been activated and is now live.", "success")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error activating offer {offer_id}: {e}", exc_info=True)
        flash("An error occurred while activating the offer.", "danger")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
    return redirect(url_for('.list_company_offers'))


@am_offer_mgmt_bp.route('/offer/<int:offer_id>/deactivate', methods=['POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def deactivate_offer(offer_id):
    """Sets a job offer's status to 'Closed' or 'On Hold'."""
    # For now, we'll use 'Closed' as the deactivated status.
    # You could pass a status in the form if you want both 'Closed' and 'On Hold'.
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE JobOffers SET Status = 'Closed', UpdatedAt = NOW() WHERE OfferID = %s", (offer_id,))
        conn.commit()
        flash("Job offer has been deactivated.", "info")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deactivating offer {offer_id}: {e}", exc_info=True)
        flash("An error occurred while deactivating the offer.", "danger")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
    return redirect(url_for('.list_company_offers'))