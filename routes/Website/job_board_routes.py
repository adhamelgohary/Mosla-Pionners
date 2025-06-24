# routes/Website/job_board_routes.py
from flask import Blueprint, render_template, request, current_app, flash, url_for, redirect
from db import get_db_connection
import datetime

job_board_bp = Blueprint('job_board_bp', __name__,
                         url_prefix='/job-board') # All routes here will be under /job-board

@job_board_bp.route('/') # Accessible at /job-board/ or /job-board/jobs
@job_board_bp.route('/jobs')
def job_offers_list():
    conn = None
    job_offers_list = []
    job_categories_for_filter = []
    
    search_term = request.args.get('q', '').strip()
    selected_category_id = request.args.get('category', type=int)
    selected_location = request.args.get('location', '').strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
            SELECT 
                jo.OfferID, jo.Title, jo.Description, jo.Location, jo.WorkLocationType, 
                jo.JobType, jo.NetSalary, jo.Currency, jo.DatePosted, jo.EnglishLevelRequirement,
                c.CompanyName, c.CompanyLogoURL,
                jc.CategoryName
            FROM JobOffers jo
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID
            WHERE jo.Status = 'Open' AND (jo.ClosingDate IS NULL OR jo.ClosingDate >= CURDATE())
        """
        params = []
        conditions = []

        if search_term:
            conditions.append("(jo.Title LIKE %s OR c.CompanyName LIKE %s OR jo.Description LIKE %s OR jc.CategoryName LIKE %s OR jo.Location LIKE %s)")
            search_like = f"%{search_term}%"
            params.extend([search_like, search_like, search_like, search_like, search_like])
        if selected_category_id:
            conditions.append("jo.CategoryID = %s")
            params.append(selected_category_id)
        if selected_location:
            conditions.append("jo.Location LIKE %s")
            params.append(f"%{selected_location}%")

        if conditions:
            sql += " AND " + " AND ".join(conditions)
        sql += " ORDER BY jo.IsFeatured DESC, jo.DatePosted DESC"
        
        cursor.execute(sql, tuple(params))
        job_offers_list = cursor.fetchall()

        cursor.execute("SELECT CategoryID, CategoryName FROM JobCategories ORDER BY CategoryName")
        job_categories_for_filter = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error fetching job offers list: {e}", exc_info=True)
        flash("Could not load job openings. Please try again.", "warning")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

    return render_template('Website/job_offers/offers_list.html', 
                           title="Current Job Openings", 
                           job_offers_list=job_offers_list,
                           job_categories=job_categories_for_filter,
                           search_term=search_term,
                           selected_category_id=selected_category_id,
                           selected_location=selected_location)

@job_board_bp.route('/offer/<int:offer_id>')
@job_board_bp.route('/offer/<int:offer_id>/<job_title_slug>')
def job_detail(offer_id, job_title_slug=None):
    conn, offer = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT jo.*, c.CompanyName, c.CompanyLogoURL, c.CompanyWebsite, 
                   c.Description as CompanyDescription, jc.CategoryName
            FROM JobOffers jo
            JOIN Companies c ON jo.CompanyID = c.CompanyID
            JOIN JobCategories jc ON jo.CategoryID = jc.CategoryID
            WHERE jo.OfferID = %s AND jo.Status = 'Open' 
                  AND (jo.ClosingDate IS NULL OR jo.ClosingDate >= CURDATE())
        """, (offer_id,))
        offer = cursor.fetchone()
        if offer:
            offer['Benefits_list'] = offer.get('Benefits', '').split(',') if offer.get('Benefits') else []
        else:
            flash("Job offer not found or is no longer available.", "warning")
            return redirect(url_for('.job_offers_list'))
    except Exception as e:
        current_app.logger.error(f"Error fetching job detail for OfferID {offer_id}: {e}", exc_info=True)
        flash("Could not load job details.", "danger")
        return redirect(url_for('.job_offers_list'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return render_template('Website/job_offers/job_detail.html', 
                           title=offer.get('Title', "Job Details"), offer=offer)

@job_board_bp.route('/offer/<int:offer_id>/apply', methods=['POST'])
def submit_job_application(offer_id):
    # Simplified: Collects data and logs. Actual file saving/DB ops are TBD.
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    phone_number = request.form.get('phone_number')
    cv_file_storage = request.files.get('cv_file')
    voice_note_file_storage = request.files.get('voice_note_file')
    voice_note_recorded_flag = request.form.get('voice_note_blob_data_exists') == 'true'

    if not all([full_name, email, phone_number]):
        flash("Please fill in Name, Email, and Phone Number.", "warning")
        return redirect(url_for('.job_detail', offer_id=offer_id))
    if not (cv_file_storage and cv_file_storage.filename):
        flash("A CV is required.", "warning")
        return redirect(url_for('.job_detail', offer_id=offer_id))
    if not ((voice_note_file_storage and voice_note_file_storage.filename) or voice_note_recorded_flag):
        flash("A voice introduction is required.", "warning")
        return redirect(url_for('.job_detail', offer_id=offer_id))

    current_app.logger.info(f"SIMULATED Job application for OfferID {offer_id} from {email}")
    flash("Your application has been received! (Simulation - No files saved, no DB records created yet)", "success")
    return redirect(url_for('.job_offers_list'))