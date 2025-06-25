# routes/Candidate_Portal/candidate_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from db import get_db_connection
from utils.directory_configs import save_file_from_config # For CV uploads
import datetime

# Define the Blueprint for the candidate portal
candidate_bp = Blueprint('candidate_bp', __name__,
                         url_prefix='/candidate',
                         template_folder='../../../templates') # Point to where candidate templates will be

@candidate_bp.route('/dashboard')
@login_required
def dashboard():
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        flash("Access denied. This area is for candidates only.", "warning")
        return redirect(url_for('homepage_bp.home_page')) # Or login_bp.login

    conn = None
    candidate_profile = None
    cv_list = []
    applied_jobs = []
    candidate_id = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get CandidateID using UserID from current_user
        cursor.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (current_user.id,))
        candidate_data = cursor.fetchone()
        if not candidate_data:
            flash("Candidate profile not found.", "danger")
            return redirect(url_for('homepage_bp.home_page'))
        candidate_id = candidate_data['CandidateID']

        # Fetch full candidate profile (Candidates table + Users table)
        cursor.execute("""
            SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL
            FROM Candidates c
            JOIN Users u ON c.UserID = u.UserID
            WHERE c.CandidateID = %s
        """, (candidate_id,))
        candidate_profile = cursor.fetchone()

        # Fetch Candidate CVs
        cursor.execute("""
            SELECT CVID, CVFileUrl, OriginalFileName, UploadedAt, IsPrimary, CVTitle
            FROM CandidateCVs 
            WHERE CandidateID = %s 
            ORDER BY IsPrimary DESC, UploadedAt DESC
        """, (candidate_id,))
        cv_list = cursor.fetchall()

        # Fetch Submitted Job Applications
        cursor.execute("""
            SELECT ja.ApplicationID, ja.ApplicationDate, ja.Status, 
                   jo.OfferID, jo.Title AS JobTitle, comp.CompanyName
            FROM JobApplications ja
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies comp ON jo.CompanyID = comp.CompanyID
            WHERE ja.CandidateID = %s
            ORDER BY ja.ApplicationDate DESC
        """, (candidate_id,))
        applied_jobs = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching candidate dashboard data for UserID {current_user.id}: {e}", exc_info=True)
        flash("An error occurred while loading your profile.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor:
                cursor.close()
            conn.close()
            
    if not candidate_profile: # Double check after DB ops
        flash("Could not load candidate profile details.", "danger")
        return redirect(url_for('homepage_bp.home_page'))

    return render_template('candidate_portal/dashboard.html', # This will be templates/candidate_portal/dashboard.html
                           title="My Profile",
                           candidate_profile=candidate_profile,
                           cv_list=cv_list,
                           applied_jobs=applied_jobs)

@candidate_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        return redirect(url_for('homepage_bp.home_page'))

    conn = None
    candidate_id = None
    try: # Get CandidateID first
        conn_check = get_db_connection()
        cursor_check = conn_check.cursor(dictionary=True)
        cursor_check.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (current_user.id,))
        res = cursor_check.fetchone()
        if cursor_check: cursor_check.close()
        if conn_check and conn_check.is_connected(): conn_check.close()
        if not res:
            flash("Candidate profile not found for editing.", "danger")
            return redirect(url_for('.dashboard'))
        candidate_id = res['CandidateID']
    except Exception as e_check:
        current_app.logger.error(f"Error getting candidate ID for edit: {e_check}")
        flash("Error accessing profile.", "danger")
        return redirect(url_for('.dashboard'))


    if request.method == 'POST':
        # Get data from form
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        # email = request.form.get('email', '').strip() # Email usually not editable by user directly
        
        portfolio_url = request.form.get('portfolio_url', '').strip()
        linkedin_url = request.form.get('linkedin_url', '').strip()
        years_of_experience_str = request.form.get('years_of_experience', '').strip()
        current_salary_str = request.form.get('current_salary', '').strip()
        expected_salary_str = request.form.get('expected_salary', '').strip()
        availability_date_str = request.form.get('availability_date', '').strip()
        preferred_job_types = request.form.get('preferred_job_types', '').strip() # Consider how to store/parse if multiple
        preferred_locations = request.form.get('preferred_locations', '').strip()
        notes = request.form.get('notes', '').strip()
        date_of_birth_str = request.form.get('date_of_birth', '').strip()
        nationality = request.form.get('nationality', '').strip()
        educational_status = request.form.get('educational_status', '').strip()
        gender = request.form.get('gender', '').strip()
        # Profile Picture
        profile_picture_file = request.files.get('profile_picture')


        # --- Validation (simplified for brevity) ---
        if not first_name or not last_name:
            flash("First name and last name are required.", "danger")
        else:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                # Update Users table
                users_update_sql = "UPDATE Users SET FirstName = %s, LastName = %s, PhoneNumber = %s"
                users_update_params = [first_name, last_name, phone_number or None]
                
                if profile_picture_file and profile_picture_file.filename:
                    # Define subfolder, e.g., 'profile_pictures/candidate/<candidate_id>'
                    # Ensure candidate_id is available here
                    profile_pic_path = save_file_from_config(profile_picture_file, f'candidate_profile_pics/{candidate_id}')
                    if profile_pic_path:
                        users_update_sql += ", ProfilePictureURL = %s"
                        users_update_params.append(profile_pic_path)
                    else:
                        flash("Could not save profile picture.", "warning")
                
                users_update_sql += " WHERE UserID = %s"
                users_update_params.append(current_user.id)
                cursor.execute(users_update_sql, tuple(users_update_params))

                # Update Candidates table
                years_of_experience = int(years_of_experience_str) if years_of_experience_str.isdigit() else None
                current_salary = float(current_salary_str) if current_salary_str else None
                expected_salary = float(expected_salary_str) if expected_salary_str else None
                availability_date = datetime.datetime.strptime(availability_date_str, '%Y-%m-%d').date() if availability_date_str else None
                date_of_birth = datetime.datetime.strptime(date_of_birth_str, '%Y-%m-%d').date() if date_of_birth_str else None
                
                gender_db = gender if gender in ['Male', 'Female', 'Other', 'PreferNotToSay'] else None


                cursor.execute("""
                    UPDATE Candidates SET
                    PortfolioURL = %s, LinkedInProfileURL = %s, YearsOfExperience = %s, CurrentSalary = %s, ExpectedSalary = %s,
                    AvailabilityDate = %s, PreferredJobTypes = %s, PreferredLocations = %s, Notes = %s, DateOfBirth = %s,
                    Nationality = %s, EducationalStatus = %s, Gender = %s
                    WHERE CandidateID = %s
                """, (portfolio_url or None, linkedin_url or None, years_of_experience, current_salary, expected_salary,
                      availability_date, preferred_job_types or None, preferred_locations or None, notes or None, date_of_birth,
                      nationality or None, educational_status or None, gender_db, candidate_id))
                
                conn.commit()
                flash("Profile updated successfully!", "success")
                # Update current_user session details if needed, e.g., name, picture
                current_user.first_name = first_name 
                current_user.last_name = last_name
                if 'profile_pic_path' in locals() and profile_pic_path:
                    # If LoginUser stores profile_picture directly, update it.
                    # This depends on your LoginUser class structure.
                    # For now, assume Users table update handles what's displayed generally.
                    pass
                return redirect(url_for('.dashboard'))
            except Exception as e:
                if conn: conn.rollback()
                current_app.logger.error(f"Error updating candidate profile for UserID {current_user.id}: {e}", exc_info=True)
                flash("An error occurred while updating your profile.", "danger")
            finally:
                if conn and conn.is_connected():
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn.close()
    
    # GET request: Fetch current profile data to populate form
    conn_get = None
    profile_data_for_form = {}
    try:
        conn_get = get_db_connection()
        cursor_get = conn_get.cursor(dictionary=True)
        cursor_get.execute("""
            SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL
            FROM Candidates c
            JOIN Users u ON c.UserID = u.UserID
            WHERE c.CandidateID = %s
        """, (candidate_id,))
        profile_data_for_form = cursor_get.fetchone()
    except Exception as e_get:
        current_app.logger.error(f"Error fetching profile for edit: {e_get}")
        flash("Could not load profile for editing.", "danger")
        return redirect(url_for('.dashboard'))
    finally:
        if conn_get and conn_get.is_connected():
            if 'cursor_get' in locals() and cursor_get: cursor_get.close()
            conn_get.close()

    if not profile_data_for_form: # Should have been caught earlier but as a safeguard
        flash("Profile data not found.", "danger")
        return redirect(url_for('.dashboard'))
        
    return render_template('candidate_portal/edit_profile.html', title="Edit My Profile", form_data=profile_data_for_form)


# --- CV Management Routes ---
@candidate_bp.route('/cv/upload', methods=['POST'])
@login_required
def upload_cv():
    if not (hasattr(current_user, 'role_type') and current_user.role_type == 'Candidate'):
        flash("Access denied.", "warning")
        return redirect(url_for('homepage_bp.home_page'))

    if 'cv_file' not in request.files:
        flash('No CV file part in the request.', 'danger')
        return redirect(url_for('.dashboard'))
    
    file = request.files['cv_file']
    cv_title = request.form.get('cv_title', '').strip()

    if file.filename == '':
        flash('No CV file selected for uploading.', 'warning')
        return redirect(url_for('.dashboard'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (current_user.id,))
        candidate_res = cursor.fetchone()
        if not candidate_res:
            flash("Candidate profile not found.", "danger")
            return redirect(url_for('.dashboard'))
        candidate_id = candidate_res[0]

        # Determine if this should be the primary CV
        cursor.execute("SELECT COUNT(*) FROM CandidateCVs WHERE CandidateID = %s AND IsPrimary = 1", (candidate_id,))
        primary_cv_count = cursor.fetchone()[0]
        is_primary = (primary_cv_count == 0) # Make primary if no other primary CV exists

        # Save the file
        # Subfolder: 'candidate_cvs/<candidate_id>/filename.ext'
        # This structure keeps CVs organized per candidate.
        cv_path = save_file_from_config(file, f'candidate_cvs/{candidate_id}')

        if cv_path:
            # If setting this as primary, unmark other CVs for this candidate
            if is_primary:
                cursor.execute("UPDATE CandidateCVs SET IsPrimary = 0 WHERE CandidateID = %s", (candidate_id,))

            cursor.execute("""
                INSERT INTO CandidateCVs (CandidateID, CVFileUrl, OriginalFileName, CVTitle, IsPrimary, FileType, FileSizeKB) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (candidate_id, cv_path, file.filename, cv_title or file.filename, is_primary, file.mimetype, file.content_length // 1024 if file.content_length else None))
            conn.commit()
            flash('CV uploaded successfully!', 'success')
        else:
            flash('Failed to save CV file.', 'danger')

    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error uploading CV for UserID {current_user.id}: {e}", exc_info=True)
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
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # First, verify this CV belongs to the current candidate
        cursor.execute("SELECT cv.CVFileUrl, cv.CandidateID, c.UserID FROM CandidateCVs cv JOIN Candidates c ON cv.CandidateID = c.CandidateID WHERE cv.CVID = %s AND c.UserID = %s", (cv_id, current_user.id))
        cv_data = cursor.fetchone()

        if not cv_data:
            return jsonify({'status': 'error', 'message': 'CV not found or you do not have permission to delete it.'}), 404

        # TODO: Delete the actual file from the server (os.remove)
        # file_to_delete_path = os.path.join(current_app.config['UPLOAD_FOLDER'], cv_data['CVFileUrl'].replace('uploads/', '', 1))
        # Be very careful with os.remove - ensure path is correct and validated
        # For now, we'll just delete the DB record.

        cursor.execute("DELETE FROM CandidateCVs WHERE CVID = %s", (cv_id,))
        conn.commit()
        
        # If the deleted CV was primary, and other CVs exist, make another one primary (e.g., most recent)
        if cv_data.get('IsPrimary'):
            cursor.execute("SELECT CVID FROM CandidateCVs WHERE CandidateID = %s ORDER BY UploadedAt DESC LIMIT 1", (cv_data['CandidateID'],))
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
        
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get CandidateID for the current user
        cursor.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (current_user.id,))
        candidate_res = cursor.fetchone()
        if not candidate_res:
            return jsonify({'status': 'error', 'message': 'Candidate profile not found.'}), 404
        candidate_id = candidate_res[0]

        # Verify the CV belongs to this candidate
        cursor.execute("SELECT CandidateID FROM CandidateCVs WHERE CVID = %s", (cv_id,))
        cv_owner = cursor.fetchone()
        if not cv_owner or cv_owner[0] != candidate_id:
            return jsonify({'status': 'error', 'message': 'CV not found or does not belong to you.'}), 404
        
        # Set all other CVs for this candidate to IsPrimary = 0
        cursor.execute("UPDATE CandidateCVs SET IsPrimary = 0 WHERE CandidateID = %s", (candidate_id,))
        # Set the selected CV to IsPrimary = 1
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