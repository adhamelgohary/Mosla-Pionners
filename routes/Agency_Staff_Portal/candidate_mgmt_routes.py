# routes/Agency_Staff_Portal/candidate_mgmt_routes.py
from flask import Blueprint, flash, redirect, render_template, abort, current_app, url_for
from flask_login import current_user
# Ensure EXECUTIVE_ROLES is available if used here, or define CANDIDATE_VIEWING_ROLES comprehensively
from utils.decorators import login_required_with_role, EXECUTIVE_ROLES 
from db import get_db_connection

# Roles that can view applicants for companies they are authorized for
CANDIDATE_VIEWING_ROLES = ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 'CEO', 'OperationsManager']

candidate_mgmt_bp = Blueprint('candidate_mgmt_bp', __name__,
                              template_folder='../../../templates',
                              url_prefix='/candidate-management')

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
        
        # 1. Get the StaffID of the manager for the company associated with the offer
        cursor.execute("""
            SELECT c.ManagedByStaffID 
            FROM JobOffers jo 
            JOIN Companies c ON jo.CompanyID = c.CompanyID 
            WHERE jo.OfferID = %s
        """, (offer_id,))
        
        company_assignment = cursor.fetchone()
        if not company_assignment or not company_assignment['ManagedByStaffID']:
            current_app.logger.info(f"Offer {offer_id} has no assigned staff manager for company.")
            return False 

        company_direct_manager_id = company_assignment['ManagedByStaffID']
        
        # 2. Direct check: Is the current viewer the direct manager of the company?
        if staff_id_of_viewer == company_direct_manager_id:
            return True
            
        # 3. Hierarchy check: Is the company's direct manager a subordinate of the current viewer?
        # We trace UP from the company_direct_manager_id to see if we hit staff_id_of_viewer.
        current_leader_in_chain = company_direct_manager_id
        for _ in range(6): # Max hierarchy depth to check
            if not current_leader_in_chain: # Reached top of a branch
                return False
            cursor.execute("SELECT ReportsToStaffID FROM Staff WHERE StaffID = %s", (current_leader_in_chain,))
            manager_of_current_leader = cursor.fetchone()
            if not manager_of_current_leader or not manager_of_current_leader['ReportsToStaffID']:
                return False # Reached the absolute top of hierarchy
            current_leader_in_chain = manager_of_current_leader['ReportsToStaffID']
            if current_leader_in_chain == staff_id_of_viewer:
                return True # The viewer is a superior of the company's direct manager

        return False # Not found in the hierarchy chain within depth
    except Exception as e:
        current_app.logger.error(f"Error in _can_staff_view_offer_applicants (viewer: {staff_id_of_viewer}, offer: {offer_id}): {e}", exc_info=True)
        return False
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

@candidate_mgmt_bp.route('/job-offer/<int:offer_id>/applicants')
@login_required_with_role(CANDIDATE_VIEWING_ROLES) # Use the defined roles list
def view_offer_applicants(offer_id):
    is_authorized = False
    # EXECUTIVE_ROLES should be defined in decorators.py and include 'CEO', 'OperationsManager'
    if current_user.role_type in EXECUTIVE_ROLES:
        is_authorized = True
    else:
        # current_user.specific_role_id is the StaffID for logged-in staff
        staff_id_of_current_user = getattr(current_user, 'specific_role_id', None)
        if staff_id_of_current_user:
            is_authorized = _can_staff_view_offer_applicants(staff_id_of_current_user, offer_id)

    if not is_authorized:
        current_app.logger.warning(f"Unauthorized access attempt to applicants for offer {offer_id} by user {current_user.id} (Role: {current_user.role_type}).")
        abort(403) 

    conn = None
    offer_details = None
    applicants = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT jo.Title, c.CompanyName 
            FROM JobOffers jo
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            WHERE jo.OfferID = %s
        """, (offer_id,))
        offer_details = cursor.fetchone()

        if not offer_details:
            abort(404) # Offer not found

        # Assuming a JobApplications table links Candidates to JobOffers
        cursor.execute("""
            SELECT c.CandidateID, u.FirstName, u.LastName, u.Email, 
                   cv.CVFileUrl, vn.VoiceNoteURL -- Assuming these columns exist from your schema
            FROM Candidates c
            JOIN Users u ON c.UserID = u.UserID
            LEFT JOIN JobApplications ja ON c.CandidateID = ja.CandidateID -- You need this table
            LEFT JOIN CandidateCVs cv ON c.CandidateID = cv.CandidateID AND cv.IsPrimary = 1
            LEFT JOIN CandidateVoiceNotes vn ON c.CandidateID = vn.CandidateID -- Assuming one primary/latest voice note
            WHERE ja.OfferID = %s
            ORDER BY ja.ApplicationDate DESC 
        """, (offer_id,)) # You need a JobApplications table with OfferID and CandidateID
        applicants = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching applicants for offer {offer_id}: {e}", exc_info=True)
        flash("Could not load applicant data.", "danger")
        # Redirect or show error page
        return redirect(url_for('staff_dashboard_bp.main_dashboard')) # Example redirect
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

    # Assuming template exists at templates/agency_staff_portal/candidates/view_applicants.html
    return render_template('agency_staff_portal/candidates/view_applicants.html',
                           title=f"Applicants for: {offer_details['Title']}",
                           offer=offer_details,
                           applicants=applicants)