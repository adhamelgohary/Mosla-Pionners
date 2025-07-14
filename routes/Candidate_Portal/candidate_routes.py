# routes/Candidate_Portal/candidate_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort, jsonify
from flask_login import login_required, current_user
from db import get_db_connection
from utils.directory_configs import save_file_from_config
from datetime import datetime, timedelta, time
import os

candidate_bp = Blueprint('candidate_bp', __name__,
                         url_prefix='/candidate',
                         template_folder='../../../templates')

def get_candidate_id(user_id):
    """Helper to get CandidateID from UserID, returns None if not found."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@candidate_bp.route('/dashboard')
@login_required
def dashboard():
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        abort(403)

    candidate_id = get_candidate_id(current_user.id)
    if not candidate_id:
        flash("Your candidate profile could not be found.", "danger")
        return redirect(url_for('public_routes_bp.home_page'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch full candidate profile
        cursor.execute("SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL FROM Candidates c JOIN Users u ON c.UserID = u.UserID WHERE c.CandidateID = %s", (candidate_id,))
        candidate_profile = cursor.fetchone()
        
        # Fetch CVs
        cursor.execute("SELECT CVID, CVFileUrl, OriginalFileName, CVTitle, UploadedAt, IsPrimary, FileSizeKB FROM CandidateCVs WHERE CandidateID = %s ORDER BY IsPrimary DESC, UploadedAt DESC", (candidate_id,))
        cv_list = cursor.fetchall()

        # Fetch Applications
        cursor.execute("SELECT ja.ApplicationID, ja.Status, jo.Title, comp.CompanyName FROM JobApplications ja JOIN JobOffers jo ON ja.OfferID = jo.OfferID JOIN Companies comp ON jo.CompanyID = comp.CompanyID WHERE ja.CandidateID = %s ORDER BY ja.ApplicationDate DESC", (candidate_id,))
        applied_jobs = cursor.fetchall()

    except Exception as e:
        flash("An error occurred while loading your profile.", "danger")
        current_app.logger.error(f"Error fetching candidate dashboard for UserID {current_user.id}: {e}", exc_info=True)
        return redirect(url_for('public_routes_bp.home_page'))
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            
    return render_template('candidate_portal/dashboard.html',
                           title="My Dashboard",
                           candidate=candidate_profile,
                           cv_list=cv_list,
                           applied_jobs=applied_jobs)


@candidate_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        abort(403)
    candidate_id = get_candidate_id(current_user.id)
    if not candidate_id:
        flash("Candidate profile not found.", "danger")
        return redirect(url_for('.dashboard'))

    if request.method == 'POST':
        form = request.form
        files = request.files
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            conn.start_transaction()

            profile_pic_path = None
            if 'profile_picture' in files and files['profile_picture'].filename:
                profile_pic_path = save_file_from_config(files['profile_picture'], f'candidate_profile_pics/{candidate_id}')
            
            user_update_query = "UPDATE Users SET FirstName=%s, LastName=%s, PhoneNumber=%s"
            user_params = [form.get('first_name'), form.get('last_name'), form.get('phone_number')]
            if profile_pic_path:
                user_update_query += ", ProfilePictureURL=%s"
                user_params.append(profile_pic_path)
            user_update_query += " WHERE UserID=%s"
            user_params.append(current_user.id)
            cursor.execute(user_update_query, tuple(user_params))

            dob_str = form.get('date_of_birth')
            date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
            languages_list = request.form.getlist('languages')
            languages_db_val = ','.join(languages_list) if languages_list else None

            candidate_params = {
                'LinkedInProfileURL': form.get('linkedin_url') or None, 'Nationality': form.get('nationality') or None,
                'EducationalStatus': form.get('educational_status') or None, 'DateOfBirth': date_of_birth,
                'Languages': languages_db_val, 'LanguageLevel': form.get('language_level') or None,
                'CandidateID': candidate_id
            }
            cursor.execute("""
                UPDATE Candidates SET LinkedInProfileURL = %(LinkedInProfileURL)s, Nationality = %(Nationality)s, 
                EducationalStatus = %(EducationalStatus)s, DateOfBirth = %(DateOfBirth)s,
                Languages = %(Languages)s, LanguageLevel = %(LanguageLevel)s
                WHERE CandidateID = %(CandidateID)s
            """, candidate_params)

            conn.commit()
            flash("Profile updated successfully!", "success")
            return redirect(url_for('.dashboard'))
        except Exception as e:
            if conn: conn.rollback()
            flash("An error occurred while updating your profile.", "danger")
            current_app.logger.error(f"Error updating candidate profile for UserID {current_user.id}: {e}", exc_info=True)
        finally:
            if conn: conn.close()

    conn_get = get_db_connection()
    try:
        cursor_get = conn_get.cursor(dictionary=True)
        cursor_get.execute("SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL FROM Candidates c JOIN Users u ON c.UserID = u.UserID WHERE c.CandidateID = %s", (candidate_id,))
        form_data = cursor_get.fetchone()
        if form_data.get('Languages') and isinstance(form_data['Languages'], (bytes, str)):
             form_data['Languages'] = form_data['Languages'].split(',')
    finally:
        if conn_get: conn_get.close()

    if not form_data:
        flash("Could not load profile data for editing.", "danger")
        return redirect(url_for('.dashboard'))
        
    return render_template('candidate_portal/edit_profile.html', title="Edit My Profile", form_data=form_data)



# --- CV Management and Scheduling Routes (No changes needed) ---
@candidate_bp.route('/cv/upload', methods=['POST'])
@login_required
def upload_cv():
    # This function is unchanged
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        abort(403)
    candidate_id = get_candidate_id(current_user.id)
    if not candidate_id:
        flash("Your candidate profile could not be found. Cannot upload CV.", "danger")
        return redirect(url_for('.dashboard'))
    if 'cv_file' not in request.files:
        flash('No CV file part in the request.', 'danger')
        return redirect(url_for('.dashboard'))
    file = request.files['cv_file']
    if file.filename == '':
        flash('No CV file selected for uploading.', 'warning')
        return redirect(url_for('.dashboard'))
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM CandidateCVs WHERE CandidateID = %s", (candidate_id,))
        cv_count = cursor.fetchone()[0]
        is_primary = 1 if cv_count == 0 else 0
        cv_path = save_file_from_config(file, f'candidate_cvs/{candidate_id}')
        if cv_path:
            if is_primary:
                cursor.execute("UPDATE CandidateCVs SET IsPrimary = 0 WHERE CandidateID = %s", (candidate_id,))
            file.seek(0, os.SEEK_END)
            file_size_kb = file.tell() // 1024
            cursor.execute("""
                INSERT INTO CandidateCVs (CandidateID, CVFileUrl, OriginalFileName, CVTitle, IsPrimary, FileType, FileSizeKB) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (candidate_id, cv_path, file.filename, request.form.get('cv_title', '').strip() or file.filename, is_primary, file.mimetype, file_size_kb))
            conn.commit()
            flash('CV uploaded successfully!', 'success')
        else:
            flash('Failed to save CV file. The file type may not be allowed.', 'danger')
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error uploading CV for UserID {current_user.id} (CandidateID: {candidate_id}): {e}", exc_info=True)
        flash('An error occurred while uploading the CV.', 'danger')
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return redirect(url_for('.dashboard'))

@candidate_bp.route('/cv/delete/<int:cv_id>', methods=['POST'])
@login_required
def delete_cv(cv_id):
    # This function is unchanged
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
    candidate_id = get_candidate_id(current_user.id)
    if not candidate_id:
        return jsonify({'status': 'error', 'message': 'Candidate profile not found.'}), 404
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT CVID, CVFileUrl, IsPrimary FROM CandidateCVs WHERE CVID = %s AND CandidateID = %s", (cv_id, candidate_id))
        cv_data = cursor.fetchone()
        if not cv_data:
            return jsonify({'status': 'error', 'message': 'CV not found or you do not have permission to delete it.'}), 404
        cursor.execute("DELETE FROM CandidateCVs WHERE CVID = %s", (cv_id,))
        if cv_data['IsPrimary']:
            cursor.execute("SELECT CVID FROM CandidateCVs WHERE CandidateID = %s ORDER BY UploadedAt DESC LIMIT 1", (candidate_id,))
            next_primary = cursor.fetchone()
            if next_primary:
                cursor.execute("UPDATE CandidateCVs SET IsPrimary = 1 WHERE CVID = %s", (next_primary['CVID'],))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'CV deleted successfully.'}), 200
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deleting CV (ID: {cv_id}) for UserID {current_user.id}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'Failed to delete CV.'}), 500
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

@candidate_bp.route('/cv/set-primary/<int:cv_id>', methods=['POST'])
@login_required
def set_primary_cv(cv_id):
    # This function is unchanged
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
    candidate_id = get_candidate_id(current_user.id)
    if not candidate_id:
        return jsonify({'status': 'error', 'message': 'Candidate profile not found.'}), 404
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM CandidateCVs WHERE CVID = %s AND CandidateID = %s", (cv_id, candidate_id))
        if cursor.fetchone()[0] == 0:
            return jsonify({'status': 'error', 'message': 'CV not found or does not belong to you.'}), 404
        cursor.execute("UPDATE CandidateCVs SET IsPrimary = 0 WHERE CandidateID = %s", (candidate_id,))
        cursor.execute("UPDATE CandidateCVs SET IsPrimary = 1 WHERE CVID = %s AND CandidateID = %s", (cv_id, candidate_id))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Primary CV updated successfully.'}), 200
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error setting primary CV (ID: {cv_id}) for UserID {current_user.id}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'Failed to set primary CV.'}), 500
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
            
@candidate_bp.route('/application/<int:application_id>/schedule-interview', methods=['GET', 'POST'])
@login_required
def schedule_interview(application_id):
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        abort(403)
    
    candidate_id = get_candidate_id(current_user.id)
    if not candidate_id:
        abort(403)

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT ja.ApplicationID, ja.Status, jo.Title, c.CompanyID, c.CompanyName
            FROM JobApplications ja
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            WHERE ja.ApplicationID = %s AND ja.CandidateID = %s
        """, (application_id, candidate_id))
        application = cursor.fetchone()

        if not application:
            abort(404, "Application not found or you are not authorized to view it.")
        
        if application['Status'] != 'Shortlisted':
            flash("This application is no longer eligible for interview scheduling.", "warning")
            return redirect(url_for('.dashboard'))

        if request.method == 'POST':
            selected_slot_str = request.form.get('interview_slot')
            if not selected_slot_str:
                flash("Please select a valid interview slot.", "danger")
                return redirect(url_for('.schedule_interview', application_id=application_id))

            scheduled_dt = datetime.fromisoformat(selected_slot_str)
            
            conn.start_transaction()
            cursor.execute("SELECT InterviewID FROM Interviews WHERE ScheduledDateTime = %s FOR UPDATE", (scheduled_dt,))
            if cursor.fetchone():
                conn.rollback()
                flash("Sorry, that time slot was just booked by another candidate. Please choose another.", "warning")
                return redirect(url_for('.schedule_interview', application_id=application_id))
            
            cursor.execute("INSERT INTO Interviews (ApplicationID, ScheduledDateTime) VALUES (%s, %s)", (application_id, scheduled_dt))
            cursor.execute("UPDATE JobApplications SET Status = 'Interview Scheduled' WHERE ApplicationID = %s", (application_id,))
            conn.commit()

            flash(f"Your interview has been successfully scheduled for {scheduled_dt.strftime('%A, %B %d at %I:%M %p')}.", "success")
            return redirect(url_for('.dashboard'))

        # --- Slot Generation Logic (Corrected) ---
        cursor.execute("SELECT DayOfWeek, StartTime, EndTime FROM CompanyInterviewSchedules WHERE CompanyID = %s AND IsActive = 1", (application['CompanyID'],))
        company_schedules = cursor.fetchall()

        cursor.execute("SELECT ScheduledDateTime FROM Interviews i JOIN JobApplications ja ON i.ApplicationID = ja.ApplicationID JOIN JobOffers jo ON ja.OfferID = jo.OfferID WHERE jo.CompanyID = %s AND i.ScheduledDateTime >= CURDATE()", (application['CompanyID'],))
        booked_slots = {row['ScheduledDateTime'] for row in cursor.fetchall()}
        
        available_slots = []
        today = datetime.today()
        for day_offset in range(1, 15):
            current_day = today + timedelta(days=day_offset)
            day_name = current_day.strftime('%A')
            for schedule in company_schedules:
                if schedule['DayOfWeek'] == day_name:
                    # --- THE FIX: Convert timedelta to time before combining ---
                    start_timedelta = schedule['StartTime']
                    end_timedelta = schedule['EndTime']
                    
                    # Create a dummy datetime to convert timedelta to a time object
                    start_time_obj = (datetime.min + start_timedelta).time()
                    end_time_obj = (datetime.min + end_timedelta).time()
                    
                    # Now combine with the correct data types
                    slot_time = datetime.combine(current_day.date(), start_time_obj)
                    end_time = datetime.combine(current_day.date(), end_time_obj)
                    
                    while slot_time < end_time:
                        if slot_time > datetime.now() and slot_time not in booked_slots:
                            available_slots.append(slot_time)
                        slot_time += timedelta(minutes=30)

        # Group slots by day for a nicer UI
        grouped_slots = {}
        for slot in sorted(available_slots):
            day_key = slot.strftime('%A, %B %d')
            if day_key not in grouped_slots:
                grouped_slots[day_key] = []
            grouped_slots[day_key].append(slot)

    except Exception as e:
        if 'conn' in locals() and conn.is_connected() and conn.in_transaction:
            conn.rollback()
        current_app.logger.error(f"Error in candidate interview scheduling for AppID {application_id}: {e}", exc_info=True)
        flash("An unexpected error occurred while loading the scheduling page.", "danger")
        return redirect(url_for('.dashboard'))
    finally:
        if 'conn' in locals() and conn and conn.is_connected():
            conn.close()
            
    return render_template('candidate_portal/schedule_interview.html',
                           title="Schedule Your Interview",
                           application=application,
                           grouped_slots=grouped_slots)