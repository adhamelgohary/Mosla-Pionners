# routes/Website/courses_page_routes.py
from flask import Blueprint, redirect, render_template, current_app, flash, request, url_for
from flask_login import current_user, login_required
from db import get_db_connection
import mysql.connector

from routes.Candidate_Portal.candidate_routes import get_candidate_id

courses_page_bp = Blueprint('courses_page_bp', __name__,
                            template_folder='../../../templates')

@courses_page_bp.route('/courses')
def view_courses():
    """
    Displays the public-facing "Train to Hire" courses page,
    fetching course data dynamically from the database.
    """
    all_courses = []
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch all active courses, ordered by category
        cursor.execute("""
            SELECT CourseID, CourseName, Description, Duration, Price, Currency, Category
            FROM Courses
            WHERE IsActive = 1
            ORDER BY Category, CourseName
        """)
        all_courses = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching courses for public page: {e}", exc_info=True)
        flash("Could not load course information at this time. Please try again later.", "warning")
        # In case of error, we can still render the page but with an empty list
        
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()
            
    # We can group courses by category for easier rendering in the template
    grouped_courses = {}
    for course in all_courses:
        category = course.get('Category', 'General') # Default category if none is set
        if category not in grouped_courses:
            grouped_courses[category] = []
        grouped_courses[category].append(course)

    return render_template('Website/courses_page.html', 
                           title="Train To Hire Courses",
                           grouped_courses=grouped_courses)
    
@courses_page_bp.route('/<int:course_id>/apply', methods=['GET'])
@login_required # Only logged-in users can apply
def apply_for_course_form(course_id):
    """
    Displays the application form for a specific course.
    """
    # Ensure the user is a candidate
    if not hasattr(current_user, 'role_type') or current_user.role_type != 'Candidate':
        flash("Only registered candidates can apply for courses. Please log in or register as a candidate.", "warning")
        return redirect(url_for('login_bp.login', next=request.url))

    conn = get_db_connection()
    course = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT CourseID, CourseName FROM Courses WHERE CourseID = %s AND IsActive = 1", (course_id,))
        course = cursor.fetchone()
    except Exception as e:
        current_app.logger.error(f"Error fetching course details for apply form: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    if not course:
        flash("This course is not available or does not exist.", "danger")
        return redirect(url_for('.view_courses'))

    # Pre-populate form data for the logged-in user
    form_data = {
        'full_name': f"{current_user.first_name} {current_user.last_name}",
        'email': current_user.email
    }

    return render_template('Website/apply_for_course.html', 
                           title=f"Apply for {course['CourseName']}",
                           course=course,
                           form_data=form_data)


@courses_page_bp.route('/<int:course_id>/submit-application', methods=['POST'])
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

    # You can add more server-side validation here if needed
    notes = request.form.get('application_notes', '').strip()

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if already applied/enrolled
        cursor.execute("SELECT EnrollmentID FROM CourseEnrollments WHERE CourseID = %s AND CandidateID = %s", (course_id, candidate_id))
        if cursor.fetchone():
            flash("You have already applied for this course.", "info")
            return redirect(url_for('.view_courses'))
            
        # Insert new application
        sql = """
            INSERT INTO CourseEnrollments (CourseID, CandidateID, Status, Notes)
            VALUES (%s, %s, 'Applied', %s)
        """
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
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            
    # If something fails, redirect back to the form
    return redirect(url_for('.apply_for_course_form', course_id=course_id))