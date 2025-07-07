# routes/Agency_Staff_Portal/team_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user, login_required
from utils.decorators import login_required_with_role, LEADER_ROLES, EXECUTIVE_ROLES
from db import get_db_connection
import mysql.connector

# At the top of team_routes.py, add this new role list
SOURCING_ROLES = ['SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 'CEO', 'OperationsManager']


team_bp = Blueprint('team_bp', __name__,
                    template_folder='../../../templates',
                    url_prefix='/staff-management/team') # New, more specific prefix

@team_bp.route('/')
@login_required
def staff_hub():
    """
    Acts as the main hub for team-related views.
    Leaders are directed to their team view, while others are sent to their own profile.
    """
    if current_user.role_type in LEADER_ROLES:
        # Redirect to the main team view within this same blueprint
        return redirect(url_for('.my_team'))
    
    # Non-leaders are redirected to their profile, which is in a different blueprint
    # Note the explicit blueprint name: 'employee_mgmt_bp.view_staff_profile'
    return redirect(url_for('employee_mgmt_bp.view_staff_profile', user_id_viewing=current_user.id))

@team_bp.route('/my-team')
@login_required_with_role(LEADER_ROLES)
def my_team():
    """
    Displays the team members (direct and indirect reports) for a logged-in leader,
    or a global view for executives.
    """
    leader_staff_id = getattr(current_user, 'specific_role_id', None)
    if not leader_staff_id and current_user.role_type not in EXECUTIVE_ROLES:
        flash("Your staff profile ID could not be found to display your team.", "warning")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))

    sort_by = request.args.get('sort', 'monthly')
    conn, team_members = None, []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        order_clause = "ORDER BY NetMonthlyPoints DESC, u.LastName"
        if sort_by == 'total':
            order_clause = "ORDER BY s.TotalPoints DESC, u.LastName"

        base_sql = """
            SELECT u.UserID, u.FirstName, u.LastName, u.ProfilePictureURL,
                   s.StaffID, s.Role, s.TotalPoints, u.IsActive,
                   COALESCE(monthly_points.net_monthly, 0) AS NetMonthlyPoints
            FROM Staff s
            JOIN Users u ON s.UserID = u.UserID
            LEFT JOIN (
                SELECT AwardedToStaffID, SUM(PointsAmount) as net_monthly
                FROM StaffPointsLog
                WHERE AwardDate >= DATE_FORMAT(NOW(), '%Y-%m-01')
                GROUP BY AwardedToStaffID
            ) AS monthly_points ON s.StaffID = monthly_points.AwardedToStaffID
        """
        params = []
        role = current_user.role_type
        page_title = "My Team Performance"
        where_clause = ""

        if role in EXECUTIVE_ROLES:
            page_title = "All Staff Performance"
            # No WHERE clause needed for global view
        else:
            # Use a recursive query to find all subordinates
            where_clause = """
            WITH RECURSIVE Subordinates AS (
                SELECT StaffID FROM Staff WHERE StaffID = %s
                UNION ALL
                SELECT s_child.StaffID FROM Staff s_child
                INNER JOIN Subordinates s_parent ON s_child.ReportsToStaffID = s_parent.StaffID
            )
            WHERE s.StaffID IN (SELECT StaffID FROM Subordinates WHERE StaffID != %s)
            """
            params.extend([leader_staff_id, leader_staff_id])

            if role == 'UnitManager': page_title = "My Unit's Performance"
            elif role == 'HeadSourcingTeamLead': page_title = "My Division's Performance"
            elif role == 'HeadAccountManager': page_title = "My Account Management Group Performance"
            elif role == 'SeniorAccountManager': page_title = "My Account Managers' Performance"

        final_sql = f"{base_sql} {where_clause} {order_clause}"
        cursor.execute(final_sql, tuple(params))
        team_members = cursor.fetchall()

        team_kpis = {
            'member_count': len(team_members),
            'total_points': sum(member.get('TotalPoints', 0) or 0 for member in team_members),
            'monthly_net_points': sum(member.get('NetMonthlyPoints', 0) for member in team_members)
        }
        is_global_view = role in EXECUTIVE_ROLES

        return render_template('agency_staff_portal/staff/my_team.html',
                               title=page_title, team_members=team_members,
                               team_kpis=team_kpis, current_sort=sort_by,
                               is_global_view=is_global_view)
    except Exception as e:
        current_app.logger.error(f"Error fetching team/staff list for user {current_user.id} (Role: {role}): {e}", exc_info=True)
        flash("Could not load team/staff information.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
            
# CORRECTED ROUTE - Replace the old my_sourced_candidates function with this
@team_bp.route('/my-referrals') # Changed URL to be more accurate
@login_required_with_role(SOURCING_ROLES)
def my_referred_applications():
    """
    Displays a list of all job applications that were submitted
    using the logged-in recruiter's referral code.
    """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id:
        flash("Your staff profile ID could not be found.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))

    conn = None
    referred_applications = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # THIS IS THE NEW, CORRECT QUERY
        # It starts from JobApplications and correctly uses ReferringStaffID
        sql = """
            SELECT 
                ja.ApplicationID,
                ja.ApplicationDate,
                ja.Status,
                c.CandidateID,
                u.FirstName,
                u.LastName,
                u.Email,
                jo.Title AS JobTitle,
                comp.CompanyName
            FROM JobApplications ja
            JOIN Candidates c ON ja.CandidateID = c.CandidateID
            JOIN Users u ON c.UserID = u.UserID
            JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            JOIN Companies comp ON jo.CompanyID = comp.CompanyID
            WHERE ja.ReferringStaffID = %s
            ORDER BY ja.ApplicationDate DESC;
        """
        cursor.execute(sql, (staff_id,))
        referred_applications = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching referred applications for StaffID {staff_id}: {e}", exc_info=True)
        flash("An error occurred while loading your referred applications.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals():
                cursor.close()
            conn.close()

    return render_template('agency_staff_portal/staff/my_referred_applications.html',
                           title="My Referred Applications",
                           applications=referred_applications)