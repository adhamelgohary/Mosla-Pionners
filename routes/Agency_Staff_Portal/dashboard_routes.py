# routes/Agency_Staff_Portal/dashboard_routes.py
from flask import Blueprint, flash, render_template, current_app
from flask_login import current_user
from utils.decorators import agency_staff_required, AGENCY_STAFF_ROLES, EXECUTIVE_ROLES
from db import get_db_connection
import datetime

# Roles for course management link on this dashboard
COURSE_MANAGEMENT_ROLES_FOR_DASH = ['SalesManager', 'CEO', 'OperationsManager']
# For announcement management link on dashboard
from routes.Agency_Staff_Portal.announcement_mgmt_routes import ANNOUNCEMENT_MANAGEMENT_ROLES as AMR_CONFIG

staff_dashboard_bp = Blueprint('staff_dashboard_bp', __name__,
                               template_folder='../../../templates/agency_staff_portal',
                               url_prefix='/dashboard')

@staff_dashboard_bp.route('/')
@agency_staff_required # Ensures only internal staff access this
def main_dashboard():
    current_app.logger.info(f"Staff user {current_user.email} (Role: {current_user.role_type}) accessed main staff dashboard.")
    
    can_manage_courses = current_user.role_type in COURSE_MANAGEMENT_ROLES_FOR_DASH
    is_executive = current_user.role_type in EXECUTIVE_ROLES
    
    dashboard_stats = {}
    manual_announcements = []
    activity_feed_items = []
    conn = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --- General Agency Stats ---
        if is_executive: # CEO/OM can see total candidates in the system
            cursor.execute("SELECT COUNT(*) AS count FROM Candidates")
            res = cursor.fetchone()
            dashboard_stats['total_candidates_system'] = res['count'] if res else 0
        
        cursor.execute("SELECT COUNT(*) AS count FROM Companies")
        res = cursor.fetchone()
        dashboard_stats['total_companies'] = res['count'] if res else 0

        cursor.execute("SELECT COUNT(*) AS count FROM JobOffers WHERE Status = 'Open'")
        res = cursor.fetchone()
        dashboard_stats['open_job_offers'] = res['count'] if res else 0
        
        # Uses Staff table for active staff count
        cursor.execute("""
            SELECT COUNT(DISTINCT s.StaffID) AS count 
            FROM Staff s 
            JOIN Users u ON s.UserID = u.UserID 
            WHERE u.IsActive = 1
        """)
        res = cursor.fetchone()
        dashboard_stats['active_staff_count'] = res['count'] if res else 0

        # --- Role-Specific Stats for current_user ---
        
        # Sourced Candidates (My Performance)
        # This applies if the user is in a role that sources and has a StaffID
        if hasattr(current_user, 'specific_role_id') and current_user.specific_role_id and \
        current_user.role_type in AGENCY_STAFF_ROLES:
            
            # --- NEW, CORRECTED LOGIC ---
            # Change KPI from "Sourced Candidates" to "Referred Applications"
            # This correctly queries the JobApplications table.
            cursor.execute(
                """SELECT COUNT(*) AS count FROM JobApplications 
                WHERE ReferringStaffID = %s AND ApplicationDate >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)""",
                (current_user.specific_role_id,)
            )
            res = cursor.fetchone()
            dashboard_stats['my_referred_applications_month'] = res['count'] if res else 0
        
        # Client related stats (My Performance / My Team's Performance)
        # ManagedByStaffID in Companies table
        if current_user.role_type == 'AccountManager':
            if hasattr(current_user, 'specific_role_id') and current_user.specific_role_id:
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM Companies WHERE ManagedByStaffID = %s",
                    (current_user.specific_role_id,) 
                )
                res = cursor.fetchone()
                dashboard_stats['my_managed_clients'] = res['count'] if res else 0
        
        if current_user.role_type in ['SeniorAccountManager', 'HeadAccountManager']:
             if hasattr(current_user, 'specific_role_id') and current_user.specific_role_id:
                # Recursive query to find all staff under this manager (their AMs)
                # Then count companies managed by those AMs
                cursor.execute("""
                    WITH RECURSIVE SubordinateStaff AS (
                        SELECT StaffID FROM Staff WHERE StaffID = %s -- The manager themselves
                        UNION ALL
                        SELECT s_child.StaffID FROM Staff s_child 
                        INNER JOIN SubordinateStaff s_parent ON s_child.ReportsToStaffID = s_parent.StaffID
                    )
                    SELECT COUNT(c.CompanyID) AS count 
                    FROM Companies c
                    WHERE c.ManagedByStaffID IN (SELECT StaffID FROM SubordinateStaff WHERE StaffID != %s) 
                """, (current_user.specific_role_id, current_user.specific_role_id)) # Exclude companies managed by the Head/Senior AM directly
                res = cursor.fetchone()
                dashboard_stats['team_managed_clients'] = res['count'] if res else 0
        
        # Agency-wide client stats for executives
        if is_executive:
            cursor.execute("SELECT COUNT(*) as count FROM Companies WHERE ManagedByStaffID IS NOT NULL")
            res = cursor.fetchone()
            dashboard_stats['total_agency_managed_clients'] = res['count'] if res else 0
            
        # New clients for the agency in the last month (visible to relevant roles)
        if current_user.role_type in ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 'SalesManager', 'CEO', 'OperationsManager']:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM Companies WHERE CreatedAt >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"
            )
            res = cursor.fetchone()
            dashboard_stats['new_clients_agency_month'] = res['count'] if res else 0
            
        # --- Fetch System Announcements & Activity Feed ---
        audience_conditions = ["sa.Audience = 'AllUsers'"] # Default for everyone
        if current_user.role_type in AGENCY_STAFF_ROLES: 
            audience_conditions.append("sa.Audience = 'AllStaff'")
        
        # More granular audience targeting based on Staff.Role if your ENUM in SystemAnnouncements supports it
        # Example: If SystemAnnouncements.Audience includes 'SourcingTeamLead', 'AccountManager', etc.
        # This requires your `current_user.role_type` to directly match an ENUM value in `SystemAnnouncements.Audience`
        if current_user.role_type: # Check if role_type is not None or empty
             audience_conditions.append(f"sa.Audience = '{current_user.role_type}'")


        audience_query_part = " OR ".join(audience_conditions)
        
        # Parameters are not strictly needed if using f-string safely with pre-validated parts
        # but if current_user.role_type was a parameter, it would be:
        # params_announcements = [datetime.datetime.now(), current_user.role_type]
        # However, the f-string for audience_query_part is usually fine if current_user.role_type is trusted.

        sql_all_announcements = f"""
            SELECT sa.Title, sa.Content, sa.Priority, sa.Source, sa.CreatedAt, 
                   u.FirstName as PosterFirstName, u.LastName as PosterLastName
            FROM SystemAnnouncements sa
            LEFT JOIN Users u ON sa.PostedByUserID = u.UserID
            WHERE sa.IsActive = 1 
              AND (sa.DisplayUntil IS NULL OR sa.DisplayUntil >= NOW())
              AND ({audience_query_part})
            ORDER BY FIELD(sa.Priority, 'Urgent', 'High', 'Normal'), sa.CreatedAt DESC
            LIMIT 10 
        """
        cursor.execute(sql_all_announcements) # No params needed with this f-string construction
        all_fetched_announcements = cursor.fetchall()

        for item in all_fetched_announcements:
            if item['Source'] == 'Manual':
                manual_announcements.append(item)
            else: 
                activity_feed_items.append(item)
        
        manual_announcements = manual_announcements[:5]
        activity_feed_items = activity_feed_items[:5]

    except Exception as e:
        current_app.logger.error(f"Error fetching main dashboard data for user {current_user.email}: {e}", exc_info=True)
        flash("Could not load all dashboard information at this time. Some data may be missing.", "warning")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
                
    return render_template(
        'agency_staff_portal/staff_dashboard.html', 
        title='Agency Staff Dashboard',
        user_role=current_user.role_type,
        can_manage_courses=can_manage_courses,
        dashboard_stats=dashboard_stats,
        manual_announcements=manual_announcements,
        activity_feed_items=activity_feed_items,
        ANNOUNCEMENT_MANAGEMENT_ROLES_FOR_TEMPLATE=AMR_CONFIG,
        is_executive=is_executive # Pass this flag for template logic
    )