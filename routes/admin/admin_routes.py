# routes/admin/admin_routes.py
import time
import datetime
import os
import subprocess # Add for running shell commands
import json       # Add for parsing JSON output
from functools import wraps
import psutil
from flask import Blueprint, render_template, request, abort, current_app, Response, jsonify
from flask_login import login_required, current_user
from db import get_db_connection

# --- Blueprint Setup ---
admin_bp = Blueprint('admin_bp', __name__, template_folder='../../templates/admin', url_prefix='/admin')

# --- Decorator for Admin Access ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role_type not in ['Admin', 'CEO', 'Founder']:
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions for Static Dashboard Data ---

def get_bandwidth_usage():
    """
    Executes vnstat to get monthly bandwidth usage and parses the JSON output.
    Returns a dictionary with usage stats or an error message.
    """
    try:
        # Execute 'vnstat' for the current month's data in JSON format
        # The 'm' flag is for monthly, '1' gets the current month
        result = subprocess.run(
            ['vnstat', '--json', 'm', '1'],
            capture_output=True,
            text=True,
            check=True # This will raise an error if the command fails
        )
        data = json.loads(result.stdout)
        
        # vnstat provides data for each network interface. We'll use the first one.
        interface = data['interfaces'][0]
        current_month_data = interface['traffic']['months'][0]
        
        # Convert KiB to GB for easier reading
        total_kib = current_month_data['rx'] + current_month_data['tx']
        total_gb = round(total_kib / (1024 * 1024), 2)
        
        month_name = current_month_data.get('date', {}).get('month_name', 'Current Month')

        return {
            "month": month_name,
            "total_gb": total_gb,
            "error": None
        }

    except FileNotFoundError:
        # This error occurs if 'vnstat' is not installed
        return {"error": "vnstat is not installed or not in PATH."}
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError) as e:
        # Handle cases where vnstat has no data yet, or other errors
        return {"error": f"Could not retrieve vnstat data. It may still be collecting. Error: {e}"}


def get_recent_error_logs(num_lines=20):
    """Reads the last N lines from the application log file that contain errors or warnings."""
    log_file_path = os.path.join(current_app.root_path, '..', 'logs', 'app.log')
    if not os.path.exists(log_file_path):
        return ["Log file not found at logs/app.log. Please ensure logging is configured."]
    
    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()
            error_lines = [line.strip() for line in lines if 'ERROR' in line or 'WARNING' in line]
            return error_lines[-num_lines:]
    except Exception as e:
        return [f"Could not read log file: {e}"]

def get_application_stats(conn):
    """Gathers key application-specific statistics from the database (non-realtime)."""
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
        return {
            'active_jobs': 'N/A', 'logins_24h': 'N/A', 
            'pending_staff_applications': 'N/A', 'pending_client_registrations': 'N/A'
        }

# --- Helper Functions for Real-time System Health ---

def get_system_performance():
    """Returns a dictionary with GLOBAL CPU, Memory, Disk, and Network usage."""
    memory = psutil.virtual_memory()
    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters()
    
    # Calculate uptime
    boot_time_timestamp = psutil.boot_time()
    # FIX: Use time.time() explicitly from the time module
    uptime_seconds = time.time() - boot_time_timestamp
    uptime_days = int(uptime_seconds // (24 * 3600))
    uptime_hours = int((uptime_seconds % (24 * 3600)) // 3600)
    
    return {
        'cpu_percent': psutil.cpu_percent(interval=None),
        'load_avg': [round(x / psutil.cpu_count() * 100, 1) for x in psutil.getloadavg()],
        'memory_percent': memory.percent,
        'disk_read_mb': round(disk_io.read_bytes / (1024*1024), 2),
        'disk_write_mb': round(disk_io.write_bytes / (1024*1024), 2),
        'net_sent_gb': round(net_io.bytes_sent / (1024*1024*1024), 2),
        'net_recv_gb': round(net_io.bytes_recv / (1024*1024*1024), 2),
        'uptime_str': f"{uptime_days}d {uptime_hours}h",
        'process_count': len(psutil.pids())
    }

def get_service_stats(service_names):
    """Checks the status and resource usage of specific services by process name."""
    stats = {name: {'status': 'Stopped', 'cpu': 0, 'memory': 0} for name in service_names.keys()}
    
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
        for display_name, process_name in service_names.items():
            if process_name in proc.info['name']:
                if stats[display_name]['status'] == 'Stopped':
                    stats[display_name]['status'] = 'Running'
                
                stats[display_name]['cpu'] += proc.info['cpu_percent']
                stats[display_name]['memory'] += proc.info['memory_info'].rss / (1024 * 1024)

    for display_name in stats:
        stats[display_name]['cpu'] = round(stats[display_name]['cpu'], 2)
        stats[display_name]['memory'] = round(stats[display_name]['memory'], 2)
        
    return stats

def get_app_activity_stats(conn):
    """Gathers real-time application activity stats."""
    stats = {}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM Users WHERE CreatedAt >= NOW() - INTERVAL 1 DAY")
        stats['new_users_24h'] = cursor.fetchone()['count']
        
        cursor.execute("""
            SELECT EmailAttempt, IPAddress, AttemptedAt 
            FROM LoginHistory 
            WHERE Status LIKE 'Failed%' 
            ORDER BY AttemptedAt DESC 
            LIMIT 5
        """)
        failed_logins = cursor.fetchall()
        stats['recent_failed_logins'] = [
            {**log, 'AttemptedAt': log['AttemptedAt'].strftime('%H:%M:%S')} for log in failed_logins
        ]
        return stats
    except Exception as e:
        current_app.logger.error(f"Failed to get app activity stats: {e}", exc_info=True)
        return {'new_users_24h': 'N/A', 'recent_failed_logins': []}

# --- Admin Page Routes ---

@admin_bp.route('/dashboard')
@login_required
@admin_required
def admin_dashboard():
    """Renders the main admin dashboard page."""
    conn = get_db_connection()
    if not conn:
        abort(500, "Database connection failed.")
    
    dashboard_data = {
        'app_stats': get_application_stats(conn),
        'recent_errors': get_recent_error_logs(),
    }
    conn.close()
    
    return render_template('admin/admin_dashboard.html', title='Admin Dashboard', data=dashboard_data)

@admin_bp.route('/login-history')
@login_required
@admin_required
def login_history():
    """Displays a paginated and searchable list of login attempts."""
    conn = get_db_connection()
    if not conn:
        abort(500, "Database connection failed.")
    
    page = request.args.get('page', 1, type=int)
    per_page = 25
    offset = (page - 1) * per_page
    search_email = request.args.get('email', '').strip()
    filter_status = request.args.get('status', '').strip()

    base_query = "FROM LoginHistory"
    where_clauses = []
    params = []

    if search_email:
        where_clauses.append("EmailAttempt LIKE %s")
        params.append(f"%{search_email}%")
    if filter_status:
        where_clauses.append("Status = %s")
        params.append(filter_status)

    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)

    try:
        cursor = conn.cursor(dictionary=True)
        count_query = "SELECT COUNT(*) as total " + base_query
        cursor.execute(count_query, tuple(params))
        total_records = cursor.fetchone()['total']
        total_pages = (total_records + per_page - 1) // per_page if per_page > 0 else 0

        data_query = "SELECT HistoryID, EmailAttempt, Status, AttemptedAt " + base_query + " ORDER BY AttemptedAt DESC LIMIT %s OFFSET %s"
        paginated_params = tuple(params) + (per_page, offset)
        cursor.execute(data_query, paginated_params)
        history_logs = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching login history: {e}", exc_info=True)
        history_logs, total_pages = [], 0
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    return render_template('admin/login_history.html', 
                           title="Login Attempt History",
                           logs=history_logs,
                           current_page=page,
                           total_pages=total_pages,
                           search_email=search_email,
                           filter_status=filter_status)

@admin_bp.route('/logs/view')
@login_required
@admin_required
def view_full_log():
    """Streams the full application log file as plain text."""
    log_file_path = os.path.join(current_app.root_path, '..', 'logs', 'app.log')
    if not os.path.exists(log_file_path):
        abort(404, "Log file not found.")
    
    with open(log_file_path, 'r') as f:
        content = f.read()
    
    return Response(content, mimetype='text/plain')

# --- API Endpoints for Real-time Data ---

@admin_bp.route('/system-stats')
@login_required
@admin_required
def system_stats_api():
    """API endpoint for system, service, and bandwidth health."""
    services_to_monitor = {"Nginx": "nginx", "MySQL": "mysqld"}
    
    all_stats = {
        'global': get_system_performance(),
        'services': get_service_stats(services_to_monitor),
        'bandwidth': get_bandwidth_usage() # Add bandwidth data here
    }
    return jsonify(all_stats)

@admin_bp.route('/app-activity-stats')
@login_required
@admin_required
def app_activity_api():
    """API endpoint for real-time application activity."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB connection failed"}), 500
    
    activity_stats = get_app_activity_stats(conn)
    conn.close()
    return jsonify(activity_stats)