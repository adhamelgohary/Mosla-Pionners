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
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch lookup data for the form on both GET and POST
    try:
        cursor.execute("SELECT BenefitID, BenefitName FROM Benefits ORDER BY BenefitName")
        all_benefits = cursor.fetchall()
        cursor.execute("SELECT InterviewTypeID, TypeName FROM InterviewTypes")
        all_interview_types = cursor.fetchall()
        # Add other lookups like Languages, Levels if needed for the form
    finally:
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
                                   title="Submit New Job Offer", 
                                   company_name=session.get('client_company_name'), 
                                   form_data=form,
                                   all_benefits=all_benefits, all_interview_types=all_interview_types,
                                   selected_shifts=form.getlist('available_shifts'),
                                   selected_benefits=[int(i) for i in form.getlist('benefit_ids')],
                                   selected_languages=form.getlist('required_languages'))
        
        # CHANGED: The main insert data no longer includes benefits or interview type text
        main_offer_data = {
            'CompanyID': company_id, 
            'SubmittedByUserID': current_user.id, 
            'Title': form.get('title'),
            'Location': form.get('location'), 
            'MaxAge': form.get('max_age') or None, 
            'ClosingDate': form.get('closing_date'),
            'HasContract': 1 if form.get('has_contract') else 0, 
            'LanguagesType': form.get('languages_type'),
            'RequiredLanguages': ",".join(request.form.getlist('required_languages')) or None, # Assuming this stays as a string for review
            'RequiredLevel': form.get('english_level_requirement'), # Assuming this stays as a string for review
            'CandidatesNeeded': form.get('candidates_needed'),
            'HiringCadence': form.get('hiring_cadence'), 
            'WorkLocationType': form.get('work_location_type'),
            'HiringPlan': form.get('hiring_plan'), 
            'ShiftType': form.get('shift_type'),
            'AvailableShifts': ",".join(request.form.getlist('available_shifts')) or None, 
            'NetSalary': form.get('net_salary') or None,
            'PaymentTerm': form.get('payment_term'), 
            'GraduationStatusRequirement': form.get('graduation_status_requirement'),
            'Nationality': form.get('nationality_requirement'),
            'InterviewTypeID': form.get('interview_type_id'), # CHANGED: Now an ID
            'ClientNotes': form.get('client_notes')
        }
        
        selected_benefit_ids = request.form.getlist('benefit_ids')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # NEW: Start a transaction
            conn.start_transaction()

            # Step 1: Insert the main offer data
            main_sql = """
                INSERT INTO ClientSubmittedJobOffers (
                    CompanyID, SubmittedByUserID, Title, Location, MaxAge, ClosingDate, HasContract, LanguagesType,
                    RequiredLanguages, RequiredLevel, CandidatesNeeded, HiringCadence, WorkLocationType, HiringPlan,
                    ShiftType, AvailableShifts, NetSalary, PaymentTerm, GraduationStatusRequirement, Nationality,
                    InterviewTypeID, ClientNotes
                ) VALUES (
                    %(CompanyID)s, %(SubmittedByUserID)s, %(Title)s, %(Location)s, %(MaxAge)s, %(ClosingDate)s, %(HasContract)s,
                    %(LanguagesType)s, %(RequiredLanguages)s, %(RequiredLevel)s, %(CandidatesNeeded)s, %(HiringCadence)s,
                    %(WorkLocationType)s, %(HiringPlan)s, %(ShiftType)s, %(AvailableShifts)s, %(NetSalary)s, %(PaymentTerm)s,
                    %(GraduationStatusRequirement)s, %(Nationality)s, %(InterviewTypeID)s, %(ClientNotes)s
                )
            """
            cursor.execute(main_sql, main_offer_data)
            submission_id = cursor.lastrowid # Get the ID of the new submission

            # Step 2: Insert the selected benefits into the junction table
            if selected_benefit_ids:
                benefits_sql = "INSERT INTO ClientSubmittedJobOfferBenefits (SubmissionID, BenefitID) VALUES (%s, %s)"
                benefits_to_insert = [(submission_id, benefit_id) for benefit_id in selected_benefit_ids]
                cursor.executemany(benefits_sql, benefits_to_insert)

            # Step 3: Commit the transaction
            conn.commit()
            
            flash("Your job offer has been submitted successfully for review.", "success")
            return redirect(url_for('.my_submissions'))
        except mysql.connector.Error as err:
            conn.rollback() # Rollback on error
            flash(f"An error occurred while submitting your offer: {err}", "danger")
            current_app.logger.error(f"Client offer submission error for company {company_id}: {err}")
            return render_template('client_portal/submit_offer.html', 
                                   title="Submit New Job Offer", 
                                   company_name=session.get('client_company_name'), 
                                   form_data=form,
                                   all_benefits=all_benefits, all_interview_types=all_interview_types,
                                   selected_shifts=form.getlist('available_shifts'),
                                   selected_benefits=[int(i) for i in form.getlist('benefit_ids')],
                                   selected_languages=form.getlist('required_languages'))
        finally:
            cursor.close()
            conn.close()

    # On initial GET request
    return render_template('client_portal/submit_offer.html', 
                           title="Submit New Job Offer", 
                           company_name=session.get('client_company_name'), 
                           form_data={},
                           all_benefits=all_benefits, all_interview_types=all_interview_types,
                           selected_shifts=[], selected_benefits=[], selected_languages=[])

@client_offers_bp.route('/my-submissions')
@client_login_required
def my_submissions():
    conn = None
    submissions = []
    company_id = session.get('client_company_id')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # CHANGED: Query now JOINs to get related data and uses GROUP_CONCAT for benefits
        query = """
            SELECT 
                csjo.*, 
                c.CompanyName,
                it.TypeName as InterviewTypeName,
                GROUP_CONCAT(b.BenefitName SEPARATOR ', ') as BenefitsList
            FROM ClientSubmittedJobOffers csjo 
            JOIN Companies c ON csjo.CompanyID = c.CompanyID
            LEFT JOIN InterviewTypes it ON csjo.InterviewTypeID = it.InterviewTypeID
            LEFT JOIN ClientSubmittedJobOfferBenefits csjob ON csjo.SubmissionID = csjob.SubmissionID
            LEFT JOIN Benefits b ON csjob.BenefitID = b.BenefitID
            WHERE csjo.CompanyID = %s 
            GROUP BY csjo.SubmissionID
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
    conn = None
    submission = None
    company_id = session.get('client_company_id')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # CHANGED: Query updated to fetch related names and list of benefits
        query = """
            SELECT 
                csjo.*, 
                c.CompanyName,
                it.TypeName as InterviewTypeName,
                GROUP_CONCAT(b.BenefitName SEPARATOR ', ') as BenefitsList
            FROM ClientSubmittedJobOffers csjo
            JOIN Companies c ON csjo.CompanyID = c.CompanyID
            LEFT JOIN InterviewTypes it ON csjo.InterviewTypeID = it.InterviewTypeID
            LEFT JOIN ClientSubmittedJobOfferBenefits csjob ON csjo.SubmissionID = csjob.SubmissionID
            LEFT JOIN Benefits b ON csjob.BenefitID = b.BenefitID
            WHERE csjo.SubmissionID = %s AND csjo.CompanyID = %s
            GROUP BY csjo.SubmissionID
        """
        cursor.execute(query, (submission_id, company_id))
        submission = cursor.fetchone()

        if not submission:
            abort(404)
        
        # REMOVED: The old Python logic for parsing strings is no longer needed
        # The query's GROUP_CONCAT provides the 'BenefitsList' directly.
        
        # The logic for AvailableShifts can remain if it's still a string
        shifts_data = submission.get('AvailableShifts')
        if isinstance(shifts_data, str):
            submission['AvailableShifts_list'] = [s.strip() for s in shifts_data.split(',')]
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
    
@client_offers_bp.route('/my-offers')
@client_login_required
def my_offers():
    """ Displays all live, on-hold, or closed job offers for the client's company. """
    conn = None
    offers = []
    company_id = session.get('client_company_id')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Query the JobOffers table for offers linked to this company
        cursor.execute("""
            SELECT 
                OfferID, 
                Title, 
                Status, 
                DatePosted, 
                ClosingDate,
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