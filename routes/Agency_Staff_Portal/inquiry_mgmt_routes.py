# routes/Agency_Staff_Portal/inquiry_mgmt_routes.py

from flask import Blueprint, render_template, current_app, flash, redirect, url_for
from db import get_db_connection
from utils.decorators import login_required_with_role, MANAGERIAL_PORTAL_ROLES

inquiry_mgmt_bp = Blueprint('inquiry_mgmt_bp', __name__,
                            template_folder='../../../templates')

@inquiry_mgmt_bp.route('/inquiries')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def list_inquiries():
    """
    Displays a list of all contact messages ever received.
    """
    inquiries = []
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch key details for the list view
        cursor.execute("""
            SELECT MessageID, Name, Subject, Status, SubmittedAt 
            FROM ContactMessages 
            ORDER BY SubmittedAt DESC
        """)
        inquiries = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching inquiries list: {e}", exc_info=True)
        flash("Could not load the list of inquiries.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

    return render_template('agency_staff_portal/inquiries/list_inquiries.html',
                           title="Contact Inquiries",
                           inquiries=inquiries)

@inquiry_mgmt_bp.route('/inquiry/<int:message_id>')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def view_inquiry(message_id):
    """
    Displays the full details of a single inquiry and marks it as 'Read'.
    """
    inquiry_details = None
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # First, mark the message as 'Read' if it's 'Unread'
        # This is good practice to do before fetching the data.
        update_cursor = conn.cursor()
        update_cursor.execute(
            "UPDATE ContactMessages SET Status = 'Read' WHERE MessageID = %s AND Status = 'Unread'", 
            (message_id,)
        )
        conn.commit()
        update_cursor.close()

        # Now, fetch the full details of the message
        cursor.execute("SELECT * FROM ContactMessages WHERE MessageID = %s", (message_id,))
        inquiry_details = cursor.fetchone()

    except Exception as e:
        current_app.logger.error(f"Error viewing inquiry {message_id}: {e}", exc_info=True)
        flash("Could not load the inquiry details.", "danger")
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor: cursor.close()
            conn.close()

    if not inquiry_details:
        flash("Inquiry not found.", "warning")
        return redirect(url_for('.list_inquiries'))

    return render_template('agency_staff_portal/inquiries/view_inquiry.html',
                           title=f"Inquiry from {inquiry_details['Name']}",
                           inquiry=inquiry_details)