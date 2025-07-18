# routes/Agency_Staff_Portal/course_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import decimal
import mysql.connector

# Roles with full management access (add/edit/delete)
COURSE_MANAGEMENT_ROLES = ['SalesManager', 'CEO', 'Founder']
# Roles that can only view the main list and dashboard
COURSE_VIEW_ROLES = ['SalesManager', 'CEO', 'Founder', 'HeadSourcingTeamLead', 'UnitManager']

course_mgmt_bp = Blueprint('course_mgmt_bp', __name__,
                           template_folder='../../../templates',
                           url_prefix='/courses-management')

# --- Main Listing Page ---
@course_mgmt_bp.route('/')
@login_required_with_role(COURSE_VIEW_ROLES)
def list_all_course_content():
    """
    Lists all Language Sections and their associated Courses for management.
    """
    language_sections = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch all language sections first
        cursor.execute("SELECT * FROM CourseLanguages ORDER BY DisplayOrder, LanguageName")
        language_sections = cursor.fetchall()

        # For each language section, fetch its courses
        for section in language_sections:
            cursor.execute("SELECT * FROM Courses WHERE LanguageID = %s ORDER BY DisplayOrder, Title", (section['LanguageID'],))
            section['courses'] = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching course management list: {e}", exc_info=True)
        flash("Could not load course content.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    
    return render_template('agency_staff_portal/courses/list_course_content.html', 
                           title="Manage Course Page Content",
                           language_sections=language_sections)

# --- Language Section Management ---
@course_mgmt_bp.route('/language-section/add', methods=['GET', 'POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES)
def add_language_section():
    if request.method == 'POST':
        form_data = request.form
        # Simple validation
        if not form_data.get('LanguageName'):
            flash("Language Name is required.", "danger")
            return render_template('agency_staff_portal/courses/add_edit_language_section.html', title="Add New Language Section", form_data=form_data)

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            sql = """
                INSERT INTO CourseLanguages (LanguageName, PageTitle, PageDescription, Benefits, PricingNotes, ImportantNotes, IsActive, DisplayOrder)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                form_data['LanguageName'], form_data.get('PageTitle'), form_data.get('PageDescription'),
                form_data.get('Benefits'), form_data.get('PricingNotes'), form_data.get('ImportantNotes'),
                'IsActive' in form_data, form_data.get('DisplayOrder', 0)
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Language Section added successfully!", "success")
            return redirect(url_for('.list_all_course_content'))
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            flash(f"Database Error: {err.msg}", "danger")
        finally:
            if conn and conn.is_connected(): conn.close()
    
    return render_template('agency_staff_portal/courses/add_edit_language_section.html', title="Add New Language Section", form_data={})

@course_mgmt_bp.route('/language-section/edit/<int:lang_id>', methods=['GET', 'POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES)
def edit_language_section(lang_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        if request.method == 'POST':
            form_data = request.form
            if not form_data.get('LanguageName'):
                flash("Language Name is required.", "danger")
                # Need to refetch to show the form again with an error
                cursor.execute("SELECT * FROM CourseLanguages WHERE LanguageID = %s", (lang_id,))
                current_data = cursor.fetchone()
                return render_template('agency_staff_portal/courses/add_edit_language_section.html', title="Edit Language Section", form_data=current_data, lang_id=lang_id)
            
            sql = """
                UPDATE CourseLanguages SET
                LanguageName = %s, PageTitle = %s, PageDescription = %s, Benefits = %s, 
                PricingNotes = %s, ImportantNotes = %s, IsActive = %s, DisplayOrder = %s, UpdatedAt = NOW()
                WHERE LanguageID = %s
            """
            params = (
                form_data['LanguageName'], form_data.get('PageTitle'), form_data.get('PageDescription'),
                form_data.get('Benefits'), form_data.get('PricingNotes'), form_data.get('ImportantNotes'),
                'IsActive' in form_data, form_data.get('DisplayOrder', 0), lang_id
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Language Section updated successfully!", "success")
            return redirect(url_for('.list_all_course_content'))

        # GET Request
        cursor.execute("SELECT * FROM CourseLanguages WHERE LanguageID = %s", (lang_id,))
        form_data = cursor.fetchone()
        if not form_data:
            flash("Language Section not found.", "danger")
            return redirect(url_for('.list_all_course_content'))
        return render_template('agency_staff_portal/courses/add_edit_language_section.html', title="Edit Language Section", form_data=form_data, lang_id=lang_id)

    except mysql.connector.Error as err:
        if conn and request.method == 'POST': conn.rollback()
        flash(f"Database Error: {err.msg}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    return redirect(url_for('.list_all_course_content'))


@course_mgmt_bp.route('/language-section/delete/<int:lang_id>', methods=['POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES)
def delete_language_section(lang_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM CourseLanguages WHERE LanguageID = %s", (lang_id,))
        conn.commit()
        flash("Language Section and all its courses have been deleted.", "success")
    except Exception as e:
        if conn: conn.rollback()
        flash(f"An error occurred: {e}", "danger")
    finally:
        if conn: conn.close()
    return redirect(url_for('.list_all_course_content'))


# --- Course Card Management ---
@course_mgmt_bp.route('/course/add/<int:lang_id>', methods=['GET', 'POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES)
def add_course(lang_id):
    if request.method == 'POST':
        form_data = request.form
        if not form_data.get('Title'):
            flash("Course Title is required.", "danger")
            return render_template('agency_staff_portal/courses/add_edit_course.html', title="Add New Course Card", form_data=form_data, lang_id=lang_id)
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            sql = """
                INSERT INTO Courses (LanguageID, Title, Description, Price, OriginalPrice, IsActive, DisplayOrder, AddedByStaffID)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            price = decimal.Decimal(form_data['Price']) if form_data.get('Price') else None
            original_price = decimal.Decimal(form_data['OriginalPrice']) if form_data.get('OriginalPrice') else None
            
            params = (
                lang_id, form_data['Title'], form_data.get('Description'),
                price, original_price, 'IsActive' in form_data,
                form_data.get('DisplayOrder', 0), current_user.specific_role_id
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Course Card added successfully!", "success")
            return redirect(url_for('.list_all_course_content'))
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            flash(f"Database Error: {err.msg}", "danger")
        finally:
            if conn and conn.is_connected(): conn.close()

    return render_template('agency_staff_portal/courses/add_edit_course.html', title="Add New Course Card", form_data={}, lang_id=lang_id)


@course_mgmt_bp.route('/course/edit/<int:course_id>', methods=['GET', 'POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES)
def edit_course(course_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        if request.method == 'POST':
            form_data = request.form
            if not form_data.get('Title'):
                flash("Course Title is required.", "danger")
                cursor.execute("SELECT * FROM Courses WHERE CourseID = %s", (course_id,))
                current_data = cursor.fetchone()
                return render_template('agency_staff_portal/courses/add_edit_course.html', title="Edit Course Card", form_data=current_data, course_id=course_id)
            
            sql = """
                UPDATE Courses SET
                Title = %s, Description = %s, Price = %s, OriginalPrice = %s,
                IsActive = %s, DisplayOrder = %s, UpdatedAt = NOW()
                WHERE CourseID = %s
            """
            price = decimal.Decimal(form_data['Price']) if form_data.get('Price') else None
            original_price = decimal.Decimal(form_data['OriginalPrice']) if form_data.get('OriginalPrice') else None

            params = (
                form_data['Title'], form_data.get('Description'),
                price, original_price, 'IsActive' in form_data,
                form_data.get('DisplayOrder', 0), course_id
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Course Card updated successfully!", "success")
            return redirect(url_for('.list_all_course_content'))
        
        # GET Request
        cursor.execute("SELECT * FROM Courses WHERE CourseID = %s", (course_id,))
        form_data = cursor.fetchone()
        if not form_data:
            flash("Course Card not found.", "danger")
            return redirect(url_for('.list_all_course_content'))
        return render_template('agency_staff_portal/courses/add_edit_course.html', title="Edit Course Card", form_data=form_data, course_id=course_id)
    
    except (mysql.connector.Error, decimal.InvalidOperation) as err:
        if conn and request.method == 'POST': conn.rollback()
        flash(f"Invalid Data or DB Error: {err}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.list_all_course_content'))


@course_mgmt_bp.route('/course/delete/<int:course_id>', methods=['POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES)
def delete_course(course_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Courses WHERE CourseID = %s", (course_id,))
        conn.commit()
        flash("Course Card deleted.", "success")
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        # Handle case where enrollments exist
        if err.errno == 1451:
            flash("Cannot delete this course as there are active enrollments. Deactivate it instead.", "danger")
        else:
            flash(f"A database error occurred: {err.msg}", "danger")
    finally:
        if conn: conn.close()
    return redirect(url_for('.list_all_course_content'))

@course_mgmt_bp.route('/dashboard')
@login_required_with_role(COURSE_VIEW_ROLES)
def courses_dashboard():
    dashboard_data = {
        'total_sales_revenue': decimal.Decimal('0.00'),
        'ongoing_students': 0, 'graduated_students': 0, 'active_courses': 0,
        'pending_applications': 0, 'default_currency': 'EGP'
    }
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # KPI 1: Active Courses
        cursor.execute("SELECT COUNT(*) as course_count FROM Courses WHERE IsActive = 1")
        dashboard_data['active_courses'] = cursor.fetchone()['course_count']
        
        # KPI 2: Total Sales Revenue (from confirmed enrollments)
        cursor.execute("""
            SELECT SUM(c.Price) as total_revenue, MIN(cl.LanguageName) as example_lang
            FROM CourseEnrollments ce
            JOIN Courses c ON ce.CourseID = c.CourseID
            JOIN CourseLanguages cl ON c.LanguageID = cl.LanguageID
            WHERE ce.Status IN ('Enrolled', 'InProgress', 'Completed') AND c.Price IS NOT NULL
        """)
        sales = cursor.fetchone()
        if sales and sales['total_revenue']:
            dashboard_data['total_sales_revenue'] = sales['total_revenue']
        
        # KPI 3: Ongoing Students
        cursor.execute("SELECT COUNT(DISTINCT CandidateID) as count FROM CourseEnrollments WHERE Status = 'InProgress'")
        dashboard_data['ongoing_students'] = cursor.fetchone()['count']
        
        # KPI 4: Graduated Students
        cursor.execute("SELECT COUNT(DISTINCT CandidateID) as count FROM CourseEnrollments WHERE Status = 'Completed'")
        dashboard_data['graduated_students'] = cursor.fetchone()['count']
        
        # KPI 5: Pending Applications
        cursor.execute("SELECT COUNT(*) as count FROM CourseEnrollments WHERE Status = 'Applied'")
        dashboard_data['pending_applications'] = cursor.fetchone()['count']
        
    except Exception as e:
        current_app.logger.error(f"Error fetching course dashboard data: {e}", exc_info=True)
        flash("Could not load all dashboard data.", "warning")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('agency_staff_portal/courses/courses_dashboard.html', 
                           title='Courses Dashboard', 
                           dashboard_data=dashboard_data)

@course_mgmt_bp.route('/enrollment-requests')
@login_required_with_role(COURSE_MANAGEMENT_ROLES)
def manage_enrollment_requests():
    applications = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                ce.EnrollmentID,
                ce.EnrollmentDate AS ApplicationDate,
                ce.Notes,
                c.Title AS CourseName,
                u.FirstName AS CandidateFirstName,
                u.LastName AS CandidateLastName,
                u.Email AS CandidateEmail,
                u.PhoneNumber AS CandidatePhone
            FROM CourseEnrollments ce
            JOIN Courses c ON ce.CourseID = c.CourseID
            JOIN Candidates cand ON ce.CandidateID = cand.CandidateID
            JOIN Users u ON cand.UserID = u.UserID
            WHERE ce.Status = 'Applied'
            ORDER BY ce.EnrollmentDate ASC
        """
        cursor.execute(sql)
        applications = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching enrollment requests: {e}", exc_info=True)
        flash("Could not load enrollment requests.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    return render_template('agency_staff_portal/courses/manage_enrollments.html', 
                           title='Manage Enrollment Requests', 
                           applications=applications)

@course_mgmt_bp.route('/enrollment/update-status/<int:enrollment_id>', methods=['POST'])
@login_required_with_role(COURSE_MANAGEMENT_ROLES)
def update_enrollment_status(enrollment_id):
    new_status = request.form.get('status')
    allowed_statuses = ['Enrolled', 'PendingPayment', 'Cancelled', 'InProgress', 'Completed']
    
    if not new_status or new_status not in allowed_statuses:
        flash("Invalid status update provided.", "danger")
        return redirect(url_for('.manage_enrollment_requests'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # We allow updating from 'Applied' or other states now
        sql = "UPDATE CourseEnrollments SET Status = %s, UpdatedAt = NOW() WHERE EnrollmentID = %s"
        cursor.execute(sql, (new_status, enrollment_id))
        conn.commit()
        
        if cursor.rowcount > 0:
            flash(f"Enrollment status successfully updated to '{new_status}'.", "success")
        else:
            flash("Could not update status. The application may no longer exist.", "warning")

    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error updating enrollment status for ID {enrollment_id}: {e}", exc_info=True)
        flash("A database error occurred while updating the status.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    # Redirect back to the page the action was taken from
    referer = request.headers.get("Referer")
    if referer and 'enrollment-requests' in referer:
        return redirect(url_for('.manage_enrollment_requests'))
    # Add other redirects if needed, e.g., from a student profile page
    return redirect(url_for('.courses_dashboard'))