# routes/Client_Portal/offer_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session, abort
from flask_login import login_required, current_user
from functools import wraps
from db import get_db_connection
import mysql.connector

# Define a specific blueprint for offers
client_offers_bp = Blueprint('client_offers_bp', __name__,
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


@client_offers_bp.route('/submit-offer', methods=['GET', 'POST'])
@client_login_required
def submit_offer():
    if request.method == 'POST':
        company_id = session.get('client_company_id')
        if not company_id:
            abort(403)

        form = request.form
        if not form.get('title') or not form.get('closing_date'):
            flash("Job Title and Closing Date are required.", "danger")
            return render_template('client_portal/submit_offer.html', title="Submit New Job Offer", company_name=session.get('client_company_name'), form_data=form)
        
        # MODIFIED: Consolidate benefits into 'BenefitsIncluded' SET column.
        # Assumes the form now passes transportation type directly (e.g., 'Transportation (Door to Door)')
        benefits_list = request.form.getlist('benefits')
        
        # MODIFIED: Map form data to the new schema.
        form_data_for_db = {
            'CompanyID': company_id, 
            'SubmittedByUserID': current_user.id, 
            'Title': form.get('title'),
            'Location': form.get('location'), 
            'MaxAge': form.get('max_age') or None, 
            'ClosingDate': form.get('closing_date'),
            'HasContract': 1 if form.get('has_contract') else 0, 
            'LanguagesType': form.get('languages_type'),
            'RequiredLanguages': ",".join(request.form.getlist('required_languages')) or None,
            'RequiredLevel': form.get('english_level_requirement'), # Mapped from old form field
            'CandidatesNeeded': form.get('candidates_needed'),
            'HiringCadence': form.get('hiring_cadence'), 
            'WorkLocationType': form.get('work_location_type'),
            'HiringPlan': form.get('hiring_plan'), 
            'ShiftType': form.get('shift_type'),
            'AvailableShifts': ",".join(request.form.getlist('available_shifts')) or None, 
            'NetSalary': form.get('net_salary') or None,
            'PaymentTerm': form.get('payment_term'), 
            'GraduationStatusRequirement': form.get('graduation_status_requirement'),
            'Nationality': form.get('nationality_requirement'), # Mapped from old form field
            'BenefitsIncluded': ",".join(benefits_list) or None,
            'InterviewType': form.get('interview_type'),
            'ClientNotes': form.get('client_notes')
        }

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # MODIFIED: Updated INSERT statement for the new schema.
            sql = """
                INSERT INTO ClientSubmittedJobOffers (
                    CompanyID, SubmittedByUserID, Title, Location, MaxAge, ClosingDate, HasContract, LanguagesType,
                    RequiredLanguages, RequiredLevel, CandidatesNeeded, HiringCadence, WorkLocationType, HiringPlan,
                    ShiftType, AvailableShifts, NetSalary, PaymentTerm, GraduationStatusRequirement, Nationality,
                    BenefitsIncluded, InterviewType, ClientNotes
                ) VALUES (
                    %(CompanyID)s, %(SubmittedByUserID)s, %(Title)s, %(Location)s, %(MaxAge)s, %(ClosingDate)s, %(HasContract)s,
                    %(LanguagesType)s, %(RequiredLanguages)s, %(RequiredLevel)s, %(CandidatesNeeded)s, %(HiringCadence)s,
                    %(WorkLocationType)s, %(HiringPlan)s, %(ShiftType)s, %(AvailableShifts)s, %(NetSalary)s, %(PaymentTerm)s,
                    %(GraduationStatusRequirement)s, %(Nationality)s, %(BenefitsIncluded)s, %(InterviewType)s, %(ClientNotes)s
                )
            """
            cursor.execute(sql, form_data_for_db)
            conn.commit()
            flash("Your job offer has been submitted successfully for review.", "success")
            return redirect(url_for('.my_submissions'))
        except mysql.connector.Error as err:
            flash(f"An error occurred while submitting your offer: {err}", "danger")
            current_app.logger.error(f"Client offer submission error for company {company_id}: {err}")
            return render_template('client_portal/submit_offer.html', title="Submit New Job Offer", company_name=session.get('client_company_name'), form_data=form)
        finally:
            cursor.close()
            conn.close()

    return render_template('client_portal/submit_offer.html', title="Submit New Job Offer", company_name=session.get('client_company_name'), form_data={})


@client_offers_bp.route('/my-submissions')
@client_login_required
def my_submissions():
    conn = None
    submissions = []
    company_id = session.get('client_company_id')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # This query is still valid and will now return the new columns.
        cursor.execute("SELECT csjo.*, c.CompanyName FROM ClientSubmittedJobOffers csjo JOIN Companies c ON csjo.CompanyID = c.CompanyID WHERE csjo.CompanyID = %s ORDER BY csjo.SubmissionDate DESC", (company_id,))
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
            # MODIFIED: Removed `c.YearsOfExperience` as it no longer exists in the `Candidates` table.
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
        # This authorization check is still valid.
        cursor.execute("SELECT jo.CompanyID FROM JobApplications ja JOIN JobOffers jo ON ja.OfferID = jo.OfferID WHERE ja.ApplicationID = %s", (application_id,))
        result = cursor.fetchone()
        if not result or result[0] != company_id:
            abort(403)
    finally:
        cursor.close()
        conn.close()

    new_status = None
    # MODIFIED: Updated status values to match the new schema's ENUM definitions.
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
    """ Displays the full details of a single job offer submission. """
    conn = None
    submission = None
    company_id = session.get('client_company_id')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT csjo.*, c.CompanyName
            FROM ClientSubmittedJobOffers csjo
            JOIN Companies c ON csjo.CompanyID = c.CompanyID
            WHERE csjo.SubmissionID = %s AND csjo.CompanyID = %s
        """, (submission_id, company_id))
        submission = cursor.fetchone()

        if not submission:
            abort(404)
        
        # MODIFIED: The processing logic now uses the new column names.
        
        # Handle BenefitsIncluded (renamed from Benefits)
        benefits_data = submission.get('BenefitsIncluded')
        if isinstance(benefits_data, set):
            submission['Benefits_list'] = sorted(list(benefits_data)) # Convert set to a sorted list
        elif isinstance(benefits_data, str):
             submission['Benefits_list'] = [b.strip() for b in benefits_data.split(',')] # Fallback for strings
        else:
            submission['Benefits_list'] = []

        # Handle AvailableShifts (this column still exists and logic is fine)
        shifts_data = submission.get('AvailableShifts')
        if isinstance(shifts_data, set):
            submission['AvailableShifts_list'] = sorted(list(shifts_data)) # Convert set to a sorted list
        elif isinstance(shifts_data, str):
            submission['AvailableShifts_list'] = [s.strip() for s in shifts_data.split(',')] # Fallback for strings
        else:
            submission['AvailableShifts_list'] = []

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