# routes/Managerial_Portal/reporting_routes.py

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
    return render_template('managerial_portal/reporting_hub.html', title="Reporting Hub")


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
    conn.close()

    # Handle CSV Download Request
    if request.args.get('format') == 'csv':
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

    return render_template('managerial_portal/reports/hiring_performance.html',
                           title="Hiring Performance Report",
                           report_data=report_data,
                           start_date=start_date_str,
                           end_date=end_date_str)

# You can add more report routes here, for example:
# @reporting_bp.route('/financial-overview')
# @reporting_bp.route('/client-activity')