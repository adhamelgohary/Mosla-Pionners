# routes/Recruiter_Team_Portal/dashboard_routes.py
from flask import Blueprint, abort, render_template, flash, redirect, url_for, current_app, request
from flask_login import login_required, current_user
from utils.decorators import login_required_with_role
from db import get_db_connection
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

# --- ROLE CONSTANTS ---
RECRUITER_PORTAL_ROLES = ['SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager', 'HeadUnitManager', 'CEO', 'Founder']
ORG_MANAGEMENT_ROLES = ['HeadUnitManager', 'CEO', 'Founder']

# Define a specific blueprint for these routes
dashboard_bp = Blueprint('dashboard_bp', __name__,
                         url_prefix='/recruiter-portal',
                         template_folder='../../../templates')

@dashboard_bp.route('/')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def dashboard():
    """
    The main dashboard for the Recruiter Portal with advanced, role-aware visualizations and announcements.
    """
    user_staff_id = getattr(current_user, 'specific_role_id', None)
    user_role = getattr(current_user, 'role_type', None)

    if not user_staff_id:
        flash("Your staff profile could not be found.", "danger")
        return redirect(url_for('staff_perf_bp.list_all_staff'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    scoped_staff_ids = []
    dashboard_title = "My Performance"
    
    kpis = {
        'funnel': {'Applied': 0, 'Shortlisted': 0, 'Interview Scheduled': 0, 'Hired': 0},
        'status_breakdown_for_chart': {},
        'total_referrals': 0,
        'monthly_performance': []
    }
    
    announcements = []
    referral_code = None

    try:
        cursor.execute("SELECT ReferralCode FROM Staff WHERE StaffID = %s", (user_staff_id,))
        result = cursor.fetchone()
        if result: referral_code = result.get('ReferralCode')

        cursor.execute("""
            SELECT Title, Content, CreatedAt, Priority
            FROM SystemAnnouncements
            WHERE IsActive = 1 AND (DisplayUntil IS NULL OR DisplayUntil > NOW())
            ORDER BY Priority DESC, CreatedAt DESC LIMIT 5
        """)
        announcements = cursor.fetchall()

        if user_role in ORG_MANAGEMENT_ROLES:
            dashboard_title = "Overall Sourcing Division Performance"
            cursor.execute("""
                SELECT s.StaffID FROM Staff s JOIN Users u ON s.UserID = u.UserID
                WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead', 'UnitManager', 'HeadUnitManager') AND u.IsActive = 1
            """)
            scoped_staff_ids = [row['StaffID'] for row in cursor.fetchall()]

        elif user_role == 'UnitManager':
            dashboard_title = f"{current_user.first_name}'s Unit Performance"
            cursor.execute("""
                SELECT s.StaffID FROM Staff s JOIN SourcingTeams st ON s.TeamID = st.TeamID
                JOIN Users u ON s.UserID = u.UserID
                WHERE st.UnitID = (SELECT su.UnitID FROM SourcingUnits su WHERE su.UnitManagerStaffID = %s) AND u.IsActive = 1
            """, (user_staff_id,))
            scoped_staff_ids = [row['StaffID'] for row in cursor.fetchall()]

        elif user_role == 'SourcingTeamLead':
            dashboard_title = f"{current_user.first_name}'s Team Performance"
            cursor.execute("""
                SELECT s.StaffID FROM Staff s JOIN Users u ON s.UserID = u.UserID
                WHERE s.TeamID = (SELECT TeamID FROM Staff WHERE StaffID = %s) AND u.IsActive = 1
            """, (user_staff_id,))
            scoped_staff_ids = [row['StaffID'] for row in cursor.fetchall()]

        if not scoped_staff_ids and current_user.is_active:
            scoped_staff_ids.append(user_staff_id)

        if scoped_staff_ids:
            placeholders = ', '.join(['%s'] * len(scoped_staff_ids))

            funnel_sql = f"SELECT Status, COUNT(ApplicationID) as count FROM JobApplications WHERE ReferringStaffID IN ({placeholders}) GROUP BY Status"
            cursor.execute(funnel_sql, tuple(scoped_staff_ids))
            funnel_data = {row['Status']: row['count'] for row in cursor.fetchall()}

            kpis['funnel'] = {
                'Applied': funnel_data.get('Applied', 0) + funnel_data.get('Submitted', 0),
                'Shortlisted': funnel_data.get('Shortlisted', 0),
                'Interview Scheduled': funnel_data.get('Interview Scheduled', 0),
                'Hired': funnel_data.get('Hired', 0)
            }
            kpis['status_breakdown_for_chart'] = funnel_data
            kpis['total_referrals'] = sum(funnel_data.values())

            monthly_sql = f"""
                SELECT DATE_FORMAT(ApplicationDate, '%%Y-%%m') AS month,
                    COUNT(ApplicationID) as total_referrals,
                    SUM(CASE WHEN Status = 'Hired' THEN 1 ELSE 0 END) as total_hires
                FROM JobApplications
                WHERE ReferringStaffID IN ({placeholders}) AND ApplicationDate >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
                GROUP BY month ORDER BY month ASC
            """
            cursor.execute(monthly_sql, tuple(scoped_staff_ids))
            kpis['monthly_performance'] = cursor.fetchall()
        
    except Exception as e:
        current_app.logger.error(f"Error fetching recruiter dashboard for StaffID {user_staff_id}: {e}", exc_info=True)
        flash("Could not load all dashboard data.", "warning")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    
    return render_template('recruiter_team_portal/recruiter_dashboard.html', title=dashboard_title, kpis=kpis, announcements=announcements, referral_code=referral_code)


@dashboard_bp.route('/my-profile', methods=['GET', 'POST'])
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def my_profile():
    user_id = current_user.id
    staff_id = current_user.specific_role_id
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_details':
            first_name, last_name, email, phone_number = request.form.get('first_name'), request.form.get('last_name'), request.form.get('email'), request.form.get('phone_number')
            cursor.execute("UPDATE Users SET FirstName = %s, LastName = %s, Email = %s, PhoneNumber = %s WHERE UserID = %s", (first_name, last_name, email, phone_number, user_id))
            conn.commit()
            current_user.first_name, current_user.last_name = first_name, last_name
            flash("Your profile details have been updated successfully.", "success")
        
        elif action == 'change_password':
            current_password, new_password, confirm_password = request.form.get('current_password'), request.form.get('new_password'), request.form.get('confirm_password')
            if not check_password_hash(current_user.password_hash, current_password):
                flash("Your current password was incorrect.", "danger")
            elif new_password != confirm_password:
                flash("The new passwords do not match.", "danger")
            else:
                hashed_password = generate_password_hash(new_password)
                cursor.execute("UPDATE Users SET PasswordHash = %s WHERE UserID = %s", (hashed_password, user_id))
                conn.commit()
                flash("Your password has been changed successfully.", "success")
        
        elif action == 'generate_code':
            cursor.execute("SELECT ReferralCode FROM Staff WHERE StaffID = %s", (staff_id,))
            existing_code = cursor.fetchone()
            if not existing_code or not existing_code['ReferralCode']:
                new_code = secrets.token_hex(4).upper()
                cursor.execute("UPDATE Staff SET ReferralCode = %s WHERE StaffID = %s", (new_code, staff_id))
                conn.commit()
                flash(f"Your new referral code has been generated: {new_code}", "success")
            else:
                flash("A referral code already exists for your account.", "info")

        cursor.close()
        conn.close()
        return redirect(url_for('dashboard_bp.my_profile'))

    try:
        cursor.execute("SELECT u.UserID, u.FirstName, u.LastName, u.Email, u.PhoneNumber, s.Role, s.ReferralCode FROM Users u LEFT JOIN Staff s ON u.UserID = s.UserID WHERE u.UserID = %s", (user_id,))
        user_data = cursor.fetchone()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    if not user_data:
        abort(404, "User profile not found.")

    return render_template('recruiter_team_portal/my_profile.html', title="My Profile", user_data=user_data)


@dashboard_bp.route('/leaderboard')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def team_leaderboard():
    sort_by = request.args.get('sort_by', 'referrals_all_time')
    sql = """
        SELECT s.StaffID, u.FirstName, u.LastName, u.ProfilePictureURL, s.Role,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID) as referrals_all_time,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND Status = 'Hired') as hires_all_time,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND ApplicationDate >= DATE_FORMAT(NOW(), '%%Y-%%m-01')) as referrals_monthly,
            (SELECT COUNT(*) FROM JobApplications WHERE ReferringStaffID = s.StaffID AND Status = 'Hired' AND ApplicationDate >= DATE_FORMAT(NOW(), '%%Y-%%m-01')) as hires_monthly
        FROM Staff s JOIN Users u ON s.UserID = u.UserID
        WHERE s.Role IN ('SourcingRecruiter', 'SourcingTeamLead', 'HeadSourcingTeamLead', 'UnitManager') AND u.IsActive = 1
    """
    if sort_by == 'hires_all_time':
        sql += " ORDER BY hires_all_time DESC, referrals_all_time DESC"; title = "Leaderboard: All-Time Hires"
    elif sort_by == 'referrals_monthly':
        sql += " ORDER BY referrals_monthly DESC, hires_monthly DESC"; title = "Leaderboard: Referrals This Month"
    elif sort_by == 'hires_monthly':
        sql += " ORDER BY hires_monthly DESC, referrals_monthly DESC"; title = "Leaderboard: Hires This Month"
    else:
        sort_by = 'referrals_all_time'; sql += " ORDER BY referrals_all_time DESC, hires_all_time DESC"; title = "Leaderboard: All-Time Referrals"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql)
    leaderboard_data = cursor.fetchall()
    conn.close()
    return render_template('recruiter_team_portal/team_leaderboard.html', title=title, leaderboard_data=leaderboard_data, current_sort=sort_by)


@dashboard_bp.route('/announcements')
@login_required_with_role(RECRUITER_PORTAL_ROLES)
def announcements_history():
    search_query, filter_priority = request.args.get('search', '').strip(), request.args.get('priority', '')
    conn, all_announcements = get_db_connection(), []
    try:
        cursor = conn.cursor(dictionary=True)
        sql, params = "SELECT Title, Content, CreatedAt, Priority, Audience FROM SystemAnnouncements WHERE IsActive = 1", []
        if search_query:
            sql += " AND (Title LIKE %s OR Content LIKE %s)"; params.extend([f"%{search_query}%", f"%{search_query}%"])
        if filter_priority:
            sql += " AND Priority = %s"; params.append(filter_priority)
        sql += " ORDER BY CreatedAt DESC"
        cursor.execute(sql, tuple(params))
        all_announcements = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching announcements history: {e}", exc_info=True)
        flash("Could not load the announcements history.", "danger")
    finally:
        if conn.is_connected(): conn.close()
    return render_template('recruiter_team_portal/announcements_history.html', title="Announcements History", announcements=all_announcements, search_query=search_query, filter_priority=filter_priority)