# routes/Website/courses_page_routes.py
from flask import Blueprint, render_template, current_app, flash
from db import get_db_connection
import mysql.connector

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