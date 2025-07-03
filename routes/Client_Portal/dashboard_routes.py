# routes/Client_Portal/dashboard_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session
from flask_login import login_required, current_user
from functools import wraps
from db import get_db_connection

# Define a specific blueprint for the dashboard
client_dashboard_bp = Blueprint('client_dashboard_bp', __name__,
                                template_folder='../../../templates/client_portal',
                                url_prefix='/client')

# --- Decorator for SINGLE Company Authorization (Duplicated here) ---
def client_login_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        # Force re-check if user changes or session data is missing
        if 'client_company_id' not in session or session.get('user_id') != current_user.id:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                # Find the FIRST company this user is a contact for
                cursor.execute("""
                    SELECT c.CompanyID, c.CompanyName 
                    FROM CompanyContacts cc
                    JOIN Companies c ON cc.CompanyID = c.CompanyID
                    WHERE cc.UserID = %s 
                    LIMIT 1
                """, (current_user.id,))
                company_contact_info = cursor.fetchone()
                
                if not company_contact_info:
                    flash("You are not authorized to access the client portal.", "danger")
                    return redirect(url_for('login_bp.login'))
                
                # Store the single company's ID and Name in the session
                session['client_company_id'] = company_contact_info['CompanyID']
                session['client_company_name'] = company_contact_info['CompanyName']
                session['user_id'] = current_user.id
            except Exception as e:
                current_app.logger.error(f"Error during client auth check for User {current_user.id}: {e}")
                flash("An error occurred during authorization.", "danger")
                return redirect(url_for('login_bp.login'))
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

        return f(*args, **kwargs)
    return decorated_function


@client_dashboard_bp.route('/dashboard')
@client_login_required
def dashboard():
    """ The main dashboard for the logged-in client's SINGLE company. """
    conn = None
    company_data = None
    company_id = session.get('client_company_id')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                c.CompanyID, c.CompanyName, c.CompanyLogoURL,
                (SELECT COUNT(*) FROM ClientSubmittedJobOffers WHERE CompanyID = c.CompanyID) as TotalSubmissions,
                (SELECT COUNT(*) FROM ClientSubmittedJobOffers WHERE CompanyID = c.CompanyID AND ReviewStatus = 'Pending') as PendingSubmissions,
                (SELECT COUNT(*) FROM JobOffers WHERE CompanyID = c.CompanyID AND Status = 'Open') as LiveOffers
            FROM Companies c
            WHERE c.CompanyID = %s
        """, (company_id,))
        company_data = cursor.fetchone()
    except Exception as e:
        current_app.logger.error(f"Client Dashboard DB Error for company {company_id}: {e}")
        flash("A database error occurred while loading your dashboard.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('client_portal/dashboard.html', title="Client Dashboard", company=company_data)