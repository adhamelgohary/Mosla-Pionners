# routes/Agency_Staff_Portal/leaderboard_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required
from utils.decorators import login_required_with_role, EXECUTIVE_ROLES # Ensure EXECUTIVE_ROLES are defined
from db import get_db_connection

leaderboard_bp = Blueprint('leaderboard_bp', __name__,
                           template_folder='../../../templates',
                           url_prefix='/leaderboards')

@leaderboard_bp.route('/performance')
@login_required # Accessible by all logged-in users
def performance_leaderboard():
    period = request.args.get('period', 'all_time')
    conn = None
    leaders = []
    title = "All-Time Performance Leaderboard"
    subtitle = "Based on total accumulated points."
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if period == 'monthly':
            title = "Top Performers (This Month)"
            subtitle = "Based on net points change this month."
            # Uses StaffPointsLog and Staff tables
            sql = """
                SELECT u.FirstName, u.LastName, SUM(spl.PointsAmount) as Points 
                FROM StaffPointsLog spl 
                JOIN Staff s ON spl.AwardedToStaffID = s.StaffID 
                JOIN Users u ON s.UserID = u.UserID 
                WHERE spl.AwardDate >= DATE_FORMAT(NOW(), '%Y-%m-01') 
                GROUP BY u.UserID, u.FirstName, u.LastName 
                HAVING SUM(spl.PointsAmount) != 0 
                ORDER BY Points DESC LIMIT 20
            """
        else: # all_time
            # Uses Staff table
            sql = """
                SELECT u.FirstName, u.LastName, s.TotalPoints as Points 
                FROM Staff s 
                JOIN Users u ON s.UserID = u.UserID 
                WHERE s.TotalPoints != 0 
                ORDER BY s.TotalPoints DESC LIMIT 20
            """
        cursor.execute(sql)
        leaders = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error loading performance leaderboard (period: {period}): {e}", exc_info=True)
        flash("Could not load the performance leaderboard.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard')) # Fallback
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    # Template path needs to be correct
    return render_template('agency_staff_portal/staff/leaderboard.html', 
                           title=title, subtitle=subtitle, leaders=leaders, current_period=period)

@leaderboard_bp.route('/companies')
@login_required_with_role(EXECUTIVE_ROLES) # Only executives see this
def company_leaderboard():
    conn = None
    top_companies = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT c.CompanyID, c.CompanyName, c.CompanyLogoURL, COUNT(jo.OfferID) as FilledJobsCount
            FROM Companies c
            JOIN JobOffers jo ON c.CompanyID = jo.CompanyID
            WHERE jo.Status = 'Filled'
            GROUP BY c.CompanyID, c.CompanyName, c.CompanyLogoURL
            ORDER BY FilledJobsCount DESC
            LIMIT 20
        """
        cursor.execute(sql)
        top_companies = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error loading company leaderboard: {e}", exc_info=True)
        flash("Could not load the company leaderboard.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard')) # Fallback
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    # Template path needs to be correct
    return render_template('agency_staff_portal/staff/company_leaderboard.html',
                           title="Top Partner Companies",
                           subtitle="Ranked by number of successfully filled positions.",
                           top_companies=top_companies)