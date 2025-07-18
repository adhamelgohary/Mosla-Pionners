# routes/Agency_Staff_Portal/package_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import decimal
import mysql.connector

# Roles with full management access (add/edit/delete)
PACKAGE_MANAGEMENT_ROLES = ['SalesManager', 'CEO', 'Founder']
# Roles that can only view the main list and dashboard
PACKAGE_VIEW_ROLES = ['SalesManager', 'CEO', 'Founder', 'HeadSourcingTeamLead', 'UnitManager']

# Renaming blueprint for clarity to align with the new structure
package_mgmt_bp = Blueprint('package_mgmt_bp', __name__,
                            template_folder='../../../templates',
                            url_prefix='/packages-management')

# --- Main Listing Page ---
@package_mgmt_bp.route('/')
@login_required_with_role(PACKAGE_VIEW_ROLES)
def list_all_packages():
    """
    Lists all Main Packages and their associated Sub-Packages for management.
    """
    main_packages = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch MainPackages and join with Languages to get the language name
        sql = """
            SELECT mp.*, l.LanguageName 
            FROM MainPackages mp
            JOIN Languages l ON mp.LanguageID = l.LanguageID
            ORDER BY l.LanguageName, mp.Name
        """
        cursor.execute(sql)
        main_packages = cursor.fetchall()

        # For each main package, fetch its sub-packages
        for package in main_packages:
            cursor.execute("SELECT * FROM SubPackages WHERE MainPackageID = %s ORDER BY DisplayOrder, Name", (package['PackageID'],))
            package['sub_packages'] = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching package management list: {e}", exc_info=True)
        flash("Could not load package content.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    
    # Template and variable names updated for new structure
    return render_template('agency_staff_portal/courses/list_packages.html', 
                           title="Manage Course Packages",
                           main_packages=main_packages)

# --- Main Package Management ---
@package_mgmt_bp.route('/main-package/add', methods=['GET', 'POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def add_main_package():
    languages = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT LanguageID, LanguageName FROM Languages ORDER BY LanguageName")
        languages = cursor.fetchall()

        if request.method == 'POST':
            form_data = request.form
            if not form_data.get('Name') or not form_data.get('LanguageID'):
                flash("Package Name and Language are required.", "danger")
                return render_template('agency_staff_portal/courses/add_edit_main_package.html', title="Add New Main Package", form_data=form_data, languages=languages)

            sql = """
                INSERT INTO MainPackages (LanguageID, Name, Description, Benefits, MonolingualOverview, BilingualOverview, Notes, IsActive, AddedByStaffID)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                form_data['LanguageID'], form_data['Name'], form_data.get('Description'),
                form_data.get('Benefits'), form_data.get('MonolingualOverview'), form_data.get('BilingualOverview'),
                form_data.get('Notes'), 'IsActive' in form_data, current_user.specific_role_id
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Main Package added successfully!", "success")
            return redirect(url_for('.list_all_packages'))
    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"Database Error: {err.msg}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    return render_template('agency_staff_portal/courses/add_edit_main_package.html', title="Add New Main Package", form_data={}, languages=languages)


@package_mgmt_bp.route('/main-package/edit/<int:package_id>', methods=['GET', 'POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def edit_main_package(package_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Always fetch languages for the dropdown
        cursor.execute("SELECT LanguageID, LanguageName FROM Languages ORDER BY LanguageName")
        languages = cursor.fetchall()

        if request.method == 'POST':
            form_data = request.form
            if not form_data.get('Name') or not form_data.get('LanguageID'):
                flash("Package Name and Language are required.", "danger")
                cursor.execute("SELECT * FROM MainPackages WHERE PackageID = %s", (package_id,))
                current_data = cursor.fetchone()
                return render_template('agency_staff_portal/courses/add_edit_main_package.html', title="Edit Main Package", form_data=current_data, package_id=package_id, languages=languages)
            
            sql = """
                UPDATE MainPackages SET
                LanguageID = %s, Name = %s, Description = %s, Benefits = %s, MonolingualOverview = %s,
                BilingualOverview = %s, Notes = %s, IsActive = %s, UpdatedAt = NOW()
                WHERE PackageID = %s
            """
            params = (
                form_data['LanguageID'], form_data['Name'], form_data.get('Description'),
                form_data.get('Benefits'), form_data.get('MonolingualOverview'), form_data.get('BilingualOverview'),
                form_data.get('Notes'), 'IsActive' in form_data, package_id
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Main Package updated successfully!", "success")
            return redirect(url_for('.list_all_packages'))

        # GET Request
        cursor.execute("SELECT * FROM MainPackages WHERE PackageID = %s", (package_id,))
        form_data = cursor.fetchone()
        if not form_data:
            flash("Main Package not found.", "danger")
            return redirect(url_for('.list_all_packages'))
        return render_template('agency_staff_portal/courses/add_edit_main_package.html', title="Edit Main Package", form_data=form_data, package_id=package_id, languages=languages)

    except mysql.connector.Error as err:
        if conn and request.method == 'POST' and conn.is_connected(): conn.rollback()
        flash(f"Database Error: {err.msg}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    return redirect(url_for('.list_all_packages'))


@package_mgmt_bp.route('/main-package/delete/<int:package_id>', methods=['POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def delete_main_package(package_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Deleting from MainPackages will cascade to SubPackages and then to Enrollments if configured
        cursor.execute("DELETE FROM MainPackages WHERE PackageID = %s", (package_id,))
        conn.commit()
        flash("Main Package and all its sub-packages have been deleted.", "success")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_all_packages'))


# --- Sub-Package Management ---
@package_mgmt_bp.route('/sub-package/add/<int:main_package_id>', methods=['GET', 'POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def add_sub_package(main_package_id):
    if request.method == 'POST':
        form_data = request.form
        if not form_data.get('Name'):
            flash("Sub-Package Name is required.", "danger")
            return render_template('agency_staff_portal/courses/add_edit_sub_package.html', title="Add New Sub-Package", form_data=form_data, main_package_id=main_package_id)
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            sql = """
                INSERT INTO SubPackages (MainPackageID, Name, Description, Price, NumSessionsMonolingual, NumSessionsBilingual, MonolingualDetails, BilingualDetails, IsActive, DisplayOrder, AddedByStaffID)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            price = decimal.Decimal(form_data['Price']) if form_data.get('Price') else decimal.Decimal('0.00')
            
            params = (
                main_package_id, form_data['Name'], form_data.get('Description'),
                price, form_data.get('NumSessionsMonolingual', 0), form_data.get('NumSessionsBilingual', 0),
                form_data.get('MonolingualDetails'), form_data.get('BilingualDetails'),
                'IsActive' in form_data, form_data.get('DisplayOrder', 0), current_user.specific_role_id
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Sub-Package added successfully!", "success")
            return redirect(url_for('.list_all_packages'))
        except (mysql.connector.Error, decimal.InvalidOperation) as err:
            if conn and conn.is_connected(): conn.rollback()
            flash(f"Invalid Data or DB Error: {err}", "danger")
        finally:
            if conn and conn.is_connected(): conn.close()

    return render_template('agency_staff_portal/courses/add_edit_sub_package.html', title="Add New Sub-Package", form_data={}, main_package_id=main_package_id)


@package_mgmt_bp.route('/sub-package/edit/<int:sub_package_id>', methods=['GET', 'POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def edit_sub_package(sub_package_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        if request.method == 'POST':
            form_data = request.form
            if not form_data.get('Name'):
                flash("Sub-Package Name is required.", "danger")
                cursor.execute("SELECT * FROM SubPackages WHERE SubPackageID = %s", (sub_package_id,))
                current_data = cursor.fetchone()
                return render_template('agency_staff_portal/courses/add_edit_sub_package.html', title="Edit Sub-Package", form_data=current_data, sub_package_id=sub_package_id)
            
            sql = """
                UPDATE SubPackages SET
                Name = %s, Description = %s, Price = %s, NumSessionsMonolingual = %s, NumSessionsBilingual = %s,
                MonolingualDetails = %s, BilingualDetails = %s, IsActive = %s, DisplayOrder = %s, UpdatedAt = NOW()
                WHERE SubPackageID = %s
            """
            price = decimal.Decimal(form_data['Price']) if form_data.get('Price') else decimal.Decimal('0.00')

            params = (
                form_data['Name'], form_data.get('Description'), price,
                form_data.get('NumSessionsMonolingual', 0), form_data.get('NumSessionsBilingual', 0),
                form_data.get('MonolingualDetails'), form_data.get('BilingualDetails'),
                'IsActive' in form_data, form_data.get('DisplayOrder', 0), sub_package_id
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Sub-Package updated successfully!", "success")
            return redirect(url_for('.list_all_packages'))
        
        # GET Request
        cursor.execute("SELECT * FROM SubPackages WHERE SubPackageID = %s", (sub_package_id,))
        form_data = cursor.fetchone()
        if not form_data:
            flash("Sub-Package not found.", "danger")
            return redirect(url_for('.list_all_packages'))
        return render_template('agency_staff_portal/courses/add_edit_sub_package.html', title="Edit Sub-Package", form_data=form_data, sub_package_id=sub_package_id)
    
    except (mysql.connector.Error, decimal.InvalidOperation) as err:
        if conn and request.method == 'POST' and conn.is_connected(): conn.rollback()
        flash(f"Invalid Data or DB Error: {err}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.list_all_packages'))


@package_mgmt_bp.route('/sub-package/delete/<int:sub_package_id>', methods=['POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def delete_sub_package(sub_package_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM SubPackages WHERE SubPackageID = %s", (sub_package_id,))
        conn.commit()
        flash("Sub-Package deleted successfully.", "success")
    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
        if err.errno == 1451: # Foreign key constraint fails
            flash("Cannot delete this sub-package as there are active enrollments. Please deactivate it instead.", "danger")
        else:
            flash(f"A database error occurred: {err.msg}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_all_packages'))


# --- Dashboard & Enrollments ---
@package_mgmt_bp.route('/dashboard')
@login_required_with_role(PACKAGE_VIEW_ROLES)
def packages_dashboard():
    dashboard_data = {
        'total_sales_revenue': decimal.Decimal('0.00'),
        'ongoing_students': 0, 'graduated_students': 0, 'active_packages': 0,
        'pending_applications': 0, 'default_currency': 'EGP'
    }
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # KPI 1: Active Sub-Packages (the purchasable items)
        cursor.execute("SELECT COUNT(*) as package_count FROM SubPackages WHERE IsActive = 1")
        dashboard_data['active_packages'] = cursor.fetchone()['package_count']
        
        # KPI 2: Total Sales Revenue (from confirmed enrollments on sub-packages)
        cursor.execute("""
            SELECT SUM(sp.Price) as total_revenue
            FROM CourseEnrollments ce
            JOIN SubPackages sp ON ce.SubPackageID = sp.SubPackageID
            WHERE ce.Status IN ('Enrolled', 'InProgress', 'Completed') AND sp.Price IS NOT NULL
        """)
        sales = cursor.fetchone()
        if sales and sales['total_revenue']:
            dashboard_data['total_sales_revenue'] = sales['total_revenue']
        
        # KPIs 3, 4, 5 query CourseEnrollments directly and need no structural change
        cursor.execute("SELECT COUNT(DISTINCT CandidateID) as count FROM CourseEnrollments WHERE Status = 'InProgress'")
        dashboard_data['ongoing_students'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(DISTINCT CandidateID) as count FROM CourseEnrollments WHERE Status = 'Completed'")
        dashboard_data['graduated_students'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM CourseEnrollments WHERE Status = 'Applied'")
        dashboard_data['pending_applications'] = cursor.fetchone()['count']
        
    except Exception as e:
        current_app.logger.error(f"Error fetching package dashboard data: {e}", exc_info=True)
        flash("Could not load all dashboard data.", "warning")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('agency_staff_portal/courses/packages_dashboard.html', 
                           title='Packages Dashboard', 
                           dashboard_data=dashboard_data)

@package_mgmt_bp.route('/enrollment-requests')
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def manage_enrollment_requests():
    applications = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # SQL updated to join on SubPackages and MainPackages for full context
        sql = """
            SELECT 
                ce.EnrollmentID,
                ce.EnrollmentDate AS ApplicationDate,
                ce.Notes,
                sp.Name AS SubPackageName,
                mp.Name AS MainPackageName,
                u.FirstName AS CandidateFirstName,
                u.LastName AS CandidateLastName,
                u.Email AS CandidateEmail,
                u.PhoneNumber AS CandidatePhone
            FROM CourseEnrollments ce
            JOIN SubPackages sp ON ce.SubPackageID = sp.SubPackageID
            JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
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

@package_mgmt_bp.route('/enrollment/update-status/<int:enrollment_id>', methods=['POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def update_enrollment_status(enrollment_id):
    # This function is generic and does not depend on the course/package structure, so it remains unchanged.
    new_status = request.form.get('status')
    allowed_statuses = ['Enrolled', 'PendingPayment', 'Cancelled', 'InProgress', 'Completed']
    
    if not new_status or new_status not in allowed_statuses:
        flash("Invalid status update provided.", "danger")
        return redirect(url_for('.manage_enrollment_requests'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = "UPDATE CourseEnrollments SET Status = %s, UpdatedAt = NOW() WHERE EnrollmentID = %s"
        cursor.execute(sql, (new_status, enrollment_id))
        conn.commit()
        
        if cursor.rowcount > 0:
            flash(f"Enrollment status successfully updated to '{new_status}'.", "success")
        else:
            flash("Could not update status. The application may no longer exist.", "warning")

    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Error updating enrollment status for ID {enrollment_id}: {e}", exc_info=True)
        flash("A database error occurred while updating the status.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    referer = request.headers.get("Referer")
    if referer and 'enrollment-requests' in referer:
        return redirect(url_for('.manage_enrollment_requests'))
    
    return redirect(url_for('.packages_dashboard'))