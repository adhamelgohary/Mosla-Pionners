# routes/Agency_Staff_Portal/group_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import mysql.connector
from werkzeug.security import generate_password_hash

# Roles with management access
GROUP_MANAGEMENT_ROLES = ['SalesManager', 'CEO', 'Founder', 'Admin'] 

group_mgmt_bp = Blueprint('group_mgmt_bp', __name__,
                          template_folder='../../../templates',
                          url_prefix='/course-groups')

@group_mgmt_bp.route('/instructors')
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def list_instructors():
    """Lists all staff members with the 'Instructor' role."""
    instructors = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # UPDATED to fetch more data for the list view
        cursor.execute("""
            SELECT 
                s.StaffID, s.Specialization,
                u.UserID, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.AccountStatus
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role = 'Instructor'
            ORDER BY u.LastName, u.FirstName
        """)
        instructors = cursor.fetchall()
    except Exception as e:
        flash("Could not load instructors.", "danger")
        current_app.logger.error(f"Error fetching instructors: {e}", exc_info=True)
    finally:
        if conn and conn.is_connected():
            conn.close()
    
    return render_template('agency_staff_portal/courses/groups/list_instructors.html',
                           title="Manage Instructors",
                           instructors=instructors)

@group_mgmt_bp.route('/instructors/add', methods=['GET', 'POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def add_instructor():
    """Adds a new instructor, which involves creating a User and a Staff record."""
    if request.method == 'POST':
        form = request.form
        email = form.get('Email')
        password = form.get('Password')
        first_name = form.get('FirstName')
        
        if not all([email, password, first_name]):
            flash("First Name, Email, and Password are required.", "danger")
            return render_template('agency_staff_portal/courses/groups/add_edit_instructor.html', title="Add New Instructor", form_data=form)

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Step 1: Create the User record
            hashed_password = generate_password_hash(password)
            sql_user = """
                INSERT INTO Users (FirstName, LastName, Email, PasswordHash, PhoneNumber, AccountStatus)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            params_user = (
                first_name, form.get('LastName'), email, hashed_password,
                form.get('PhoneNumber'), form.get('AccountStatus', 'Active')
            )
            cursor.execute(sql_user, params_user)
            new_user_id = cursor.lastrowid

            # Step 2: Create the Staff record with the 'Instructor' role
            sql_staff = """
                INSERT INTO Staff (UserID, Role, Specialization, Bio)
                VALUES (%s, 'Instructor', %s, %s)
            """
            params_staff = (new_user_id, form.get('Specialization'), form.get('Bio'))
            cursor.execute(sql_staff, params_staff)
            
            conn.commit()
            flash('Instructor added successfully!', 'success')
            return redirect(url_for('.list_instructors'))

        except mysql.connector.Error as err:
            if conn and conn.is_connected(): conn.rollback()
            if err.errno == 1062: # Duplicate entry
                flash('An account with this email already exists.', 'danger')
            else:
                flash(f'Database error: {err.msg}', 'danger')
            return render_template('agency_staff_portal/courses/groups/add_edit_instructor.html', title="Add New Instructor", form_data=form)
        finally:
            if conn and conn.is_connected(): conn.close()
            
    return render_template('agency_staff_portal/courses/groups/add_edit_instructor.html', title="Add New Instructor", form_data={})

@group_mgmt_bp.route('/instructors/edit/<int:staff_id>', methods=['GET', 'POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def edit_instructor(staff_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        if request.method == 'POST':
            form = request.form
            password = form.get('Password')
            
            # Get UserID for updates
            cursor.execute("SELECT UserID FROM Staff WHERE StaffID = %s", (staff_id,))
            user = cursor.fetchone()
            if not user:
                flash("Instructor not found.", "danger")
                return redirect(url_for('.list_instructors'))
            user_id = user['UserID']

            # Update Users table
            sql_user_update = """
                UPDATE Users SET FirstName=%s, LastName=%s, Email=%s, PhoneNumber=%s, AccountStatus=%s
                WHERE UserID = %s
            """
            params_user = (form.get('FirstName'), form.get('LastName'), form.get('Email'),
                           form.get('PhoneNumber'), form.get('AccountStatus'), user_id)
            cursor.execute(sql_user_update, params_user)
            
            # Optionally update password
            if password:
                hashed_password = generate_password_hash(password)
                cursor.execute("UPDATE Users SET PasswordHash = %s WHERE UserID = %s", (hashed_password, user_id))

            # Update Staff table
            sql_staff_update = "UPDATE Staff SET Specialization=%s, Bio=%s WHERE StaffID = %s"
            params_staff = (form.get('Specialization'), form.get('Bio'), staff_id)
            cursor.execute(sql_staff_update, params_staff)
            
            conn.commit()
            flash('Instructor details updated successfully!', 'success')
            return redirect(url_for('.list_instructors'))

        # GET request: Fetch current data
        cursor.execute("""
            SELECT s.StaffID, s.Specialization, s.Bio,
                   u.UserID, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.AccountStatus
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.StaffID = %s AND s.Role = 'Instructor'
        """, (staff_id,))
        form_data = cursor.fetchone()
        
        if not form_data:
            flash("Instructor not found.", "danger")
            return redirect(url_for('.list_instructors'))
            
        return render_template('agency_staff_portal/courses/groups/add_edit_instructor.html',
                               title="Edit Instructor", form_data=form_data)
                               
    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
        if err.errno == 1062:
            flash('An account with this email already exists.', 'danger')
        else:
            flash(f'Database error: {err.msg}', 'danger')
        # On POST error, we need to refetch data for the form
        cursor.execute("""
            SELECT s.StaffID, u.UserID, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.AccountStatus, s.Specialization, s.Bio
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.StaffID = %s AND s.Role = 'Instructor'
        """, (staff_id,))
        form_data = cursor.fetchone()
        return render_template('agency_staff_portal/courses/groups/add_edit_instructor.html', title="Edit Instructor", form_data=form_data)
    finally:
        if conn and conn.is_connected(): conn.close()


@group_mgmt_bp.route('/instructors/delete/<int:staff_id>', methods=['POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def delete_instructor(staff_id):
    """ Deletes an instructor. The ON DELETE CASCADE on fk_staff_user will handle removing the Staff record. """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Find the UserID associated with this StaffID
        cursor.execute("SELECT UserID FROM Staff WHERE StaffID = %s", (staff_id,))
        user = cursor.fetchone()
        
        if user:
            # Deleting the User will trigger a cascade delete on the Staff table
            cursor.execute("DELETE FROM Users WHERE UserID = %s", (user[0],))
            conn.commit()
            flash("Instructor deleted successfully.", "success")
        else:
            flash("Instructor not found.", "danger")

    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
        # You might have foreign key constraints if an instructor is a TeamLead, etc.
        flash(f"Could not delete instructor. They may be linked to other records. Error: {err.msg}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('.list_instructors'))


# --- Group Management ---
@group_mgmt_bp.route('/')
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def list_groups():
    """Lists all course groups."""
    groups = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT
                cg.GroupID, cg.GroupName, cg.Status, cg.StartDate,
                sp.Name AS SubPackageName,
                mp.Name AS MainPackageName,
                (SELECT COUNT(*) FROM CourseGroupMembers cgm WHERE cgm.GroupID = cg.GroupID) as member_count,
                GROUP_CONCAT(DISTINCT CONCAT(u.FirstName, ' ', u.LastName) SEPARATOR ', ') as instructors
            FROM CourseGroups cg
            JOIN SubPackages sp ON cg.SubPackageID = sp.SubPackageID
            JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            LEFT JOIN CourseGroupInstructors cgi ON cg.GroupID = cgi.GroupID
            LEFT JOIN Staff s ON cgi.InstructorStaffID = s.StaffID
            LEFT JOIN Users u ON s.UserID = u.UserID
            GROUP BY cg.GroupID
            ORDER BY cg.StartDate DESC, cg.GroupName
        """
        cursor.execute(sql)
        groups = cursor.fetchall()
    except Exception as e:
        flash("Could not load course groups.", "danger")
        current_app.logger.error(f"Error fetching course groups: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()
    return render_template('agency_staff_portal/courses/groups/list_groups.html',
                           title="Manage Course Groups",
                           groups=groups)

@group_mgmt_bp.route('/add', methods=['GET', 'POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def add_group():
    conn = get_db_connection()
    sub_packages = []
    instructors = []
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Fetch sub-packages for the dropdown
        cursor.execute("""
            SELECT sp.SubPackageID, CONCAT(mp.Name, ' - ', sp.Name) AS FullName
            FROM SubPackages sp
            JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            WHERE sp.Status = 'Active' ORDER BY FullName
        """)
        sub_packages = cursor.fetchall()
        
        # Fetch instructors for the multi-select
        cursor.execute("""
            SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) AS FullName
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role = 'Instructor' AND u.AccountStatus = 'Active' ORDER BY FullName
        """)
        instructors = cursor.fetchall()
        
        if request.method == 'POST':
            form = request.form
            group_name = form.get('GroupName')
            sub_package_id = form.get('SubPackageID')
            selected_instructors = form.getlist('InstructorStaffID')
            
            if not group_name or not sub_package_id:
                flash("Group Name and a Sub-Package are required.", "danger")
                # Return with form data preserved
                return render_template('agency_staff_portal/courses/groups/add_edit_group.html',
                                       title="Add New Group", sub_packages=sub_packages,
                                       instructors=instructors, form_data=form)
            
            # Insert into CourseGroups
            sql_group = """
                INSERT INTO CourseGroups (GroupName, SubPackageID, StartDate, EndDate, Status, MaxCapacity, Notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            params_group = (
                group_name, sub_package_id,
                form.get('StartDate') or None, form.get('EndDate') or None,
                form.get('Status', 'Planning'), form.get('MaxCapacity', 0),
                form.get('Notes')
            )
            cursor.execute(sql_group, params_group)
            new_group_id = cursor.lastrowid
            
            # Insert into CourseGroupInstructors
            if selected_instructors:
                sql_instructors = "INSERT INTO CourseGroupInstructors (GroupID, InstructorStaffID) VALUES (%s, %s)"
                instructor_data = [(new_group_id, inst_id) for inst_id in selected_instructors]
                cursor.executemany(sql_instructors, instructor_data)
                
            conn.commit()
            flash("Course Group created successfully!", "success")
            return redirect(url_for('.list_groups'))
            
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred: {e}", "danger")
        current_app.logger.error(f"Error adding group: {e}")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('agency_staff_portal/courses/groups/add_edit_group.html',
                           title="Add New Group", sub_packages=sub_packages,
                           instructors=instructors, form_data={})

@group_mgmt_bp.route('/manage/<int:group_id>', methods=['GET', 'POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def manage_group_members(group_id):
    conn = get_db_connection()
    group_details = {}
    assigned_members = []
    available_candidates = []
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get Group Details
        cursor.execute("SELECT cg.*, sp.Name as SubPackageName FROM CourseGroups cg JOIN SubPackages sp ON cg.SubPackageID = sp.SubPackageID WHERE cg.GroupID = %s", (group_id,))
        group_details = cursor.fetchone()
        
        if not group_details:
            flash("Group not found.", "danger")
            return redirect(url_for('.list_groups'))

        # Get Assigned Members
        cursor.execute("""
            SELECT u.FirstName, u.LastName, u.Email, ce.EnrollmentID
            FROM CourseGroupMembers cgm
            JOIN CourseEnrollments ce ON cgm.EnrollmentID = ce.EnrollmentID
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            WHERE cgm.GroupID = %s
        """, (group_id,))
        assigned_members = cursor.fetchall()
        
        # Get Available (Enrolled but not assigned) Candidates for this Sub-Package
        cursor.execute("""
            SELECT u.FirstName, u.LastName, u.Email, ce.EnrollmentID
            FROM CourseEnrollments ce
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            WHERE ce.SubPackageID = %s
            AND ce.Status IN ('Enrolled', 'InProgress')
            AND ce.EnrollmentID NOT IN (SELECT EnrollmentID FROM CourseGroupMembers)
        """, (group_details['SubPackageID'],))
        available_candidates = cursor.fetchall()
        
        if request.method == 'POST':
            enrollment_id_to_add = request.form.get('enrollment_id')
            if enrollment_id_to_add:
                cursor.execute(
                    "INSERT INTO CourseGroupMembers (GroupID, EnrollmentID) VALUES (%s, %s)",
                    (group_id, enrollment_id_to_add)
                )
                conn.commit()
                flash("Member added to the group.", "success")
                return redirect(url_for('.manage_group_members', group_id=group_id))

    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred: {e}", "danger")
        current_app.logger.error(f"Error managing group {group_id}: {e}")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    return render_template('agency_staff_portal/courses/groups/manage_group.html',
                           title=f"Manage Group: {group_details.get('GroupName', '')}",
                           group=group_details,
                           members=assigned_members,
                           available_candidates=available_candidates)

@group_mgmt_bp.route('/manage/<int:group_id>/remove/<int:enrollment_id>', methods=['POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def remove_group_member(group_id, enrollment_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM CourseGroupMembers WHERE GroupID = %s AND EnrollmentID = %s",
            (group_id, enrollment_id)
        )
        conn.commit()
        if cursor.rowcount > 0:
            flash("Member removed from group successfully.", "success")
        else:
            flash("Member not found in this group.", "warning")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash("An error occurred while removing the member.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('.manage_group_members', group_id=group_id))