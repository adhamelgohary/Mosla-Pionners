# routes/Website/courses_page_routes.py
from flask import Blueprint, render_template, current_app, flash, request, url_for, redirect
from flask_login import current_user, login_required
from db import get_db_connection
import mysql.connector
from collections import OrderedDict

# This blueprint will handle public-facing pages like Home, About, Courses, etc.
courses_page_bp = Blueprint('courses_page_bp', __name__,
                            template_folder='../../../templates')

# Helper function to get CandidateID from UserID
# This should ideally be in a shared utility file or within the candidate routes
def get_candidate_id(user_id):
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

@courses_page_bp.route('/courses')
def view_courses():
    """
    Fetches all active course and language information from the new database schema,
    structures it, and passes it to the courses_page.html template.
    This replaces the old logic entirely.
    """
    conn = get_db_connection()
    # Use an OrderedDict to preserve the display order from the database
    courses_by_language = OrderedDict()
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # SQL query to get all active languages and their associated active courses
        sql = """
            SELECT
                cl.LanguageID,
                cl.LanguageName,
                cl.PageTitle,
                cl.PageDescription,
                cl.Benefits,
                cl.PricingNotes,
                cl.ImportantNotes,
                c.CourseID,
                c.Title AS CourseTitle,
                c.Description AS CourseDescription,
                c.Price AS CoursePrice,
                c.OriginalPrice AS CourseOriginalPrice
            FROM CourseLanguages cl
            LEFT JOIN Courses c ON cl.LanguageID = c.LanguageID AND c.IsActive = TRUE
            WHERE cl.IsActive = TRUE
            ORDER BY cl.DisplayOrder, cl.LanguageName, c.DisplayOrder, c.CourseTitle;
        """
        cursor.execute(sql)
        results = cursor.fetchall()
        
        # Process the flat list of results into a nested, ordered dictionary
        for row in results:
            lang_id = row['LanguageID']
            if lang_id not in courses_by_language:
                # First time we see this language, create its entry
                courses_by_language[lang_id] = {
                    'language_name': row['LanguageName'],
                    'title': row['PageTitle'],
                    'description': row['PageDescription'],
                    'benefits': [b.strip() for b in row['Benefits'].split(',') if b.strip()] if row['Benefits'] else [],
                    'pricing_notes': row['PricingNotes'],
                    'important_notes': row['ImportantNotes'],
                    'courses': [] # Initialize an empty list for its courses
                }
            
            # If the course part of the row exists (from the LEFT JOIN), add it
            if row['CourseID']:
                courses_by_language[lang_id]['courses'].append({
                    'id': row['CourseID'],
                    'title': row['CourseTitle'],
                    'description': row['CourseDescription'],
                    'price': row['CoursePrice'],
                    'original_price': row['CourseOriginalPrice']
                })

    except Exception as e:
        current_app.logger.error(f"Error fetching courses page data: {e}", exc_info=True)
        flash("Could not load course information at this time. Please try again later.", "warning")
        courses_by_language = {}
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            
    return render_template('Website/courses_page.html', 
                           title="Train To Hire Courses",
                           courses_by_language=courses_by_language)

@courses_page_bp.route('/course/<int:course_id>/apply', methods=['GET'])
@login_required # Only logged-in users can apply
def apply_for_course_form(course_id):
    """
    Displays the application form for a specific course.
    """
    if not hasattr(current_user, 'role_type') or current_user.role_type != 'Candidate':
        flash("Only registered candidates can apply for courses.", "warning")
        return redirect(url_for('login_bp.login', next=request.url))

    conn = get_db_connection()
    course = None
    try:
        # Note: We query the 'Courses' table which now has the updated schema
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT CourseID, Title as CourseName FROM Courses WHERE CourseID = %s AND IsActive = 1", (course_id,))
        course = cursor.fetchone()
    finally:
        if conn and conn.is_connected(): conn.close()

    if not course:
        flash("This course is not available or does not exist.", "danger")
        return redirect(url_for('.view_courses'))

    form_data = {
        'full_name': f"{current_user.first_name} {current_user.last_name}",
        'email': current_user.email
    }

    return render_template('Website/apply_for_course.html', 
                           title=f"Apply for {course['CourseName']}",
                           course=course,
                           form_data=form_data)


@courses_page_bp.route('/course/<int:course_id>/submit-application', methods=['POST'])
@login_required
def submit_course_application(course_id):
    """
    Handles the submission of the course application form.
    """
    if not hasattr(current_user, 'role_type') or current_user.role_type != 'Candidate':
        flash("Only candidates can submit applications.", "danger")
        return redirect(url_for('.view_courses'))
        
    candidate_id = get_candidate_id(current_user.id)
    if not candidate_id:
        flash("Your candidate profile could not be found. Please complete your profile first.", "danger")
        return redirect(url_for('candidate_bp.dashboard'))

    notes = request.form.get('application_notes', '').strip()

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT EnrollmentID FROM CourseEnrollments WHERE CourseID = %s AND CandidateID = %s", (course_id, candidate_id))
        if cursor.fetchone():
            flash("You have already applied for this course.", "info")
            return redirect(url_for('.view_courses'))
            
        sql = "INSERT INTO CourseEnrollments (CourseID, CandidateID, Status, Notes) VALUES (%s, %s, 'Applied', %s)"
        cursor.execute(sql, (course_id, candidate_id, notes))
        conn.commit()
        
        flash("Your application has been submitted successfully! We will review it and get back to you.", "success")
        return redirect(url_for('candidate_bp.dashboard'))

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"DB Error submitting course application: {err}")
        flash("A database error occurred. Please try again.", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"General Error submitting course application: {e}")
        flash("An unexpected error occurred. Please try again.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    return redirect(url_for('.apply_for_course_form', course_id=course_id))