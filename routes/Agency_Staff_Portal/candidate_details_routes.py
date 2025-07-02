from flask import Blueprint, render_template, abort, current_app
from flask_login import login_required # Or your specific role decorator
from db11 import get_db_connection
import mysql.connector

candidate_details_bp = Blueprint('candidate_details_bp', __name__,
                                 template_folder='../../../templates',
                                 url_prefix='/staff/candidate')

# Define roles that can view detailed candidate profiles (e.g., AMs, Recruiters, Managers)
CANDIDATE_VIEW_ROLES = ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 
                        'SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead',
                        'OperationsManager', 'CEO']

@candidate_details_bp.route('/profile/<int:candidate_id>')
@login_required # Consider using @login_required_with_role(CANDIDATE_VIEW_ROLES)
def view_candidate_profile(candidate_id):
    # Optional: Add specific role check here if not done by decorator
    # if current_user.role_type not in CANDIDATE_VIEW_ROLES:
    #     abort(403) 

    conn = None
    candidate_data = {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Fetch Basic Candidate and User Info
        cursor.execute("""
            SELECT 
                c.*, 
                u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL, u.RegistrationDate,
                s_source.FirstName as SourcedByFirstName, s_source.LastName as SourcedByLastName 
            FROM Candidates c
            JOIN Users u ON c.UserID = u.UserID
            LEFT JOIN Staff s_staff ON c.SourcedByStaffID = s_staff.StaffID
            LEFT JOIN Users s_source ON s_staff.UserID = s_source.UserID
            WHERE c.CandidateID = %s
        """, (candidate_id,))
        candidate_info = cursor.fetchone()

        if not candidate_info:
            abort(404, "Candidate not found.")
        candidate_data['info'] = candidate_info

        # 2. Fetch CVs
        cursor.execute("""
            SELECT CVID, CVFileUrl, OriginalFileName, FileType, FileSizeKB, UploadedAt, IsPrimary, CVTitle, Notes 
            FROM CandidateCVs 
            WHERE CandidateID = %s 
            ORDER BY IsPrimary DESC, UploadedAt DESC
        """, (candidate_id,))
        candidate_data['cvs'] = cursor.fetchall()

        # 3. Fetch Voice Notes
        cursor.execute("""
            SELECT VoiceNoteID, VoiceNoteURL, Title, Purpose, DurationSeconds, UploadedAt 
            FROM CandidateVoiceNotes 
            WHERE CandidateID = %s 
            ORDER BY UploadedAt DESC
        """, (candidate_id,))
        candidate_data['voice_notes'] = cursor.fetchall()

        # 4. Fetch Profile Feedbacks (by staff)
        cursor.execute("""
            SELECT 
                cpf.*, u.FirstName as FeedbackByFirstName, u.LastName as FeedbackByLastName, s.Role as FeedbackByRole
            FROM CandidateProfileFeedbacks cpf
            JOIN Staff s ON cpf.FeedbackByStaffID = s.StaffID
            JOIN Users u ON s.UserID = u.UserID
            WHERE cpf.CandidateID = %s
            ORDER BY cpf.FeedbackDate DESC
        """, (candidate_id,))
        candidate_data['feedbacks'] = cursor.fetchall()

        # 5. Fetch Orientations
        cursor.execute("""
            SELECT 
                co.*, u.FirstName as ConductedByFirstName, u.LastName as ConductedByLastName
            FROM CandidateOrientations co
            LEFT JOIN Staff s ON co.ConductedByStaffID = s.StaffID
            LEFT JOIN Users u ON s.UserID = u.UserID
            WHERE co.CandidateID = %s
            ORDER BY co.OrientationDateTime DESC
        """, (candidate_id,))
        candidate_data['orientations'] = cursor.fetchall()
        
        # 6. Fetch Course Enrollments
        cursor.execute("""
            SELECT ce.*, crs.CourseName, crs.Category as CourseCategory
            FROM CourseEnrollments ce
            JOIN Courses crs ON ce.CourseID = crs.CourseID
            WHERE ce.CandidateID = %s
            ORDER BY ce.EnrollmentDate DESC
        """, (candidate_id,))
        candidate_data['enrollments'] = cursor.fetchall()
        
        # 7. Fetch Job Applications
        cursor.execute("""
            SELECT ja.*, jo.Title as OfferTitle, comp.CompanyName
            FROM JobApplications ja
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies comp ON jo.CompanyID = comp.CompanyID
            WHERE ja.CandidateID = %s
            ORDER BY ja.ApplicationDate DESC
        """, (candidate_id,))
        candidate_data['applications'] = cursor.fetchall()


    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error fetching profile for candidate {candidate_id}: {err}", exc_info=True)
        abort(500, "Database error occurred.")
    except Exception as e:
        current_app.logger.error(f"Error fetching profile for candidate {candidate_id}: {e}", exc_info=True)
        abort(500, "An unexpected error occurred.")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
            
    return render_template('agency_staff_portal/candidate/candidate_profile_detailed.html',
                           title=f"Candidate Profile: {candidate_data['info']['FirstName']} {candidate_data['info']['LastName']}",
                           candidate=candidate_data)