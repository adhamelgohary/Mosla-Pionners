# routes/Client_Portal/offer_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session, abort
from flask_login import login_required, current_user
from functools import wraps
from db import get_db_connection
import mysql.connector
import re # Import the regular expression module

# Define a specific blueprint for offers
client_offers_bp = Blueprint('client_offers_bp', __name__,
                             template_folder='../../../templates/client_portal',
                             url_prefix='/client')


# --- Helper Function to Query ENUM/SET Options (with Fixes) ---
def get_column_options(cursor, db_name, table_name, column_name):
    """
    Queries the information_schema to get the possible values for an ENUM or SET column.
    Returns a list of strings.
    """
    # FIX: Add a check to ensure db_name is configured. This is a common point of failure.
    if not db_name:
        current_app.logger.error(f"FATAL: MYSQL_DB configuration is not set. Cannot get options for {table_name}.{column_name}.")
        return []
    try:
        query = """
            SELECT COLUMN_TYPE 
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        
        if result and result[0]:
            # FIX: Handle potential bytearray response from some database connectors, which was causing the regex to fail silently.
            type_string = result[0].decode('utf-8') if isinstance(result[0], bytearray) else result[0]
            options = re.findall(r"'(.*?)'", type_string)
            return options
        
        current_app.logger.warning(f"No options found in schema for {table_name}.{column_name}. The column might not exist or is not an ENUM/SET.")
        return []
    except Exception as e:
        current_app.logger.error(f"DATABASE ERROR fetching options for {table_name}.{column_name}: {e}")
        return []

# --- Decorator (No changes needed) ---
def client_login_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if 'client_company_id' not in session or session.get('user_id') != current_user.id:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
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

@client_offers_bp.route('/submit-offer', methods=['GET', 'POST'])
@client_login_required
def submit_offer():
    form_options = {}
    db_name = current_app.config.get('MYSQL_DB')
    conn = None
    
    # DYNAMICALLY FETCH ALL OPTIONS FROM DB SCHEMA FOR THE FORM
    try:
        conn = get_db_connection()
        cursor = conn.cursor() # A raw tuple-based cursor is fine for the helper
        table = 'ClientSubmittedJobOffers'
        form_options = {
            'benefits_included': get_column_options(cursor, db_name, table, 'BenefitsIncluded'),
            'interview_types': get_column_options(cursor, db_name, table, 'InterviewType'),
            'nationalities': get_column_options(cursor, db_name, table, 'Nationality'),
            'genders': get_column_options(cursor, db_name, table, 'Gender'),
            'military_statuses': get_column_options(cursor, db_name, table, 'MilitaryStatus'),
            'graduation_statuses': get_column_options(cursor, db_name, table, 'GraduationStatusRequirement'),
            'available_shifts': get_column_options(cursor, db_name, table, 'AvailableShifts'),
            'required_languages': get_column_options(cursor, db_name, table, 'RequiredLanguages'),
            'payment_terms': get_column_options(cursor, db_name, table, 'PaymentTerm'),
            'required_levels': get_column_options(cursor, db_name, table, 'RequiredLevel')
        }
    except Exception as e:
        flash("Could not load form options from the database.", "danger")
        current_app.logger.error(f"Error establishing connection to fetch form options: {e}")
        # Initialize with empty lists to prevent template errors
        form_options = {key: [] for key in ['benefits_included', 'interview_types', 'nationalities', 'genders', 'military_statuses', 'graduation_statuses', 'available_shifts', 'required_languages', 'payment_terms', 'required_levels']}
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    if request.method == 'POST':
        company_id = session.get('client_company_id')
        if not company_id:
            abort(403)

        form = request.form
        if not form.get('title') or not form.get('closing_date'):
            flash("Job Title and Closing Date are required.", "danger")
            return render_template('client_portal/submit_offer.html', 
                                   title="Submit New Job Offer", company_name=session.get('client_company_name'), 
                                   form_data=form, options=form_options,
                                   selected_benefits=form.getlist('benefits_included'),
                                   selected_shifts=form.getlist('available_shifts'),
                                   selected_languages=form.getlist('required_languages'),
                                   selected_grad_statuses=form.getlist('graduation_status_requirement'))
        
        submitted_offer_data = {
            'CompanyID': company_id, 'SubmittedByUserID': current_user.id, 
            'Title': form.get('title'), 'Location': form.get('location'), 
            'MaxAge': form.get('max_age') or None, 'ClosingDate': form.get('closing_date'),
            'HasContract': 1 if form.get('has_contract') else 0, 
            'LanguagesType': form.get('languages_type'),
            'RequiredLanguages': ",".join(form.getlist('required_languages')) or None,
            'RequiredLevel': form.get('required_level'),
            'CandidatesNeeded': form.get('candidates_needed', 1),
            'HiringCadence': form.get('hiring_cadence'), 'WorkLocationType': form.get('work_location_type'),
            'HiringPlan': form.get('hiring_plan'), 'ShiftType': form.get('shift_type'),
            'AvailableShifts': ",".join(form.getlist('available_shifts')) or None, 
            'NetSalary': form.get('net_salary') or None,
            'PaymentTerm': form.get('payment_term'), 
            'GraduationStatusRequirement': ",".join(form.getlist('graduation_status_requirement')) or None,
            'Nationality': form.get('nationality'), 'InterviewType': form.get('interview_type'),
            'Gender': form.get('gender'), 'MilitaryStatus': form.get('military_status'),
            'ClientNotes': form.get('client_notes'),
            'BenefitsIncluded': ",".join(form.getlist('benefits_included')) or None
        }
        
        conn_insert = None
        try:
            conn_insert = get_db_connection()
            cursor_insert = conn_insert.cursor()
            sql = """
                INSERT INTO ClientSubmittedJobOffers (
                    CompanyID, SubmittedByUserID, Title, Location, MaxAge, ClosingDate, HasContract, 
                    LanguagesType, RequiredLanguages, RequiredLevel, CandidatesNeeded, HiringCadence, 
                    WorkLocationType, HiringPlan, ShiftType, AvailableShifts, NetSalary, PaymentTerm, 
                    GraduationStatusRequirement, BenefitsIncluded, InterviewType, Nationality, Gender, MilitaryStatus, ClientNotes
                ) VALUES (
                    %(CompanyID)s, %(SubmittedByUserID)s, %(Title)s, %(Location)s, %(MaxAge)s, %(ClosingDate)s, %(HasContract)s,
                    %(LanguagesType)s, %(RequiredLanguages)s, %(RequiredLevel)s, %(CandidatesNeeded)s, %(HiringCadence)s,
                    %(WorkLocationType)s, %(HiringPlan)s, %(ShiftType)s, %(AvailableShifts)s, %(NetSalary)s, %(PaymentTerm)s,
                    %(GraduationStatusRequirement)s, %(BenefitsIncluded)s, %(InterviewType)s, %(Nationality)s, %(Gender)s,
                    %(MilitaryStatus)s, %(ClientNotes)s
                )
            """
            cursor_insert.execute(sql, submitted_offer_data)
            conn_insert.commit()
            flash("Your job offer has been submitted successfully for review.", "success")
            return redirect(url_for('.my_submissions'))
        except mysql.connector.Error as err:
            if conn_insert: conn_insert.rollback()
            flash(f"An error occurred while submitting your offer: {err}", "danger")
            current_app.logger.error(f"Client offer submission error for company {company_id}: {err}")
            return render_template('client_portal/submit_offer.html', 
                                   title="Submit New Job Offer", company_name=session.get('client_company_name'), 
                                   form_data=form, options=form_options,
                                   selected_benefits=form.getlist('benefits_included'),
                                   selected_shifts=form.getlist('available_shifts'),
                                   selected_languages=form.getlist('required_languages'),
                                   selected_grad_statuses=form.getlist('graduation_status_requirement'))
        finally:
            if conn_insert and conn_insert.is_connected():
                cursor_insert.close()
                conn_insert.close()

    # On initial GET request
    return render_template('client_portal/submit_offer.html', 
                           title="Submit New Job Offer", 
                           company_name=session.get('client_company_name'), 
                           form_data={},
                           options=form_options,
                           selected_benefits=[], selected_shifts=[], selected_languages=[], selected_grad_statuses=[])

@client_offers_bp.route('/my-submissions')
@client_login_required
def my_submissions():
    conn = None
    submissions = []
    company_id = session.get('client_company_id')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                csjo.*, 
                c.CompanyName
            FROM ClientSubmittedJobOffers csjo 
            JOIN Companies c ON csjo.CompanyID = c.CompanyID
            WHERE csjo.CompanyID = %s 
            ORDER BY csjo.SubmissionDate DESC
        """
        cursor.execute(query, (company_id,))
        submissions = cursor.fetchall()
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    return render_template('client_portal/my_submissions.html', title="My Job Offer Submissions", submissions=submissions)

@client_offers_bp.route('/pipeline')
@client_login_required
def pipeline():
    conn = None
    offers_with_candidates = []
    company_id = session.get('client_company_id')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT OfferID, Title, CandidatesNeeded FROM JobOffers WHERE CompanyID = %s AND Status = 'Open' ORDER BY Title", (company_id,))
        live_offers = cursor.fetchall()
        for offer in live_offers:
            cursor.execute("""
                SELECT 
                    ja.ApplicationID, ja.Status, u.FirstName, u.LastName, cv.CVFileUrl 
                FROM JobApplications ja 
                JOIN Candidates c ON ja.CandidateID = c.CandidateID 
                JOIN Users u ON c.UserID = u.UserID 
                LEFT JOIN CandidateCVs cv ON c.CandidateID = cv.CandidateID AND cv.IsPrimary = 1 
                WHERE ja.OfferID = %s AND ja.Status = 'Shortlisted' 
                ORDER BY ja.ApplicationDate DESC
            """, (offer['OfferID'],))
            candidates = cursor.fetchall()
            offer['candidates'] = candidates
            offers_with_candidates.append(offer)
    except Exception as e:
        current_app.logger.error(f"Client Pipeline DB Error for company {company_id}: {e}")
        flash("A database error occurred while loading your candidate pipeline.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    return render_template('client_portal/pipeline.html', title="Candidate Pipeline", offers=offers_with_candidates)


@client_offers_bp.route('/pipeline/update-application-status/<int:application_id>', methods=['POST'])
@client_login_required
def update_application_status(application_id):
    action = request.form.get('action')
    company_id = session.get('client_company_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT jo.CompanyID FROM JobApplications ja JOIN JobOffers jo ON ja.OfferID = jo.OfferID WHERE ja.ApplicationID = %s", (application_id,))
        result = cursor.fetchone()
        if not result or result[0] != company_id:
            abort(403)
    finally:
        cursor.close()
        conn.close()

    new_status = None
    if action == 'schedule_interview':
        new_status = 'Interview Scheduled'
    elif action == 'reject':
        new_status = 'Rejected'

    if new_status:
        conn_update = get_db_connection()
        cursor_update = conn_update.cursor()
        try:
            cursor_update.execute("UPDATE JobApplications SET Status = %s WHERE ApplicationID = %s", (new_status, application_id))
            conn_update.commit()
            flash(f"Candidate status has been updated to '{new_status}'.", "success")
        except Exception as e:
            flash("Failed to update candidate status.", "danger")
            current_app.logger.error(f"Error updating app status for AppID {application_id}: {e}")
        finally:
            cursor_update.close()
            conn_update.close()
    
    return redirect(url_for('.pipeline'))

@client_offers_bp.route('/my-submissions/<int:submission_id>')
@client_login_required
def view_submission_details(submission_id):
    conn = None
    submission = None
    company_id = session.get('client_company_id')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                csjo.*, 
                c.CompanyName
            FROM ClientSubmittedJobOffers csjo
            JOIN Companies c ON csjo.CompanyID = c.CompanyID
            WHERE csjo.SubmissionID = %s AND csjo.CompanyID = %s
        """
        cursor.execute(query, (submission_id, company_id))
        submission = cursor.fetchone()

        if not submission:
            abort(404)
        
        def split_set_field(data):
            return [item.strip() for item in data.split(',')] if isinstance(data, str) else []

        submission['Benefits_list'] = split_set_field(submission.get('BenefitsIncluded'))
        submission['AvailableShifts_list'] = split_set_field(submission.get('AvailableShifts'))
        submission['RequiredLanguages_list'] = split_set_field(submission.get('RequiredLanguages'))
        submission['GraduationStatus_list'] = split_set_field(submission.get('GraduationStatusRequirement'))

    except Exception as e:
        current_app.logger.error(f"Error fetching submission details for ID {submission_id}: {e}")
        flash("A database error occurred while trying to load submission details.", "danger")
        return redirect(url_for('.my_submissions'))
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            
    return render_template('client_portal/submission_details.html', 
                           title=f"Submission Details: {submission.get('Title', '')}", 
                           submission=submission)
    
@client_offers_bp.route('/my-offers')
@client_login_required
def my_offers():
    conn = None
    offers = []
    company_id = session.get('client_company_id')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                OfferID, Title, Status, DatePosted, ClosingDate,
                (SELECT COUNT(*) FROM JobApplications WHERE OfferID = jo.OfferID) as ApplicationCount
            FROM JobOffers jo
            WHERE jo.CompanyID = %s
            ORDER BY jo.DatePosted DESC
        """, (company_id,))
        offers = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Client My Offers DB Error for company {company_id}: {e}")
        flash("A database error occurred while loading your job offers.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            
    return render_template('client_portal/my_offers.html', title="My Job Offers", offers=offers)