# routes/Agency_Staff_Portal/group_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import mysql.connector

# Roles with management access
GROUP_MANAGEMENT_ROLES = ['SalesManager', 'CEO', 'Founder', 'Admin'] 

group_mgmt_bp = Blueprint('group_mgmt_bp', __name__,
                          template_folder='../../../templates',
                          url_prefix='/course-groups')

# --- Instructor Management ---
@group_mgmt_bp.route('/instructors')
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def list_instructors():
    """Lists all staff members with the 'Instructor' role."""
    instructors = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Assuming you'll create a view or a separate process for adding instructors
        # For now, we list them.
        cursor.execute("""
            SELECT s.StaffID, u.FirstName, u.LastName, u.Email, s.Specialization
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            WHERE s.Role = 'Instructor'
            ORDER BY u.LastName, u.FirstName
        """)
        instructors = cursor.fetchall()
    except Exception as e:
        flash("Could not load instructors.", "danger")
        current_app.logger.error(f"Error fetching instructors: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()
    
    return render_template('agency_staff_portal/courses/groups/list_instructors.html',
                           title="Manage Instructors",
                           instructors=instructors)
    # NOTE: You will need to build the add/edit instructor forms and routes.
    # These would be similar to other staff management forms you might have.

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