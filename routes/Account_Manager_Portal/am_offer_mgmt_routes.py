# routes/Account_Manager_Portal/am_offer_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import decimal

# Roles that can manage offers within the AM portal
AM_OFFER_MANAGEMENT_ROLES = ['HeadAccountManager', 'CEO', 'OperationsManager']

am_offer_mgmt_bp = Blueprint('am_offer_mgmt_bp', __name__,
                             template_folder='../../../templates',
                             url_prefix='/am-portal/offer-management')

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

    return render_template('account_manager_portal/offers/list_companies.html',
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

    return render_template('account_manager_portal/offers/list_offers_for_company.html',
                           title=f"Offers for {company['CompanyName']}",
                           company=company,
                           offers=offers,
                           current_filter=status_filter)


# The 'add_offer_for_company' route remains largely the same, but we update the redirect
@am_offer_mgmt_bp.route('/add-offer/for-company/<int:company_id>', methods=['GET', 'POST'])
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def add_offer_for_company(company_id):
    # ... (The entire logic for GET and POST remains the same)
    # The only change is the final redirect on success:
    # return redirect(url_for('.list_company_offers'))
    # becomes:
    # return redirect(url_for('.list_offers_for_company', company_id=company_id))
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
            return redirect(url_for('.list_companies_for_offers'))
        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
        categories = cursor.fetchall()
    except Exception as e:
        flash("Could not load required data.", "danger")
        return redirect(url_for('.list_companies_for_offers'))
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
    if request.method == 'POST':
        # ... validation logic ...
        if not errors:
            # ... database insertion logic ...
            flash("New job offer created successfully.", "success")
            # --- THIS IS THE UPDATED REDIRECT ---
            return redirect(url_for('.list_offers_for_company', company_id=company_id))
    return render_template('account_manager_portal/offers/add_edit_offer.html',
                           title=f"Add Offer for {company['CompanyName']}",
                           form_data=form_data, errors=errors, company=company,
                           categories=categories, action_verb="Create")


# The activate, deactivate, and delete routes now redirect back to the specific company's offer list
@am_offer_mgmt_bp.route('/offer/<int:offer_id>/<action>')
@login_required_with_role(AM_OFFER_MANAGEMENT_ROLES)
def set_offer_status(offer_id, action):
    # ... (This can be a combined route for activate/deactivate) ...
    # On success, it should redirect back to the company page. To do that,
    # we need the company_id, which we can get with one more query.
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT CompanyID FROM JobOffers WHERE OfferID = %s", (offer_id,))
        result = cursor.fetchone()
        if not result:
            flash("Offer not found.", "warning")
            return redirect(url_for('.list_companies_for_offers'))
        company_id_redirect = result['CompanyID']
        
        if action == 'activate':
            new_status = 'Open'
            message = "Job offer has been activated."
        elif action == 'deactivate':
            new_status = 'Closed'
            message = "Job offer has been deactivated."
        else:
            flash("Invalid action.", "danger")
            return redirect(url_for('.list_offers_for_company', company_id=company_id_redirect))

        cursor.execute("UPDATE JobOffers SET Status = %s WHERE OfferID = %s", (new_status, offer_id))
        conn.commit()
        flash(message, "success")
    except Exception as e:
        flash("An error occurred.", "danger")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
    return redirect(url_for('.list_offers_for_company', company_id=company_id_redirect))