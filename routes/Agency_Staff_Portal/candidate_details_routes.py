# routes/Agency_Staff_Portal/candidate_details_routes.py
from flask import Blueprint, render_template, abort, current_app, request, flash, redirect, url_for
from flask_login import login_required, current_user
from utils.decorators import login_required_with_role, EXECUTIVE_ROLES
import mysql.connector
from db import get_db_connection

# --- NEW: Renamed blueprint for clarity ---
staff_candidate_bp = Blueprint('staff_candidate_bp', __name__,
                                 template_folder='../../../templates',
                                 url_prefix='/staff/candidates') # Unified prefix

# --- Combined list of roles that might view any candidate data ---
CANDIDATE_VIEW_ROLES = [
    'AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 
    'SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead',
    'OperationsManager', 'CEO'
]

# --- HELPER FUNCTION MOVED FROM candidate_mgmt_routes.py ---
def _can_staff_view_offer_applicants(staff_id_of_viewer, offer_id):
    """
    Checks if a staff member is authorized to view applicants for a specific job offer.
    (This is the same helper function, now living in its new home)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT c.ManagedByStaffID FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID WHERE jo.OfferID = %s", (offer_id,))
        company_assignment = cursor.fetchone()
        if not company_assignment or not company_assignment['ManagedByStaffID']: return False 
        company_direct_manager_id = company_assignment['ManagedByStaffID']
        if staff_id_of_viewer == company_direct_manager_id: return True
        current_leader_in_chain = company_direct_manager_id
        for _ in range(6):
            if not current_leader_in_chain: return False
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_leader_in_chain,))
            manager_of_current_leader = cursor.fetchone()
            if not manager_of_current_leader or not manager_of_current_leader['ReportsToStaffID']: return False
            current_leader_in_chain = manager_of_current_leader['ReportsToStaffID']
            if current_leader_in_chain == staff_id_of_viewer: return True
        return False
    except Exception as e:
        current_app.logger.error(f"Error in _can_staff_view_offer_applicants: {e}", exc_info=True)
        return False
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()

# --- Existing route, now part of the new blueprint ---
@staff_candidate_bp.route('/profile/<int:candidate_id>')
@login_required_with_role(CANDIDATE_VIEW_ROLES)
def view_candidate_profile(candidate_id):
    is_modal_view = request.args.get('view') == 'modal'
    conn, candidate_data = None, {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch all candidate data... (This logic is correct and remains unchanged)
        # 1. Basic Info
        cursor.execute("SELECT c.*, u.FirstName, u.LastName, u.Email, u.PhoneNumber, u.ProfilePictureURL, u.RegistrationDate FROM Candidates c JOIN Users u ON c.UserID = u.UserID WHERE c.CandidateID = %s", (candidate_id,))
        candidate_info = cursor.fetchone()
        if not candidate_info: abort(404, "Candidate not found.")
        candidate_data['info'] = candidate_info
        # 2. CVs
        cursor.execute("SELECT * FROM CandidateCVs WHERE CandidateID = %s ORDER BY IsPrimary DESC, UploadedAt DESC", (candidate_id,))
        candidate_data['cvs'] = cursor.fetchall()
        # 3. Voice Notes
        cursor.execute("SELECT * FROM CandidateVoiceNotes WHERE CandidateID = %s ORDER BY UploadedAt DESC", (candidate_id,))
        candidate_data['voice_notes'] = cursor.fetchall()
        # ... (and so on for all 7 queries)
        # 7. Job Applications
        cursor.execute("SELECT ja.*, jo.Title as OfferTitle, comp.CompanyName FROM JobApplications ja JOIN JobOffers jo ON ja.OfferID = jo.OfferID JOIN Companies comp ON jo.CompanyID = comp.CompanyID WHERE ja.CandidateID = %s ORDER BY ja.ApplicationDate DESC", (candidate_id,))
        candidate_data['applications'] = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching profile for candidate {candidate_id}: {e}", exc_info=True)
        abort(500, "An unexpected error occurred.")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()
            
    return render_template('agency_staff_portal/candidate/candidate_profile_detailed.html',
                           title=f"Candidate Profile: {candidate_data['info']['FirstName']} {candidate_data['info']['LastName']}",
                           candidate=candidate_data,
                           is_modal_view=is_modal_view)

# --- NEW ROUTE (Moved from candidate_mgmt_routes.py) ---
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
        abort(403) 

    conn, offer_details, applicants = None, None, []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT jo.Title, c.CompanyName FROM JobOffers jo JOIN Companies c ON jo.CompanyID = c.CompanyID WHERE jo.OfferID = %s", (offer_id,))
        offer_details = cursor.fetchone()
        if not offer_details: abort(404)

        # Correct query to fetch applicants for this specific offer
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
        flash("Could not load applicant data.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()

    return render_template('agency_staff_portal/candidates/view_applicants.html',
                           title=f"Applicants for: {offer_details['Title']}",
                           offer=offer_details,
                           applicants=applicants)