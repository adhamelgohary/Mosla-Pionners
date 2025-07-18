# routes/public_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session
from db import get_db_connection
import datetime
import mysql.connector

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

# === CONTACT PAGE (UPDATED) ===
@public_routes_bp.route('/contact', methods=['GET', 'POST'])
def contact_page():
    form_data = {} 
    if request.method == 'POST':
        form_data = request.form.to_dict()
        name = form_data.get('name', '').strip()
        email = form_data.get('email', '').strip()
        subject = form_data.get('subject', '').strip()
        message_text = form_data.get('message', '').strip()

        if not all([name, email, subject, message_text]):
            flash("Please fill in all required fields of the contact form.", "warning")
            return render_template('Website/contact.html', title="Contact Us", form_data=form_data)
        
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            sql = "INSERT INTO ContactMessages (Name, Email, Subject, Message) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (name, email, subject, message_text))
            conn.commit()
            
            current_app.logger.info(f"New contact message saved from {email} with subject: '{subject}'")
            flash("Thank you for your message! Our team has received it and will get back to you shortly.", "success")
            return redirect(url_for('.contact_page'))

        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"Database error saving contact message: {err}")
            flash("A database error occurred while sending your message. Please try again later.", "danger")
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"An unexpected error occurred saving contact message: {e}")
            flash("An unexpected error occurred. Please contact support if the problem persists.", "danger")
        finally:
            if conn and conn.is_connected():
                if 'cursor' in locals() and cursor: cursor.close()
                conn.close()

        # If an error occurred, re-render the form with the user's data
        return render_template('Website/contact.html', title="Contact Us", form_data=form_data)

    return render_template('Website/contact.html', title="Contact Us", form_data=form_data)