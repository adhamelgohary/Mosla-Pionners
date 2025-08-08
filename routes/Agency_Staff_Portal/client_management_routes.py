# routes/Agency_Staff_Portal/client_management_routes.py

from flask import Blueprint, abort, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role, MANAGERIAL_PORTAL_ROLES
from db import get_db_connection
import mysql.connector

client_mgmt_bp = Blueprint('client_mgmt_bp', __name__,
                           template_folder='../../../templates',
                           url_prefix='/managerial/clients')

@client_mgmt_bp.route('/')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def list_companies():
    """Displays a list of all companies and their primary contacts."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # This query joins companies with contacts to see which ones have a registered user.
    cursor.execute("""
        SELECT 
            c.CompanyID, c.CompanyName, c.CompanyWebsite, c.Industry,
            u.FirstName AS ContactFirstName, u.LastName AS ContactLastName, u.Email AS ContactEmail
        FROM Companies c
        LEFT JOIN CompanyContacts cc ON c.CompanyID = cc.CompanyID AND cc.IsPrimaryContact = 1
        LEFT JOIN Users u ON cc.UserID = u.UserID
        ORDER BY c.CompanyName ASC
    """)
    companies = cursor.fetchall()

    # Get a count of pending client registrations for a notification badge
    cursor.execute("SELECT COUNT(RegistrationID) as pending_count FROM ClientRegistrations WHERE Status = 'Pending'")
    pending_count = cursor.fetchone()['pending_count']
    
    conn.close()
    return render_template('agency_staff_portal/clients/manage_companies.html',
                           title="Manage Companies",
                           companies=companies,
                           pending_count=pending_count)

@client_mgmt_bp.route('/review-registrations')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def review_client_registrations():
    """Displays a list of pending client registration applications."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            cr.RegistrationID, cr.CompanyName, cr.CreatedAt,
            u.FirstName, u.LastName, u.Email
        FROM ClientRegistrations cr
        JOIN Users u ON cr.UserID = u.UserID
        WHERE cr.Status = 'Pending'
        ORDER BY cr.CreatedAt ASC
    """)
    pending_registrations = cursor.fetchall()
    conn.close()
    return render_template('agency_staff_portal/clients/review_registrations.html',
                           title="Review Client Registrations",
                           pending_registrations=pending_registrations)

@client_mgmt_bp.route('/registrations/<int:reg_id>/approve', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def approve_client_registration(reg_id):
    """Approves a client registration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Get application details
        cursor.execute("SELECT * FROM ClientRegistrations WHERE RegistrationID = %s AND Status = 'Pending'", (reg_id,))
        app_data = cursor.fetchone()

        if not app_data:
            flash("Registration not found or already processed.", "warning")
            return redirect(url_for('.review_client_registrations'))

        # Check if company already exists, otherwise create it
        cursor.execute("SELECT CompanyID FROM Companies WHERE CompanyName = %s", (app_data['CompanyName'],))
        company = cursor.fetchone()
        if company:
            company_id = company['CompanyID']
        else:
            cursor.execute("INSERT INTO Companies (CompanyName, CompanyWebsite, Industry) VALUES (%s, %s, %s)",
                           (app_data['CompanyName'], app_data['CompanyWebsite'], app_data['Industry']))
            company_id = cursor.lastrowid
        
        # Create the contact link
        cursor.execute("INSERT INTO CompanyContacts (UserID, CompanyID, IsPrimaryContact) VALUES (%s, %s, 1)",
                       (app_data['UserID'], company_id))

        # Activate the user
        cursor.execute("UPDATE Users SET AccountStatus = 'Active' WHERE UserID = %s", (app_data['UserID'],))

        # Update the registration record
        cursor.execute("""
            UPDATE ClientRegistrations SET Status = 'Approved', ReviewedByStaffID = %s, ReviewedAt = NOW(), ApprovedCompanyID = %s
            WHERE RegistrationID = %s
        """, (current_user.specific_role_id, company_id, reg_id))

        conn.commit()
        flash(f"Client registration for '{app_data['CompanyName']}' has been approved.", "success")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error approving client registration {reg_id}: {e}")
        flash("An error occurred during approval.", "danger")
    finally:
        if conn: conn.close()

    return redirect(url_for('.review_client_registrations'))

@client_mgmt_bp.route('/registrations/<int:reg_id>/reject', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def reject_client_registration(reg_id):
    """Rejects a client registration."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT UserID FROM ClientRegistrations WHERE RegistrationID = %s", (reg_id,))
        app_data = cursor.fetchone()

        if app_data:
            cursor.execute("UPDATE Users SET AccountStatus = 'Inactive' WHERE UserID = %s", (app_data['UserID'],))

        cursor.execute("""
            UPDATE ClientRegistrations SET Status = 'Rejected', ReviewedByStaffID = %s, ReviewedAt = NOW()
            WHERE RegistrationID = %s
        """, (current_user.specific_role_id, reg_id))
        
        conn.commit()
        flash("Client registration has been rejected.", "info")
    except Exception as e:
        if conn: conn.rollback()
        flash("An error occurred.", "danger")
    finally:
        if conn: conn.close()
        
    return redirect(url_for('.review_client_registrations'))

@client_mgmt_bp.route('/add-company', methods=['GET', 'POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def add_company():
    """Allows a manager to manually add a new company."""
    if request.method == 'POST':
        company_name = request.form.get('company_name').strip()
        if not company_name:
            flash("Company Name is required.", "danger")
            return render_template('agency_staff_portal/clients/add_edit_company.html', title="Add New Company", form_data=request.form)

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Companies (CompanyName, CompanyWebsite, Industry, Address, Description) VALUES (%s, %s, %s, %s, %s)",
                           (company_name, request.form.get('company_website'), request.form.get('industry'), request.form.get('address'), request.form.get('description')))
            conn.commit()
            flash(f"Company '{company_name}' created successfully.", "success")
            return redirect(url_for('.list_companies'))
        except mysql.connector.Error as err:
            if err.errno == 1062: # Duplicate entry
                flash("A company with this name already exists.", "danger")
            else:
                flash("A database error occurred.", "danger")
        finally:
            if conn: conn.close()
            
    return render_template('agency_staff_portal/clients/add_edit_company.html', title="Add New Company")

@client_mgmt_bp.route('/edit-company/<int:company_id>', methods=['GET', 'POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def edit_company(company_id):
    """Allows a manager to edit an existing company's details."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        company_name = request.form.get('company_name').strip()
        if not company_name:
            flash("Company Name is required.", "danger")
            return redirect(url_for('.edit_company', company_id=company_id))

        try:
            cursor.execute("""
                UPDATE Companies SET CompanyName = %s, CompanyWebsite = %s, Industry = %s, Address = %s, Description = %s
                WHERE CompanyID = %s
            """, (company_name, request.form.get('company_website'), request.form.get('industry'), request.form.get('address'), request.form.get('description'), company_id))
            conn.commit()
            flash(f"Company '{company_name}' updated successfully.", "success")
            return redirect(url_for('.list_companies'))
        except mysql.connector.Error as err:
            flash("A database error occurred.", "danger")
        finally:
            if conn: conn.close()
    
    cursor.execute("SELECT * FROM Companies WHERE CompanyID = %s", (company_id,))
    company = cursor.fetchone()
    conn.close()
    if not company:
        abort(404)
        
    return render_template('agency_staff_portal/clients/add_edit_company.html', title="Edit Company", company=company)

@client_mgmt_bp.route('/delete-company/<int:company_id>', methods=['POST'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def delete_company(company_id):
    """Deletes a company and all its associated data (contacts, job offers, etc.)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # The database's ON DELETE CASCADE constraints will handle associated records.
        cursor.execute("DELETE FROM Companies WHERE CompanyID = %s", (company_id,))
        conn.commit()
        flash("Company and all associated data have been permanently deleted.", "success")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deleting company with ID {company_id}: {e}")
        flash("An error occurred while trying to delete the company.", "danger")
    finally:
        if conn: conn.close()
    
    return redirect(url_for('.list_companies'))