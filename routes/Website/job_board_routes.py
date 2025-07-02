# routes/Website/job_board_routes.py
from flask import Blueprint, render_template, request, current_app, flash, url_for, redirect, jsonify
from flask_login import login_required, current_user
from db11 import get_db_connection
import datetime
from utils.directory_configs import save_file_from_config
from werkzeug.utils import secure_filename

job_board_bp = Blueprint('job_board_bp', __name__,
                         url_prefix='/job-board',
                         template_folder='../../../templates')


@job_board_bp.route('/')
@job_board_bp.route('/jobs')
def job_offers_list():
    """
    Displays the main job board with filtering and search capabilities.
    """
    conn = None
    cursor = None
    job_offers_list = []
    job_categories_for_filter = []
    
    search_term = request.args.get('q', '').strip()
    selected_category_id = request.args.get('category', type=int)
    selected_location = request.args.get('location', '').strip()

    try:
        conn = get_db_connection()
        if not conn:
            current_app.logger.error("Failed to get database connection for job offers list.")
            flash("Database connection error. Please try again later.", "danger")
            return render_template('Website/job_offers/offers_list.html', 
                                   title="Current Job Openings", 
                                   job_offers_list=[],
                                   job_categories=[],
                                   search_term=search_term,
                                   selected_category_id=selected_category_id,
                                   selected_location=selected_location)

        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                jo.OfferID, jo.Title, jo.Location, jo.WorkLocationType, 
                jo.NetSalary, jo.DatePosted, jo.EnglishLevelRequirement,
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
            conditions.append("(jo.Title LIKE %s OR c.CompanyName LIKE %s OR jo.Description LIKE %s OR jc.CategoryName LIKE %s OR jo.Location LIKE %s)")
            search_like = f"%{search_term}%"
            params.extend([search_like, search_like, search_like, search_like, search_like])
        if selected_category_id:
            conditions.append("jo.CategoryID = %s")
            params.append(selected_category_id)
        if selected_location:
            conditions.append("jo.Location LIKE %s")
            params.append(f"%{selected_location}%")

        
        cursor.execute(sql, tuple(params))
        job_offers_list = cursor.fetchall()

        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
        job_categories_for_filter = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error fetching job offers list: {e}", exc_info=True)
        flash("Could not load job openings. Please try again.", "warning")
    finally:
        if cursor:
            try: cursor.close()
            except Exception as e_cursor_close: current_app.logger.warning(f"Warning: Could not close cursor in job_offers_list: {e_cursor_close}")
        if conn and conn.is_connected():
            try: conn.close()
            except Exception as e_conn_close: current_app.logger.warning(f"Warning: Could not close connection in job_offers_list: {e_conn_close}")

    return render_template('Website/job_offers/offers_list.html', 
                           title="Current Job Openings", 
                           job_offers_list=job_offers_list,
                           job_categories=job_categories_for_filter,
                           search_term=search_term,
                           selected_category_id=selected_category_id,
                           selected_location=selected_location)


@job_board_bp.route('/offer/<int:offer_id>')
@job_board_bp.route('/offer/<int:offer_id>/<job_title_slug>')
def job_detail(offer_id, job_title_slug=None):
    """
    Displays the rich, read-only details for a single job offer.
    """
    conn = None
    cursor = None 
    offer = None

    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('.job_offers_list'))
            
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT jo.*, c.CompanyName, c.CompanyLogoURL, c.CompanyWebsite, 
                   c.Description as CompanyDescription, jc.CategoryName
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

        # Handle Requirements (this is a TEXT field, so split is correct)
        if offer.get('Requirements') and isinstance(offer.get('Requirements'), str):
            offer['Requirements_list'] = [req.strip() for req in offer['Requirements'].split(';') if req.strip()]
        else:
            offer['Requirements_list'] = []

        # Handle Benefits (this is a SET field in MySQL which the driver converts to a Python set)
        if offer.get('Benefits'):
            offer['Benefits_list'] = list(offer['Benefits'])
        else:
            offer['Benefits_list'] = []

    except Exception as e:
        current_app.logger.error(f"Error fetching job detail for OfferID {offer_id}: {e}", exc_info=True)
        flash("Could not load job details.", "danger")
        return redirect(url_for('.job_offers_list'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
            
    return render_template('Website/job_offers/job_detail.html', offer=offer)


@job_board_bp.route('/offer/<int:offer_id>/apply', methods=['GET'])
@login_required
def apply_to_job(offer_id):
    """
    Displays the application form page for a specific job offer.
    Accessible only by authenticated Candidates.
    """
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        flash("Only registered candidates can apply for jobs.", "warning")
        return redirect(url_for('.job_detail', offer_id=offer_id))

    conn = None
    cursor = None
    offer = None
    form_data = {}

    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('.job_detail', offer_id=offer_id))

        cursor = conn.cursor(dictionary=True)
        # Fetch only the necessary offer details for the form
        cursor.execute("SELECT OfferID, Title FROM JobOffers WHERE OfferID = %s AND Status = 'Open'", (offer_id,))
        offer = cursor.fetchone()

        if not offer:
            flash("This job offer is no longer available.", "warning")
            return redirect(url_for('.job_offers_list'))

        # Pre-populate form data for the logged-in candidate
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
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template('Website/job_offers/apply_to_job.html', offer=offer, form_data=form_data)


@job_board_bp.route('/api/validate-referral-code', methods=['POST'])
@login_required 
def validate_referral_code_api():
    """
    API endpoint to validate a referral code via AJAX.
    """
    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Invalid request format: JSON expected.'}), 400
        
    data = request.get_json()
    if not data or 'referral_code' not in data:
        return jsonify({'status': 'error', 'message': 'Referral code not provided in JSON body.'}), 400

    referral_code = data['referral_code'].strip().upper()
    if not referral_code: 
        return jsonify({'status': 'valid_but_empty', 'message': 'Referral code field is empty.'}), 200

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
             return jsonify({'status': 'error', 'message': 'Database connection error.'}), 500
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.FirstName, u.LastName
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            WHERE s.ReferralCode = %s AND u.IsActive = 1
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
    finally:
        if cursor:
            try: cursor.close()
            except Exception as e_vc_cursor: current_app.logger.warning(f"API validate_referral_code cursor close error: {e_vc_cursor}")
        if conn and conn.is_connected():
            try: conn.close()
            except Exception as e_vc_conn: current_app.logger.warning(f"API validate_referral_code conn close error: {e_vc_conn}")


@job_board_bp.route('/offer/<int:offer_id>/submit', methods=['POST'])
@login_required
def submit_application_form(offer_id):
    """
    Handles the POST submission of the job application form.
    """
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        return jsonify({'status': 'error', 'message': 'Access denied: Only candidates can apply.'}), 403

    full_name = request.form.get('full_name', f"{current_user.first_name} {current_user.last_name}").strip()
    email = request.form.get('email', current_user.email).strip()
    phone_number = request.form.get('phone_number', '').strip()
    referral_code_input = request.form.get('referral_code', '').strip().upper()
    candidate_questions = request.form.get('candidateQuestions', '').strip()
    
    cv_file = request.files.get('cv_file')
    voice_note_blob = request.files.get('voice_note')
    voice_note_filename_from_form = request.form.get('voice_note_filename', '')

    errors = {}
    if not full_name: errors['full_name'] = "Full name is required."
    if not email: errors['email'] = "Email is required."
    if not phone_number: errors['phone_number'] = "Phone number is required."
    if not candidate_questions: errors['candidateQuestions'] = "Please answer why you are interested in this role."
    if not cv_file or not cv_file.filename: errors['cv_file'] = "CV upload is required."
    if not voice_note_blob or not voice_note_blob.filename: errors['voice_note'] = "Voice introduction is required."
    
    referring_staff_id = None
    referring_staff_team_lead_id = None
    
    if referral_code_input:
        try:
            with get_db_connection() as conn_ref_check:
                with conn_ref_check.cursor(dictionary=True) as cursor_ref_check:
                    cursor_ref_check.execute("""
                        SELECT s.StaffID, s.ReportsToStaffID 
                        FROM Staff s JOIN Users u ON s.UserID = u.UserID
                        WHERE s.ReferralCode = %s AND u.IsActive = 1 
                        """, (referral_code_input,))
                    referred_by_staff = cursor_ref_check.fetchone()
                    if referred_by_staff:
                        referring_staff_id = referred_by_staff['StaffID']
                        referring_staff_team_lead_id = referred_by_staff.get('ReportsToStaffID')
                    else:
                        errors['referral_code'] = "Invalid or inactive referral code."
        except Exception as e_ref:
            current_app.logger.error(f"Error checking referral code '{referral_code_input}': {e_ref}", exc_info=True)
            errors['referral_code'] = "Error validating referral code. Please try again or leave blank."

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
            return jsonify({'status': 'error', 'message': 'Your candidate profile was not found. Please contact support.'}), 404
        candidate_id = candidate_result[0]

        cv_db_path = save_file_from_config(cv_file, f'candidate_applications/cv/{candidate_id}')
        if not cv_db_path:
             raise Exception("Failed to save CV file.")
        
        default_voice_filename = f"voice_offer_{offer_id}_candidate_{candidate_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.webm"
        final_voice_note_filename_to_save = secure_filename(voice_note_filename_from_form or voice_note_blob.filename or default_voice_filename)
        voice_note_db_path = save_file_from_config(voice_note_blob, f'candidate_applications/voice/{candidate_id}', filename_override=final_voice_note_filename_to_save)
        if not voice_note_db_path:
            raise Exception("Failed to save voice note file.")

        cursor.execute("""
            INSERT INTO JobApplications 
            (OfferID, CandidateID, ApplicationDate, Status, NotesByCandidate, 
             ReferringStaffID, ReferringStaffTeamLeadID)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (offer_id, candidate_id, datetime.datetime.now(), 'Submitted', 
              candidate_questions, referring_staff_id, referring_staff_team_lead_id))
        
        cursor.execute("SELECT 1 FROM CandidateCVs WHERE CandidateID = %s AND IsPrimary = 1", (candidate_id,))
        is_primary_for_this_upload = not bool(cursor.fetchone())
        if is_primary_for_this_upload:
             cursor.execute("UPDATE CandidateCVs SET IsPrimary = 0 WHERE CandidateID = %s", (candidate_id,))

        cursor.execute("""
            INSERT INTO CandidateCVs (CandidateID, CVFileUrl, OriginalFileName, IsPrimary, UploadedAt, FileType, FileSizeKB)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (candidate_id, cv_db_path, cv_file.filename, is_primary_for_this_upload, datetime.datetime.now(), 
             cv_file.mimetype, cv_file.content_length // 1024 if cv_file.content_length else None))
        
        cursor.execute("""
            INSERT INTO CandidateVoiceNotes (CandidateID, VoiceNoteURL, Title, Purpose, UploadedAt)
            VALUES (%s, %s, %s, %s, %s)
            """, (candidate_id, voice_note_db_path, final_voice_note_filename_to_save, "Job Application", datetime.datetime.now()))

        conn.commit()
        flash("Your application has been submitted successfully!", "success") 
        return jsonify({'status': 'success', 
                        'message': 'Your application has been submitted successfully!', 
                        'redirect_url': url_for('.job_offers_list')}), 200

    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error submitting application for OfferID {offer_id} by UserID {current_user.id}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred during submission. Please try again.'}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()