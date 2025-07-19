# routes/Agency_staff_portal/dashboard_routes.py

from flask import Blueprint, flash, render_template, current_app
from flask_login import current_user
# --- UPDATED IMPORT --- Now uses MANAGERIAL_PORTAL_ROLES which excludes SalesManager
from utils.decorators import login_required_with_role, MANAGERIAL_PORTAL_ROLES
from db import get_db_connection
import datetime

managerial_dashboard_bp = Blueprint('managerial_dashboard_bp', __name__,
                                    template_folder='../../../templates/agency_staff_portal',
                                    url_prefix='/managerial')

@managerial_dashboard_bp.route('/')
# --- SECURITY UPDATED --- This decorator now correctly blocks SalesManagers
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def main_dashboard():
    current_app.logger.info(f"Managerial user {current_user.email} accessed main dashboard.")
    
    dashboard_stats = {}
    manual_announcements = []
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS count FROM Candidates")
        dashboard_stats['total_candidates_system'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) AS count FROM Companies")
        dashboard_stats['total_companies'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) AS count FROM JobOffers WHERE Status = 'Open'")
        dashboard_stats['open_job_offers'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(DISTINCT s.StaffID) AS count FROM Staff s JOIN Users u ON s.UserID = u.UserID WHERE u.IsActive = 1")
        dashboard_stats['active_staff_count'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM Companies WHERE CreatedAt >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)")
        dashboard_stats['new_clients_agency_month'] = cursor.fetchone()['count']
        
        cursor.execute("""
                SELECT sa.Title, sa.Content, sa.Priority, sa.CreatedAt, 
                       u.FirstName as PosterFirstName
                FROM SystemAnnouncements sa
                LEFT JOIN Users u ON sa.PostedByUserID = u.UserID
                WHERE sa.IsActive = 1 AND (sa.DisplayUntil IS NULL OR sa.DisplayUntil >= NOW())
                ORDER BY FIELD(sa.Priority, 'Urgent', 'High', 'Normal'), sa.CreatedAt DESC LIMIT 5
            """)
        manual_announcements = cursor.fetchall()
    
    except Exception as e:
        current_app.logger.error(f"Error loading managerial dashboard: {e}", exc_info=True)
        flash("Could not load all dashboard data.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
                
    return render_template(
        'agency_staff_portal/staff_dashboard.html',
        title='Managerial Dashboard',
        dashboard_stats=dashboard_stats,
        manual_announcements=manual_announcements
    )