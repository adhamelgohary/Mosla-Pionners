# routes/Account_Manager_Portal/am_interview_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import datetime

AM_PORTAL_ACCESS_ROLES = ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 'CEO', 'Founder', 'OperationsManager']

am_interview_mgmt_bp = Blueprint('am_interview_mgmt_bp', __name__,
                                 template_folder='../../../templates',
                                 url_prefix='/am-portal/company-schedules')

@am_interview_mgmt_bp.route('/manage/<int:company_id>', methods=['GET', 'POST'])
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def manage_company_schedule(company_id):
    """
    Manages general interview availability (days and times) for a specific company.
    Supports Adding, Editing, and Deleting schedule slots.
    """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)
    
    conn = get_db_connection()
    slot_to_edit = None
    schedules = []
    company = None

    try:
        cursor = conn.cursor(dictionary=True)
        
        # --- Authorization Check ---
        cursor.execute("SELECT CompanyID, CompanyName, ManagedByStaffID FROM Companies WHERE CompanyID = %s", (company_id,))
        company = cursor.fetchone()
        
        is_owner = company and company.get('ManagedByStaffID') == staff_id
        is_senior_manager = current_user.role_type in ['HeadAccountManager', 'CEO', 'OperationsManager', 'Founder', 'Admin']
        
        if not (is_owner or is_senior_manager):
            flash("Company not found or you are not authorized to manage it.", "danger")
            return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))
        
        if not company:
            flash("Company not found.", "danger")
            return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))

        # --- EDIT WORKFLOW (GET) ---
        edit_id = request.args.get('edit_id', type=int)
        if edit_id:
            cursor.execute("SELECT * FROM CompanyInterviewSchedules WHERE ScheduleID = %s AND CompanyID = %s", (edit_id, company_id))
            slot_to_edit = cursor.fetchone()

        # --- FORM SUBMISSION (POST) ---
        if request.method == 'POST':
            try:
                # --- THE DEFINITIVE FIX ---
                # Before starting a new transaction, check if one is already active from the connection pool.
                # If so, roll it back to clean the state. This is a robust way to prevent the error.
                if conn.in_transaction:
                    current_app.logger.warning(f"Connection for company {company_id} had a lingering transaction. Rolling back.")
                    conn.rollback()
                
                conn.start_transaction()
                # --- END OF FIX ---
                
                action = request.form.get('action')
                
                if action == 'delete':
                    schedule_id = request.form.get('schedule_id')
                    cursor.execute("DELETE FROM CompanyInterviewSchedules WHERE ScheduleID = %s AND CompanyID = %s", (schedule_id, company_id))
                    flash("Schedule slot deleted successfully.", "success")
                else: # Handles 'add' and 'edit'
                    day_of_week = request.form.get('day_of_week')
                    start_time = request.form.get('start_time')
                    end_time = request.form.get('end_time')

                    if not all([day_of_week, start_time, end_time]) or start_time >= end_time:
                        flash("Invalid schedule details provided. End time must be after start time.", "danger")
                    else:
                        if action == 'add':
                            cursor.execute("""
                                INSERT INTO CompanyInterviewSchedules (CompanyID, DayOfWeek, StartTime, EndTime)
                                VALUES (%s, %s, %s, %s)
                            """, (company_id, day_of_week, start_time, end_time))
                            flash("New interview availability added successfully.", "success")
                        elif action == 'edit':
                            schedule_id = request.form.get('schedule_id')
                            cursor.execute("""
                                UPDATE CompanyInterviewSchedules SET DayOfWeek = %s, StartTime = %s, EndTime = %s
                                WHERE ScheduleID = %s AND CompanyID = %s
                            """, (day_of_week, start_time, end_time, schedule_id, company_id))
                            flash("Schedule slot updated successfully.", "success")
                
                conn.commit()
            except Exception as e:
                if conn and conn.in_transaction: 
                    conn.rollback()
                current_app.logger.error(f"Database operation failed for company {company_id}: {e}", exc_info=True)
                flash("An error occurred while processing your request. Please try again.", "danger")
            
            return redirect(url_for('.manage_company_schedule', company_id=company_id))

        # --- DATA FOR LISTING (GET request) ---
        cursor.execute("""
            SELECT ScheduleID, DayOfWeek, StartTime, EndTime FROM CompanyInterviewSchedules 
            WHERE CompanyID = %s 
            ORDER BY FIELD(DayOfWeek, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), StartTime
            """, (company_id,)
        )
        schedules = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error managing schedule for company {company_id}: {e}", exc_info=True)
        flash("An unexpected server error occurred.", "danger")
        return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))
    finally:
        if 'conn' in locals() and conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('account_manager_portal/manage_company_schedule.html',
                           title=f"Interview Availability for {company['CompanyName']}",
                           company=company,
                           schedules=schedules,
                           slot_to_edit=slot_to_edit)