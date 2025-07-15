# routes/Agency_staff_portal/reporting_routes.py

from flask import Blueprint, render_template, request, flash, url_for, current_app, make_response
from utils.decorators import login_required_with_role, MANAGERIAL_PORTAL_ROLES
from db import get_db_connection
import datetime
import csv
import io # Used for in-memory CSV generation

reporting_bp = Blueprint('reporting_bp', __name__,
                         template_folder='../../../templates',
                         url_prefix='/managerial/reports')

@reporting_bp.route('/')
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def reporting_hub():
    """Main dashboard for all available reports."""
    return render_template('agency_staff_portal/reports/reporting_hub.html', title="Reporting Hub")


@reporting_bp.route('/hiring-performance', methods=['GET'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def hiring_performance_report():
    """A detailed report on job offer and recruitment performance."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get date filters from URL (e.g., /hiring-performance?start_date=...&end_date=...)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # Build query with optional date filters
    params = []
    sql = """
        SELECT 
            jo.OfferID,
            jo.Title,
            c.CompanyName,
            jo.Status,
            jo.DatePosted,
            jo.FilledDate,
            DATEDIFF(jo.FilledDate, jo.DatePosted) as TimeToFill,
            jo.CandidatesNeeded,
            (SELECT COUNT(*) FROM JobApplications ja WHERE ja.OfferID = jo.OfferID) as TotalApplicants
        FROM JobOffers jo
        JOIN Companies c ON jo.CompanyID = c.CompanyID
    """
    
    conditions = []
    if start_date_str:
        conditions.append("jo.DatePosted >= %s")
        params.append(start_date_str)
    if end_date_str:
        conditions.append("jo.DatePosted <= %s")
        params.append(end_date_str)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    
    sql += " ORDER BY jo.DatePosted DESC"
    
    cursor.execute(sql, tuple(params))
    report_data = cursor.fetchall()
    cursor.close()
    conn.close()

    # Handle CSV Download Request
    if request.args.get('format') == 'csv':
        if not report_data:
            flash("No data to export.", "warning")
            # Redirect to the page without the format parameter
            return render_template('agency_staff_portal/reports/hiring_performance.html',
                           title="Hiring Performance Report",
                           report_data=[],
                           start_date=start_date_str,
                           end_date=end_date_str)

        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        headers = report_data[0].keys() if report_data else []
        writer.writerow(headers)
        
        # Write data
        for row in report_data:
            writer.writerow(row.values())
        
        output.seek(0)
        
        response = make_response(output.read())
        response.headers["Content-Disposition"] = f"attachment; filename=hiring_report_{datetime.date.today()}.csv"
        response.headers["Content-type"] = "text/csv"
        return response

    return render_template('agency_staff_portal/reports/hiring_performance.html',
                           title="Hiring Performance Report",
                           report_data=report_data,
                           start_date=start_date_str,
                           end_date=end_date_str)

@reporting_bp.route('/staff-performance', methods=['GET'])
@login_required_with_role(MANAGERIAL_PORTAL_ROLES)
def staff_performance_report():
    """A report on individual staff performance metrics."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get filters from URL
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    selected_role = request.args.get('role')

    # Fetch all available staff roles for the filter dropdown
    cursor.execute("SELECT DISTINCT Role FROM Staff ORDER BY Role")
    roles = [row['Role'] for row in cursor.fetchall()]

    # Build the main query with date and role filters
    params = []
    
    # --- Date filtering sub-clauses ---
    app_date_filter = ""
    offer_date_filter = ""
    points_date_filter = ""
    if start_date_str and end_date_str:
        app_date_filter = "WHERE ja.ApplicationDate BETWEEN %s AND %s"
        offer_date_filter = "WHERE jo.DatePosted BETWEEN %s AND %s"
        points_date_filter = "WHERE spl.AwardDate BETWEEN %s AND %s"
        # Add params multiple times for each subquery
        params.extend([start_date_str, end_date_str, start_date_str, end_date_str, start_date_str, end_date_str, start_date_str, end_date_str])

    # --- Main SQL query using subqueries for aggregation ---
    sql = f"""
        SELECT
            s.StaffID,
            CONCAT(u.FirstName, ' ', u.LastName) as StaffName,
            s.Role,
            COALESCE(ja_referred.TotalReferred, 0) as TotalApplicationsReferred,
            COALESCE(ja_hired.TotalHired, 0) as TotalHires,
            COALESCE(jo_posted.TotalOffersPosted, 0) as TotalOffersPosted,
            COALESCE(spl_points.TotalPoints, 0) as TotalPoints
        FROM Staff s
        JOIN Users u ON s.UserID = u.UserID
        LEFT JOIN (
            SELECT ReferringStaffID, COUNT(ApplicationID) as TotalReferred
            FROM JobApplications ja
            {app_date_filter}
            GROUP BY ReferringStaffID
        ) as ja_referred ON s.StaffID = ja_referred.ReferringStaffID
        LEFT JOIN (
            SELECT ReferringStaffID, COUNT(ApplicationID) as TotalHired
            FROM JobApplications ja
            WHERE ja.Status = 'Hired' {'AND ja.ApplicationDate BETWEEN %s AND %s' if start_date_str and end_date_str else ''}
            GROUP BY ReferringStaffID
        ) as ja_hired ON s.StaffID = ja_hired.ReferringStaffID
        LEFT JOIN (
            SELECT PostedByStaffID, COUNT(OfferID) as TotalOffersPosted
            FROM JobOffers jo
            {offer_date_filter}
            GROUP BY PostedByStaffID
        ) as jo_posted ON s.StaffID = jo_posted.PostedByStaffID
        LEFT JOIN (
            SELECT AwardedToStaffID, SUM(PointsAmount) as TotalPoints
            FROM StaffPointsLog spl
            {points_date_filter}
            GROUP BY AwardedToStaffID
        ) as spl_points ON s.StaffID = spl_points.AwardedToStaffID
    """
    
    # --- Role filtering ---
    role_condition = ""
    if selected_role:
        role_condition = "WHERE s.Role = %s"
        params.append(selected_role)
    
    sql += f" {role_condition} ORDER BY StaffName;"

    cursor.execute(sql, tuple(params))
    report_data = cursor.fetchall()
    cursor.close()
    conn.close()

    # Handle CSV Download Request
    if request.args.get('format') == 'csv':
        if not report_data:
            flash("No data to export for the selected filters.", "warning")
            # Redirect or render empty state
            return render_template('agency_staff_portal/reports/staff_performance.html',
                           title="Staff Performance Report",
                           report_data=[], roles=roles, start_date=start_date_str,
                           end_date=end_date_str, selected_role=selected_role)

        output = io.StringIO()
        # Add a Hire Rate column to the CSV data
        csv_data = []
        for row in report_data:
            new_row = dict(row)
            if new_row['TotalApplicationsReferred'] > 0:
                hire_rate = (new_row['TotalHires'] / new_row['TotalApplicationsReferred']) * 100
                new_row['HireRate (%)'] = f"{hire_rate:.2f}"
            else:
                new_row['HireRate (%)'] = "0.00"
            csv_data.append(new_row)
            
        writer = csv.DictWriter(output, fieldnames=csv_data[0].keys())
        writer.writeheader()
        writer.writerows(csv_data)
        
        output.seek(0)
        
        response = make_response(output.read())
        response.headers["Content-Disposition"] = f"attachment; filename=staff_performance_report_{datetime.date.today()}.csv"
        response.headers["Content-type"] = "text/csv"
        return response

    return render_template('agency_staff_portal/reports/staff_performance.html',
                           title="Staff Performance Report",
                           report_data=report_data,
                           roles=roles,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           selected_role=selected_role)