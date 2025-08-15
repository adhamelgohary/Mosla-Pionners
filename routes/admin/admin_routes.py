# routes/admin/admin_routes.py

import time
import datetime
import os
import subprocess
import json
from functools import wraps
import psutil
from flask import Blueprint, render_template, request, abort, current_app, Response, jsonify
from flask_login import login_required, current_user
from db import get_db_connection

admin_bp = Blueprint('admin_bp', __name__, template_folder='../../templates/admin', url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role_type not in ['Admin', 'CEO', 'Founder']:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions for System Monitoring (Unchanged) ---
def get_bandwidth_usage():
    try:
        result = subprocess.run(['vnstat', '--json', 'm', '1'], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        interface = data['interfaces'][0]
        monthly_data = interface['traffic'].get('months', [])
        if monthly_data:
            current_month_stats = monthly_data[0]
            total_kib = current_month_stats.get('rx', 0) + current_month_stats.get('tx', 0)
            total_gb = round(total_kib / (1024 * 1024), 2)
            month_name = current_month_stats.get('date', {}).get('month_name', 'Current Month')
        else:
            total_gb = 0.0
            month_name = datetime.datetime.now().strftime('%B')
        return {"month": month_name, "total_gb": total_gb, "error": None}
    except FileNotFoundError:
        return {"error": "vnstat is not installed or not in PATH."}
    except Exception as e:
        current_app.logger.error(f"vnstat error: {e}")
        return {"error": "Could not retrieve vnstat data."}

def get_system_performance():
    memory = psutil.virtual_memory()
    net_io = psutil.net_io_counters()
    boot_time_timestamp = psutil.boot_time()
    uptime_seconds = time.time() - boot_time_timestamp
    uptime_days = int(uptime_seconds // (24 * 3600))
    uptime_hours = int((uptime_seconds % (24 * 3600)) // 3600)
    return {
        'cpu_percent': psutil.cpu_percent(interval=None),
        'load_avg': [round(x / psutil.cpu_count() * 100, 1) for x in psutil.getloadavg()],
        'memory_percent': memory.percent,
        'uptime_str': f"{uptime_days}d {uptime_hours}h",
        'process_count': len(psutil.pids()),
        'net_bytes_sent_raw': net_io.bytes_sent,
        'net_bytes_recv_raw': net_io.bytes_recv
    }

def get_service_stats(service_names):
    stats = {name: {'status': 'Stopped', 'cpu': 0, 'memory': 0} for name in service_names.keys()}
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
        for display_name, process_name in service_names.items():
            if process_name in proc.info['name']:
                if stats[display_name]['status'] == 'Stopped': stats[display_name]['status'] = 'Running'
                stats[display_name]['cpu'] += proc.info['cpu_percent']
                stats[display_name]['memory'] += proc.info['memory_info'].rss / (1024 * 1024)
    for display_name in stats:
        stats[display_name]['cpu'] = round(stats[display_name]['cpu'], 2)
        stats[display_name]['memory'] = round(stats[display_name]['memory'], 2)
    return stats

# --- Helper Functions for Application Data (Updated) ---
def get_app_activity_stats(conn):
    stats = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM Users WHERE CreatedAt >= NOW() - INTERVAL 1 DAY")
        stats['new_users_24h'] = cursor.fetchone()['count']
        cursor.execute("SELECT EmailAttempt, IPAddress, AttemptedAt FROM LoginHistory WHERE Status LIKE 'Failed%' ORDER BY AttemptedAt DESC LIMIT 5")
        failed_logins = cursor.fetchall()
        stats['recent_failed_logins'] = [{**log, 'AttemptedAt': log['AttemptedAt'].strftime('%H:%M:%S')} for log in failed_logins]
        return stats
    except Exception as e:
        current_app.logger.error(f"Failed to get app activity stats: {e}", exc_info=True)
        return {'new_users_24h': 'N/A', 'recent_failed_logins': []}

def get_application_stats(conn):
    stats = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM JobOffers WHERE Status = 'Open'")
        stats['active_jobs'] = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM LoginHistory WHERE Status = 'Success' AND AttemptedAt >= NOW() - INTERVAL 1 DAY")
        stats['logins_24h'] = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM StaffApplications WHERE Status = 'Pending'")
        stats['pending_staff_applications'] = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM ClientRegistrations WHERE Status = 'Pending'")
        stats['pending_client_registrations'] = cursor.fetchone()['count']
        return stats
    except Exception as e:
        current_app.logger.error(f"Failed to get application stats: {e}", exc_info=True)
        return {'active_jobs': 'N/A', 'logins_24h': 'N/A', 'pending_staff_applications': 'N/A', 'pending_client_registrations': 'N/A'}

def get_recent_db_errors(conn, limit=10):
    """
    Retrieves the most recent error logs from the ErrorLog database table.
    """
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT ErrorID, Timestamp, Route, RequestMethod, ErrorMessage 
            FROM ErrorLog 
            ORDER BY Timestamp DESC 
            LIMIT %s
        """, (limit,))
        return cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Could not fetch recent DB errors: {e}", exc_info=True)
        return []

# --- API Endpoints (Unchanged) ---
@admin_bp.route('/system-stats')
@login_required
@admin_required
def system_stats_api():
    services_to_monitor = {"Nginx": "nginx", "MySQL": "mysqld"}
    return jsonify({
        'global': get_system_performance(),
        'services': get_service_stats(services_to_monitor),
        'bandwidth': get_bandwidth_usage()
    })

@admin_bp.route('/app-activity-stats')
@login_required
@admin_required
def app_activity_api():
    conn = get_db_connection()
    if not conn: return jsonify({"error": "DB connection failed"}), 500
    activity_stats = get_app_activity_stats(conn)
    conn.close()
    return jsonify(activity_stats)

# --- Page-Rendering Routes (Updated & New Routes Added) ---
@admin_bp.route('/dashboard')
@login_required
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    if not conn: abort(500, "Database connection failed.")
    dashboard_data = {
        'app_stats': get_application_stats(conn),
        'recent_errors': get_recent_db_errors(conn) # Fetch recent errors for the dashboard
    }
    conn.close()
    return render_template('admin/admin_dashboard.html', title='Admin Dashboard', data=dashboard_data)

@admin_bp.route('/login-history')
@login_required
@admin_required
def login_history():
    conn = get_db_connection()
    if not conn: abort(500, "Database connection failed.")
    
    page = request.args.get('page', 1, type=int)
    per_page = 25
    offset = (page - 1) * per_page
    search_email = request.args.get('email', '').strip()
    filter_status = request.args.get('status', '').strip()

    base_query = "FROM LoginHistory"
    where_clauses, params = [], []

    if search_email:
        where_clauses.append("EmailAttempt LIKE %s")
        params.append(f"%{search_email}%")
    if filter_status:
        where_clauses.append("Status = %s")
        params.append(filter_status)

    if where_clauses: base_query += " WHERE " + " AND ".join(where_clauses)

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as total " + base_query, tuple(params))
        total_records = cursor.fetchone()['total']
        total_pages = (total_records + per_page - 1) // per_page
        
        data_query = "SELECT HistoryID, EmailAttempt, Status, AttemptedAt " + base_query + " ORDER BY AttemptedAt DESC LIMIT %s OFFSET %s"
        cursor.execute(data_query, tuple(params) + (per_page, offset))
        history_logs = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching login history: {e}", exc_info=True)
        history_logs, total_pages = [], 0
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('admin/login_history.html', 
                           title="Login Attempt History",
                           logs=history_logs,
                           current_page=page,
                           total_pages=total_pages,
                           search_email=search_email,
                           filter_status=filter_status)

# --- NEW ROUTE: Error Log Viewer ---
@admin_bp.route('/error-log')
@login_required
@admin_required
def error_log_viewer():
    """Displays a paginated and searchable list of recorded errors from the database."""
    conn = get_db_connection()
    if not conn: abort(500, "Database connection failed.")
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    search_route = request.args.get('route', '').strip()
    
    base_query = "FROM ErrorLog"
    params = []
    if search_route:
        base_query += " WHERE Route LIKE %s"
        params.append(f"%{search_route}%")

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as total " + base_query, tuple(params))
        total_records = cursor.fetchone()['total']
        total_pages = (total_records + per_page - 1) // per_page

        query = "SELECT ErrorID, Timestamp, Route, RequestMethod, ErrorMessage, UserID " + base_query + " ORDER BY Timestamp DESC LIMIT %s OFFSET %s"
        cursor.execute(query, tuple(params) + (per_page, offset))
        error_logs = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching error log: {e}", exc_info=True)
        error_logs, total_pages = [], 0
    finally:
        if conn and conn.is_connected(): conn.close()

    return render_template('admin/error_log.html', 
                           title="Application Error Log",
                           logs=error_logs,
                           current_page=page,
                           total_pages=total_pages,
                           search_route=search_route)

# --- NEW ROUTE: Audit Log Viewer ---
@admin_bp.route('/audit-log')
@login_required
@admin_required
def audit_log_viewer():
    """Displays a paginated and searchable list of user actions from the AuditLog."""
    conn = get_db_connection()
    if not conn: abort(500, "Database connection failed.")
    
    page = request.args.get('page', 1, type=int)
    per_page = 25
    offset = (page - 1) * per_page
    search_action = request.args.get('action', '').strip()
    search_user = request.args.get('user_id', '').strip()
    
    base_query = "FROM AuditLog a LEFT JOIN Users u ON a.UserID = u.UserID"
    where_clauses, params = [], []

    if search_action:
        where_clauses.append("a.Action LIKE %s")
        params.append(f"%{search_action}%")
    if search_user:
        where_clauses.append("a.UserID = %s")
        params.append(search_user)

    if where_clauses: base_query += " WHERE " + " AND ".join(where_clauses)

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as total " + base_query, tuple(params))
        total_records = cursor.fetchone()['total']
        total_pages = (total_records + per_page - 1) // per_page

        query = "SELECT a.*, u.Email FROM AuditLog a LEFT JOIN Users u ON a.UserID = u.UserID"
        if where_clauses: query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY a.Timestamp DESC LIMIT %s OFFSET %s"
        cursor.execute(query, tuple(params) + (per_page, offset))
        audit_logs = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching audit log: {e}", exc_info=True)
        audit_logs, total_pages = [], 0
    finally:
        if conn and conn.is_connected(): conn.close()
        
    return render_template('admin/audit_log.html', 
                           title="User Audit Log",
                           logs=audit_logs,
                           current_page=page,
                           total_pages=total_pages,
                           search_action=search_action,
                           search_user=search_user)
                           
@admin_bp.route('/error-log/<int:error_id>')
@login_required
@admin_required
def view_error_details(error_id):
    """Fetches full details for a single error log entry."""
    conn = get_db_connection()
    if not conn: return jsonify({'error': 'Database connection failed'}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ErrorLog WHERE ErrorID = %s", (error_id,))
        error_log = cursor.fetchone()
        if error_log:
            # Safely parse JSON data
            try:
                error_log['RequestData'] = json.loads(error_log['RequestData'])
            except (json.JSONDecodeError, TypeError):
                pass # Keep as string if not valid JSON
            return jsonify(error_log)
        else:
            return jsonify({'error': 'Log not found'}), 404
    except Exception as e:
        current_app.logger.error(f"Error fetching error details for ErrorID {error_id}: {e}", exc_info=True)
        return jsonify({'error': 'An internal error occurred'}), 500
    finally:
        if conn and conn.is_connected(): conn.close()