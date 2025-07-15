# routes/Agency_Staff_Portal/staff_candidate_routes.py
from flask import Blueprint, render_template, abort, current_app, request, flash, redirect, url_for
from flask_login import current_user
from utils.decorators import login_required_with_role, EXECUTIVE_ROLES
import mysql.connector
from db import get_db_connection

# --- The single, unified blueprint for all staff-related candidate views ---
staff_candidate_bp = Blueprint('staff_candidate_bp', __name__,
                                 template_folder='../../../templates',
                                 url_prefix='/staff/candidates')

# --- Consolidated list of all roles that can view any candidate data ---
CANDIDATE_VIEW_ROLES = [
    'AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 
    'SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead',
    'OperationsManager', 'CEO'
]

# --- HELPER FUNCTION: Defined once in its final home ---
def _can_staff_view_offer_applicants(staff_id_of_viewer, offer_id):
    """
    Checks if a staff member is authorized to view applicants for a specific job offer.
    Authorization is granted if the offer's company is managed by this staff member OR
    by someone who reports to this staff member (up the hierarchy).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT c.ManagedByStaffID FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID WHERE jo.OfferID = %s", (offer_id,))
        company_assignment = cursor.fetchone()
        
        if not company_assignment or not company_assignment['ManagedByStaffID']:
            current_app.logger.info(f"Offer {offer_id} has no assigned staff manager for company.")
            return False 

        company_direct_manager_id = company_assignment['ManagedByStaffID']
        if staff_id_of_viewer == company_direct_manager_id:
            return True
            
        current_leader_in_chain = company_direct_manager_id
        for _ in range(6): # Max hierarchy depth to check
            if not current_leader_in_chain: return False
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_leader_in_chain,))
            manager_of_current_leader = cursor.fetchone()
            if not manager_of_current_leader or not manager_of_current_leader['ReportsToStaffID']:
                return False
            current_leader_in_chain = manager_of_current_leader['ReportsToStaffID']
            if current_leader_in_chain == staff_id_of_viewer:
                return True

        return False
    except Exception as e:
        current_app.logger.error(f"Error in _can_staff_view_offer_applicants (viewer: {staff_id_of_viewer}, offer: {offer_id}): {e}", exc_info=True)
        return False
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()

@staff_candidate_bp.route('/profile/<int:candidate_id>')
@login_required_with_role(CANDIDATE_VIEW_ROLES)
def view_candidate_profile(candidate_id):
    is_modal_view = request.args.get('view') == 'modal'
    conn, candidate_data = None, {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Basic Info
        cursor.execute("""
            SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL, u.RegistrationDate 
            FROM Candidates c JOIN Users u ON c.UserID = u.UserID WHERE c.CandidateID = %s
        """, (candidate_id,))
        candidate_info = cursor.fetchone()
        if not candidate_info: abort(404, "Candidate not found.")
        candidate_data['info'] = candidate_info
        
        # 2. CVs
        cursor.execute("SELECT * FROM CandidateCVs WHERE CandidateID = %s ORDER BY IsPrimary DESC, UploadedAt DESC", (candidate_id,))
        candidate_data['cvs'] = cursor.fetchall()
        
        # 3. Voice Notes
        cursor.execute("SELECT * FROM CandidateVoiceNotes WHERE CandidateID = %s ORDER BY UploadedAt DESC", (candidate_id,))
        candidate_data['voice_notes'] = cursor.fetchall()

        # 4. Job Applications
        cursor.execute("""
            SELECT ja.*, jo.Title as OfferTitle, comp.CompanyName 
            FROM JobApplications ja 
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID 
            JOIN Companies comp ON jo.CompanyID = comp.CompanyID 
            WHERE ja.CandidateID = %s ORDER BY ja.ApplicationDate DESC
        """, (candidate_id,))
        candidate_data['applications'] = cursor.fetchall()

        # 5. Course Enrollments
        cursor.execute("""
            SELECT ce.*, c.CourseName, c.Price, c.Currency
            FROM CourseEnrollments ce
            JOIN Courses c ON ce.CourseID = c.CourseID
            WHERE ce.CandidateID = %s ORDER BY ce.EnrollmentDate DESC
        """, (candidate_id,))
        candidate_data['enrollments'] = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching profile for candidate {candidate_id}: {e}", exc_info=True)
        abort(500, "An unexpected error occurred while fetching candidate data.")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()
            
    return render_template('agency_staff_portal/candidates/candidate_profile_detailed.html',
                           title=f"Candidate: {candidate_data['info']['FirstName']} {candidate_data['info']['LastName']}",
                           candidate=candidate_data,
                           is_modal_view=is_modal_view)


@staff_candidate_bp.route('/job-offer/<int:offer_id>/applicants')
@login_required_with_role(CANDIDATE_VIEW_ROLES)
def view_offer_applicants(offer_id):
    is_authorized = False
    if current_user.role_type in EXECUTIVE_ROLES:
        is_authorized = True
    else:
        staff_id = getattr(current_user, 'specific_role_id', None)
        if staff_id:
            is_authorized = _can_staff_view_offer_applicants(staff_id, offer_id)

    if not is_authorized:
        current_app.logger.warning(f"Unauthorized access attempt to applicants for offer {offer_id} by user {current_user.id} (Role: {current_user.role_type}).")
        abort(403, "You are not authorized to view applicants for this job offer.")

    conn, offer_details, applicants = None, None, []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT jo.Title, c.CompanyName FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID WHERE jo.OfferID = %s", (offer_id,))
        offer_details = cursor.fetchone()
        if not offer_details: abort(404, "Job offer not found.")

        cursor.execute("""
            SELECT c.CandidateID, u.FirstName, u.LastName, u.Email 
            FROM JobApplications ja
            JOIN Candidates c ON ja.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            WHERE ja.OfferID = %s
            ORDER BY ja.ApplicationDate DESC 
        """, (offer_id,))
        applicants = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching applicants for offer {offer_id}: {e}", exc_info=True)
        flash("Could not load applicant data due to a server error.", "danger")
        return redirect(url_for('managerial_dashboard_bp.main_dashboard'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()

    return render_template('agency_staff_portal/candidates/view_applicants.html',
                           title=f"Applicants for: {offer_details['Title']}",
                           offer=offer_details,
                           applicants=applicants)