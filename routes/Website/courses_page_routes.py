# routes/Website/courses_page_routes.py
from flask import Blueprint, render_template, current_app, flash, request, url_for, redirect
from flask_login import current_user, login_required
from db import get_db_connection
import mysql.connector

# This blueprint will handle public-facing pages like Home, About, Courses, etc.
courses_page_bp = Blueprint('courses_page_bp', __name__,
                            template_folder='../../../templates')

# Helper function to get CandidateID from UserID (remains unchanged)
def get_candidate_id(user_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True) # Using dictionary=True for consistency
        cursor.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (user_id,))
        result = cursor.fetchone()
        return result['CandidateID'] if result else None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Route to display new Package structure (Unchanged) ---
@courses_page_bp.route('/courses')
def view_packages():
    """
    Fetches all active Main Packages and their associated Sub-Packages
    and passes the structured data to the courses_page.html template.
    """
    main_packages = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # 1. Fetch all active MainPackages
        cursor.execute("SELECT * FROM MainPackages WHERE IsActive = TRUE ORDER BY Name")
        main_packages = cursor.fetchall()

        # 2. For each package, fetch its languages and active sub-packages
        for package in main_packages:
            # Fetch languages for this package
            cursor.execute("""
                SELECT l.LanguageName 
                FROM MainPackageLanguages mpl
                JOIN Languages l ON mpl.LanguageID = l.LanguageID
                WHERE mpl.PackageID = %s
            """, (package['PackageID'],))
            languages_raw = cursor.fetchall()
            package['languages'] = [lang['LanguageName'] for lang in languages_raw]

            # Fetch its active sub-packages (the items candidates can apply for)
            cursor.execute("""
                SELECT * FROM SubPackages 
                WHERE MainPackageID = %s AND IsActive = TRUE 
                ORDER BY DisplayOrder, Name
            """, (package['PackageID'],))
            package['sub_packages'] = cursor.fetchall()
            
    except Exception as e:
        current_app.logger.error(f"Error fetching public packages page data: {e}", exc_info=True)
        flash("Could not load course information at this time. Please try again later.", "warning")
        main_packages = [] # Ensure it's an empty list on error
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            
    return render_template('Website/courses_page.html', 
                           title="Our Programs & Courses",
                           main_packages=main_packages)

# --- UPDATED: Application form for a Sub-Package ---
@courses_page_bp.route('/package/<int:sub_package_id>/apply', methods=['GET'])
@login_required
def apply_for_package_form(sub_package_id):
    """
    Displays the application form for a specific Sub-Package.
    """
    if not hasattr(current_user, 'role_type') or current_user.role_type != 'Candidate':
        flash("Only registered candidates can apply for courses.", "warning")
        return redirect(url_for('login_bp.login', next=request.url))

    conn = get_db_connection()
    package_details = None
    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch details for the sub-package and its parent main package for context
        # --- MODIFICATION: Added sp.Price to the query ---
        sql = """
            SELECT 
                sp.SubPackageID, 
                sp.Name AS SubPackageName,
                sp.Price,
                mp.Name AS MainPackageName
            FROM SubPackages sp
            JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            WHERE sp.SubPackageID = %s AND sp.IsActive = 1 AND mp.IsActive = 1
        """
        cursor.execute(sql, (sub_package_id,))
        package_details = cursor.fetchone()
    finally:
        if conn and conn.is_connected(): conn.close()

    if not package_details:
        flash("This package is not available or does not exist.", "danger")
        return redirect(url_for('.view_packages'))

    form_data = {
        'full_name': f"{current_user.first_name} {current_user.last_name}",
        'email': current_user.email
    }

    return render_template('Website/apply_for_package.html', 
                           title=f"Apply for {package_details['MainPackageName']}: {package_details['SubPackageName']}",
                           package=package_details,
                           form_data=form_data)


# --- UPDATED: Submission logic for a Sub-Package application ---
@courses_page_bp.route('/package/<int:sub_package_id>/submit-application', methods=['POST'])
@login_required
def submit_package_application(sub_package_id):
    """
    Handles the submission of the sub-package application form.
    """
    if not hasattr(current_user, 'role_type') or current_user.role_type != 'Candidate':
        flash("Only candidates can submit applications.", "danger")
        return redirect(url_for('.view_packages'))
        
    candidate_id = get_candidate_id(current_user.id)
    if not candidate_id:
        flash("Your candidate profile could not be found. Please complete your profile first.", "danger")
        return redirect(url_for('candidate_bp.dashboard'))

    notes = request.form.get('application_notes', '').strip()

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if the candidate has already applied for this specific sub-package
        cursor.execute("SELECT EnrollmentID FROM CourseEnrollments WHERE SubPackageID = %s AND CandidateID = %s", (sub_package_id, candidate_id))
        if cursor.fetchone():
            flash("You have already applied for this package.", "info")
            return redirect(url_for('.view_packages'))
            
        # Insert the enrollment record with SubPackageID, leaving CourseID as NULL
        sql = "INSERT INTO CourseEnrollments (SubPackageID, CandidateID, Status, Notes) VALUES (%s, %s, 'Applied', %s)"
        cursor.execute(sql, (sub_package_id, candidate_id, notes))
        conn.commit()
        
        flash("Your application has been submitted successfully! We will review it and get back to you.", "success")
        return redirect(url_for('candidate_bp.dashboard'))

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"DB Error submitting package application: {err}")
        flash("A database error occurred. Please try again.", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"General Error submitting package application: {e}")
        flash("An unexpected error occurred. Please try again.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    return redirect(url_for('.apply_for_package_form', sub_package_id=sub_package_id))