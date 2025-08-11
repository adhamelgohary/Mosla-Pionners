# routes/instructor_portal/portal_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app , jsonify
from flask_login import current_user
from utils.decorators import instructor_required
from db import get_db_connection
import uuid
import mysql.connector

instructor_portal_bp = Blueprint('instructor_portal_bp', __name__,
                                 template_folder='../../../templates',
                                 url_prefix='/instructor')

# --- Main Portal Routes ---
@instructor_portal_bp.route('/dashboard')
@instructor_required
def dashboard():
    """The main dashboard for the instructor."""
    dashboard_data = {'group_count': 0, 'student_count': 0}
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        instructor_staff_id = current_user.specific_role_id
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
        if request.method == 'POST' and 'generate_code' in request.form:
            new_code = f"INST-{str(uuid.uuid4())[:8].upper()}"
            cursor.execute("UPDATE Staff SET ReferralCode = %s WHERE StaffID = %s", (new_code, instructor_staff_id))
            conn.commit()
            flash(f"Referral code generated: {new_code}", "success")
            current_user.specific_role_details['ReferralCode'] = new_code
            return redirect(url_for('.profile'))
        cursor.execute("""
            SELECT u.*, s.Role, s.Bio, s.Specialization, s.ReferralCode
            FROM Users u JOIN Staff s ON u.UserID = s.UserID
            WHERE s.StaffID = %s
        """, (instructor_staff_id,))
        profile_data = cursor.fetchone()
    except Exception as e:
        flash("An error occurred while fetching your profile.", "danger")
        profile_data = {}
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('instructor_portal/profile.html', title='My Profile', profile_data=profile_data)

# --- Group Listing & Management ---
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
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('instructor_portal/my_groups.html', title='My Groups', groups=groups)

@instructor_portal_bp.route('/groups/add', methods=['GET', 'POST'])
@instructor_required
def add_group():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT sp.SubPackageID, sp.NumSessionsMonolingual, CONCAT(mp.Name, ' - ', sp.Name) AS FullName
            FROM SubPackages sp JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            WHERE sp.Status = 'Active' ORDER BY FullName
        """)
        sub_packages = cursor.fetchall()

        if request.method == 'POST':
            form = request.form
            sub_package_id = form.get('SubPackageID')
            if not form.get('GroupName') or not sub_package_id:
                flash("Group Name and a Course Package are required.", "danger")
                return render_template('instructor_portal/add_edit_group.html', title="Create New Group", sub_packages=sub_packages, form_data=form)
            
            sql_group = "INSERT INTO CourseGroups (GroupName, SubPackageID, StartDate, EndDate, Status, MaxCapacity, Notes) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            params_group = (form.get('GroupName'), sub_package_id, form.get('StartDate') or None, form.get('EndDate') or None, form.get('Status', 'Planning'), form.get('MaxCapacity', 0), form.get('Notes'))
            cursor.execute(sql_group, params_group)
            new_group_id = cursor.lastrowid
            
            sql_assign = "INSERT INTO CourseGroupInstructors (GroupID, InstructorStaffID, IsLeadInstructor) VALUES (%s, %s, 1)"
            cursor.execute(sql_assign, (new_group_id, current_user.specific_role_id))
            
            num_sessions = 0
            for sp in sub_packages:
                if str(sp['SubPackageID']) == sub_package_id:
                    num_sessions = sp.get('NumSessionsMonolingual', 0)
                    break
            
            if num_sessions > 0:
                session_data = [(new_group_id, i, f"Session {i}") for i in range(1, num_sessions + 1)]
                sql_insert_sessions = "INSERT INTO GroupSessions (GroupID, SessionNumber, SessionTitle) VALUES (%s, %s, %s)"
                cursor.executemany(sql_insert_sessions, session_data)
            
            conn.commit()
            flash("Course Group and its sessions created successfully!", "success")
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
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM CourseGroupInstructors WHERE GroupID = %s AND InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        if not cursor.fetchone():
            flash("You are not authorized to edit this group.", "danger")
            return redirect(url_for('.my_groups'))
            
        cursor.execute("SELECT sp.SubPackageID, CONCAT(mp.Name, ' - ', sp.Name) AS FullName FROM SubPackages sp JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID WHERE sp.Status = 'Active' ORDER BY FullName")
        sub_packages = cursor.fetchall()

        if request.method == 'POST':
            form = request.form
            sql_update = "UPDATE CourseGroups SET GroupName=%s, SubPackageID=%s, StartDate=%s, EndDate=%s, Status=%s, MaxCapacity=%s, Notes=%s, UpdatedAt=NOW() WHERE GroupID=%s"
            params = (form.get('GroupName'), form.get('SubPackageID'), form.get('StartDate') or None, form.get('EndDate') or None, form.get('Status'), form.get('MaxCapacity', 0), form.get('Notes'), group_id)
            cursor.execute(sql_update, params)
            conn.commit()
            flash("Group details updated successfully.", "success")
            return redirect(url_for('.group_dashboard', group_id=group_id))

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
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM CourseGroupInstructors WHERE GroupID = %s AND InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        if not cursor.fetchone():
            flash("You are not authorized to delete this group.", "danger")
            return redirect(url_for('.my_groups'))
        cursor.execute("DELETE FROM CourseGroups WHERE GroupID = %s", (group_id,))
        conn.commit()
        flash("Group and all its associated data have been deleted.", "success")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.my_groups'))

@instructor_portal_bp.route('/group/<int:group_id>')
@instructor_required
def group_dashboard(group_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT GroupName FROM CourseGroups cg JOIN CourseGroupInstructors cgi ON cg.GroupID = cgi.GroupID WHERE cg.GroupID = %s AND cgi.InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        group = cursor.fetchone()
        if not group:
            flash("You do not have permission to view this group.", "danger")
            return redirect(url_for('.my_groups'))
            
        cursor.execute("SELECT * FROM GroupAssessments WHERE GroupID = %s ORDER BY DueDate DESC", (group_id,))
        assessments = cursor.fetchall()
    except Exception as e:
        flash("Could not load group details.", "danger")
        return redirect(url_for('.my_groups'))
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('instructor_portal/group_dashboard.html', title=group['GroupName'], group=group, group_id=group_id, assessments=assessments)

# --- Roster & Student Management ---
@instructor_portal_bp.route('/group/<int:group_id>/roster', methods=['GET', 'POST'])
@instructor_required
def manage_roster(group_id):
    """
    Allows an instructor to view, add, and remove students from a group they manage,
    and also update their placement details.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        instructor_staff_id = current_user.specific_role_id

        # Authorization Check
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

        # Handle adding a new member via POST request
        if request.method == 'POST':
            enrollment_id_to_add = request.form.get('enrollment_id')
            if enrollment_id_to_add:
                cursor.execute("SELECT MaxCapacity, (SELECT COUNT(*) FROM CourseGroupMembers WHERE GroupID = %s) as member_count FROM CourseGroups WHERE GroupID = %s", (group_id, group_id))
                capacity_info = cursor.fetchone()
                if capacity_info['MaxCapacity'] > 0 and capacity_info['member_count'] >= capacity_info['MaxCapacity']:
                    flash("Cannot add member. The group is at full capacity.", "warning")
                else:
                    cursor.execute("INSERT INTO CourseGroupMembers (GroupID, EnrollmentID) VALUES (%s, %s)", (group_id, enrollment_id_to_add))
                    cursor.execute("SELECT SessionID FROM GroupSessions WHERE GroupID = %s", (group_id,))
                    sessions = cursor.fetchall()
                    if sessions:
                        attendance_data = [(s['SessionID'], enrollment_id_to_add) for s in sessions]
                        sql_insert_attendance = "INSERT INTO SessionAttendance (SessionID, EnrollmentID) VALUES (%s, %s)"
                        cursor.executemany(sql_insert_attendance, attendance_data)
                    conn.commit()
                    flash("Student added and attendance records created.", "success")
                return redirect(url_for('.manage_roster', group_id=group_id))

        # --- Data Fetching for GET request ---
        # 1. Get currently assigned members with all details
        cursor.execute("""
            SELECT 
                u.FirstName, u.LastName, u.Email, u.PhoneNumber, 
                ce.EnrollmentID, 
                cgm.PerformanceNotes, cgm.PlacementStatus, cgm.CompanyRecommendation
            FROM CourseGroupMembers cgm
            JOIN CourseEnrollments ce ON cgm.EnrollmentID = ce.EnrollmentID
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            WHERE cgm.GroupID = %s ORDER BY u.LastName, u.FirstName
        """, (group_id,))
        assigned_members = cursor.fetchall()

        # 2. Get available candidates for the "Add Student" dropdown
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

@instructor_portal_bp.route('/group/<int:group_id>/roster/update-student/<int:enrollment_id>', methods=['POST'])
@instructor_required
def update_student_details(group_id, enrollment_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM CourseGroupInstructors WHERE GroupID = %s AND InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        if not cursor.fetchone():
            flash("Unauthorized.", "danger")
            return redirect(url_for('.my_groups'))
        placement_status = request.form.get('placement_status')
        recommendation = request.form.get('recommendation')
        cursor.execute("UPDATE CourseGroupMembers SET PlacementStatus = %s, CompanyRecommendation = %s WHERE GroupID = %s AND EnrollmentID = %s", (placement_status, recommendation, group_id, enrollment_id))
        conn.commit()
        flash("Student details updated successfully.", "success")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"A database error occurred: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.manage_roster', group_id=group_id))
    
# --- Assessment & Attendance Routes ---
@instructor_portal_bp.route('/group/<int:group_id>/assessment/add', methods=['GET', 'POST'])
@instructor_required
def add_assessment(group_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM CourseGroupInstructors WHERE GroupID = %s AND InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        if not cursor.fetchone():
            flash("Access denied.", "danger")
            return redirect(url_for('.my_groups'))

        if request.method == 'POST':
            form = request.form
            sql_insert_assessment = "INSERT INTO GroupAssessments (GroupID, CreatedByInstructorStaffID, Title, Description, AssessmentType, DueDate, MaxPoints) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            params = (group_id, current_user.specific_role_id, form['Title'], form['Description'], form['AssessmentType'], form.get('DueDate') or None, form.get('MaxPoints', 100))
            cursor.execute(sql_insert_assessment, params)
            new_assessment_id = cursor.lastrowid

            cursor.execute("SELECT EnrollmentID FROM CourseGroupMembers WHERE GroupID = %s", (group_id,))
            enrollments = cursor.fetchall()

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
        return redirect(url_for('.group_dashboard', group_id=group_id))
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('instructor_portal/add_edit_assessment.html', title="Add New Assessment", group_id=group_id)

@instructor_portal_bp.route('/assessment/<int:assessment_id>/grade', methods=['GET', 'POST'])
@instructor_required
def grade_assessment(assessment_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT ga.*, cg.GroupName FROM GroupAssessments ga JOIN CourseGroups cg ON ga.GroupID = cg.GroupID JOIN CourseGroupInstructors cgi ON cg.GroupID = cgi.GroupID WHERE ga.AssessmentID = %s AND cgi.InstructorStaffID = %s", (assessment_id, current_user.specific_role_id))
        assessment = cursor.fetchone()
        if not assessment:
            flash("Assessment not found or you do not have permission to grade it.", "danger")
            return redirect(url_for('.my_groups'))

        if request.method == 'POST':
            for key, value in request.form.items():
                if key.startswith('score_'):
                    submission_id = key.split('_')[1]
                    score = value or None
                    feedback = request.form.get(f'feedback_{submission_id}', '')
                    sql_update = "UPDATE CandidateSubmissions SET Score = %s, InstructorFeedback = %s, Status = 'Graded', GradedAt = NOW() WHERE SubmissionID = %s"
                    cursor.execute(sql_update, (score, feedback, submission_id))
            conn.commit()
            flash("Grades saved successfully!", "success")
            return redirect(url_for('.grade_assessment', assessment_id=assessment_id))

        cursor.execute("SELECT cs.*, u.FirstName, u.LastName FROM CandidateSubmissions cs JOIN CourseEnrollments ce ON cs.EnrollmentID = ce.EnrollmentID JOIN Candidates c ON ce.CandidateID = c.CandidateID JOIN Users u ON c.UserID = u.UserID WHERE cs.AssessmentID = %s ORDER BY u.LastName, u.FirstName", (assessment_id,))
        submissions = cursor.fetchall()
    except Exception as e:
        if conn and conn.is_connected() and request.method == 'POST': conn.rollback()
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('.my_groups'))
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('instructor_portal/grade_assessment.html', title=f"Grade: {assessment['Title']}", assessment=assessment, submissions=submissions)

@instructor_portal_bp.route('/group/<int:group_id>/attendance')
@instructor_required
def attendance(group_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT GroupName FROM CourseGroups cg JOIN CourseGroupInstructors cgi ON cg.GroupID = cgi.GroupID WHERE cg.GroupID = %s AND cgi.InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        group = cursor.fetchone()
        if not group:
            flash("You are not authorized to view this group.", "danger")
            return redirect(url_for('.my_groups'))
        
        cursor.execute("SELECT SessionID, SessionNumber, SessionTitle FROM GroupSessions WHERE GroupID = %s ORDER BY SessionNumber", (group_id,))
        sessions = cursor.fetchall()

        cursor.execute("""
            SELECT 
                u.UserID, u.FirstName, u.LastName, cgm.EnrollmentID,
                sa.SessionID, sa.Status, sa.AttendanceNotes, sa.PerformanceNotes
            FROM CourseGroupMembers cgm
            JOIN CourseEnrollments ce ON cgm.EnrollmentID = ce.EnrollmentID
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            LEFT JOIN SessionAttendance sa ON cgm.EnrollmentID = sa.EnrollmentID AND sa.SessionID IN (SELECT SessionID FROM GroupSessions WHERE GroupID = %s)
            WHERE cgm.GroupID = %s
            ORDER BY u.LastName, u.FirstName, sa.SessionID
        """, (group_id, group_id))
        attendance_raw = cursor.fetchall()
        
        students_attendance = {}
        for row in attendance_raw:
            enrollment_id = row['EnrollmentID']
            if enrollment_id not in students_attendance:
                students_attendance[enrollment_id] = {'FirstName': row['FirstName'], 'LastName': row['LastName'], 'attendance': {}}
            if row['SessionID']:
                students_attendance[enrollment_id]['attendance'][row['SessionID']] = {
                    'Status': row['Status'],
                    'AttendanceNotes': row['AttendanceNotes'],
                    'PerformanceNotes': row['PerformanceNotes']
                }
    except Exception as e:
        flash(f"An error occurred while loading attendance data: {e}", "danger")
        return redirect(url_for('.group_dashboard', group_id=group_id))
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('instructor_portal/attendance.html', title=f"Attendance: {group['GroupName']}", group_id=group_id, group_name=group['GroupName'], sessions=sessions, students_attendance=students_attendance)

@instructor_portal_bp.route('/group/<int:group_id>/attendance/update', methods=['POST'])
@instructor_required
def update_attendance(group_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM CourseGroupInstructors WHERE GroupID = %s AND InstructorStaffID = %s", (group_id, current_user.specific_role_id))
        if not cursor.fetchone():
            flash("You are not authorized to update this group's attendance.", "danger")
            return redirect(url_for('.my_groups'))

        for key, value in request.form.items():
            if key.startswith('status_'):
                _, session_id, enrollment_id = key.split('_')
                new_status = value
                attendance_notes = request.form.get(f'attendance_notes_{session_id}_{enrollment_id}', '')
                performance_notes = request.form.get(f'performance_notes_{session_id}_{enrollment_id}', '')
                cursor.execute("UPDATE SessionAttendance SET Status = %s, AttendanceNotes = %s, PerformanceNotes = %s WHERE SessionID = %s AND EnrollmentID = %s", (new_status, attendance_notes, performance_notes, session_id, enrollment_id))
        
        conn.commit()
        flash("Attendance updated successfully!", "success")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"A database error occurred: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.attendance', group_id=group_id))
    
# --- Utility and Placement Tracking ---
@instructor_portal_bp.route('/utility/sync-sessions', methods=['GET', 'POST'])
@instructor_required
def sync_sessions_utility():
    from utils.group_utils import sync_sessions_for_groups # Local import
    if request.method == 'POST':
        message, category = sync_sessions_for_groups()
        flash(message, category)
        return redirect(url_for('.my_groups'))
    return render_template('instructor_portal/sync_sessions_utility.html', title="Sync Group Sessions")

@instructor_portal_bp.route('/my-placements')
@instructor_required
def my_placements():
    placements = []
    # Logic to query `InstructorPlacements` table will go here
    return render_template('instructor_portal/my_placements.html', 
                           title="My Placements & Commissions",
                           placements=placements)
    
@instructor_portal_bp.route('/placement-requests')
@instructor_required
def placement_requests():
    """Lists all candidates who have applied but are not yet placed in a group."""
    conn = get_db_connection()
    applications = []
    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch all enrollments with 'Applied' status
        cursor.execute("""
        SELECT 
            ce.EnrollmentID, ce.EnrollmentDate,
            u.FirstName, u.LastName, u.Email,
            sp.Name AS AppliedSubPackageName,
            apt.TestID, pt.Title AS AssignedTestTitle
        FROM CourseEnrollments ce
        JOIN Candidates c ON ce.CandidateID = c.CandidateID
        JOIN Users u ON c.UserID = u.UserID
        LEFT JOIN SubPackages sp ON ce.OriginalSubPackageID = sp.SubPackageID
        LEFT JOIN AssignedPlacementTests apt ON ce.EnrollmentID = apt.EnrollmentID
        LEFT JOIN PlacementTests pt ON apt.TestID = pt.TestID
        WHERE ce.Status = 'Applied'
        ORDER BY ce.EnrollmentDate ASC
    """)
        applications = cursor.fetchall()
    except Exception as e:
        flash("An error occurred while fetching placement requests.", "danger")
        current_app.logger.error(f"Error fetching placement requests: {e}")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('instructor_portal/placement_requests.html',
                           title="Student Placement Requests",
                           applications=applications)


@instructor_portal_bp.route('/place-student/<int:enrollment_id>', methods=['GET', 'POST'])
@instructor_required
def place_student(enrollment_id):
    """Page for an instructor to place a student into a group after assessment."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        instructor_staff_id = current_user.specific_role_id

        # Fetch the application details
        cursor.execute("""
            SELECT ce.EnrollmentID, u.FirstName, u.LastName, sp.Name as AppliedSubPackageName
            FROM CourseEnrollments ce
            JOIN Candidates c ON ce.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            LEFT JOIN SubPackages sp ON ce.OriginalSubPackageID = sp.SubPackageID
            WHERE ce.EnrollmentID = %s AND ce.Status = 'Applied'
        """, (enrollment_id,))
        application = cursor.fetchone()

        if not application:
            flash("This application is not available for placement or has already been processed.", "warning")
            return redirect(url_for('.placement_requests'))
            
        # Fetch all groups managed by this instructor to populate the dropdown
        cursor.execute("""
            SELECT cg.GroupID, cg.GroupName, sp.Name as SubPackageName, mp.Name as MainPackageName
            FROM CourseGroups cg
            JOIN CourseGroupInstructors cgi ON cg.GroupID = cgi.GroupID
            JOIN SubPackages sp ON cg.SubPackageID = sp.SubPackageID
            JOIN MainPackages mp ON sp.MainPackageID = mp.PackageID
            WHERE cgi.InstructorStaffID = %s AND cg.Status IN ('Planning', 'Active')
        """, (instructor_staff_id,))
        available_groups = cursor.fetchall()

        if request.method == 'POST':
            form = request.form
            group_id = form.get('group_id')
            test_score = form.get('test_score')

            if not group_id:
                flash("You must select a group to place the student in.", "danger")
                return render_template('instructor_portal/place_student.html',
                                       title="Place Student",
                                       application=application,
                                       available_groups=available_groups)
            
            # --- THE CORE PLACEMENT LOGIC ---
            # 1. Get the SubPackageID from the selected group
            cursor.execute("SELECT SubPackageID FROM CourseGroups WHERE GroupID = %s", (group_id,))
            group_data = cursor.fetchone()
            final_subpackage_id = group_data['SubPackageID']

            # 2. Update the CourseEnrollments record
            cursor.execute("""
                UPDATE CourseEnrollments 
                SET 
                    Status = 'Enrolled', 
                    SubPackageID = %s,
                    PlacementTestScore = %s,
                    AssignedByInstructorStaffID = %s,
                    UpdatedAt = NOW()
                WHERE EnrollmentID = %s
            """, (final_subpackage_id, test_score, instructor_staff_id, enrollment_id))

            # 3. Add the student to the group's roster
            cursor.execute("INSERT INTO CourseGroupMembers (GroupID, EnrollmentID) VALUES (%s, %s)", (group_id, enrollment_id))

            # 4. Generate their attendance records for all sessions in that group
            cursor.execute("SELECT SessionID FROM GroupSessions WHERE GroupID = %s", (group_id,))
            sessions = cursor.fetchall()
            if sessions:
                attendance_data = [(s['SessionID'], enrollment_id) for s in sessions]
                sql_insert_attendance = "INSERT INTO SessionAttendance (SessionID, EnrollmentID) VALUES (%s, %s)"
                cursor.executemany(sql_insert_attendance, attendance_data)

            conn.commit()
            flash(f"{application['FirstName']} {application['LastName']} has been successfully placed.", "success")
            return redirect(url_for('.placement_requests'))

    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"An error occurred during placement: {e}", "danger")
        current_app.logger.error(f"Error placing student (EnrollmentID {enrollment_id}): {e}", exc_info=True)
        return redirect(url_for('.placement_requests'))
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('instructor_portal/place_student.html',
                           title=f"Place Student: {application['FirstName']} {application['LastName']}",
                           application=application,
                           available_groups=available_groups)
    
@instructor_portal_bp.route('/placement-tests')
@instructor_required
def list_placement_tests():
    """Lists all placement tests created by the instructor."""
    conn = get_db_connection()
    tests = []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT TestID, Title, TestType, ExternalURL, IsActive 
            FROM PlacementTests 
            WHERE CreatedByInstructorStaffID = %s
            ORDER BY CreatedAt DESC
        """, (current_user.specific_role_id,))
        tests = cursor.fetchall()
    finally:
        if conn and conn.is_connected(): conn.close()
    return render_template('instructor_portal/list_placement_tests.html', 
                           title="Manage Placement Tests", tests=tests)


@instructor_portal_bp.route('/placement-tests/add', methods=['GET', 'POST'])
@instructor_required
def add_placement_test():
    """Add a new external or internal placement test."""
    if request.method == 'POST':
        form = request.form
        test_type = form.get('test_type')
        title = form.get('title')
        external_url = form.get('external_url')

        if not title or not test_type:
            flash("Title and Test Type are required.", "danger")
            return render_template('instructor_portal/add_edit_placement_test.html', title="Add Placement Test", form_data=form)
        
        if test_type == 'External' and not external_url:
            flash("External URL is required for an external test.", "danger")
            return render_template('instructor_portal/add_edit_placement_test.html', title="Add Placement Test", form_data=form)
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO PlacementTests (Title, Description, TestType, ExternalURL, CreatedByInstructorStaffID)
                VALUES (%s, %s, %s, %s, %s)
            """, (title, form.get('description'), test_type, external_url if test_type == 'External' else None, current_user.specific_role_id))
            conn.commit()
            flash("Placement test created successfully.", "success")
            return redirect(url_for('.list_placement_tests'))
        except Exception as e:
            if conn and conn.is_connected(): conn.rollback()
            flash(f"Database error: {e}", "danger")
        finally:
            if conn and conn.is_connected(): conn.close()
    
    return render_template('instructor_portal/add_edit_placement_test.html', title="Add Placement Test", form_data={})

# Note: An edit_placement_test route would follow the same pattern.

@instructor_portal_bp.route('/placement-requests/<int:enrollment_id>/assign-test', methods=['GET', 'POST'])
@instructor_required
def assign_placement_test(enrollment_id):
    """Assign an existing placement test to a student's application."""
    conn = get_db_connection()
    # Initialize variables outside the try block to ensure they always exist
    available_tests = []
    student = None
    
    try:
        cursor = conn.cursor(dictionary=True)
        instructor_staff_id = current_user.specific_role_id

        # --- Fetch data needed for both GET and POST (for validation and display) ---
        
        # 1. Fetch student info
        cursor.execute("""
            SELECT u.FirstName, u.LastName 
            FROM CourseEnrollments ce 
            JOIN Candidates c ON ce.CandidateID = c.CandidateID 
            JOIN Users u ON c.UserID = u.UserID 
            WHERE ce.EnrollmentID = %s
        """, (enrollment_id,))
        student = cursor.fetchone()

        # If student not found, we can't proceed.
        if not student:
            flash("Could not find the specified student application.", "danger")
            return redirect(url_for('.placement_requests'))

        # 2. Fetch available tests created by this instructor
        cursor.execute("""
            SELECT TestID, Title 
            FROM PlacementTests 
            WHERE CreatedByInstructorStaffID = %s AND IsActive = 1
        """, (instructor_staff_id,))
        available_tests = cursor.fetchall()

        # --- Handle form submission ---
        if request.method == 'POST':
            test_id = request.form.get('test_id')
            if not test_id:
                flash("You must select a test to assign.", "danger")
                # We can re-render the template because student and available_tests are already fetched
                return render_template('instructor_portal/assign_test.html', 
                                       title=f"Assign Test to {student['FirstName']}", 
                                       enrollment_id=enrollment_id, 
                                       student=student,
                                       available_tests=available_tests)
            
            # Use INSERT ... ON DUPLICATE KEY UPDATE to handle re-assignment smoothly
            cursor.execute("""
                INSERT INTO AssignedPlacementTests (EnrollmentID, TestID, AssignedByInstructorStaffID)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE TestID = VALUES(TestID), AssignedByInstructorStaffID = VALUES(AssignedByInstructorStaffID), AssignedAt = NOW()
            """, (enrollment_id, test_id, instructor_staff_id))
            conn.commit()
            
            flash("Test assigned to student successfully.", "success")
            return redirect(url_for('.placement_requests'))
            
    except Exception as e:
        # Catch any other unexpected errors
        current_app.logger.error(f"Error in assign_placement_test for EnrollmentID {enrollment_id}: {e}", exc_info=True)
        flash("An unexpected server error occurred. Please try again.", "danger")
        return redirect(url_for('.placement_requests'))
    finally:
        if conn and conn.is_connected():
            conn.close()
        
    # This part now only runs for GET requests
    return render_template('instructor_portal/assign_test.html', 
                           title=f"Assign Test to {student['FirstName']}", 
                           enrollment_id=enrollment_id, 
                           student=student,
                           available_tests=available_tests)
    
@instructor_portal_bp.route('/placement-tests/edit/<int:test_id>', methods=['GET', 'POST'])
@instructor_required
def edit_placement_test(test_id):
    """Edit an existing placement test."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        instructor_staff_id = current_user.specific_role_id

        # Authorization Check: Make sure the test belongs to the logged-in instructor
        cursor.execute("SELECT * FROM PlacementTests WHERE TestID = %s AND CreatedByInstructorStaffID = %s", (test_id, instructor_staff_id))
        test = cursor.fetchone()
        if not test:
            flash("Placement test not found or you do not have permission to edit it.", "danger")
            return redirect(url_for('.list_placement_tests'))

        if request.method == 'POST':
            form = request.form
            test_type = form.get('test_type')
            title = form.get('title')
            external_url = form.get('external_url')
            is_active = 1 if form.get('is_active') else 0

            if not title or not test_type:
                flash("Title and Test Type are required.", "danger")
                return render_template('instructor_portal/add_edit_placement_test.html', title="Edit Placement Test", form_data=form, test_id=test_id)
            
            if test_type == 'External' and not external_url:
                flash("External URL is required for an external test.", "danger")
                return render_template('instructor_portal/add_edit_placement_test.html', title="Edit Placement Test", form_data=form, test_id=test_id)

            cursor.execute("""
                UPDATE PlacementTests SET
                Title = %s, Description = %s, TestType = %s, ExternalURL = %s, IsActive = %s, UpdatedAt = NOW()
                WHERE TestID = %s
            """, (title, form.get('description'), test_type, external_url if test_type == 'External' else None, is_active, test_id))
            conn.commit()
            flash("Placement test updated successfully.", "success")
            return redirect(url_for('.list_placement_tests'))

        # GET request: Populate form with existing data
        return render_template('instructor_portal/add_edit_placement_test.html', title="Edit Placement Test", form_data=test, test_id=test_id)
    
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash(f"Database error: {e}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
    
    return redirect(url_for('.list_placement_tests'))


@instructor_portal_bp.route('/placement-tests/delete/<int:test_id>', methods=['POST'])
@instructor_required
def delete_placement_test(test_id):
    """Delete a placement test."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        instructor_staff_id = current_user.specific_role_id

        # Authorization Check
        cursor.execute("SELECT TestID FROM PlacementTests WHERE TestID = %s AND CreatedByInstructorStaffID = %s", (test_id, instructor_staff_id))
        if not cursor.fetchone():
            flash("Placement test not found or you do not have permission to delete it.", "danger")
            return redirect(url_for('.list_placement_tests'))

        # The ON DELETE CASCADE constraint will handle removing related records in AssignedPlacementTests
        cursor.execute("DELETE FROM PlacementTests WHERE TestID = %s", (test_id,))
        conn.commit()
        flash("Placement test deleted successfully.", "success")

    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
        # This will catch if a test is linked somewhere without ON DELETE CASCADE
        flash(f"Could not delete test. It may be in use. Error: {err.msg}", "danger")
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('.list_placement_tests'))

@instructor_portal_bp.route('/placement-tests/build/<int:test_id>')
@instructor_required
def build_placement_test(test_id):
    """The main page for building/editing an internal placement test."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Auth check and ensure it's an internal test
        cursor.execute("""
            SELECT * FROM PlacementTests 
            WHERE TestID = %s AND CreatedByInstructorStaffID = %s AND TestType = 'Internal'
        """, (test_id, current_user.specific_role_id))
        test = cursor.fetchone()
        if not test:
            flash("Internal test not found or you are not authorized to edit it.", "danger")
            return redirect(url_for('.list_placement_tests'))

        # Fetch all questions and their options for this test
        cursor.execute("SELECT * FROM PlacementTestQuestions WHERE TestID = %s ORDER BY DisplayOrder", (test_id,))
        questions = cursor.fetchall()

        if questions:
            question_ids = [q['QuestionID'] for q in questions]
            # Use a format string for the IN clause placeholder
            format_strings = ','.join(['%s'] * len(question_ids))
            cursor.execute(f"""
                SELECT * FROM PlacementTestQuestionOptions 
                WHERE QuestionID IN ({format_strings})
            """, tuple(question_ids))
            options = cursor.fetchall()
            
            # Map options to their questions
            options_map = {}
            for opt in options:
                qid = opt['QuestionID']
                if qid not in options_map:
                    options_map[qid] = []
                options_map[qid].append(opt)
            
            for q in questions:
                q['options'] = options_map.get(q['QuestionID'], [])

    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('instructor_portal/build_placement_test.html',
                           title=f"Build Test: {test['Title']}",
                           test=test,
                           questions=questions)


@instructor_portal_bp.route('/placement-tests/build/<int:test_id>/add-question', methods=['POST'])
@instructor_required
def add_test_question(test_id):
    """Adds a new question (MultipleChoice or WrittenAnswer) to an internal test."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        question_text = request.form.get('question_text')
        question_type = request.form.get('question_type', 'MultipleChoice') # Default to MC
        model_answer = request.form.get('model_answer') # This will be None for MC questions

        if not question_text:
            return jsonify({'status': 'error', 'message': 'Question text cannot be empty.'}), 400
        
        cursor.execute(
            """INSERT INTO PlacementTestQuestions 
               (TestID, QuestionText, QuestionType, ModelAnswer) 
               VALUES (%s, %s, %s, %s)""",
            (test_id, question_text, question_type, model_answer)
        )
        conn.commit()
        return jsonify({'status': 'success', 'question_id': cursor.lastrowid})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()


@instructor_portal_bp.route('/placement-tests/question/<int:question_id>/add-option', methods=['POST'])
@instructor_required
def add_question_option(question_id):
    """Adds a new option to a question via AJAX."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        option_text = request.form.get('option_text')
        is_correct = 1 if request.form.get('is_correct') == 'true' else 0
        
        cursor.execute(
            "INSERT INTO PlacementTestQuestionOptions (QuestionID, OptionText, IsCorrect) VALUES (%s, %s, %s)",
            (question_id, option_text, is_correct)
        )
        conn.commit()
        return jsonify({'status': 'success', 'option_id': cursor.lastrowid})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()
        
@instructor_portal_bp.route('/placement-tests/question/<int:question_id>/update', methods=['POST'])
@instructor_required
def update_test_question(question_id):
    """Updates the text and model answer of an existing question."""
    # NOTE: A full implementation would also check that the question_id
    # belongs to a test owned by the current_user.
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        question_text = request.form.get('question_text')
        model_answer = request.form.get('model_answer') # Will be None for MCQ
        
        cursor.execute(
            "UPDATE PlacementTestQuestions SET QuestionText = %s, ModelAnswer = %s WHERE QuestionID = %s",
            (question_text, model_answer, question_id)
        )
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Question updated.'})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()

@instructor_portal_bp.route('/placement-tests/option/<int:option_id>/update', methods=['POST'])
@instructor_required
def update_question_option(option_id):
    """Updates the text and correctness of an existing option."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        option_text = request.form.get('option_text')
        is_correct = 1 if request.form.get('is_correct') == 'true' else 0
        
        # If this option is being marked as correct, we must first ensure
        # no other option for this question is marked as correct.
        if is_correct:
            cursor.execute("SELECT QuestionID FROM PlacementTestQuestionOptions WHERE OptionID = %s", (option_id,))
            question_id = cursor.fetchone()[0]
            cursor.execute("UPDATE PlacementTestQuestionOptions SET IsCorrect = 0 WHERE QuestionID = %s", (question_id,))
        
        cursor.execute(
            "UPDATE PlacementTestQuestionOptions SET OptionText = %s, IsCorrect = %s WHERE OptionID = %s",
            (option_text, is_correct, option_id)
        )
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Option updated.'})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()

@instructor_portal_bp.route('/placement-tests/question/<int:question_id>/delete', methods=['POST'])
@instructor_required
def delete_test_question(question_id):
    """Deletes a question and its associated options."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # The ON DELETE CASCADE constraint will automatically delete the options.
        cursor.execute("DELETE FROM PlacementTestQuestions WHERE QuestionID = %s", (question_id,))
        conn.commit()
        flash("Question deleted successfully.", "success")
        return jsonify({'status': 'success'})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()