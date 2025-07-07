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
            
# ADD THIS NEW ROUTE AT THE END OF THE FILE
@team_bp.route('/my-sourced-candidates')
@login_required_with_role(SOURCING_ROLES)
def my_sourced_candidates():
    """
    Displays a list of candidates sourced by the logged-in recruiter,
    along with the jobs they have applied for.
    """
    staff_id = getattr(current_user, 'specific_role_id', None)
    if not staff_id:
        flash("Your staff profile ID could not be found.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))

    conn = None
    sourced_candidates = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # This query finds all candidates sourced by the current staff member
        # and then joins with applications and job offers to see where they applied.
        sql = """
            SELECT 
                c.CandidateID,
                u.FirstName,
                u.LastName,
                u.Email,
                c.SourceDate,
                GROUP_CONCAT(
                    DISTINCT jo.Title 
                    ORDER BY ja.ApplicationDate DESC 
                    SEPARATOR '||'
                ) AS AppliedJobs,
                GROUP_CONCAT(
                    DISTINCT ja.Status 
                    ORDER BY ja.ApplicationDate DESC 
                    SEPARATOR '||'
                ) AS ApplicationStatuses
            FROM Candidates c
            JOIN Users u ON c.UserID = u.UserID
            LEFT JOIN JobApplications ja ON c.CandidateID = ja.CandidateID
            LEFT JOIN JobOffers jo ON ja.OfferID = jo.OfferID
            WHERE c.SourcedByStaffID = %s
            GROUP BY c.CandidateID, u.FirstName, u.LastName, u.Email, c.SourceDate
            ORDER BY c.SourceDate DESC, u.LastName ASC;
        """
        cursor.execute(sql, (staff_id,))
        results = cursor.fetchall()
        
        # Process the results to be more template-friendly
        for row in results:
            applications = []
            if row['AppliedJobs']:
                jobs = row['AppliedJobs'].split('||')
                statuses = row['ApplicationStatuses'].split('||')
                applications = list(zip(jobs, statuses))
            row['applications_list'] = applications
            sourced_candidates.append(row)

    except Exception as e:
        current_app.logger.error(f"Error fetching sourced candidates for StaffID {staff_id}: {e}", exc_info=True)
        flash("An error occurred while loading your sourced candidates.", "danger")
        return redirect(url_for('staff_dashboard_bp.main_dashboard'))
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals():
                cursor.close()
            conn.close()

    return render_template('agency_staff_portal/staff/my_sourced_candidates.html',
                           title="My Sourced Candidates",
                           candidates=sourced_candidates)