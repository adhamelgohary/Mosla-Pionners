# routes/Agency_Staff_Portal/group_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import mysql.connector
from werkzeug.security import generate_password_hash


from utils.group_utils import sync_sessions_for_groups

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
            if err.errno == 1062:
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
            
            cursor.execute("SELECT UserID FROM Staff WHERE StaffID = %s", (staff_id,))
            user = cursor.fetchone()
            if not user:
                flash("Instructor not found.", "danger")
                return redirect(url_for('.list_instructors'))
            user_id = user['UserID']

            sql_user_update = """
                UPDATE Users SET FirstName=%s, LastName=%s, Email=%s, PhoneNumber=%s, AccountStatus=%s
                WHERE UserID = %s
            """
            params_user = (form.get('FirstName'), form.get('LastName'), form.get('Email'),
                           form.get('PhoneNumber'), form.get('AccountStatus'), user_id)
            cursor.execute(sql_user_update, params_user)
            
            if password:
                hashed_password = generate_password_hash(password)
                cursor.execute("UPDATE Users SET PasswordHash = %s WHERE UserID = %s", (hashed_password, user_id))

            sql_staff_update = "UPDATE Staff SET Specialization=%s, Bio=%s WHERE StaffID = %s"
            params_staff = (form.get('Specialization'), form.get('Bio'), staff_id)
            cursor.execute(sql_staff_update, params_staff)
            
            conn.commit()
            flash('Instructor details updated successfully!', 'success')
            return redirect(url_for('.list_instructors'))

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
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT UserID FROM Staff WHERE StaffID = %s", (staff_id,))
        user = cursor.fetchone()
        if user:
            cursor.execute("DELETE FROM Users WHERE UserID = %s", (user[0],))
            conn.commit()
            flash("Instructor deleted successfully.", "success")
        else:
            flash("Instructor not found.", "danger")
    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
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
        cursor.execute("""
            SELECT sp.SubPackageID, CONCAT(mp.Name, ' - ', sp.Name) AS FullName
            FROM SubPackages sp
            JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            WHERE sp.Status = 'Active' ORDER BY FullName
        """)
        sub_packages = cursor.fetchall()
        
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
                return render_template('agency_staff_portal/courses/groups/add_edit_group.html',
                                       title="Add New Group", sub_packages=sub_packages,
                                       instructors=instructors, form_data=form)
            
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

@group_mgmt_bp.route('/edit/<int:group_id>', methods=['GET', 'POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def edit_group(group_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT sp.SubPackageID, CONCAT(mp.Name, ' - ', sp.Name) AS FullName
            FROM SubPackages sp JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            WHERE sp.Status = 'Active' ORDER BY FullName
        """)
        sub_packages = cursor.fetchall()

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
                cursor.execute("SELECT * FROM CourseGroups WHERE GroupID = %s", (group_id,))
                form_data = cursor.fetchone()
                cursor.execute("SELECT InstructorStaffID FROM CourseGroupInstructors WHERE GroupID = %s", (group_id,))
                form_data['selected_instructors'] = [row['InstructorStaffID'] for row in cursor.fetchall()]
                return render_template('agency_staff_portal/courses/groups/add_edit_group.html',
                                       title="Edit Group", sub_packages=sub_packages, instructors=instructors,
                                       form_data=form_data, group_id=group_id)
            
            sql_update_group = """
                UPDATE CourseGroups SET
                GroupName = %s, SubPackageID = %s, StartDate = %s, EndDate = %s,
                Status = %s, MaxCapacity = %s, Notes = %s, UpdatedAt = NOW()
                WHERE GroupID = %s
            """
            params_update = (
                group_name, sub_package_id, form.get('StartDate') or None, form.get('EndDate') or None,
                form.get('Status'), form.get('MaxCapacity', 0), form.get('Notes'), group_id
            )
            cursor.execute(sql_update_group, params_update)

            cursor.execute("DELETE FROM CourseGroupInstructors WHERE GroupID = %s", (group_id,))
            if selected_instructors:
                sql_instructors = "INSERT INTO CourseGroupInstructors (GroupID, InstructorStaffID) VALUES (%s, %s)"
                instructor_data = [(group_id, inst_id) for inst_id in selected_instructors]
                cursor.executemany(sql_instructors, instructor_data)

            conn.commit()
            flash("Course Group updated successfully!", "success")
            return redirect(url_for('.list_groups'))

        cursor.execute("SELECT * FROM CourseGroups WHERE GroupID = %s", (group_id,))
        form_data = cursor.fetchone()
        if not form_data:
            flash("Group not found.", "danger")
            return redirect(url_for('.list_groups'))

        cursor.execute("SELECT InstructorStaffID FROM CourseGroupInstructors WHERE GroupID = %s", (group_id,))
        form_data['selected_instructors'] = [row['InstructorStaffID'] for row in cursor.fetchall()]
        
        return render_template('agency_staff_portal/courses/groups/add_edit_group.html',
                               title="Edit Group", form_data=form_data, group_id=group_id,
                               sub_packages=sub_packages, instructors=instructors)

    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred: {e}", "danger")
        current_app.logger.error(f"Error editing group {group_id}: {e}", exc_info=True)
        return redirect(url_for('.list_groups'))
    finally:
        if conn and conn.is_connected(): conn.close()

@group_mgmt_bp.route('/group/<int:group_id>/roster', methods=['GET', 'POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def admin_manage_roster(group_id):
    """Admin page to manage a group's roster, including adding/removing students and updating their details."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT cg.GroupName, sp.SubPackageID FROM CourseGroups cg JOIN SubPackages sp ON cg.SubPackageID = sp.SubPackageID WHERE cg.GroupID = %s", (group_id,))
        group_info = cursor.fetchone()
        if not group_info:
            flash("Group not found.", "danger")
            return redirect(url_for('.list_groups'))

        if request.method == 'POST':
            # This handles adding a new student
            enrollment_id_to_add = request.form.get('enrollment_id')
            if enrollment_id_to_add:
                cursor.execute("INSERT INTO CourseGroupMembers (GroupID, EnrollmentID) VALUES (%s, %s)", (group_id, enrollment_id_to_add))
                cursor.execute("SELECT SessionID FROM GroupSessions WHERE GroupID = %s", (group_id,))
                sessions = cursor.fetchall()
                if sessions:
                    attendance_data = [(s['SessionID'], enrollment_id_to_add) for s in sessions]
                    cursor.executemany("INSERT INTO SessionAttendance (SessionID, EnrollmentID) VALUES (%s, %s)", attendance_data)
                conn.commit()
                flash("Student added to group.", "success")
                return redirect(url_for('.admin_manage_roster', group_id=group_id))

        # Fetch assigned members with full details
        cursor.execute("""
            SELECT u.FirstName, u.LastName, u.Email, u.PhoneNumber, ce.EnrollmentID, 
                   cgm.PerformanceNotes, cgm.PlacementStatus, cgm.CompanyRecommendation
            FROM CourseGroupMembers cgm
            JOIN CourseEnrollments ce ON cgm.EnrollmentID = ce.EnrollmentID
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            WHERE cgm.GroupID = %s ORDER BY u.LastName, u.FirstName
        """, (group_id,))
        assigned_members = cursor.fetchall()

        # Fetch available candidates for the dropdown
        cursor.execute("""
            SELECT u.FirstName, u.LastName, ce.EnrollmentID FROM CourseEnrollments ce
            JOIN Candidates c ON ce.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID
            WHERE ce.SubPackageID = %s AND ce.Status IN ('Enrolled', 'InProgress') 
            AND ce.EnrollmentID NOT IN (SELECT EnrollmentID FROM CourseGroupMembers)
            ORDER BY u.LastName, u.FirstName
        """, (group_info['SubPackageID'],))
        available_candidates = cursor.fetchall()
    finally:
        if conn: conn.close()

    return render_template('agency_staff_portal/courses/groups/admin_manage_roster.html',
                           title=f"Manage Roster: {group_info['GroupName']}",
                           group_id=group_id, group_name=group_info['GroupName'],
                           members=assigned_members, available_candidates=available_candidates)

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

@group_mgmt_bp.route('/utility/sync-sessions', methods=['GET', 'POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def sync_sessions_utility():
    if request.method == 'POST':
        message, category = sync_sessions_for_groups()
        flash(message, category)
        return redirect(url_for('.list_groups'))
    
    return render_template('agency_staff_portal/courses/groups/sync_sessions_utility.html',
                           title="Sync Group Sessions")

@group_mgmt_bp.route('/placement-pipeline')
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def placement_pipeline():
    """Shows all pending student applications for admin review and placement."""
    conn = get_db_connection()
    applications = []
    try:
        cursor = conn.cursor(dictionary=True)
        # This query is similar to the manager's pipeline but provides links for action
        cursor.execute("""
            SELECT 
                ce.EnrollmentID, ce.EnrollmentDate,
                u.FirstName, u.LastName, u.Email,
                sp.Name AS AppliedSubPackageName,
                instructor_user.FirstName AS InstructorFirstName
            FROM CourseEnrollments ce
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            LEFT JOIN SubPackages sp ON ce.OriginalSubPackageID = sp.SubPackageID
            LEFT JOIN Staff instructor_staff ON ce.AssignedByInstructorStaffID = instructor_staff.StaffID
            LEFT JOIN Users instructor_user ON instructor_staff.UserID = instructor_user.UserID
            WHERE ce.Status = 'Applied'
            ORDER BY ce.EnrollmentDate ASC
        """)
        applications = cursor.fetchall()
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('agency_staff_portal/courses/groups/placement_pipeline.html',
                           title="Student Placement Pipeline",
                           applications=applications)


@group_mgmt_bp.route('/place-student/<int:enrollment_id>', methods=['GET', 'POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def place_student_admin(enrollment_id):
    """Admin/Manager page to place a student into any group."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Fetch application details
        cursor.execute("SELECT ce.EnrollmentID, u.FirstName, u.LastName FROM CourseEnrollments ce JOIN Candidates c ON ce.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID WHERE ce.EnrollmentID = %s", (enrollment_id,))
        application = cursor.fetchone()
        if not application:
            flash("Application not found.", "danger")
            return redirect(url_for('.placement_pipeline'))

        # Admins can see ALL active groups
        cursor.execute("SELECT GroupID, GroupName FROM CourseGroups WHERE Status IN ('Planning', 'Active')")
        available_groups = cursor.fetchall()

        if request.method == 'POST':
            group_id = request.form.get('group_id')
            test_score = request.form.get('test_score')
            if not group_id:
                flash("A group must be selected.", "danger")
                # Need to refetch data for the template
                return render_template('agency_staff_portal/courses/groups/place_student_admin.html', title="Place Student", application=application, available_groups=available_groups)

            # Get SubPackageID and any instructor from the selected group
            cursor.execute("SELECT SubPackageID FROM CourseGroups WHERE GroupID = %s", (group_id,))
            group_data = cursor.fetchone()
            
            # Find an instructor for the group to assign credit
            cursor.execute("SELECT InstructorStaffID FROM CourseGroupInstructors WHERE GroupID = %s LIMIT 1", (group_id,))
            instructor = cursor.fetchone()
            assigned_instructor_id = instructor['InstructorStaffID'] if instructor else None

            # --- Perform Placement ---
            # 1. Update Enrollment
            cursor.execute("""
                UPDATE CourseEnrollments SET Status = 'Enrolled', SubPackageID = %s, PlacementTestScore = %s, AssignedByInstructorStaffID = %s, UpdatedAt = NOW()
                WHERE EnrollmentID = %s
            """, (group_data['SubPackageID'], test_score, assigned_instructor_id, enrollment_id))

            # 2. Add to Roster
            cursor.execute("INSERT INTO CourseGroupMembers (GroupID, EnrollmentID) VALUES (%s, %s)", (group_id, enrollment_id))
            
            # 3. Generate Attendance
            cursor.execute("SELECT SessionID FROM GroupSessions WHERE GroupID = %s", (group_id,))
            sessions = cursor.fetchall()
            if sessions:
                attendance_data = [(s['SessionID'], enrollment_id) for s in sessions]
                cursor.executemany("INSERT INTO SessionAttendance (SessionID, EnrollmentID) VALUES (%s, %s)", attendance_data)

            conn.commit()
            flash(f"Student {application['FirstName']} placed successfully.", "success")
            return redirect(url_for('.placement_pipeline'))

    except Exception as e:
        if conn: conn.rollback()
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('.placement_pipeline'))
    finally:
        if conn: conn.close()

    return render_template('agency_staff_portal/courses/groups/place_student_admin.html',
                           title=f"Place Student: {application['FirstName']}",
                           application=application,
                           available_groups=available_groups)
    

@group_mgmt_bp.route('/group/<int:group_id>/dashboard')
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def admin_group_dashboard(group_id):
    """The main dashboard for an admin to manage a specific group."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT GroupName FROM CourseGroups WHERE GroupID = %s", (group_id,))
        group = cursor.fetchone()
        if not group:
            flash("Group not found.", "danger")
            return redirect(url_for('.list_groups'))
        
        # Fetch assessments for this group to display on the dashboard
        cursor.execute("SELECT * FROM GroupAssessments WHERE GroupID = %s ORDER BY DueDate DESC", (group_id,))
        assessments = cursor.fetchall()

    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('agency_staff_portal/courses/groups/admin_group_dashboard.html',
                           title=f"Manage Group: {group['GroupName']}",
                           group=group,
                           group_id=group_id,
                           assessments=assessments)


@group_mgmt_bp.route('/group/<int:group_id>/attendance', methods=['GET'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def admin_attendance(group_id):
    """Displays the attendance grid for a group for an admin."""
    # This logic is nearly identical to the instructor's version, but without the ownership check.
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT GroupName FROM CourseGroups WHERE GroupID = %s", (group_id,))
        group = cursor.fetchone()
        if not group:
            flash("Group not found.", "danger")
            return redirect(url_for('.list_groups'))
        
        cursor.execute("SELECT SessionID, SessionNumber, SessionTitle FROM GroupSessions WHERE GroupID = %s ORDER BY SessionNumber", (group_id,))
        sessions = cursor.fetchall()

        cursor.execute("""
            SELECT u.FirstName, u.LastName, cgm.EnrollmentID, sa.SessionID, sa.Status, sa.AttendanceNotes, sa.PerformanceNotes
            FROM CourseGroupMembers cgm
            JOIN CourseEnrollments ce ON cgm.EnrollmentID = ce.EnrollmentID
            JOIN Users u ON ce.CandidateID = (SELECT UserID FROM Candidates WHERE CandidateID = u.UserID)
            LEFT JOIN SessionAttendance sa ON cgm.EnrollmentID = sa.EnrollmentID AND sa.SessionID IN (SELECT SessionID FROM GroupSessions WHERE GroupID = %s)
            WHERE cgm.GroupID = %s ORDER BY u.LastName, u.FirstName
        """, (group_id, group_id))
        attendance_raw = cursor.fetchall()
        
        students_attendance = {}
        for row in attendance_raw:
            enrollment_id = row['EnrollmentID']
            if enrollment_id not in students_attendance:
                students_attendance[enrollment_id] = {'FirstName': row['FirstName'], 'LastName': row['LastName'], 'attendance': {}}
            if row['SessionID']:
                students_attendance[enrollment_id]['attendance'][row['SessionID']] = {'Status': row['Status'], 'AttendanceNotes': row['AttendanceNotes'], 'PerformanceNotes': row['PerformanceNotes']}
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('agency_staff_portal/courses/groups/admin_attendance.html',
                           title=f"Attendance: {group['GroupName']}", group_id=group_id, group_name=group['GroupName'], sessions=sessions, students_attendance=students_attendance)

@group_mgmt_bp.route('/group/<int:group_id>/attendance/update', methods=['POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def admin_update_attendance(group_id):
    """Handles admin submission for updating attendance."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for key, value in request.form.items():
            if key.startswith('status_'):
                _, session_id, enrollment_id = key.split('_')
                new_status = value
                attendance_notes = request.form.get(f'attendance_notes_{session_id}_{enrollment_id}', '')
                performance_notes = request.form.get(f'performance_notes_{session_id}_{enrollment_id}', '')
                cursor.execute("UPDATE SessionAttendance SET Status = %s, AttendanceNotes = %s, PerformanceNotes = %s WHERE SessionID = %s AND EnrollmentID = %s", (new_status, attendance_notes, performance_notes, session_id, enrollment_id))
        conn.commit()
        flash("Attendance updated successfully!", "success")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.admin_attendance', group_id=group_id))


@group_mgmt_bp.route('/tests-and-assessments')
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def list_all_tests():
    """
    Admin view to see a unified list of all Placement Tests and Group Assessments
    from across the entire system.
    """
    conn = get_db_connection()
    all_tests = []
    try:
        cursor = conn.cursor(dictionary=True)
        # This powerful UNION ALL query combines results from two different tables
        # into a single, cohesive list.
        sql_query = """
            -- Part 1: Select all Placement Tests
            SELECT 
                pt.TestID AS id,
                pt.Title AS title,
                'Placement Test' AS type,
                pt.CreatedAt AS created_at,
                CONCAT(u.FirstName, ' ', u.LastName) AS author,
                NULL AS group_name  -- Placeholder for consistent columns
            FROM PlacementTests pt
            JOIN Staff s ON pt.CreatedByInstructorStaffID = s.StaffID
            JOIN Users u ON s.UserID = u.UserID

            UNION ALL

            -- Part 2: Select all Group Assessments
            SELECT 
                ga.AssessmentID AS id,
                ga.Title AS title,
                ga.AssessmentType AS type,
                ga.CreatedAt AS created_at,
                CONCAT(u.FirstName, ' ', u.LastName) AS author,
                cg.GroupName AS group_name
            FROM GroupAssessments ga
            JOIN Staff s ON ga.CreatedByInstructorStaffID = s.StaffID
            JOIN Users u ON s.UserID = u.UserID
            JOIN CourseGroups cg ON ga.GroupID = cg.GroupID
            
            -- Order the final combined list by the creation date
            ORDER BY created_at DESC;
        """
        cursor.execute(sql_query)
        all_tests = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching all tests and assessments: {e}", exc_info=True)
        flash("Could not load the list of tests and assessments.", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('agency_staff_portal/courses/groups/list_all_tests.html', 
                           title="Tests & Assessments Center", 
                           all_tests=all_tests)

@group_mgmt_bp.route('/placement-pipeline/<int:enrollment_id>/assign-test', methods=['GET', 'POST'])
@login_required_with_role(GROUP_MANAGEMENT_ROLES)
def assign_test_admin(enrollment_id):
    """Admin page to assign any test to any applicant."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        if request.method == 'POST':
            test_id = request.form.get('test_id')
            instructor_id = request.form.get('instructor_id') # Who to assign this task to
            if not test_id or not instructor_id:
                flash("You must select both a test and an instructor.", "danger")
                return redirect(url_for('.assign_test_admin', enrollment_id=enrollment_id))
            
            cursor.execute("""
                INSERT INTO AssignedPlacementTests (EnrollmentID, TestID, AssignedByInstructorStaffID)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE TestID = VALUES(TestID), AssignedByInstructorStaffID = VALUES(AssignedByInstructorStaffID)
            """, (enrollment_id, test_id, instructor_id))
            conn.commit()
            flash("Test assigned successfully.", "success")
            return redirect(url_for('.placement_pipeline'))
            
        # GET Request Data
        cursor.execute("SELECT u.FirstName, u.LastName FROM CourseEnrollments ce JOIN Candidates c ON ce.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID WHERE ce.EnrollmentID = %s", (enrollment_id,))
        student = cursor.fetchone()
        
        # Admins can see ALL active tests and ALL active instructors
        cursor.execute("SELECT TestID, Title FROM PlacementTests WHERE IsActive = 1")
        all_tests = cursor.fetchall()
        cursor.execute("SELECT s.StaffID, CONCAT(u.FirstName, ' ', u.LastName) AS FullName FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE s.Role = 'Instructor' AND u.AccountStatus = 'Active'")
        all_instructors = cursor.fetchall()

    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('agency_staff_portal/courses/groups/assign_test_admin.html', 
                           title=f"Assign Test to {student['FirstName']}", 
                           enrollment_id=enrollment_id, 
                           student=student,
                           all_tests=all_tests,
                           all_instructors=all_instructors)