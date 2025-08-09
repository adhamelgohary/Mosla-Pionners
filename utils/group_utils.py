# utils/group_utils.py
from flask import current_app, flash
from db import get_db_connection
import os

def sync_sessions_for_groups():
    """
    A helper function to retroactively create sessions and attendance records
    for existing groups. Returns a summary message.
    """
    conn = get_db_connection()
    if not conn:
        return "Database connection failed.", "danger"
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 1. Find all groups that have ZERO sessions.
        cursor.execute("""
            SELECT cg.GroupID, cg.SubPackageID, sp.NumSessionsMonolingual
            FROM CourseGroups cg
            LEFT JOIN GroupSessions gs ON cg.GroupID = gs.GroupID
            JOIN SubPackages sp ON cg.SubPackageID = sp.SubPackageID
            WHERE gs.SessionID IS NULL AND sp.NumSessionsMonolingual > 0
        """)
        groups_to_fix = cursor.fetchall()

        if not groups_to_fix:
            return "All groups are already up-to-date with sessions.", "info"

        sessions_created_count = 0
        attendance_records_created_count = 0

        for group in groups_to_fix:
            group_id = group['GroupID']
            num_sessions = group.get('NumSessionsMonolingual', 0)

            if num_sessions > 0:
                # 2. Create the missing sessions
                session_data = [(group_id, i, f"Session {i}") for i in range(1, num_sessions + 1)]
                sql_insert_sessions = "INSERT INTO GroupSessions (GroupID, SessionNumber, SessionTitle) VALUES (%s, %s, %s)"
                cursor.executemany(sql_insert_sessions, session_data)
                sessions_created_count += cursor.rowcount

                # 3. Find members and create attendance records
                cursor.execute("SELECT EnrollmentID FROM CourseGroupMembers WHERE GroupID = %s", (group_id,))
                members = cursor.fetchall()
                
                if members:
                    cursor.execute("SELECT SessionID FROM GroupSessions WHERE GroupID = %s", (group_id,))
                    new_sessions = cursor.fetchall()
                    
                    attendance_data = []
                    for member in members:
                        for session in new_sessions:
                            attendance_data.append((session['SessionID'], member['EnrollmentID']))
                    
                    if attendance_data:
                        sql_insert_attendance = "INSERT INTO SessionAttendance (SessionID, EnrollmentID) VALUES (%s, %s)"
                        cursor.executemany(sql_insert_attendance, attendance_data)
                        attendance_records_created_count += cursor.rowcount
        
        conn.commit()
        message = f"Sync complete! Fixed {len(groups_to_fix)} groups. Created {sessions_created_count} sessions and {attendance_records_created_count} attendance records."
        return message, "success"

    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Error during session sync utility: {e}")
        return f"An error occurred during sync: {e}", "danger"
    finally:
        if conn and conn.is_connected(): conn.close()