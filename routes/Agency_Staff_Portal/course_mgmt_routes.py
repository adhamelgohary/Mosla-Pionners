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

# --- Main Listing Page (Unchanged) ---
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
        # 1. Fetch all MainPackages
        cursor.execute("SELECT * FROM MainPackages ORDER BY Name")
        main_packages = cursor.fetchall()

        # 2. For each package, fetch its associated languages and sub-packages
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

            # Fetch sub-packages
            cursor.execute("SELECT * FROM SubPackages WHERE MainPackageID = %s ORDER BY DisplayOrder, Name", (package['PackageID'],))
            package['sub_packages'] = cursor.fetchall()
            
    except Exception as e:
        current_app.logger.error(f"Error fetching package management list: {e}", exc_info=True)
        flash("Could not load package content.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    
    return render_template('agency_staff_portal/courses/list_packages.html', 
                           title="Manage Course Packages",
                           main_packages=main_packages)
    

# --- Main Package CRUD (FIXED) ---
@package_mgmt_bp.route('/main-package/add', methods=['GET', 'POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def add_main_package():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT LanguageID, LanguageName FROM Languages ORDER BY LanguageName")
        languages = cursor.fetchall()

        if request.method == 'POST':
            form_data = request.form
            selected_languages = form_data.getlist('LanguageIDs')

            if not form_data.get('Name') or not selected_languages:
                flash("Package Name and at least one Language are required.", "danger")
                return render_template('agency_staff_portal/courses/add_edit_main_package.html', title="Add New Main Package", form_data=form_data, languages=languages)
            
            sql_main = """
                INSERT INTO MainPackages (Name, Description, Benefits, MonolingualOverview, BilingualOverview, Notes, Status, AddedByStaffID)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            params_main = (
                form_data['Name'], form_data.get('Description'),
                form_data.get('Benefits'), form_data.get('MonolingualOverview'), form_data.get('BilingualOverview'),
                form_data.get('Notes'), form_data.get('Status', 'Inactive'), current_user.specific_role_id
            )
            cursor.execute(sql_main, params_main)
            new_package_id = cursor.lastrowid
            
            sql_lang = "INSERT INTO MainPackageLanguages (PackageID, LanguageID) VALUES (%s, %s)"
            for lang_id in selected_languages:
                cursor.execute(sql_lang, (new_package_id, lang_id))
            
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
        cursor.execute("SELECT LanguageID, LanguageName FROM Languages ORDER BY LanguageName")
        languages = cursor.fetchall()

        if request.method == 'POST':
            form_data = request.form
            selected_languages = form_data.getlist('LanguageIDs')

            if not form_data.get('Name') or not selected_languages:
                flash("Package Name and at least one Language are required.", "danger")
                cursor.execute("SELECT * FROM MainPackages WHERE PackageID = %s", (package_id,))
                current_data = cursor.fetchone()
                cursor.execute("SELECT LanguageID FROM MainPackageLanguages WHERE PackageID = %s", (package_id,))
                current_data['selected_languages'] = [row['LanguageID'] for row in cursor.fetchall()]
                return render_template('agency_staff_portal/courses/add_edit_main_package.html', title="Edit Main Package", form_data=current_data, package_id=package_id, languages=languages)

            sql_main = """
                UPDATE MainPackages SET
                Name = %s, Description = %s, Benefits = %s, MonolingualOverview = %s,
                BilingualOverview = %s, Notes = %s, Status = %s, UpdatedAt = NOW()
                WHERE PackageID = %s
            """
            params_main = (
                form_data['Name'], form_data.get('Description'), form_data.get('Benefits'),
                form_data.get('MonolingualOverview'), form_data.get('BilingualOverview'),
                form_data.get('Notes'), form_data.get('Status', 'Inactive'), package_id
            )
            cursor.execute(sql_main, params_main)
            
            cursor.execute("DELETE FROM MainPackageLanguages WHERE PackageID = %s", (package_id,))
            
            sql_lang = "INSERT INTO MainPackageLanguages (PackageID, LanguageID) VALUES (%s, %s)"
            for lang_id in selected_languages:
                cursor.execute(sql_lang, (package_id, lang_id))
            
            conn.commit()
            flash("Main Package updated successfully!", "success")
            return redirect(url_for('.list_all_packages'))

        cursor.execute("SELECT * FROM MainPackages WHERE PackageID = %s", (package_id,))
        form_data = cursor.fetchone()
        if not form_data:
            flash("Main Package not found.", "danger")
            return redirect(url_for('.list_all_packages'))
        
        cursor.execute("SELECT LanguageID FROM MainPackageLanguages WHERE PackageID = %s", (package_id,))
        form_data['selected_languages'] = [row['LanguageID'] for row in cursor.fetchall()]
        return render_template('agency_staff_portal/courses/add_edit_main_package.html', title="Edit Main Package", form_data=form_data, package_id=package_id, languages=languages)

    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
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
        cursor.execute("DELETE FROM MainPackages WHERE PackageID = %s", (package_id,))
        conn.commit()
        flash("Main Package and all its sub-packages have been deleted.", "success")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_all_packages'))


# --- Sub-Package CRUD (Unchanged) ---
@package_mgmt_bp.route('/sub-package/add/<int:main_package_id>', methods=['GET', 'POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def add_sub_package(main_package_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT l.LanguageID, l.LanguageName 
            FROM MainPackageLanguages mpl
            JOIN Languages l ON mpl.LanguageID = l.LanguageID
            WHERE mpl.PackageID = %s
            ORDER BY l.LanguageName
        """, (main_package_id,))
        main_package_languages = cursor.fetchall()

        if not main_package_languages:
            flash("Cannot add a sub-package to a main package with no languages defined.", "danger")
            return redirect(url_for('.list_all_packages'))

        if request.method == 'POST':
            form_data = request.form
            if not form_data.get('Name'):
                flash("Sub-Package Name is required.", "danger")
                return render_template('agency_staff_portal/courses/add_edit_sub_package.html', 
                                       title="Add New Sub-Package", form_data=form_data, 
                                       main_package_id=main_package_id, main_package_languages=main_package_languages)
            
            sql = """
                INSERT INTO SubPackages (MainPackageID, Name, Description, Price, NumSessionsMonolingual, NumSessionsBilingual, MonolingualDetails, BilingualDetails, Status, DisplayOrder, AddedByStaffID)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            price = decimal.Decimal(form_data['Price']) if form_data.get('Price') else decimal.Decimal('0.00')
            num_mono = form_data.get('NumSessionsMonolingual', 0)
            num_bi = form_data.get('NumSessionsBilingual', 0)
            params = (
                main_package_id, form_data['Name'], form_data.get('Description'),
                price, num_mono, num_bi,
                form_data.get('MonolingualDetails'), form_data.get('BilingualDetails'),
                form_data.get('Status', 'Inactive'), form_data.get('DisplayOrder', 0), current_user.specific_role_id
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Sub-Package added successfully!", "success")
            return redirect(url_for('.list_all_packages'))
            
        return render_template('agency_staff_portal/courses/add_edit_sub_package.html', 
                               title="Add New Sub-Package", form_data={}, 
                               main_package_id=main_package_id, main_package_languages=main_package_languages)

    except (mysql.connector.Error, decimal.InvalidOperation) as err:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"Invalid Data or DB Error: {err}", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    
    return redirect(url_for('.list_all_packages'))


@package_mgmt_bp.route('/sub-package/edit/<int:sub_package_id>', methods=['GET', 'POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def edit_sub_package(sub_package_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM SubPackages WHERE SubPackageID = %s", (sub_package_id,))
        form_data = cursor.fetchone()
        if not form_data:
            flash("Sub-Package not found.", "danger")
            return redirect(url_for('.list_all_packages'))
            
        cursor.execute("""
            SELECT l.LanguageID, l.LanguageName 
            FROM MainPackageLanguages mpl
            JOIN Languages l ON mpl.LanguageID = l.LanguageID
            WHERE mpl.PackageID = %s
            ORDER BY l.LanguageName
        """, (form_data['MainPackageID'],))
        main_package_languages = cursor.fetchall()

        if request.method == 'POST':
            form_data_from_post = request.form
            if not form_data_from_post.get('Name'):
                flash("Sub-Package Name is required.", "danger")
                return render_template('agency_staff_portal/courses/add_edit_sub_package.html', 
                                       title="Edit Sub-Package", form_data=form_data, 
                                       sub_package_id=sub_package_id, main_package_languages=main_package_languages)
            
            sql = """
                UPDATE SubPackages SET
                Name = %s, Description = %s, Price = %s, NumSessionsMonolingual = %s, NumSessionsBilingual = %s,
                MonolingualDetails = %s, BilingualDetails = %s, Status = %s, DisplayOrder = %s, UpdatedAt = NOW()
                WHERE SubPackageID = %s
            """
            price = decimal.Decimal(form_data_from_post['Price']) if form_data_from_post.get('Price') else decimal.Decimal('0.00')
            num_mono = form_data_from_post.get('NumSessionsMonolingual', 0)
            num_bi = form_data_from_post.get('NumSessionsBilingual', 0)
            params = (
                form_data_from_post['Name'], form_data_from_post.get('Description'), price,
                num_mono, num_bi,
                form_data_from_post.get('MonolingualDetails'), form_data_from_post.get('BilingualDetails'),
                form_data_from_post.get('Status', 'Inactive'), form_data_from_post.get('DisplayOrder', 0), sub_package_id
            )
            cursor.execute(sql, params)
            conn.commit()
            flash("Sub-Package updated successfully!", "success")
            return redirect(url_for('.list_all_packages'))
        
        return render_template('agency_staff_portal/courses/add_edit_sub_package.html', 
                               title="Edit Sub-Package", form_data=form_data, 
                               sub_package_id=sub_package_id, main_package_languages=main_package_languages)
    
    except (mysql.connector.Error, decimal.InvalidOperation) as err:
        if conn and request.method == 'POST' and conn.is_connected(): conn.rollback()
        flash(f"Invalid Data or DB Error: {err}", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

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
        if err.errno == 1451:
            flash("Cannot delete this sub-package as there are active enrollments. Please deactivate it instead.", "danger")
        else:
            flash(f"A database error occurred: {err.msg}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_all_packages'))


# --- Dashboard & Enrollments (UPDATED SECTION) ---
@package_mgmt_bp.route('/dashboard')
@login_required_with_role(PACKAGE_VIEW_ROLES)
def packages_dashboard():
    dashboard_data = {
        'total_sales_revenue': decimal.Decimal('0.00'),
        'ongoing_students': 0, 'graduated_students': 0, 'active_packages': 0,
        'pending_applications': 0, 'default_currency': 'EGP', 'rejected_applications': 0
    }
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # KPI 1: Active Sub-Packages
        cursor.execute("SELECT COUNT(*) as package_count FROM SubPackages WHERE IsActive = 1")
        dashboard_data['active_packages'] = cursor.fetchone()['package_count']
        
        # KPI 2: Total Sales Revenue
        cursor.execute("""
            SELECT SUM(sp.Price) as total_revenue
            FROM CourseEnrollments ce
            JOIN SubPackages sp ON ce.SubPackageID = sp.SubPackageID
            WHERE ce.Status IN ('Enrolled', 'InProgress', 'Completed') AND sp.Price IS NOT NULL
        """)
        sales = cursor.fetchone()
        if sales and sales['total_revenue']:
            dashboard_data['total_sales_revenue'] = sales['total_revenue']
        
        # Other KPIs
        cursor.execute("SELECT COUNT(DISTINCT CandidateID) as count FROM CourseEnrollments WHERE Status = 'InProgress'")
        dashboard_data['ongoing_students'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(DISTINCT CandidateID) as count FROM CourseEnrollments WHERE Status = 'Completed'")
        dashboard_data['graduated_students'] = cursor.fetchone()['count']
        
        # PENDING now includes 'Applied' and 'PendingPayment'
        cursor.execute("SELECT COUNT(*) as count FROM CourseEnrollments WHERE Status IN ('Applied', 'PendingPayment')")
        dashboard_data['pending_applications'] = cursor.fetchone()['count']

        # NEW KPI for Rejected
        cursor.execute("SELECT COUNT(*) as count FROM CourseEnrollments WHERE Status = 'Cancelled'")
        dashboard_data['rejected_applications'] = cursor.fetchone()['count']
        
    except Exception as e:
        current_app.logger.error(f"Error fetching package dashboard data: {e}", exc_info=True)
        flash("Could not load all dashboard data.", "warning")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('agency_staff_portal/courses/packages_dashboard.html', 
                           title='Packages Dashboard', 
                           dashboard_data=dashboard_data)


# UPDATED to show 'Applied' and 'PendingPayment' statuses
@package_mgmt_bp.route('/enrollment-requests')
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def manage_enrollment_requests():
    applications = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                ce.EnrollmentID, ce.Status, ce.EnrollmentDate AS ApplicationDate, ce.Notes,
                sp.Name AS SubPackageName, mp.Name AS MainPackageName,
                u.FirstName AS CandidateFirstName, u.LastName AS CandidateLastName,
                u.Email AS CandidateEmail, u.PhoneNumber AS CandidatePhone
            FROM CourseEnrollments ce
            JOIN SubPackages sp ON ce.SubPackageID = sp.SubPackageID
            JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            JOIN Candidates cand ON ce.CandidateID = cand.CandidateID
            JOIN Users u ON cand.UserID = u.UserID
            WHERE ce.Status IN ('Applied', 'PendingPayment')
            ORDER BY ce.EnrollmentDate ASC
        """
        cursor.execute(sql)
        applications = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching pending enrollment requests: {e}", exc_info=True)
        flash("Could not load pending enrollment requests.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    return render_template('agency_staff_portal/courses/manage_enrollments.html', 
                           title='Manage Pending Enrollments', 
                           applications=applications)


# NEW ROUTE for approved applications
@package_mgmt_bp.route('/enrollments/approved')
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def manage_approved_enrollments():
    applications = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                ce.EnrollmentID, ce.Status, ce.EnrollmentDate AS ApplicationDate, ce.Notes,
                sp.Name AS SubPackageName, mp.Name AS MainPackageName,
                u.FirstName AS CandidateFirstName, u.LastName AS CandidateLastName,
                u.Email AS CandidateEmail, u.PhoneNumber AS CandidatePhone
            FROM CourseEnrollments ce
            JOIN SubPackages sp ON ce.SubPackageID = sp.SubPackageID
            JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            JOIN Candidates cand ON ce.CandidateID = cand.CandidateID
            JOIN Users u ON cand.UserID = u.UserID
            WHERE ce.Status IN ('Enrolled', 'InProgress', 'Completed')
            ORDER BY ce.UpdatedAt DESC
        """
        cursor.execute(sql)
        applications = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching approved enrollments: {e}", exc_info=True)
        flash("Could not load approved enrollments.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    return render_template('agency_staff_portal/courses/approved_enrollments.html', 
                           title='Approved & Active Enrollments', 
                           applications=applications)


# NEW ROUTE for rejected applications
@package_mgmt_bp.route('/enrollments/rejected')
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def manage_rejected_enrollments():
    applications = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT 
                ce.EnrollmentID, ce.Status, ce.EnrollmentDate AS ApplicationDate, ce.Notes,
                sp.Name AS SubPackageName, mp.Name AS MainPackageName,
                u.FirstName AS CandidateFirstName, u.LastName AS CandidateLastName,
                u.Email AS CandidateEmail, u.PhoneNumber AS CandidatePhone
            FROM CourseEnrollments ce
            JOIN SubPackages sp ON ce.SubPackageID = sp.SubPackageID
            JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            JOIN Candidates cand ON ce.CandidateID = cand.CandidateID
            JOIN Users u ON cand.UserID = u.UserID
            WHERE ce.Status = 'Cancelled'
            ORDER BY ce.UpdatedAt DESC
        """
        cursor.execute(sql)
        applications = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching rejected enrollments: {e}", exc_info=True)
        flash("Could not load rejected enrollments.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    return render_template('agency_staff_portal/courses/rejected_enrollments.html', 
                           title='Rejected & Cancelled Enrollments', 
                           applications=applications)


@package_mgmt_bp.route('/enrollment/update-status/<int:enrollment_id>', methods=['POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def update_enrollment_status(enrollment_id):
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
            
    # Intelligent redirect based on where the user came from
    referer = request.headers.get("Referer")
    if referer:
        if 'enrollments/approved' in referer:
            return redirect(url_for('.manage_approved_enrollments'))
        if 'enrollment-requests' in referer:
             return redirect(url_for('.manage_enrollment_requests'))
    
    return redirect(url_for('.packages_dashboard'))

@package_mgmt_bp.route('/update-status', methods=['POST'])
@login_required_with_role(PACKAGE_MANAGEMENT_ROLES)
def update_package_status():
    package_type = request.form.get('package_type')
    package_id = request.form.get('package_id', type=int)
    new_status = request.form.get('status')
    
    allowed_types = {'main': 'MainPackages', 'sub': 'SubPackages'}
    allowed_statuses = ['Active', 'Inactive', 'On Hold']

    if not all([package_type, package_id, new_status]) or package_type not in allowed_types or new_status not in allowed_statuses:
        flash("Invalid request. Could not update status.", "danger")
        return redirect(url_for('.list_all_packages'))

    table_name = allowed_types[package_type]
    id_column = 'PackageID' if package_type == 'main' else 'SubPackageID'

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = f"UPDATE {table_name} SET Status = %s, UpdatedAt = NOW() WHERE {id_column} = %s"
        cursor.execute(sql, (new_status, package_id))
        conn.commit()
        
        if cursor.rowcount > 0:
            flash(f"Package status updated to '{new_status}'.", "success")
        else:
            flash("Package not found or status was already set.", "warning")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Error updating package status: {e}", exc_info=True)
        flash("A database error occurred.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
            
    return redirect(url_for('.list_all_packages'))