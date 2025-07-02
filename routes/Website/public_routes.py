# routes/public_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session
from db import get_db_connection
import datetime

public_routes_bp = Blueprint('public_routes_bp', __name__,
                             template_folder='../../templates')

# === HOMEPAGE ROUTE ===
@public_routes_bp.route('/')
def home_page():
    current_app.logger.info(f"Accessing homepage. Current theme: {session.get('theme', current_app.config.get('DEFAULT_THEME', 'light'))}")
    recent_jobs = []
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                jo.OfferID, jo.Title, c.CompanyName, jo.Location 
            FROM JobOffers jo 
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            WHERE jo.Status = 'Open' AND (jo.ClosingDate IS NULL OR jo.ClosingDate >= CURDATE())
            ORDER BY  jo.DatePosted DESC 
            LIMIT 3 
        """)
        recent_jobs = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching recent jobs for homepage: {e}", exc_info=True)
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    
    return render_template('Website/home.html', recent_jobs=recent_jobs, title="Welcome to Mosla Pioneers")


# === CONTACT PAGE ===
@public_routes_bp.route('/contact', methods=['GET', 'POST'])
def contact_page():
    form_data = {} 
    if request.method == 'POST':
        form_data = request.form.to_dict()
        name = form_data.get('name')
        email = form_data.get('email')
        subject = form_data.get('subject')
        message_text = form_data.get('message')

        if not all([name, email, subject, message_text]):
            flash("Please fill in all fields of the contact form.", "warning")
            return render_template('Website/contact.html', title="Contact Us", form_data=form_data)
        
        current_app.logger.info(f"Contact form received (DEMO): Name: {name}, Email: {email}, Subject: {subject}")
        flash("Thank you for your message! We will get back to you shortly. (This is a demo - email not actually sent)", "success")
        return redirect(url_for('.contact_page')) 

    return render_template('Website/contact.html', title="Contact Us", form_data=form_data)