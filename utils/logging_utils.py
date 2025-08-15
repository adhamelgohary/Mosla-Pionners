# utils/logging_utils.py
from flask import request
from flask_login import current_user
from db import get_db_connection

def log_audit(action, target_entity_type=None, target_entity_id=None, details=""):
    """Records an action to the AuditLog table."""
    try:
        user_id = current_user.id if current_user.is_authenticated else None
        
        # --- IP ADDRESS LOGIC ---
        # Use X-Forwarded-For if behind a proxy, otherwise use remote_addr.
        if request.headers.getlist("X-Forwarded-For"):
            ip_address = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip_address = request.remote_addr
        # --- END IP LOGIC ---
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO AuditLog 
            (UserID, IPAddress, Action, TargetEntityType, TargetEntityID, Details)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (user_id, ip_address, action, target_entity_type, target_entity_id, details)
        
        cursor.execute(sql, params)
        conn.commit()
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Failed to write to AuditLog: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()