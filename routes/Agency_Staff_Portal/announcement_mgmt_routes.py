# routes/Agency_Staff_Portal/announcement_mgmt_routes.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user
from utils.decorators import login_required_with_role 
from db import get_db_connection
import datetime
import mysql.connector

# Ensure these roles match your Staff.Role ENUM values
ANNOUNCEMENT_MANAGEMENT_ROLES = ['Admin', 'CEO', 'Founder']

announcement_bp = Blueprint('announcement_bp', __name__,
                            # --- CORRECTED URL PREFIX ---
                            url_prefix='/staff-portal/announcements')

def validate_announcement_data(form_data):
    errors = {}
    title = form_data.get('title', '').strip()
    content = form_data.get('content', '').strip()
    audience = form_data.get('audience')
    priority = form_data.get('priority')
    display_until_str = form_data.get('display_until')

    if not title: errors['title'] = 'Title is required.'
    elif len(title) > 255: errors['title'] = 'Title is too long.'
    if not content: errors['content'] = 'Content is required.'
    if display_until_str:
        try: datetime.datetime.strptime(display_until_str, '%Y-%m-%dT%H:%M')
        except ValueError: errors['display_until'] = 'Invalid date/time format.'
    # Ensure valid_audiences match your SystemAnnouncements.Audience ENUM
    valid_audiences = ['AllStaff', 'Recruiters', 'AccountManagers', 'Sales', 'AllUsers']
    if audience not in valid_audiences: errors['audience'] = 'Invalid audience.'
    valid_priorities = ['Normal', 'High', 'Urgent']
    if priority not in valid_priorities: errors['priority'] = 'Invalid priority.'
    return errors

@announcement_bp.route('/')
# --- CORRECTED REDIRECT ---
@login_required_with_role(ANNOUNCEMENT_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')
def list_announcements():
    announcements = []
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT sa.*, u.FirstName as PosterFirstName, u.LastName as PosterLastName FROM SystemAnnouncements sa LEFT JOIN Users u ON sa.PostedByUserID = u.UserID"
        conditions = []
        if not show_all:
            conditions.append("sa.IsActive = 1 AND (sa.DisplayUntil IS NULL OR sa.DisplayUntil >= NOW())")
        if conditions: query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY FIELD(sa.Priority, 'Urgent', 'High', 'Normal'), sa.CreatedAt DESC"
        cursor.execute(query)
        announcements = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error loading announcements list: {e}", exc_info=True)
        flash("Could not load announcements.", "danger")
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return render_template('agency_staff_portal/announcements/list_announcements.html', 
                           title='Manage Announcements', announcements=announcements, show_all=show_all)

@announcement_bp.route('/add', methods=['GET', 'POST'])
# --- CORRECTED REDIRECT ---
@login_required_with_role(ANNOUNCEMENT_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')
def add_announcement():
    form_data = {'audience': 'AllStaff', 'priority': 'Normal', 'is_active': True}
    errors = {}
    if request.method == 'POST':
        form_data = request.form.to_dict()
        form_data['is_active'] = request.form.get('is_active') == 'on'
        errors = validate_announcement_data(form_data)
        if not errors:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                sql = "INSERT INTO SystemAnnouncements (Title, Content, PostedByUserID, IsActive, DisplayUntil, Audience, Priority) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                display_until = datetime.datetime.strptime(form_data['display_until'], '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S') if form_data.get('display_until') else None
                val = (form_data['title'], form_data['content'], current_user.id, form_data['is_active'], display_until, form_data['audience'], form_data['priority'])
                cursor.execute(sql, val)
                conn.commit()
                flash('Announcement added!', 'success')
                return redirect(url_for('.list_announcements'))
            except Exception as e:
                if conn: conn.rollback()
                current_app.logger.error(f"Error adding announcement: {e}", exc_info=True)
                flash(f'An unexpected error occurred. Please check the logs.', 'danger')
                errors['form'] = str(e)
            finally:
                if conn and conn.is_connected(): 
                    if 'cursor' in locals() and cursor: cursor.close()
                    conn.close()
        else:
            flash('Please correct the errors below.', 'warning')
    return render_template('agency_staff_portal/announcements/add_edit_announcement.html', title='Add Announcement', form_data=form_data, errors=errors, action_verb='Add')

@announcement_bp.route('/edit/<int:announcement_id>', methods=['GET', 'POST'])
# --- CORRECTED REDIRECT ---
@login_required_with_role(ANNOUNCEMENT_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')
def edit_announcement(announcement_id):
    form_data, errors = {}, {}
    original_title_hidden = "Announcement"
    conn = get_db_connection()

    try:
        if request.method == 'GET':
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM SystemAnnouncements WHERE AnnouncementID = %s", (announcement_id,))
            data = cursor.fetchone()
            if data:
                form_data = data
                original_title_hidden = data.get('Title', 'Announcement')
                if data.get('DisplayUntil') and isinstance(data['DisplayUntil'], datetime.datetime):
                    form_data['DisplayUntil'] = data['DisplayUntil'].strftime('%Y-%m-%dT%H:%M')
                form_data['IsActive'] = bool(data.get('IsActive'))
            else:
                flash('Announcement not found.', 'danger')
                return redirect(url_for('.list_announcements'))
        
        elif request.method == 'POST':
            form_data = request.form.to_dict()
            form_data['is_active'] = request.form.get('is_active') == 'on'
            original_title_hidden = request.form.get('original_title_hidden', form_data.get('title', 'Announcement'))
            errors = validate_announcement_data(form_data)
            if not errors:
                cursor = conn.cursor()
                sql = "UPDATE SystemAnnouncements SET Title=%s, Content=%s, IsActive=%s, DisplayUntil=%s, Audience=%s, Priority=%s, UpdatedAt=NOW() WHERE AnnouncementID=%s"
                display_until = datetime.datetime.strptime(form_data['display_until'], '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S') if form_data.get('display_until') else None
                val = (form_data['title'], form_data['content'], form_data['is_active'], display_until, form_data['audience'], form_data['priority'], announcement_id)
                cursor.execute(sql, val)
                conn.commit()
                flash('Announcement updated!', 'success')
                return redirect(url_for('.list_announcements'))
            else: 
                flash('Please correct the errors below.', 'warning')
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Error editing announcement {announcement_id}: {e}", exc_info=True)
        flash(f'An unexpected error occurred. Please check the logs.', 'danger')
        if request.method == 'POST': errors['form'] = str(e)
    finally:
        if conn and conn.is_connected(): 
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

    return render_template('agency_staff_portal/announcements/add_edit_announcement.html', title=f"Edit: {original_title_hidden}", form_data=form_data, errors=errors, action_verb='Update', announcement_id=announcement_id, original_title_hidden=original_title_hidden)

@announcement_bp.route('/delete/<int:announcement_id>', methods=['POST'])
# --- CORRECTED REDIRECT ---
@login_required_with_role(ANNOUNCEMENT_MANAGEMENT_ROLES, insufficient_role_redirect='managerial_dashboard_bp.main_dashboard')
def delete_announcement(announcement_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM SystemAnnouncements WHERE AnnouncementID = %s", (announcement_id,))
        conn.commit()
        if cursor.rowcount > 0:
            flash('Announcement deleted successfully!', 'success')
        else:
            flash('Announcement could not be found or was already deleted.', 'warning')
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deleting announcement {announcement_id}: {e}", exc_info=True)
        flash(f'An error occurred while deleting the announcement.', 'danger')
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()
    return redirect(url_for('.list_announcements'))