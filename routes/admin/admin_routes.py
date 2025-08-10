# routes/admin/admin_routes.py
from flask import Blueprint, render_template, request, abort, current_app, Response
from flask_login import login_required, current_user
from db import get_db_connection
from functools import wraps
import psutil  # For system stats
import os      # For log file path

admin_bp = Blueprint('admin_bp', __name__, template_folder='../../templates/admin', url_prefix='/admin')

# --- Simple Decorator for Admin Access ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role_type not in ['Admin', 'CEO', 'Founder']:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions for Dashboard Data ---

def get_system_performance():
    """Returns a dictionary with CPU, Memory, and Disk usage."""
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return {
        'cpu_percent': psutil.cpu_percent(interval=0.1),
        'memory_percent': memory.percent,
        'memory_total_gb': round(memory.total / (1024**3), 2),
        'memory_used_gb': round(memory.used / (1024**3), 2),
        'disk_percent': disk.percent,
        'disk_total_gb': round(disk.total / (1024**3), 2),
        'disk_used_gb': round(disk.used / (1024**3), 2),
    }

def get_recent_error_logs(num_lines=20):
    """Reads the last N lines from the application log file."""
    log_file_path = os.path.join(current_app.root_path, '..', 'logs', 'app.log')
    if not os.path.exists(log_file_path):
        return ["Log file not found at logs/app.log. Please ensure logging is configured."]
    
    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()
            # Return the last `num_lines` that are error or warning level
            error_lines = [line.strip() for line in lines if 'ERROR' in line or 'WARNING' in line]
            return error_lines[-num_lines:]
    except Exception as e:
        return [f"Could not read log file: {e}"]

def get_application_stats(conn):
    """Gathers key statistics from the database."""
    stats = {}
    try:
        cursor = conn.cursor(dictionary=True)
        
        # --- Existing Stats ---
        cursor.execute("SELECT COUNT(*) as count FROM JobOffers WHERE Status = 'Open'")
        stats['active_jobs'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM LoginHistory WHERE Status = 'Success' AND AttemptedAt >= NOW() - INTERVAL 1 DAY")
        stats['logins_24h'] = cursor.fetchone()['count']

        # --- NEW WIDGET STATS ---
        
        # Pending Staff Applications
        cursor.execute("SELECT COUNT(*) as count FROM StaffApplications WHERE Status = 'Pending'")
        stats['pending_staff_applications'] = cursor.fetchone()['count']
        
        # Pending Client Registrations
        cursor.execute("SELECT COUNT(*) as count FROM ClientRegistrations WHERE Status = 'Pending'")
        stats['pending_client_registrations'] = cursor.fetchone()['count']

        # Unassigned Companies
        cursor.execute("SELECT COUNT(*) as count FROM Companies WHERE ManagedByStaffID IS NULL")
        stats['unassigned_companies'] = cursor.fetchone()['count']

        # New Applications in last 24 hours
        cursor.execute("SELECT COUNT(*) as count FROM JobApplications WHERE ApplicationDate >= NOW() - INTERVAL 1 DAY")
        stats['new_applications_24h'] = cursor.fetchone()['count']
        
        return stats
    except Exception as e:
        current_app.logger.error(f"Failed to get application stats: {e}", exc_info=True)
        # Return default values for all stats to prevent crashes
        return {
            'active_jobs': 'N/A', 'logins_24h': 'N/A', 
            'pending_staff_applications': 'N/A', 'pending_client_registrations': 'N/A', 
            'unassigned_companies': 'N/A', 'new_applications_24h': 'N/A'
        }

# --- Main Admin Routes ---

@admin_bp.route('/dashboard')
@login_required
@admin_required
def admin_dashboard():
    """The main landing page for the admin panel with performance metrics."""
    conn = get_db_connection()
    if not conn:
        abort(500, "Database connection failed.")
    
    dashboard_data = {
        'performance': get_system_performance(),
        'recent_errors': get_recent_error_logs(),
        'app_stats': get_application_stats(conn)
    }
    
    conn.close()
    
    return render_template('admin/admin_dashboard.html', title='Admin Dashboard', data=dashboard_data)

@admin_bp.route('/logs/view')
@login_required
@admin_required
def view_full_log():
    """Streams the full application log file for viewing."""
    log_file_path = os.path.join(current_app.root_path, '..', 'logs', 'app.log')
    if not os.path.exists(log_file_path):
        abort(404, "Log file not found.")
    
    with open(log_file_path, 'r') as f:
        content = f.read()
    
    # IMPORTANT: Do not render this in a normal template to avoid XSS if log contains malicious user input.
    # Serving as plain text is safest.
    return Response(content, mimetype='text/plain')

@admin_bp.route('/login-history')
@login_required
@admin_required
def login_history():
    """Displays a paginated and searchable list of login attempts."""
    conn = get_db_connection()
    if not conn:
        abort(500, "Database connection failed.")
    
    # --- Pagination ---
    page = request.args.get('page', 1, type=int)
    per_page = 50 # Number of records per page
    offset = (page - 1) * per_page

    # --- Search/Filter ---
    search_email = request.args.get('email', '').strip()
    filter_status = request.args.get('status', '').strip()

    base_query = """
        FROM LoginHistory lh
        LEFT JOIN Users u ON lh.UserID = u.UserID
    """
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
        
        # --- Get total count for pagination ---
        count_query = "SELECT COUNT(*) as total " + base_query
        cursor.execute(count_query, tuple(params))
        total_records = cursor.fetchone()['total']
        total_pages = (total_records + per_page - 1) // per_page

        # --- Get records for the current page ---
        data_query = """
            SELECT
                lh.HistoryID,
                lh.EmailAttempt,
                CONCAT(u.FirstName, ' ', u.LastName) as UserName,
                lh.Status,
                lh.IPAddress,
                lh.UserAgent,
                lh.AttemptedAt
        """ + base_query + " ORDER BY lh.AttemptedAt DESC LIMIT %s OFFSET %s"
        
        paginated_params = tuple(params) + (per_page, offset)
        cursor.execute(data_query, paginated_params)
        history_logs = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error fetching login history: {e}", exc_info=True)
        history_logs = []
        total_pages = 0
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