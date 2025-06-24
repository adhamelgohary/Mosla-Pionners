# routes/Agency_Staff_Portal/course_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user 
from utils.decorators import login_required_with_role # Ensure this decorator uses current_user.role_type
from db import get_db_connection
import datetime 
import decimal 
import mysql.connector

# These roles should match the ENUM values in your Staff.Role column
COURSE_MANAGEMENT_ROLES = ['SalesManager', 'CEO', 'OperationsManager']
COURSE_DASHBOARD_VIEW_ROLES = ['SalesManager', 'CEO', 'OperationsManager', 'HeadSourcingTeamLead', 'UnitManager', 'HeadAccountManager', 'SeniorAccountManager', 'AccountManager']

course_mgmt_bp = Blueprint('course_mgmt_bp', __name__,
                           url_prefix='/courses')

# --- Helper Validation Functions (Keep as is, they are good) ---
def validate_course_data(form_data):
    errors = {}
    if not form_data.get('course_name', '').strip():
        errors['course_name'] = 'Course name is required.'
    elif len(form_data.get('course_name', '')) > 255:
        errors['course_name'] = 'Course name is too long (max 255 characters).'
    price_str = form_data.get('price', '').strip()
    if price_str:
        try:
            price_val = decimal.Decimal(price_str)
            if price_val < 0: errors['price'] = 'Price cannot be negative.'
            if price_val > decimal.Decimal('99999999.99'): errors['price'] = 'Price value is too large.'
        except decimal.InvalidOperation: errors['price'] = 'Invalid price format.'
    currency_str = form_data.get('currency', '').strip()
    if currency_str and len(currency_str) > 10: errors['currency'] = 'Currency code too long (max 10 chars).'
    start_date_str = form_data.get('start_date')
    end_date_str = form_data.get('end_date')
    if start_date_str and end_date_str:
        try:
            start_date_obj = datetime.date.fromisoformat(start_date_str)
            end_date_obj = datetime.date.fromisoformat(end_date_str)
            if end_date_obj < start_date_obj: errors['end_date'] = 'End date cannot be before start date.'
        except ValueError:
            errors.setdefault('start_date', []).append('Invalid date format.')
            errors.setdefault('end_date', []).append('Invalid date format.')
    # ... (rest of your validation logic is fine) ...
    return errors

@course_mgmt_bp.route('/')
@login_required_with_role(COURSE_DASHBOARD_VIEW_ROLES, insufficient_role_redirect='staff_dashboard_bp.main_dashboard') # Broader view access
def list_courses():
    courses = []
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT CourseID, CourseName, Duration, Price, Currency, IsActive FROM Courses ORDER BY CreatedAt DESC")
        courses = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching courses: {e}", exc_info=True)
        flash("Could not load courses.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return render_template('agency_staff_portal/courses/staff_list_courses.html', title='Manage Courses', courses=courses)

@course_mgmt_bp.route('/add', methods=['GET', 'POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES, insufficient_role_redirect='staff_dashboard_bp.main_dashboard')
def add_course():
    form_data = {'currency':'EGP', 'is_active': True} # Defaults
    errors = {}
    if request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['is_active'] = request.form.get('is_active') == 'on'
        errors = validate_course_data(form_data)
        if not errors:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                # current_user.specific_role_id is the StaffID for logged-in staff
                added_by_staff_id = current_user.specific_role_id 
                
                # The decorator already ensures only correct roles can access.
                # This check is redundant if decorator is working.
                if not added_by_staff_id or current_user.role_type not in COURSE_MANAGEMENT_ROLES:
                    flash('Error: Your staff profile is not correctly set up to add courses.', 'danger')
                    return render_template('agency_staff_portal/courses/add_edit_course.html', title='Add New Course', form_data=form_data, errors=errors, action_verb='Add')

                sql = """INSERT INTO Courses (CourseName, Description, Duration, Price, Currency,
                                            InstructorName, StartDate, EndDate, Category, Prerequisites,
                                            SyllabusLink, IsActive, AddedByStaffID)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                price_to_insert = decimal.Decimal(form_data['price']) if form_data.get('price','').strip() else None
                val = (form_data.get('course_name').strip(), form_data.get('description') or None, 
                       form_data.get('duration') or None, price_to_insert, 
                       form_data.get('currency').strip() or 'EGP', # Default to EGP if empty
                       form_data.get('instructor_name') or None,
                       form_data.get('start_date') if form_data.get('start_date') else None, 
                       form_data.get('end_date') if form_data.get('end_date') else None, 
                       form_data.get('category') or None, form_data.get('prerequisites') or None, 
                       form_data.get('syllabus_link').strip() or None, 
                       form_data.get('is_active', True), 
                       added_by_staff_id)
                
                cursor.execute(sql, val)
                course_id = cursor.lastrowid 
                
                # Automated announcement (ensure _create_automated_announcement helper is defined, like in job_offer_mgmt)
                # For now, assuming it's not defined here, so commenting out.
                # If you have a shared helper:
                # from ..utils.common_helpers import _create_automated_announcement
                # _create_automated_announcement(cursor, 'Automated_Course', ...)
                
                conn.commit()
                flash('Course added successfully!', 'success')
                # Redirect to view the newly added course, assuming such a route exists
                # If not, redirect to list_courses
                # return redirect(url_for('.view_course', course_id=course_id)) 
                return redirect(url_for('.list_courses'))
            except mysql.connector.Error as db_err: 
                if conn: conn.rollback()
                flash(f'Database error: {str(db_err)}', 'danger'); errors['form'] = str(db_err)
            except Exception as e:
                if conn: conn.rollback()
                flash(f'An unexpected error occurred: {str(e)}', 'danger'); errors['form'] = str(e)
            finally:
                if conn and conn.is_connected():
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn.close()
        else:
            flash('Please correct the errors highlighted below.', 'warning') 
    return render_template('agency_staff_portal/courses/add_edit_course.html', title='Add New Course', form_data=form_data, errors=errors, action_verb='Add')

@course_mgmt_bp.route('/edit/<int:course_id>', methods=['GET', 'POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES, insufficient_role_redirect='staff_dashboard_bp.main_dashboard')
def edit_course(course_id):
    form_data, errors = {}, {}
    original_course_name_for_title = "Course"
    if request.method == 'GET':
        conn_fetch = None
        try:
            conn_fetch = get_db_connection()
            cursor = conn_fetch.cursor(dictionary=True)
            cursor.execute("SELECT * FROM Courses WHERE CourseID = %s", (course_id,))
            data = cursor.fetchone()
            if data:
                form_data = data
                original_course_name_for_title = data.get('CourseName', 'Course')
                if 'Price' in data and isinstance(data['Price'], decimal.Decimal):
                    form_data['Price'] = str(data['Price'])
                if 'StartDate' in data and data['StartDate'] and isinstance(data['StartDate'], datetime.date):
                    form_data['StartDate'] = data['StartDate'].isoformat()
                if 'EndDate' in data and data['EndDate'] and isinstance(data['EndDate'], datetime.date):
                    form_data['EndDate'] = data['EndDate'].isoformat()
                form_data['IsActive'] = bool(data.get('IsActive', True))
            else:
                flash('Course not found.', 'danger')
                return redirect(url_for('.list_courses'))
        except Exception as e:
            flash('Error fetching course details.', 'danger')
            return redirect(url_for('.list_courses'))
        finally:
            if conn_fetch and conn_fetch.is_connected():
                if 'cursor' in locals() and cursor: cursor.close()
                conn_fetch.close()
    
    elif request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['is_active'] = request.form.get('is_active') == 'on'
        original_course_name_for_title = request.form.get('original_course_name_for_title_hidden', form_data.get('course_name', 'Course'))
        errors = validate_course_data(form_data)
        if not errors:
            conn_update = None
            try:
                conn_update = get_db_connection()
                cursor = conn_update.cursor()
                # AddedByStaffID is not updated on edit, only CourseName etc.
                sql = """UPDATE Courses SET CourseName=%s, Description=%s, Duration=%s, Price=%s, Currency=%s,
                                           InstructorName=%s, StartDate=%s, EndDate=%s, Category=%s, Prerequisites=%s,
                                           SyllabusLink=%s, IsActive=%s, UpdatedAt=NOW()
                         WHERE CourseID=%s"""
                price_val = decimal.Decimal(form_data['price']) if form_data.get('price','').strip() else None
                val = (form_data.get('course_name').strip(), form_data.get('description') or None, 
                       form_data.get('duration') or None, price_val, 
                       form_data.get('currency').strip() or 'EGP', 
                       form_data.get('instructor_name') or None,
                       form_data.get('start_date') if form_data.get('start_date') else None, 
                       form_data.get('end_date') if form_data.get('end_date') else None,
                       form_data.get('category') or None, form_data.get('prerequisites') or None, 
                       form_data.get('syllabus_link').strip() or None, 
                       form_data.get('is_active', True), course_id)
                cursor.execute(sql, val)
                conn_update.commit()
                flash('Course updated successfully!', 'success')
                return redirect(url_for('.list_courses'))
            except mysql.connector.Error as db_err:
                if conn_update: conn_update.rollback()
                flash(f'Database error: {str(db_err)}.', 'danger'); errors['form'] = str(db_err)
            except Exception as e:
                if conn_update: conn_update.rollback()
                flash(f'An unexpected error: {str(e)}.', 'danger'); errors['form'] = str(e)
            finally:
                if conn_update and conn_update.is_connected():
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn_update.close()
        else:
            flash('Please correct errors.', 'warning') 
    
    display_course_name = original_course_name_for_title
    return render_template('agency_staff_portal/courses/add_edit_course.html', 
                           title=f"Edit Course: {display_course_name}", form_data=form_data, 
                           errors=errors, action_verb='Update', course_id=course_id,
                           original_course_name_for_title_hidden=original_course_name_for_title)

@course_mgmt_bp.route('/delete/<int:course_id>', methods=['POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES, insufficient_role_redirect='staff_dashboard_bp.main_dashboard')
def delete_course(course_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Check if course exists
        cursor.execute("SELECT CourseID FROM Courses WHERE CourseID = %s", (course_id,))
        if not cursor.fetchone():
            flash('Course not found.', 'warning')
            return redirect(url_for('.list_courses'))
        cursor.execute("DELETE FROM Courses WHERE CourseID = %s", (course_id,))
        conn.commit()
        flash('Course deleted!', 'success' if cursor.rowcount > 0 else 'warning')
    except mysql.connector.Error as e: 
        if conn: conn.rollback()
        if hasattr(e, 'errno') and e.errno == 1451: # FK violation
             flash('Cannot delete course: it is referenced by other records (e.g., enrollments).', 'danger')
        else: flash(f'Database error: {str(e)}', 'danger')
    except Exception as e:
        if conn: conn.rollback() 
        flash(f'An unexpected error: {str(e)}', 'danger')
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return redirect(url_for('.list_courses'))

@course_mgmt_bp.route('/dashboard')
@login_required_with_role(COURSE_DASHBOARD_VIEW_ROLES, insufficient_role_redirect='staff_dashboard_bp.main_dashboard')
def courses_dashboard_page():
    dashboard_data = { 'total_sales_revenue': decimal.Decimal('0.00'), 'potential_course_value': decimal.Decimal('0.00'), 'ongoing_students': 0, 'graduated_students': 0, 'active_courses': 0, 'total_enrollments': 0, 'default_currency': 'EGP' }
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # KPI 1: Active Courses & Potential Value
        cursor.execute("SELECT COUNT(*) as course_count, SUM(Price) as potential_value, MIN(Currency) as base_currency FROM Courses WHERE IsActive = 1")
        stats = cursor.fetchone()
        if stats:
            dashboard_data['active_courses'] = stats.get('course_count', 0)
            dashboard_data['potential_course_value'] = stats.get('potential_value') or decimal.Decimal('0.00')
            dashboard_data['default_currency'] = stats.get('base_currency') or 'EGP'
        # KPI 2: Total Sales Revenue
        cursor.execute("SELECT SUM(c.Price) as total_revenue, MIN(c.Currency) as revenue_currency FROM CourseEnrollments ce JOIN Courses c ON ce.CourseID = c.CourseID WHERE ce.Status IN ('Enrolled', 'InProgress', 'Completed') AND c.Price IS NOT NULL")
        sales = cursor.fetchone()
        if sales and sales.get('total_revenue') is not None:
            dashboard_data['total_sales_revenue'] = sales.get('total_revenue')
            if sales.get('revenue_currency'): dashboard_data['default_currency'] = sales.get('revenue_currency')
        # KPI 3: Ongoing Students
        cursor.execute("SELECT COUNT(DISTINCT CandidateID) as count FROM CourseEnrollments WHERE Status IN ('Enrolled', 'InProgress')")
        res = cursor.fetchone(); dashboard_data['ongoing_students'] = res.get('count', 0) if res else 0
        # KPI 4: Graduated Students
        cursor.execute("SELECT COUNT(DISTINCT CandidateID) as count FROM CourseEnrollments WHERE Status = 'Completed'")
        res = cursor.fetchone(); dashboard_data['graduated_students'] = res.get('count', 0) if res else 0
        # KPI 5: Total Enrollments
        cursor.execute("SELECT COUNT(DISTINCT CandidateID) as count FROM CourseEnrollments WHERE Status NOT IN ('DroppedOut', 'Cancelled', 'Applied')")
        res = cursor.fetchone(); dashboard_data['total_enrollments'] = res.get('count', 0) if res else 0
    except Exception as e:
        flash("Could not load all dashboard data.", "warning")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return render_template('agency_staff_portal/courses/courses_dashboard.html', title='Courses Dashboard', dashboard_data=dashboard_data)