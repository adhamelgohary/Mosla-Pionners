# routes/Account_Manager_Portal/am_interview_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import datetime

AM_PORTAL_ACCESS_ROLES = ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 'CEO', 'Founder', 'OperationsManager', 'Admin']

am_interview_mgmt_bp = Blueprint('am_interview_mgmt_bp', __name__,
                                 template_folder='../../../templates',
                                 url_prefix='/am-portal/company-schedules')

def format_timedelta(td):
    """Helper function to format a timedelta object into a 12-hour time string (e.g., '02:30 PM')."""
    if not isinstance(td, datetime.timedelta):
        return ""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    # Create a dummy datetime object to use strftime
    dummy_dt = datetime.datetime.min + datetime.timedelta(hours=hours, minutes=minutes)
    return dummy_dt.strftime("%I:%M %p")

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
        
        cursor.execute("SELECT CompanyID, CompanyName, ManagedByStaffID FROM Companies WHERE CompanyID = %s", (company_id,))
        company = cursor.fetchone()
        
        if not company:
            flash("Company not found.", "danger")
            return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))

        is_owner = company.get('ManagedByStaffID') == staff_id
        is_senior_manager = current_user.role_type in ['HeadAccountManager', 'CEO', 'OperationsManager', 'Founder', 'Admin']
        
        if not (is_owner or is_senior_manager):
            flash("You are not authorized to manage this company's schedule.", "danger")
            return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))
        
        edit_id = request.args.get('edit_id', type=int)
        if edit_id:
            cursor.execute("SELECT * FROM CompanyInterviewSchedules WHERE ScheduleID = %s AND CompanyID = %s", (edit_id, company_id))
            slot_to_edit = cursor.fetchone()

        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'delete':
                schedule_id = request.form.get('schedule_id')
                cursor.execute("DELETE FROM CompanyInterviewSchedules WHERE ScheduleID = %s AND CompanyID = %s", (schedule_id, company_id))
                flash("Schedule slot deleted successfully.", "success")
            
            elif action in ['add', 'edit']:
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
            
            return redirect(url_for('.manage_company_schedule', company_id=company_id))

        cursor.execute("""
            SELECT ScheduleID, DayOfWeek, StartTime, EndTime FROM CompanyInterviewSchedules 
            WHERE CompanyID = %s AND IsActive = 1
            ORDER BY FIELD(DayOfWeek, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), StartTime
            """, (company_id,)
        )
        schedules_raw = cursor.fetchall()
        
        # Pre-format the time strings before sending to the template
        schedules = []
        for sched in schedules_raw:
            sched['start_time_formatted'] = format_timedelta(sched.get('StartTime'))
            sched['end_time_formatted'] = format_timedelta(sched.get('EndTime'))
            schedules.append(sched)
        
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