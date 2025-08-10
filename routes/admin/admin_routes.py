# routes/admin/admin_routes.py

from flask import Blueprint, render_template, request, abort, current_app, Response, jsonify
from flask_login import login_required, current_user
from db import get_db_connection
from functools import wraps
import psutil  # For system stats
import os      # For log file path

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
    """Returns a dictionary with GLOBAL CPU and Memory usage."""
    memory = psutil.virtual_memory()
    return {
        'cpu_percent': psutil.cpu_percent(interval=None),
        'memory_percent': memory.percent,
    }

def get_service_stats(service_names):
    """
    Checks the status and resource usage of specific services by process name.
    
    Args:
        service_names (dict): A dictionary mapping a display name (e.g., "Nginx") 
                              to a process name to search for (e.g., "nginx").
    """
    stats = {name: {'status': 'Stopped', 'cpu': 0, 'memory': 0} for name in service_names.keys()}
    
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
        for display_name, process_name in service_names.items():
            if process_name in proc.info['name']:
                if stats[display_name]['status'] == 'Stopped':
                    stats[display_name]['status'] = 'Running'
                
                stats[display_name]['cpu'] += proc.info['cpu_percent']
                stats[display_name]['memory'] += proc.info['memory_info'].rss / (1024 * 1024) # Convert to MB

    # Round the final values for cleaner display
    for display_name in stats:
        stats[display_name]['cpu'] = round(stats[display_name]['cpu'], 2)
        stats[display_name]['memory'] = round(stats[display_name]['memory'], 2)
        
    return stats

# --- Admin Page Routes ---

@admin_bp.route('/dashboard')
@login_required
@admin_required
def admin_dashboard():
    """
    Renders the main admin dashboard page.
    This route now only loads the initial, non-realtime data. The live stats
    are fetched by JavaScript from the '/system-stats' API endpoint.
    """
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

    base_query = "FROM LoginHistory lh LEFT JOIN Users u ON lh.UserID = u.UserID"
    where_clauses = []
    params = []

    if search_email:
        where_clauses.append("lh.EmailAttempt LIKE %s")
        params.append(f"%{search_email}%")
    if filter_status:
        where_clauses.append("lh.Status = %s")
        params.append(filter_status)

    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)

    try:
        cursor = conn.cursor(dictionary=True)
        count_query = "SELECT COUNT(*) as total " + base_query
        cursor.execute(count_query, tuple(params))
        total_records = cursor.fetchone()['total']
        total_pages = (total_records + per_page - 1) // per_page

        data_query = """
            SELECT lh.HistoryID, lh.EmailAttempt, lh.Status, lh.AttemptedAt
        """ + base_query + " ORDER BY lh.AttemptedAt DESC LIMIT %s OFFSET %s"
        
        paginated_params = tuple(params) + (per_page, offset)
        cursor.execute(data_query, paginated_params)
        history_logs = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching login history: {e}", exc_info=True)
        history_logs, total_pages = [], 0
    finally:
        if conn.is_connected():
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
    """Streams the full application log file for viewing as plain text."""
    log_file_path = os.path.join(current_app.root_path, '..', 'logs', 'app.log')
    if not os.path.exists(log_file_path):
        abort(404, "Log file not found.")
    
    with open(log_file_path, 'r') as f:
        content = f.read()
    
    return Response(content, mimetype='text/plain')


# --- NEW API Endpoint for Real-time Stats ---

@admin_bp.route('/system-stats')
@login_required
@admin_required
def system_stats_api():
    """
    API endpoint that returns system and service health as JSON.
    This is called by the JavaScript on the dashboard for live updates.
    """
    # IMPORTANT: Verify these process names on your server using `ps aux`.
    # Common names are 'nginx', 'apache2', 'httpd', 'mysqld', 'mariadbd'.
    services_to_monitor = {
        "Nginx": "nginx",
        "MySQL": "mysqld",
        # phpMyAdmin is part of the Nginx/PHP-FPM stack, not a separate service.
    }

    all_stats = {
        'global': get_system_performance(),
        'services': get_service_stats(services_to_monitor)
    }
    return jsonify(all_stats)