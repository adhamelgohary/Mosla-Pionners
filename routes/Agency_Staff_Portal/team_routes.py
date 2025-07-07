# routes/Agency_Staff_Portal/team_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user, login_required
from utils.decorators import login_required_with_role, LEADER_ROLES, EXECUTIVE_ROLES
from db import get_db_connection
import mysql.connector

# This blueprint is now for HIGH-LEVEL leadership views that span multiple departments.
# Recruiter-specific team views have been moved to recruiter_routes.py.
team_bp = Blueprint('team_bp', __name__,
                    template_folder='../../../templates',
                    url_prefix='/staff-management/team-overview')

@team_bp.route('/')
@login_required_with_role(EXECUTIVE_ROLES) # Only executives can see this overview now
def global_team_overview():
    """
    Displays a high-level overview of all teams and departments.
    This is a placeholder for a future executive dashboard.
    For now, it will list all staff with their leaders.
    """
    conn, staff_list = None, []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # This query is similar to the one in employee_mgmt_routes, but can be adapted for a team-centric view
        sql = """
            SELECT 
                s.StaffID, u.FirstName, u.LastName, s.Role,
                leader_user.FirstName AS LeaderFirstName, leader_user.LastName AS LeaderLastName
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            LEFT JOIN Staff leader_s ON s.ReportsToStaffID = leader_s.StaffID
            LEFT JOIN Users leader_user ON leader_s.UserID = leader_user.UserID
            ORDER BY LeaderFirstName, u.LastName
        """
        cursor.execute(sql)
        staff_list = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching global team overview: {e}", exc_info=True)
        flash("Could not load the global team overview.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals(): cursor.close()
            conn.close()
    
    return render_template('agency_staff_portal/staff/global_team_overview.html',
                           title="Global Team Overview",
                           staff_list=staff_list)