# routes/Website/job_board_routes.py
from flask import Blueprint, render_template, request, current_app, flash, url_for, redirect, jsonify
from flask_login import login_required, current_user
from db import get_db_connection
import datetime
from utils.directory_configs import save_file_from_config
from werkzeug.utils import secure_filename

job_board_bp = Blueprint('job_board_bp', __name__,
                         url_prefix='/job-board',
                         template_folder='../../../templates')


@job_board_bp.route('/jobs')
def job_offers_list():
    """
    Displays the main job board with filtering and search capabilities.
    """
    conn = get_db_connection()
    job_offers_list = []
    job_categories_for_filter = []
    
    search_term = request.args.get('q', '').strip()
    selected_category_id = request.args.get('category', type=int)
    
    try:
        cursor = conn.cursor(dictionary=True)
        # UPDATED: Query to select more fields for richer list cards
        base_sql = """
            SELECT 
                jo.OfferID, jo.Title, jo.Location, jo.WorkLocationType, jo.RequiredLevel,
                jo.NetSalary, jo.DatePosted,
                c.CompanyName, c.CompanyLogoURL,
                jc.CategoryName
            FROM JobOffers jo
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID
            WHERE jo.Status = 'Open' AND (jo.ClosingDate IS NULL OR jo.ClosingDate >= CURDATE())
        """
        params = []
        conditions = []

        if search_term:
            conditions.append("(jo.Title LIKE %s OR c.CompanyName LIKE %s OR jc.CategoryName LIKE %s OR jo.Location LIKE %s)")
            search_like = f"%{search_term}%"
            params.extend([search_like, search_like, search_like, search_like])
        if selected_category_id:
            conditions.append("jo.CategoryID = %s")
            params.append(selected_category_id)
        
        sql = base_sql
        if conditions:
            sql += " AND " + " AND ".join(conditions)
        sql += " ORDER BY jo.DatePosted DESC"
        
        cursor.execute(sql, tuple(params))
        job_offers_list = cursor.fetchall()

        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
        job_categories_for_filter = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error fetching job offers list: {e}", exc_info=True)
        flash("Could not load job openings. Please try again.", "warning")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

    return render_template('Website/job_offers/offers_list.html', 
                           title="Current Job Openings", 
                           job_offers_list=job_offers_list,
                           job_categories=job_categories_for_filter,
                           search_term=search_term,
                           selected_category_id=selected_category_id)


@job_board_bp.route('/offer/<int:offer_id>')
@job_board_bp.route('/offer/<int:offer_id>/<job_title_slug>')
def job_detail(offer_id, job_title_slug=None):
    """
    Displays the rich, read-only details for a single job offer.
    """
    conn = get_db_connection()
    offer = None
    try:
        cursor = conn.cursor(dictionary=True)
        # UPDATED: Query to select all relevant candidate-facing fields from the new schema
        cursor.execute("""
            SELECT 
                jo.OfferID, jo.Title, jo.Location, jo.WorkLocationType, jo.NetSalary,
                jo.PaymentTerm, jo.MaxAge, jo.HasContract, jo.GraduationStatusRequirement,
                jo.LanguagesType, jo.RequiredLanguages, jo.RequiredLevel, jo.ShiftType,
                jo.AvailableShifts, jo.BenefitsIncluded, jo.InterviewType, jo.Nationality,
                jo.DatePosted, jo.ClosingDate,
                c.CompanyName, c.CompanyLogoURL, c.CompanyWebsite, c.Description as CompanyDescription,
                jc.CategoryName
            FROM JobOffers jo
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID
            WHERE jo.OfferID = %s AND jo.Status = 'Open' 
                  AND (jo.ClosingDate IS NULL OR jo.ClosingDate >= CURDATE())
        """, (offer_id,))
        offer = cursor.fetchone()

        if not offer:
            flash("Job offer not found or is no longer available.", "warning")
            return redirect(url_for('.job_offers_list'))

        # UPDATED: Process all comma-separated fields into lists for the template
        for field in ['BenefitsIncluded', 'RequiredLanguages', 'AvailableShifts']:
            template_key = f"{field}_list"
            db_value = offer.get(field)
            if isinstance(db_value, (bytes, str)) and db_value.strip():
                offer[template_key] = [item.strip() for item in db_value.split(',')]
            else:
                offer[template_key] = []

    except Exception as e:
        current_app.logger.error(f"Error fetching job detail for OfferID {offer_id}: {e}", exc_info=True)
        flash("Could not load job details.", "danger")
        return redirect(url_for('.job_offers_list'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
            
    return render_template('Website/job_offers/job_detail.html', offer=offer)


# No changes needed for apply_to_job route. It is correct.
@job_board_bp.route('/offer/<int:offer_id>/apply', methods=['GET'])
@login_required
def apply_to_job(offer_id):
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        flash("Only registered candidates can apply for jobs.", "warning")
        return redirect(url_for('.job_detail', offer_id=offer_id))
    conn = get_db_connection()
    offer = None
    form_data = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT OfferID, Title FROM JobOffers WHERE OfferID = %s AND Status = 'Open'", (offer_id,))
        offer = cursor.fetchone()
        if not offer:
            flash("This job offer is no longer available.", "warning")
            return redirect(url_for('.job_offers_list'))
        form_data['full_name'] = f"{current_user.first_name} {current_user.last_name}"
        form_data['email'] = current_user.email
        cursor.execute("SELECT PhoneNumber FROM Users WHERE UserID = %s", (current_user.id,))
        user_details = cursor.fetchone()
        if user_details:
            form_data['phone_number'] = user_details.get('PhoneNumber', '')
    except Exception as e:
        current_app.logger.error(f"Error preparing application page for OfferID {offer_id}: {e}", exc_info=True)
        flash("Could not load the application page.", "danger")
        return redirect(url_for('.job_detail', offer_id=offer_id))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return render_template('Website/job_offers/apply_to_job.html', offer=offer, form_data=form_data)


# No changes needed for validate_referral_code_api route. It is correct.
@job_board_bp.route('/api/validate-referral-code', methods=['POST'])
@login_required 
def validate_referral_code_api():
    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Invalid request format: JSON expected.'}), 400
    data = request.get_json()
    referral_code = data.get('referral_code', '').strip().upper()
    if not referral_code: 
        return jsonify({'status': 'valid_but_empty', 'message': 'Referral code field is empty.'}), 200
    try:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT u.FirstName, u.LastName FROM Staff s
                    JOIN Users u ON s.UserID = u.UserID WHERE s.ReferralCode = %s AND u.IsActive = 1
                """, (referral_code,))
                staff_member = cursor.fetchone()
                if staff_member:
                    recruiter_name = f"{staff_member['FirstName']} {staff_member['LastName']}"
                    return jsonify({'status': 'success', 'recruiter_name': recruiter_name}), 200
                else:
                    return jsonify({'status': 'error', 'message': 'Invalid or inactive referral code.'}), 404 
    except Exception as e:
        current_app.logger.error(f"API Error validating referral code '{referral_code}': {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'Server error during validation.'}), 500


# No changes needed for submit_application_form route. It is correct.
@job_board_bp.route('/offer/<int:offer_id>/submit', methods=['POST'])
@login_required
def submit_application_form(offer_id):
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        return jsonify({'status': 'error', 'message': 'Access denied: Only candidates can apply.'}), 403

    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone_number = request.form.get('phone_number', '').strip()
    referral_code_input = request.form.get('referral_code', '').strip().upper()
    candidate_questions = request.form.get('candidateQuestions', '').strip()
    cv_file = request.files.get('cv_file')
    voice_note_file = request.files.get('voice_note_file')

    errors = {}
    if not full_name: errors['full_name'] = "Full name is required."
    if not email: errors['email'] = "Email is required."
    if not phone_number: errors['phone_number'] = "Phone number is required."
    if not candidate_questions: errors['candidateQuestions'] = "Please answer why you are interested in this role."
    if not cv_file or not cv_file.filename: errors['cv_file'] = "CV upload is required."
    if not voice_note_file or not voice_note_file.filename: errors['voice_note_file'] = "Voice note upload is required."
    
    referring_staff_id, referring_staff_team_lead_id = None, None
    if referral_code_input:
        try:
            with get_db_connection() as conn_ref:
                with conn_ref.cursor(dictionary=True) as cursor_ref:
                    cursor_ref.execute("SELECT StaffID, ReportsToStaffID FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.ReferralCode = %s AND u.IsActive = 1", (referral_code_input,))
                    staff = cursor_ref.fetchone()
                    if staff:
                        referring_staff_id = staff['StaffID']
                        referring_staff_team_lead_id = staff.get('ReportsToStaffID')
                    else:
                        errors['referral_code'] = "Invalid or inactive referral code."
        except Exception as e:
            current_app.logger.error(f"Error checking referral code '{referral_code_input}': {e}", exc_info=True)
            errors['referral_code'] = "Error validating referral code."

    if errors:
        return jsonify({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors}), 400

    conn = None
    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor()
        cursor.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (current_user.id,))
        candidate_result = cursor.fetchone()
        if not candidate_result:
            raise Exception(f"Candidate profile not found for UserID {current_user.id}")
        candidate_id = candidate_result[0]

        cv_db_path = save_file_from_config(cv_file, f'candidate_cvs/{candidate_id}')
        voice_note_db_path = save_file_from_config(voice_note_file, f'candidate_applications/voice/{candidate_id}')
        if not cv_db_path or not voice_note_db_path:
             raise Exception("Failed to save one or more files.")

        cursor.execute("INSERT INTO JobApplications (OfferID, CandidateID, ApplicationDate, Status, NotesByCandidate, ReferringStaffID, ReferringStaffTeamLeadID) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                       (offer_id, candidate_id, datetime.datetime.now(), 'Submitted', candidate_questions, referring_staff_id, referring_staff_team_lead_id))
        
        cursor.execute("UPDATE CandidateCVs SET IsPrimary = 0 WHERE CandidateID = %s", (candidate_id,))
        cursor.execute("INSERT INTO CandidateCVs (CandidateID, CVFileUrl, OriginalFileName, IsPrimary, CVTitle) VALUES (%s, %s, %s, 1, %s)",
                       (candidate_id, cv_db_path, secure_filename(cv_file.filename), f"CV for Offer {offer_id}"))
        
        cursor.execute("INSERT INTO CandidateVoiceNotes (CandidateID, VoiceNoteURL, Title, Purpose) VALUES (%s, %s, %s, %s)",
                       (candidate_id, voice_note_db_path, secure_filename(voice_note_file.filename), "Job Application"))

        conn.commit()
        flash("Your application has been submitted successfully!", "success") 
        return jsonify({'status': 'success', 'message': 'Application submitted!', 'redirect_url': url_for('.job_offers_list')}), 200

    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error submitting application for OfferID {offer_id} by UserID {current_user.id}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'An unexpected server error occurred. Please try again.'}), 500
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()