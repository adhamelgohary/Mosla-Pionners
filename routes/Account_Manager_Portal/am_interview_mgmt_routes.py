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

# --- Helper functions ---

def format_timedelta_for_display(td):
    """Helper function to format a timedelta object into a 12-hour time string (e.g., '02:30 PM')."""
    if not isinstance(td, datetime.timedelta):
        return ""
    # Create a dummy datetime object at the beginning of a day, then add the timedelta
    dummy_dt = datetime.datetime.min + td
    return dummy_dt.strftime("%I:%M %p")

def check_auth_and_get_company(company_id, staff_id):
    """A helper to authorize the user and fetch company details."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT CompanyID, CompanyName, ManagedByStaffID FROM Companies WHERE CompanyID = %s", (company_id,))
    company = cursor.fetchone()
    
    if not company:
        flash("Company not found.", "danger")
        return None, None, None

    is_owner = company.get('ManagedByStaffID') == staff_id
    is_senior_manager = current_user.role_type in ['HeadAccountManager', 'CEO', 'OperationsManager', 'Founder', 'Admin']
    
    if not (is_owner or is_senior_manager):
        flash("You are not authorized to manage this company's schedule.", "danger")
        return None, None, None
    
    return conn, cursor, company

# --- View Route (GET) ---
@am_interview_mgmt_bp.route('/manage/<int:company_id>', methods=['GET'])
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def view_schedules(company_id):
    """Displays the list of schedules and the form to add a new one."""
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)

    conn, cursor, company = check_auth_and_get_company(company_id, staff_id)
    if not conn:
        return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))

    schedules = []
    try:
        cursor.execute("""
            SELECT ScheduleID, DayOfWeek, StartTime, EndTime FROM CompanyInterviewSchedules 
            WHERE CompanyID = %s AND IsActive = 1
            ORDER BY FIELD(DayOfWeek, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), StartTime
            """, (company_id,)
        )
        schedules_raw = cursor.fetchall()
        
        # Pre-format the time strings before sending to the template
        for sched in schedules_raw:
            sched['start_time_formatted'] = format_timedelta_for_display(sched.get('StartTime'))
            sched['end_time_formatted'] = format_timedelta_for_display(sched.get('EndTime'))
            schedules.append(sched)

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('account_manager_portal/manage_company_schedule.html',
                           title=f"Interview Availability for {company['CompanyName']}",
                           company=company,
                           schedules=schedules)


# --- ADD Route (POST) ---
@am_interview_mgmt_bp.route('/add/<int:company_id>', methods=['POST'])
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def add_schedule(company_id):
    """Handles the form submission for adding a new schedule slot."""
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)

    conn, _, company = check_auth_and_get_company(company_id, staff_id)
    if not conn:
        return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))
    
    try:
        cursor = conn.cursor()
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
            conn.commit()
            flash("New interview availability added successfully.", "success")
    except Exception as e:
        if conn: conn.rollback()
        flash("An error occurred while adding the slot.", "danger")
        current_app.logger.error(f"Error adding schedule for CompanyID {company_id}: {e}", exc_info=True)
    finally:
        if conn: conn.close()
    
    return redirect(url_for('.view_schedules', company_id=company_id))

# --- EDIT Route (GET and POST) ---
@am_interview_mgmt_bp.route('/edit/<int:schedule_id>', methods=['GET', 'POST'])
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def edit_schedule(schedule_id):
    """Handles both displaying the edit form and processing the update."""
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Fetch the slot and its company to verify ownership
        cursor.execute("SELECT s.*, c.CompanyName, c.ManagedByStaffID FROM CompanyInterviewSchedules s JOIN Companies c ON s.CompanyID = c.CompanyID WHERE s.ScheduleID = %s", (schedule_id,))
        slot_to_edit = cursor.fetchone()

        if not slot_to_edit:
            flash("Schedule slot not found.", "warning")
            return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))
        
        # Authorization check
        is_owner = slot_to_edit.get('ManagedByStaffID') == staff_id
        is_senior_manager = current_user.role_type in ['HeadAccountManager', 'CEO', 'OperationsManager', 'Founder', 'Admin']
        if not (is_owner or is_senior_manager):
            flash("You are not authorized to edit this schedule.", "danger")
            return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))

        company_id = slot_to_edit['CompanyID']
        company = {'CompanyID': company_id, 'CompanyName': slot_to_edit['CompanyName']}

        if request.method == 'POST':
            day_of_week = request.form.get('day_of_week')
            start_time = request.form.get('start_time')
            end_time = request.form.get('end_time')

            if not all([day_of_week, start_time, end_time]) or start_time >= end_time:
                flash("Invalid schedule details provided.", "danger")
            else:
                cursor.execute("UPDATE CompanyInterviewSchedules SET DayOfWeek = %s, StartTime = %s, EndTime = %s WHERE ScheduleID = %s", (day_of_week, start_time, end_time, schedule_id))
                conn.commit()
                flash("Schedule slot updated successfully.", "success")
            return redirect(url_for('.view_schedules', company_id=company_id))

        # For GET request, render the main page but in "edit mode"
        cursor.execute("SELECT ScheduleID, DayOfWeek, StartTime, EndTime FROM CompanyInterviewSchedules WHERE CompanyID = %s AND IsActive = 1 ORDER BY FIELD(DayOfWeek, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), StartTime", (company_id,))
        schedules_raw = cursor.fetchall()
        schedules = []
        for sched in schedules_raw:
            sched['start_time_formatted'] = (datetime.datetime.min + sched['StartTime']).strftime('%I:%M %p')
            sched['end_time_formatted'] = (datetime.datetime.min + sched['EndTime']).strftime('%I:%M %p')
            schedules.append(sched)

        return render_template('account_manager_portal/manage_company_schedule.html',
                           title=f"Interview Availability for {company['CompanyName']}",
                           company=company,
                           schedules=schedules,
                           slot_to_edit=slot_to_edit) # Pass the specific slot to the template
    except Exception as e:
        if conn: conn.rollback()
        flash("An error occurred.", "danger")
        current_app.logger.error(f"Error editing schedule {schedule_id}: {e}", exc_info=True)
        return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))
    finally:
        if conn: conn.close()

# --- DELETE Route (POST) ---
@am_interview_mgmt_bp.route('/delete/<int:schedule_id>', methods=['POST'])
@login_required_with_role(AM_PORTAL_ACCESS_ROLES)
def delete_schedule(schedule_id):
    """Handles the deletion of a single schedule slot."""
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id: abort(403)
    
    company_id = request.form.get('company_id', type=int)
    if not company_id:
        flash("Missing company context for deletion.", "danger")
        return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))

    conn, _, _ = check_auth_and_get_company(company_id, staff_id)
    if not conn:
        return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))
        
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM CompanyInterviewSchedules WHERE ScheduleID = %s AND CompanyID = %s", (schedule_id, company_id))
        conn.commit()
        flash("Schedule slot deleted successfully.", "success")
    except Exception as e:
        if conn: conn.rollback()
        flash("An error occurred while deleting the slot.", "danger")
        current_app.logger.error(f"Error deleting schedule {schedule_id}: {e}", exc_info=True)
    finally:
        if conn: conn.close()

    return redirect(url_for('.view_schedules', company_id=company_id))