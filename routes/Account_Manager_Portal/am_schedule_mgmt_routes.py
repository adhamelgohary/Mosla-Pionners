# routes/Account_Manager_Portal/am_schedule_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from utils.decorators import login_required_with_role
from db import get_db_connection

AM_SCHEDULE_MANAGEMENT_ROLES = ['HeadAccountManager', 'CEO', 'Admin', 'AccountManager']

am_schedule_mgmt_bp = Blueprint('am_schedule_mgmt_bp', __name__,
                                template_folder='../../../templates',
                                url_prefix='/am-portal/company-schedules')

@am_schedule_mgmt_bp.route('/manage/<int:company_id>', methods=['GET', 'POST'])
@login_required_with_role(AM_SCHEDULE_MANAGEMENT_ROLES)
def manage_company_schedule(company_id):
    """
    Manages interview availability (days and times) for a specific company.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Fetch company details
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE CompanyID = %s", (company_id,))
        company = cursor.fetchone()
        if not company:
            flash("Company not found.", "danger")
            return redirect(url_for('am_offer_mgmt_bp.list_companies_for_offers'))

        if request.method == 'POST':
            if request.form.get('action') == 'delete':
                schedule_id = request.form.get('schedule_id')
                cursor.execute("DELETE FROM CompanyInterviewSchedules WHERE ScheduleID = %s AND CompanyID = %s", (schedule_id, company_id))
                conn.commit()
                flash("Schedule slot deleted successfully.", "success")
            else:
                day_of_week = request.form.get('day_of_week')
                start_time = request.form.get('start_time')
                end_time = request.form.get('end_time')
                
                # Basic validation
                if not all([day_of_week, start_time, end_time]) or start_time >= end_time:
                    flash("Invalid schedule details provided.", "danger")
                else:
                    cursor.execute("""
                        INSERT INTO CompanyInterviewSchedules (CompanyID, DayOfWeek, StartTime, EndTime)
                        VALUES (%s, %s, %s, %s)
                    """, (company_id, day_of_week, start_time, end_time))
                    conn.commit()
                    flash("New interview schedule slot added successfully.", "success")
            
            return redirect(url_for('.manage_company_schedule', company_id=company_id))

        # GET request: fetch existing schedules
        cursor.execute("SELECT * FROM CompanyInterviewSchedules WHERE CompanyID = %s ORDER BY FIELD(DayOfWeek, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), StartTime", (company_id,))
        schedules = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error managing schedule for company {company_id}: {e}", exc_info=True)
        flash("An unexpected server error occurred.", "danger")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('account_manager_portal/schedules/manage_company_schedule.html',
                           title=f"Interview Schedule for {company['CompanyName']}",
                           company=company,
                           schedules=schedules)