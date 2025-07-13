# routes/Account_Manager_Portal/am_interview_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection

AM_PORTAL_ACCESS_ROLES = ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 'CEO', 'Founder', 'OperationsManager']

am_interview_mgmt_bp = Blueprint('am_interview_mgmt_bp', __name__,
                                 template_folder='../../../templates',
                                 url_prefix='/am-portal/company-schedules')

@am_interview_mgmt_bp.route('/manage/<int:company_id>', methods=['GET', 'POST'])
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def manage_company_schedule(company_id):
    """
    Manages general interview availability (days and times) for a specific company.
    """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Verify user is authorized for this company
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE CompanyID = %s AND ManagedByStaffID = %s", (company_id, staff_id))
        company = cursor.fetchone()
        if not company:
            flash("Company not found or you are not authorized to manage it.", "danger")
            return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))

        if request.method == 'POST':
            conn.start_transaction()
            if request.form.get('action') == 'delete':
                schedule_id = request.form.get('schedule_id')
                cursor.execute("DELETE FROM CompanyInterviewSchedules WHERE ScheduleID = %s AND CompanyID = %s", (schedule_id, company_id))
                flash("Schedule slot deleted successfully.", "success")
            else:
                day_of_week = request.form.get('day_of_week')
                start_time = request.form.get('start_time')
                end_time = request.form.get('end_time')
                
                if not all([day_of_week, start_time, end_time]) or start_time >= end_time:
                    flash("Invalid schedule details provided. End time must be after start time.", "danger")
                else:
                    cursor.execute("""
                        INSERT INTO CompanyInterviewSchedules (CompanyID, DayOfWeek, StartTime, EndTime)
                        VALUES (%s, %s, %s, %s)
                    """, (company_id, day_of_week, start_time, end_time))
                    flash("New interview availability added successfully.", "success")
            
            conn.commit()
            return redirect(url_for('.manage_company_schedule', company_id=company_id))

        # GET request: fetch existing schedules
        cursor.execute("""
            SELECT ScheduleID, DayOfWeek, StartTime, EndTime FROM CompanyInterviewSchedules 
            WHERE CompanyID = %s 
            ORDER BY FIELD(DayOfWeek, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), StartTime
            """, (company_id,)
        )
        schedules = cursor.fetchall()
        
    except Exception as e:
        if 'conn' in locals() and conn.is_connected() and conn.in_transaction: conn.rollback()
        current_app.logger.error(f"Error managing schedule for company {company_id}: {e}", exc_info=True)
        flash("An unexpected server error occurred.", "danger")
    finally:
        if 'conn' in locals() and conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('account_manager_portal/manage_company_schedule.html',
                           title=f"Interview Availability for {company['CompanyName']}",
                           company=company,
                           schedules=schedules)