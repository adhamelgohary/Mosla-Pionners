# routes/Agency_Staff_Portal/company_assignment_routes.py
# PURPOSE: This module exclusively handles the assignment ACTION.
# The staff list view is now handled by am_portal_routes.my_staff.

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from utils.decorators import login_required_with_role
from db import get_db_connection
import mysql.connector

# --- Roles are defined here for clarity and security ---
COMPANY_ASSIGNMENT_MANAGEMENT_ROLES = ['HeadAccountManager', 'CEO', 'Founder']
# This list now includes senior roles, allowing them to self-assign companies.
ASSIGNABLE_ROLES = ['AccountManager', 'SeniorAccountManager', 'HeadAccountManager', 'CEO', 'Founder']

# --- BLUEPRINT UPDATED for a cleaner, more specific template path ---
company_assignment_bp = Blueprint('company_assignment_bp', __name__,
                                  template_folder='../../../templates/account_manager_portal/assignments',
                                  url_prefix='/am-portal/assignments')

@company_assignment_bp.route('/manage-for-am/<int:manager_staff_id>', methods=['GET', 'POST'])
@login_required_with_role(COMPANY_ASSIGNMENT_MANAGEMENT_ROLES)
def manage_assignments_for_am(manager_staff_id):
    """
    Manages company assignments for a specific Account Manager.
    Allows assigning new companies and unassigning existing ones.
    """
    conn = None
    manager_details = None
    MAX_TOTAL_COMPANIES_PER_AM = 5

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --- QUERY FIXED: Now finds any assignable role, including senior staff ---
        role_placeholders = ', '.join(['%s'] * len(ASSIGNABLE_ROLES))
        manager_check_query = f"""
            SELECT s.StaffID, u.FirstName, u.LastName, s.Role,
                   (SELECT COUNT(*) FROM Companies WHERE ManagedByStaffID = s.StaffID) AS CurrentAssignedCount
            FROM Staff s JOIN Users u ON s.UserID = u.UserID
            WHERE s.StaffID = %s AND s.Role IN ({role_placeholders}) AND u.IsActive = 1
        """
        cursor.execute(manager_check_query, (manager_staff_id, *ASSIGNABLE_ROLES))
        manager_details = cursor.fetchone()

        if not manager_details:
            flash("Account Manager not found or is not an eligible role.", "danger")
            # --- REDIRECT FIXED: Points to the correct central staff list ---
            return redirect(url_for('account_manager_bp.my_staff'))

        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'unassign':
                company_id = request.form.get('unassign_company_id')
                cursor.execute("UPDATE Companies SET ManagedByStaffID = NULL WHERE CompanyID = %s AND ManagedByStaffID = %s", (company_id, manager_staff_id))
                conn.commit()
                flash("Company unassigned successfully.", "success")
            elif action == 'assign_selected':
                company_ids = request.form.getlist('companies_to_assign[]')
                if not company_ids:
                    flash("No companies selected.", "info")
                else:
                    current_count = manager_details['CurrentAssignedCount']
                    can_assign_count = MAX_TOTAL_COMPANIES_PER_AM - current_count
                    if len(company_ids) > can_assign_count:
                        flash(f"Cannot assign {len(company_ids)} companies. Manager can only be assigned {can_assign_count} more.", "warning")
                    else:
                        placeholders = ', '.join(['%s'] * len(company_ids))
                        cursor.execute(f"UPDATE Companies SET ManagedByStaffID = %s WHERE CompanyID IN ({placeholders}) AND ManagedByStaffID IS NULL", (manager_staff_id, *company_ids))
                        conn.commit()
                        flash(f"{cursor.rowcount} companies assigned successfully.", "success")
            return redirect(url_for('.manage_assignments_for_am', manager_staff_id=manager_staff_id))

        # GET request data
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE ManagedByStaffID = %s ORDER BY CompanyName", (manager_staff_id,))
        assigned_companies = cursor.fetchall()
        
        cursor.execute("SELECT CompanyID, CompanyName FROM Companies WHERE ManagedByStaffID IS NULL ORDER BY CompanyName")
        available_companies = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(f"Error for AM assignments page (AM ID {manager_staff_id}): {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
        # --- REDIRECT FIXED: Points to the correct central staff list ---
        return redirect(url_for('account_manager_bp.my_staff'))
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

    # The template path is now simpler due to the updated blueprint
    return render_template('account_manager_portal/manage_assignments_for_am.html',
                           title=f"Manage Assignments for {manager_details['FirstName']}",
                           manager=manager_details,
                           assigned_companies=assigned_companies,
                           available_companies=available_companies,
                           max_total_companies_per_am=MAX_TOTAL_COMPANIES_PER_AM)