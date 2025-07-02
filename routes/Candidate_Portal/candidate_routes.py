# routes/Candidate_Portal/candidate_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort, jsonify
from flask_login import login_required, current_user
from db11 import get_db_connection
from utils.directory_configs import save_file_from_config # For CV uploads
import datetime
import mysql.connector
import os

# Define the Blueprint for the candidate portal
candidate_bp = Blueprint('candidate_bp', __name__,
                         url_prefix='/candidate',
                         template_folder='../../../templates')

def get_candidate_id(user_id):
    """Helper to get CandidateID from UserID, returns None if not found."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
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
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch full candidate profile
        cursor.execute("""
            SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL
            FROM Candidates c
            JOIN Users u ON c.UserID = u.UserID
            WHERE c.CandidateID = %s
        """, (candidate_id,))
        candidate_profile = cursor.fetchone()

        # --- UPDATED QUERY ---
        # This query now explicitly includes CVTitle for a better user experience.
        cursor.execute("""
            SELECT CVID, CVFileUrl, OriginalFileName, CVTitle, UploadedAt, IsPrimary 
            FROM CandidateCVs 
            WHERE CandidateID = %s 
            ORDER BY IsPrimary DESC, UploadedAt DESC
        """, (candidate_id,))
        cv_list = cursor.fetchall()

        # Fetch Applications
        cursor.execute("""
            SELECT ja.ApplicationDate, ja.Status, jo.Title, comp.CompanyName
            FROM JobApplications ja
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies comp ON jo.CompanyID = comp.CompanyID
            WHERE ja.CandidateID = %s ORDER BY ja.ApplicationDate DESC
        """, (candidate_id,))
        applied_jobs = cursor.fetchall()

    except Exception as e:
        flash("An error occurred while loading your profile.", "danger")
        current_app.logger.error(f"Error fetching candidate dashboard for UserID {current_user.id}: {e}")
        return redirect(url_for('public_routes_bp.home_page'))
    finally:
        cursor.close()
        conn.close()
            
    return render_template('candidate_portal/dashboard.html',
                           title="My Profile",
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
        cursor = conn.cursor()
        try:
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
            date_of_birth = datetime.datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None

            # Added YearsOfExperience to the update
            candidate_params = {
                'LinkedInProfileURL': form.get('linkedin_url') or None,
                'YearsOfExperience': form.get('years_of_experience') or None,
                'Nationality': form.get('nationality') or None,
                'EducationalStatus': form.get('educational_status') or None,
                'EnglishLevel': form.get('english_level') or None,
                'DateOfBirth': date_of_birth,
                'CandidateID': candidate_id
            }
            cursor.execute("""
                UPDATE Candidates SET 
                    LinkedInProfileURL = %(LinkedInProfileURL)s, Nationality = %(Nationality)s, 
                    EducationalStatus = %(EducationalStatus)s, EnglishLevel = %(EnglishLevel)s, 
                    DateOfBirth = %(DateOfBirth)s, YearsOfExperience = %(YearsOfExperience)s
                WHERE CandidateID = %(CandidateID)s
            """, candidate_params)

            conn.commit()
            flash("Profile updated successfully!", "success")
            return redirect(url_for('.dashboard'))
        except Exception as e:
            conn.rollback()
            flash("An error occurred while updating your profile.", "danger")
            current_app.logger.error(f"Error updating candidate profile for UserID {current_user.id}: {e}")
        finally:
            cursor.close()
            conn.close()

    conn_get = get_db_connection()
    cursor_get = conn_get.cursor(dictionary=True)
    try:
        cursor_get.execute("""
            SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL
            FROM Candidates c JOIN Users u ON c.UserID = u.UserID
            WHERE c.CandidateID = %s
        """, (candidate_id,))
        form_data = cursor_get.fetchone()
    finally:
        cursor_get.close()
        conn_get.close()

    if not form_data:
        flash("Could not load profile data for editing.", "danger")
        return redirect(url_for('.dashboard'))
        
    return render_template('candidate_portal/edit_profile.html', title="Edit My Profile", form_data=form_data)


# --- CV Management Routes ---
@candidate_bp.route('/cv/upload', methods=['POST'])
@login_required
def upload_cv():
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        abort(403)

    # --- FIX: USE THE HELPER AND VALIDATE IMMEDIATELY ---
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

    # The rest of the logic can now safely assume `candidate_id` is valid.
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Refined logic: make this the primary CV only if it's the very first one being uploaded.
        cursor.execute("SELECT COUNT(*) FROM CandidateCVs WHERE CandidateID = %s", (candidate_id,))
        cv_count = cursor.fetchone()[0]
        is_primary = 1 if cv_count == 0 else 0

        # Save the file. The subfolder structure is good practice.
        cv_path = save_file_from_config(file, f'candidate_cvs/{candidate_id}')

        if cv_path:
            # If setting this as primary, all others must be un-marked.
            # This is handled more safely by the set_primary_cv route, but for the very first upload this is fine.
            if is_primary:
                cursor.execute("UPDATE CandidateCVs SET IsPrimary = 0 WHERE CandidateID = %s", (candidate_id,))

            # This INSERT will now succeed because candidate_id is guaranteed to be valid.
            cursor.execute("""
                INSERT INTO CandidateCVs (CandidateID, CVFileUrl, OriginalFileName, CVTitle, IsPrimary, FileType, FileSizeKB) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (candidate_id, cv_path, file.filename, request.form.get('cv_title', '').strip() or file.filename, is_primary, file.mimetype, file.tell() // 1024))
            
            conn.commit()
            flash('CV uploaded successfully!', 'success')
        else:
            flash('Failed to save CV file. The file type may not be allowed.', 'danger')

    except Exception as e:
        if conn: conn.rollback()
        # This is where your error was caught.
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

        # Physical file deletion should be implemented here carefully
        # e.g., os.remove(os.path.join(current_app.config['STATIC_FOLDER'], cv_data['CVFileUrl']))

        cursor.execute("DELETE FROM CandidateCVs WHERE CVID = %s", (cv_id,))
        
        # If the deleted CV was primary, promote the most recent one.
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
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
        
    candidate_id = get_candidate_id(current_user.id)
    if not candidate_id:
        return jsonify({'status': 'error', 'message': 'Candidate profile not found.'}), 404
        
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify the CV belongs to this candidate
        cursor.execute("SELECT COUNT(*) FROM CandidateCVs WHERE CVID = %s AND CandidateID = %s", (cv_id, candidate_id))
        if cursor.fetchone()[0] == 0:
            return jsonify({'status': 'error', 'message': 'CV not found or does not belong to you.'}), 404
        
        # Transaction: Set all to 0, then set the chosen one to 1.
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