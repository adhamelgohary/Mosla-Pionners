# routes/instructor_portal/portal_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import instructor_required # Use the new decorator
from db import get_db_connection
import uuid
import mysql.connector

instructor_portal_bp = Blueprint('instructor_portal_bp', __name__,
                                 template_folder='../../../templates',
                                 url_prefix='/instructor')

@instructor_portal_bp.route('/dashboard')
@instructor_required
def dashboard():
    """The main dashboard for the instructor."""
    dashboard_data = {'group_count': 0, 'student_count': 0}
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        instructor_staff_id = current_user.specific_role_id

        # Get count of groups and students
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT cgi.GroupID) as group_count,
                COUNT(DISTINCT cgm.EnrollmentID) as student_count
            FROM CourseGroupInstructors cgi
            LEFT JOIN CourseGroupMembers cgm ON cgi.GroupID = cgm.GroupID
            WHERE cgi.InstructorStaffID = %s
        """, (instructor_staff_id,))
        data = cursor.fetchone()
        if data:
            dashboard_data['group_count'] = data['group_count']
            dashboard_data['student_count'] = data['student_count']
        
        # You can also fetch upcoming due dates here
        
    except Exception as e:
        flash("Could not load dashboard data.", "warning")
        current_app.logger.error(f"Instructor dashboard error: {e}")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('instructor_portal/dashboard.html', 
                           title='Instructor Dashboard', 
                           dashboard_data=dashboard_data)

@instructor_portal_bp.route('/profile', methods=['GET', 'POST'])
@instructor_required
def profile():
    """Allows instructor to view their profile and generate a referral code."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        instructor_staff_id = current_user.specific_role_id

        if request.method == 'POST':
            # This handles the referral code generation
            if 'generate_code' in request.form:
                new_code = f"INST-{str(uuid.uuid4())[:8].upper()}"
                cursor.execute("UPDATE Staff SET ReferralCode = %s WHERE StaffID = %s", (new_code, instructor_staff_id))
                conn.commit()
                flash(f"Referral code generated: {new_code}", "success")
                # Update the user object in session
                current_user.specific_role_details['ReferralCode'] = new_code
                return redirect(url_for('.profile'))

        # Fetch profile data (similar to the staff profile page)
        cursor.execute("""
            SELECT u.*, s.Role, s.Bio, s.Specialization, s.ReferralCode
            FROM Users u JOIN Staff s ON u.UserID = s.UserID
            WHERE s.StaffID = %s
        """, (instructor_staff_id,))
        profile_data = cursor.fetchone()

    except Exception as e:
        flash("An error occurred while fetching your profile.", "danger")
        current_app.logger.error(f"Instructor profile error: {e}")
        profile_data = {}
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('instructor_portal/profile.html', title='My Profile', profile_data=profile_data)

# --- Group Listing and Management ---
@instructor_portal_bp.route('/my-groups')
@instructor_required
def my_groups():
    groups = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        instructor_staff_id = current_user.specific_role_id
        cursor.execute("""
            SELECT 
                cg.GroupID, cg.GroupName, cg.Status,
                sp.Name as SubPackageName,
                (SELECT COUNT(*) FROM CourseGroupMembers cgm WHERE cgm.GroupID = cg.GroupID) as member_count
            FROM CourseGroups cg
            JOIN CourseGroupInstructors cgi ON cg.GroupID = cgi.GroupID
            JOIN SubPackages sp ON cg.SubPackageID = sp.SubPackageID
            WHERE cgi.InstructorStaffID = %s
            ORDER BY cg.Status, cg.GroupName
        """, (instructor_staff_id,))
        groups = cursor.fetchall()
    except Exception as e:
        flash("Could not load your assigned groups.", "danger")
        current_app.logger.error(f"Instructor my_groups error: {e}")
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('instructor_portal/my_groups.html', title='My Groups', groups=groups)


# --- NEW AND UPDATED: Full CRUD for Groups by Instructors ---

@instructor_portal_bp.route('/groups/add', methods=['GET', 'POST'])
@instructor_required
def add_group():
    """Allows an instructor to create a new group."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT sp.SubPackageID, CONCAT(mp.Name, ' - ', sp.Name) AS FullName
            FROM SubPackages sp JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            WHERE sp.Status = 'Active' ORDER BY FullName
        """)
        sub_packages = cursor.fetchall()

        if request.method == 'POST':
            form = request.form
            if not form.get('GroupName') or not form.get('SubPackageID'):
                flash("Group Name and a Course Package are required.", "danger")
                return render_template('instructor_portal/add_edit_group.html', title="Create New Group", sub_packages=sub_packages, form_data=form)
            
            sql_group = """INSERT INTO CourseGroups (GroupName, SubPackageID, StartDate, EndDate, Status, MaxCapacity, Notes) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            params_group = (form.get('GroupName'), form.get('SubPackageID'), form.get('StartDate') or None, form.get('EndDate') or None, form.get('Status', 'Planning'), form.get('MaxCapacity', 0), form.get('Notes'))
            cursor.execute(sql_group, params_group)
            new_group_id = cursor.lastrowid
            
            sql_assign = "INSERT INTO CourseGroupInstructors (GroupID, InstructorStaffID, IsLeadInstructor) VALUES (%s, %s, 1)"
            cursor.execute(sql_assign, (new_group_id, current_user.specific_role_id))
            
            conn.commit()
            flash("Course Group created successfully!", "success")
            return redirect(url_for('.my_groups'))
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('instructor_portal/add_edit_group.html', title="Create New Group", sub_packages=sub_packages, form_data={})

@instructor_portal_bp.route('/group/<int:group_id>/edit', methods=['GET', 'POST'])
@instructor_required
def edit_group(group_id):
    """Allows an instructor to edit a group they are assigned to."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Authorization check: Ensure instructor is assigned to this group
        cursor.execute("SELECT 1 FROM CourseGroupInstructors WHERE GroupID = %s AND InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        if not cursor.fetchone():
            flash("You are not authorized to edit this group.", "danger")
            return redirect(url_for('.my_groups'))
            
        # Fetch data for form dropdowns
        cursor.execute("""
            SELECT sp.SubPackageID, CONCAT(mp.Name, ' - ', sp.Name) AS FullName
            FROM SubPackages sp JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            WHERE sp.Status = 'Active' ORDER BY FullName
        """)
        sub_packages = cursor.fetchall()

        if request.method == 'POST':
            form = request.form
            sql_update = """UPDATE CourseGroups SET GroupName=%s, SubPackageID=%s, StartDate=%s, EndDate=%s, Status=%s, MaxCapacity=%s, Notes=%s, UpdatedAt=NOW() WHERE GroupID=%s"""
            params = (form.get('GroupName'), form.get('SubPackageID'), form.get('StartDate') or None, form.get('EndDate') or None, form.get('Status'), form.get('MaxCapacity', 0), form.get('Notes'), group_id)
            cursor.execute(sql_update, params)
            conn.commit()
            flash("Group details updated successfully.", "success")
            return redirect(url_for('.group_dashboard', group_id=group_id))

        # GET request: Fetch current group data
        cursor.execute("SELECT * FROM CourseGroups WHERE GroupID = %s", (group_id,))
        form_data = cursor.fetchone()
        return render_template('instructor_portal/add_edit_group.html', title="Edit Group", form_data=form_data, group_id=group_id, sub_packages=sub_packages)
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('.my_groups'))
    finally:
        if conn and conn.is_connected(): conn.close()

@instructor_portal_bp.route('/group/<int:group_id>/delete', methods=['POST'])
@instructor_required
def delete_group(group_id):
    """Deletes a group if the instructor is assigned to it."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Authorization check
        cursor.execute("SELECT 1 FROM CourseGroupInstructors WHERE GroupID = %s AND InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        if not cursor.fetchone():
            flash("You are not authorized to delete this group.", "danger")
            return redirect(url_for('.my_groups'))

        # The ON DELETE CASCADE in the DB schema will handle cleanup of members, instructors, and assessments.
        cursor.execute("DELETE FROM CourseGroups WHERE GroupID = %s", (group_id,))
        conn.commit()
        flash("Group and all its associated data have been deleted.", "success")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred while trying to delete the group: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.my_groups'))


@instructor_portal_bp.route('/group/<int:group_id>')
@instructor_required
def group_dashboard(group_id):
    """Shows the dashboard for a single group, listing its assessments."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Check if instructor has access to this group
        cursor.execute("SELECT GroupName FROM CourseGroups cg JOIN CourseGroupInstructors cgi ON cg.GroupID = cgi.GroupID WHERE cg.GroupID = %s AND cgi.InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        group = cursor.fetchone()
        if not group:
            flash("You do not have permission to view this group.", "danger")
            return redirect(url_for('.my_groups'))
            
        # Fetch assessments for this group
        cursor.execute("SELECT * FROM GroupAssessments WHERE GroupID = %s ORDER BY DueDate DESC", (group_id,))
        assessments = cursor.fetchall()

    except Exception as e:
        flash("Could not load group details.", "danger")
        current_app.logger.error(f"Error loading group dashboard {group_id}: {e}")
        return redirect(url_for('.my_groups'))
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('instructor_portal/group_dashboard.html', title=group['GroupName'], group=group, group_id=group_id, assessments=assessments)


@instructor_portal_bp.route('/group/<int:group_id>/assessment/add', methods=['GET', 'POST'])
@instructor_required
def add_assessment(group_id):
    """Create a new assessment and auto-generate gradebook entries for all students."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Verify instructor access
        cursor.execute("SELECT 1 FROM CourseGroupInstructors WHERE GroupID = %s AND InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        if not cursor.fetchone():
            flash("Access denied.", "danger")
            return redirect(url_for('.my_groups'))

        if request.method == 'POST':
            form = request.form
            # Step 1: Insert the new assessment
            sql_insert_assessment = """
                INSERT INTO GroupAssessments (GroupID, CreatedByInstructorStaffID, Title, Description, AssessmentType, DueDate, MaxPoints)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            params = (group_id, current_user.specific_role_id, form['Title'], form['Description'], form['AssessmentType'], form.get('DueDate') or None, form.get('MaxPoints', 100))
            cursor.execute(sql_insert_assessment, params)
            new_assessment_id = cursor.lastrowid

            # Step 2: Get all students (EnrollmentIDs) in the group
            cursor.execute("SELECT EnrollmentID FROM CourseGroupMembers WHERE GroupID = %s", (group_id,))
            enrollments = cursor.fetchall()

            # Step 3: Create a placeholder submission for each student (THE CRITICAL STEP)
            if enrollments:
                sql_insert_submissions = "INSERT INTO CandidateSubmissions (AssessmentID, EnrollmentID) VALUES (%s, %s)"
                submission_data = [(new_assessment_id, en['EnrollmentID']) for en in enrollments]
                cursor.executemany(sql_insert_submissions, submission_data)

            conn.commit()
            flash("Assessment created successfully. You can now enter grades.", "success")
            return redirect(url_for('.grade_assessment', assessment_id=new_assessment_id))

    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"Error creating assessment: {e}", "danger")
        current_app.logger.error(f"Error in add_assessment for group {group_id}: {e}")
        return redirect(url_for('.group_dashboard', group_id=group_id))
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('instructor_portal/add_edit_assessment.html', title="Add New Assessment", group_id=group_id)


@instructor_portal_bp.route('/assessment/<int:assessment_id>/grade', methods=['GET', 'POST'])
@instructor_required
def grade_assessment(assessment_id):
    """The Gradebook page. Allows viewing and saving scores and feedback."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Get assessment details and verify instructor access
        cursor.execute("""
            SELECT ga.*, cg.GroupName
            FROM GroupAssessments ga
            JOIN CourseGroups cg ON ga.GroupID = cg.GroupID
            JOIN CourseGroupInstructors cgi ON cg.GroupID = cgi.GroupID
            WHERE ga.AssessmentID = %s AND cgi.InstructorStaffID = %s
        """, (assessment_id, current_user.specific_role_id))
        assessment = cursor.fetchone()
        if not assessment:
            flash("Assessment not found or you do not have permission to grade it.", "danger")
            return redirect(url_for('.my_groups'))

        if request.method == 'POST':
            # Loop through form data to update each submission
            for key, value in request.form.items():
                if key.startswith('score_'):
                    submission_id = key.split('_')[1]
                    score = value or None
                    feedback = request.form.get(f'feedback_{submission_id}', '')
                    # Update the submission record
                    sql_update = """
                        UPDATE CandidateSubmissions 
                        SET Score = %s, InstructorFeedback = %s, Status = 'Graded', GradedAt = NOW()
                        WHERE SubmissionID = %s
                    """
                    cursor.execute(sql_update, (score, feedback, submission_id))
            
            conn.commit()
            flash("Grades saved successfully!", "success")
            return redirect(url_for('.grade_assessment', assessment_id=assessment_id))

        # GET Request: Fetch all submission records for the gradebook view
        cursor.execute("""
            SELECT cs.*, u.FirstName, u.LastName
            FROM CandidateSubmissions cs
            JOIN CourseEnrollments ce ON cs.EnrollmentID = ce.EnrollmentID
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            WHERE cs.AssessmentID = %s
            ORDER BY u.LastName, u.FirstName
        """, (assessment_id,))
        submissions = cursor.fetchall()
        
    except Exception as e:
        if conn and conn.is_connected() and request.method == 'POST': conn.rollback()
        flash(f"An error occurred: {e}", "danger")
        current_app.logger.error(f"Error grading assessment {assessment_id}: {e}")
        return redirect(url_for('.my_groups'))
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('instructor_portal/grade_assessment.html', title=f"Grade: {assessment['Title']}", assessment=assessment, submissions=submissions)

@instructor_portal_bp.route('/group/<int:group_id>/roster', methods=['GET', 'POST'])
@instructor_required
def manage_roster(group_id):
    """
    Allows an instructor to view, add, and remove students from a group they manage.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        instructor_staff_id = current_user.specific_role_id

        # Authorization Check: Ensure instructor is assigned to this group
        cursor.execute("""
            SELECT cg.GroupName, sp.SubPackageID
            FROM CourseGroups cg
            JOIN CourseGroupInstructors cgi ON cg.GroupID = cgi.GroupID
            JOIN SubPackages sp ON cg.SubPackageID = sp.SubPackageID
            WHERE cg.GroupID = %s AND cgi.InstructorStaffID = %s
        """, (group_id, instructor_staff_id))
        group_info = cursor.fetchone()

        if not group_info:
            flash("You are not authorized to manage this group's roster.", "danger")
            return redirect(url_for('.my_groups'))

        # Handle adding a new member
        if request.method == 'POST':
            enrollment_id_to_add = request.form.get('enrollment_id')
            if enrollment_id_to_add:
                # Check if the group is at capacity
                cursor.execute("SELECT MaxCapacity, (SELECT COUNT(*) FROM CourseGroupMembers WHERE GroupID = %s) as member_count FROM CourseGroups WHERE GroupID = %s", (group_id, group_id))
                capacity_info = cursor.fetchone()
                if capacity_info['MaxCapacity'] > 0 and capacity_info['member_count'] >= capacity_info['MaxCapacity']:
                    flash("Cannot add member. The group is at full capacity.", "warning")
                else:
                    cursor.execute("INSERT INTO CourseGroupMembers (GroupID, EnrollmentID) VALUES (%s, %s)", (group_id, enrollment_id_to_add))
                    conn.commit()
                    flash("Student added to the group successfully.", "success")
                return redirect(url_for('.manage_roster', group_id=group_id))

        # --- Data Fetching for GET request ---
        # 1. Get currently assigned members (the roster)
        cursor.execute("""
            SELECT u.FirstName, u.LastName, u.Email, ce.EnrollmentID
            FROM CourseGroupMembers cgm
            JOIN CourseEnrollments ce ON cgm.EnrollmentID = ce.EnrollmentID
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            WHERE cgm.GroupID = %s ORDER BY u.LastName, u.FirstName
        """, (group_id,))
        assigned_members = cursor.fetchall()

        # 2. Get available candidates (enrolled in the package, but not in any group yet)
        cursor.execute("""
            SELECT u.FirstName, u.LastName, ce.EnrollmentID
            FROM CourseEnrollments ce
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            WHERE ce.SubPackageID = %s
            AND ce.Status IN ('Enrolled', 'InProgress')
            AND ce.EnrollmentID NOT IN (SELECT EnrollmentID FROM CourseGroupMembers)
            ORDER BY u.LastName, u.FirstName
        """, (group_info['SubPackageID'],))
        available_candidates = cursor.fetchall()

    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('.group_dashboard', group_id=group_id))
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('instructor_portal/manage_roster.html',
                           title=f"Manage Roster: {group_info['GroupName']}",
                           group_id=group_id,
                           group_name=group_info['GroupName'],
                           members=assigned_members,
                           available_candidates=available_candidates)


@instructor_portal_bp.route('/group/<int:group_id>/roster/remove/<int:enrollment_id>', methods=['POST'])
@instructor_required
def remove_from_roster(group_id, enrollment_id):
    """Handles removing a student from a group."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Authorization check
        cursor.execute("SELECT 1 FROM CourseGroupInstructors WHERE GroupID = %s AND InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        if not cursor.fetchone():
            flash("You are not authorized to manage this group's roster.", "danger")
            return redirect(url_for('.my_groups'))
            
        cursor.execute("DELETE FROM CourseGroupMembers WHERE GroupID = %s AND EnrollmentID = %s", (group_id, enrollment_id))
        conn.commit()
        if cursor.rowcount > 0:
            flash("Student removed from group successfully.", "success")
        else:
            flash("Student not found in this group.", "warning")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred while removing the student: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('.manage_roster', group_id=group_id))