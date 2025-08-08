# routes/Auth/register_routes.py
from flask import Blueprint, render_template, request, flash, redirect, session, url_for, current_app
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import os
import datetime
import re
import mysql.connector
from db import get_db_connection

register_bp = Blueprint('register_bp', __name__, template_folder='../../templates/auth')

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

def create_user_in_db(email, password, first_name, last_name, phone_number=None, profile_picture_url=None, account_status='Active'):
    """
    Creates a new user with a specific account status and returns their ID.
    Defaults to 'Active' for candidates, but will be 'PendingApproval' for clients/staff.
    """
    conn = get_db_connection()
    if not conn:
        current_app.logger.error("create_user_in_db: Database connection failed.")
        return None
    try:
        cursor = conn.cursor()
        hashed_password = generate_password_hash(password)
        cursor.execute(
            """INSERT INTO Users (Email, PasswordHash, FirstName, LastName, PhoneNumber, ProfilePictureURL, AccountStatus)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (email, hashed_password, first_name, last_name, phone_number, profile_picture_url, account_status)
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
                    phone_number=step1_data['phone_number'],
                    account_status='Active' # Candidates are auto-approved
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
        job_title = request.form.get('job_title', '').strip()

        if not company_name: errors['company_name'] = 'Company name is required.'
        if not first_name: errors['first_name'] = 'Your first name is required.'
        if not last_name: errors['last_name'] = 'Your last name is required.'
        if not email: errors['email'] = 'Work email is required for the contact person.'
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", email): errors['email'] = 'Invalid email format for contact person.'
        elif check_email_exists_in_db(email): errors['email'] = 'This email is already registered. Please log in or use a different email.'
        if not job_title: errors['job_title'] = 'Your job title is required.'
        
        if len(password) < 8: errors['password'] = 'Password must be at least 8 characters long.'
        if password != confirm_password: errors['confirm_password'] = 'Passwords do not match.'

        if not errors:
            user_id = create_user_in_db(
                email, password, first_name, last_name, phone_number,
                account_status='PendingApproval'
            )
            
            if user_id:
                conn = None
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO ClientRegistrations (UserID, CompanyName, CompanyWebsite, Industry, JobTitle, Message)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        user_id,
                        company_name,
                        request.form.get('company_website'),
                        request.form.get('industry'),
                        job_title,
                        request.form.get('message')
                    ))
                    conn.commit()
                    
                    flash('Thank you for registering! Your application has been submitted for review. You will be notified by email once it is approved.', 'success')
                    current_app.logger.info(f"New client registration submitted for {email} (UserID: {user_id}) from company {company_name}")
                    return redirect(url_for('public_routes_bp.home_page'))

                except Exception as e:
                    if conn: conn.rollback()
                    current_app.logger.error(f"Error creating client registration record for {email}: {e}", exc_info=True)
                    flash('A server error occurred during registration. Please try again or contact support.', 'danger')
                finally:
                    if conn and conn.is_connected():
                        if 'cursor' in locals() and cursor: cursor.close()
                        conn.close()
            else:
                flash('An unexpected server error occurred creating your account. Please try again.', 'danger')
        else:
            flash('Please correct the form errors and try again.', 'warning')
            
    return render_template('auth/register_client.html', title='Register as Client', errors=errors, form_data=form_data)

@register_bp.route('/register/apply-staff', methods=['GET', 'POST'])
def apply_to_be_staff():
    errors, form_data = {}, {}
    staff_roles = ['SourcingRecruiter', 'AccountManager', 'SalesManager', 'UnitManager']

    if request.method == 'POST':
        form_data = request.form.to_dict()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        desired_role = request.form.get('desired_role', '')
        cv_file = request.files.get('cv_file')

        if not first_name: errors['first_name'] = 'First name is required.'
        if not last_name: errors['last_name'] = 'Last name is required.'
        if not email: errors['email'] = 'Email is required.'
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", email): errors['email'] = 'Invalid email format.'
        elif check_email_exists_in_db(email): errors['email'] = 'This email is already registered. If you are already staff, please log in.'
        if len(password) < 8: errors['password'] = 'Password must be at least 8 characters long.'
        if password != confirm_password: errors['confirm_password'] = 'Passwords do not match.'
        if not desired_role: errors['desired_role'] = 'Please select the role you are applying for.'
        if not cv_file or not cv_file.filename: errors['cv_file'] = 'Your CV is required for the application.'
        
        if not errors:
            cv_path = save_file(cv_file, subfolder='staff_cvs')
            if not cv_path:
                flash('There was an error uploading your CV. Please try again.', 'danger')
                errors['cv_file'] = 'CV upload failed. Please try again.'
            else:
                user_id = create_user_in_db(
                    email, password, first_name, last_name, phone_number,
                    account_status='PendingApproval'
                )
                if not user_id:
                    flash('Account creation failed. Please try again.', 'danger')
                else:
                    conn = None
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO StaffApplications (UserID, DesiredRole, CVFilePath, LinkedInProfileURL, CoverLetter)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            user_id,
                            desired_role,
                            cv_path,
                            request.form.get('linkedin_profile_url'),
                            request.form.get('cover_letter')
                        ))
                        conn.commit()
                        flash('Your application to join our staff has been submitted! Our team will review it and contact you if your application is approved.', 'success')
                        current_app.logger.info(f"New staff application submitted: {email}, UserID: {user_id}")
                        return redirect(url_for('public_routes_bp.home_page')) 
                    
                    except Exception as e:
                        if conn: conn.rollback()
                        current_app.logger.error(f"DB error creating Staff application for applicant {email} (UserID: {user_id}): {e}", exc_info=True)
                        flash('A database error occurred while submitting your application.', 'danger')
                    finally:
                        if conn and conn.is_connected():
                            if 'cursor' in locals() and cursor: cursor.close()
                            conn.close()
        else:
            flash('Please correct the errors in the form and try again.', 'warning')

    return render_template('auth/apply_staff.html', title='Apply to Join Our Team', errors=errors, form_data=form_data, staff_roles=staff_roles)