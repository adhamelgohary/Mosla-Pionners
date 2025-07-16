# routes/Auth/register_routes.py

from flask import Blueprint, render_template, request, flash, redirect, session, url_for, current_app
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import os
import datetime
import re
import mysql.connector
from db import get_db_connection
# from .login_routes import is_safe_url # No longer needed

register_bp = Blueprint('register_bp', __name__, template_folder='../../templates/auth')

# --- Helper Functions (Unchanged) ---
def check_email_exists_in_db(email):
    """Checks if an email already exists in the Users table."""
    conn = get_db_connection()
    if not conn:
        current_app.logger.error("check_email_exists_in_db: Database connection failed.")
        return True 
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT UserID FROM Users WHERE Email = %s", (email,))
        exists = cursor.fetchone() is not None
        return exists
    except Exception as e:
        current_app.logger.error(f"Error checking email existence for {email}: {e}", exc_info=True)
        return True 
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

def create_user_in_db(email, password, first_name, last_name, phone_number=None, profile_picture_url=None, is_active=True):
    """Creates a new user and returns their ID, or None on failure."""
    conn = get_db_connection()
    if not conn:
        current_app.logger.error("create_user_in_db: Database connection failed.")
        return None
    try:
        cursor = conn.cursor()
        hashed_password = generate_password_hash(password)
        cursor.execute(
            """INSERT INTO Users (Email, PasswordHash, FirstName, LastName, PhoneNumber, ProfilePictureURL, IsActive)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (email, hashed_password, first_name, last_name, phone_number, profile_picture_url, is_active)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return user_id
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error creating user in DB for {email}: {e}", exc_info=True)
        return None
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

# This function is not used in this file, but can be kept if it's part of a shared utility pattern
def save_file(file_storage, subfolder='general'):
    """Saves an uploaded file and returns its relative path for DB or None."""
    if file_storage and file_storage.filename:
        filename = secure_filename(file_storage.filename)
        upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.static_folder, 'uploads'))
        specific_upload_path = os.path.join(upload_folder, subfolder)
        os.makedirs(specific_upload_path, exist_ok=True)
        file_path_on_disk = os.path.join(specific_upload_path, filename)
        try:
            file_storage.save(file_path_on_disk)
            relative_path = os.path.join('uploads', subfolder, filename).replace("\\", "/")
            current_app.logger.info(f"File saved: {file_path_on_disk}, DB path: {relative_path}")
            return relative_path
        except Exception as e:
            current_app.logger.error(f"Error saving file {filename} to {file_path_on_disk}: {e}")
            return None
    return None

# --- Main Routes ---
@register_bp.route('/register', methods=['GET'])
def register_options():
    """Presents the choice to register as a Candidate, a Client, or Apply to be Staff."""
    return render_template('auth/register_options.html', title='Register')


@register_bp.route('/register/candidate', methods=['GET', 'POST'])
def register_candidate():
    """Handles the two-step registration for a new Candidate."""
    errors = {}
    
    try:
        step = int(request.form.get('step', 1))
    except ValueError:
        step = 1

    form_data = request.form.to_dict()

    if request.method == 'POST':
        if step == 1:
            email = form_data.get('email', '').strip()
            password = form_data.get('password', '')
            
            if not form_data.get('first_name'): errors['first_name'] = 'First name is required.'
            if not form_data.get('last_name'): errors['last_name'] = 'Last name is required.'
            if not email: errors['email'] = 'Email is required.'
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", email): errors['email'] = 'Invalid email format.'
            elif check_email_exists_in_db(email): errors['email'] = 'This email is already registered.'
            if len(password) < 8: errors['password'] = 'Password must be at least 8 characters long.'
            if password != form_data.get('confirm_password'): errors['confirm_password'] = 'Passwords do not match.'

            if not errors:
                session['registration_step1_data'] = {
                    'email': email, 'password': password,
                    'first_name': form_data.get('first_name'),
                    'last_name': form_data.get('last_name'),
                    'phone_number': form_data.get('phone_number')
                }
                return render_template('auth/register_candidate.html', title='Complete Your Profile', step=2, errors={}, form_data={})
            else:
                flash('Please correct the errors to continue.', 'warning')
                step = 1

        elif step == 2:
            step1_data = session.get('registration_step1_data')
            if not step1_data:
                flash('Your session has expired. Please start the registration process again.', 'danger')
                return redirect(url_for('.register_candidate'))
            
            date_of_birth_str = form_data.get('date_of_birth', '')
            date_of_birth = None
            if date_of_birth_str:
                try:
                    date_of_birth = datetime.datetime.strptime(date_of_birth_str, '%Y-%m-%d').date()
                except ValueError:
                    errors['date_of_birth'] = 'Invalid date format. Please use YYYY-MM-DD.'
            
            if not errors:
                user_id = create_user_in_db(
                    email=step1_data['email'], password=step1_data['password'],
                    first_name=step1_data['first_name'], last_name=step1_data['last_name'],
                    phone_number=step1_data['phone_number']
                )
                
                if user_id:
                    conn = None
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        languages_list = request.form.getlist('languages')
                        languages_db_val = ','.join(languages_list) if languages_list else None
                        
                        cursor.execute("""
                            INSERT INTO Candidates (UserID, LinkedInProfileURL, EducationalStatus, DateOfBirth, Nationality, Gender, Languages, LanguageLevel)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            user_id, form_data.get('linkedin_profile_url'), form_data.get('educational_status'), 
                            date_of_birth, form_data.get('nationality'), form_data.get('gender'),
                            languages_db_val, form_data.get('language_level')
                        ))
                        
                        conn.commit()
                        session.pop('registration_step1_data', None)
                        
                        flash('Your profile has been created successfully! You can now log in.', 'success')
                        return redirect(url_for('login_bp.login', email=step1_data['email']))

                    except Exception as e:
                        if conn: conn.rollback()
                        current_app.logger.error(f"DB Error creating Candidate profile for {step1_data['email']}: {e}", exc_info=True)
                        flash('A database error occurred creating your profile details.', 'danger')
                        step = 2
                else:
                    flash('An error occurred creating your user account.', 'danger')
                    step = 1
            else:
                flash('Please correct the errors.', 'warning')
                step = 2

    return render_template('auth/register_candidate.html', title='Register as Candidate', step=step, errors=errors, form_data=form_data)


@register_bp.route('/register/client', methods=['GET', 'POST'])
def register_client():
    errors, form_data = {}, {}
    if request.method == 'POST':
        form_data = request.form.to_dict()
        company_name = request.form.get('company_name', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip() 
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        phone_number = request.form.get('phone_number', '').strip()

        if not company_name: errors['company_name'] = 'Company name is required.'
        if not first_name: errors['first_name'] = 'Your first name is required.'
        if not last_name: errors['last_name'] = 'Your last name is required.'
        if not email: errors['email'] = 'Work email is required for the contact person.'
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", email): errors['email'] = 'Invalid email format for contact person.'
        elif check_email_exists_in_db(email): errors['email'] = 'This email is already registered. Please log in or use a different email.'
        
        if len(password) < 8: errors['password'] = 'Password must be at least 8 characters long.'
        if password != confirm_password: errors['confirm_password'] = 'Passwords do not match.'

        if not errors:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                cursor.execute("SELECT CompanyID FROM Companies WHERE CompanyName = %s", (company_name,))
                if company_result := cursor.fetchone():
                    company_id = company_result[0]
                else:
                    cursor.execute("INSERT INTO Companies (CompanyName) VALUES (%s)", (company_name,))
                    company_id = cursor.lastrowid
                
                user_id = create_user_in_db(email, password, first_name, last_name, phone_number)
                if not user_id:
                    raise Exception(f"User account creation failed in DB for client contact {email}.")

                cursor.execute("INSERT INTO CompanyContacts (UserID, CompanyID, IsPrimaryContact) VALUES (%s, %s, %s)", (user_id, company_id, True))
                conn.commit()
                flash(f'Company account for "{company_name}" and your contact profile have been registered! You can now log in.', 'success')
                current_app.logger.info(f"New client contact registered: {email} (UserID: {user_id}) for CompanyID: {company_id}")
                
                # --- UPDATED: Simplified redirect ---
                # Always redirect to the login page, passing only the email for user convenience.
                return redirect(url_for('login_bp.login', email=email))

            except Exception as e:
                if conn: conn.rollback()
                current_app.logger.error(f"Error during client registration process for {email} and company {company_name}: {e}", exc_info=True)
                flash('An unexpected server error occurred during registration. Please try again or contact support.', 'danger')
            finally:
                if conn and conn.is_connected():
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn.close()
        else:
            flash('Please correct the form errors and try again.', 'warning')
            
    return render_template('auth/register_client.html', title='Register as Client', errors=errors, form_data=form_data)


@register_bp.route('/register/apply-staff', methods=['GET', 'POST'])
def apply_to_be_staff():
    errors, form_data = {}, {}
    if request.method == 'POST':
        form_data = request.form.to_dict()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone_number = request.form.get('phone_number', '').strip()

        if not first_name: errors['first_name'] = 'First name is required.'
        if not last_name: errors['last_name'] = 'Last name is required.'
        if not email: errors['email'] = 'Email is required.'
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", email): errors['email'] = 'Invalid email format.'
        elif check_email_exists_in_db(email): errors['email'] = 'This email is already registered. If you are already staff, please log in.'
        if len(password) < 8: errors['password'] = 'Password must be at least 8 characters long.'
        if password != confirm_password: errors['confirm_password'] = 'Passwords do not match.'

        if not errors:
            # Create the user as inactive by default for staff applications
            user_id = create_user_in_db(email, password, first_name, last_name, phone_number, is_active=False)
            if not user_id:
                flash('Account creation failed. Please try again.', 'danger')
            else:
                conn = None
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    initial_staff_role = 'SourcingRecruiter' 

                    cursor.execute("INSERT INTO Staff (UserID, Role) VALUES (%s, %s)", (user_id, initial_staff_role))
                    conn.commit()
                    flash('Your application to join our staff has been submitted! Our team will review it and contact you if your application is approved.', 'success')
                    current_app.logger.info(f"New staff application submitted: {email}, UserID: {user_id}")
                    return redirect(url_for('public_routes_bp.home_page')) 
                
                except Exception as e:
                    if conn: conn.rollback()
                    current_app.logger.error(f"DB error creating Staff profile for applicant {email} (UserID: {user_id}): {e}", exc_info=True)
                    flash('A database error occurred while submitting your application.', 'danger')
                finally:
                    if conn and conn.is_connected():
                        if 'cursor' in locals() and cursor: cursor.close()
                        conn.close()
        else:
            flash('Please correct the errors in the form and try again.', 'warning')

    return render_template('auth/apply_staff.html', title='Apply to Join Our Team', errors=errors, form_data=form_data)