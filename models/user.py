# models/user.py
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection
import datetime
import mysql.connector # For specific error handling if needed, though general Exception is often fine

# It's good practice to import current_app for logging if you need it within the model,
# but be careful of circular imports if model is imported by app.py very early.
# from flask import current_app

class User(UserMixin):
    def __init__(self, user_id, email, first_name, last_name, password_hash=None, is_active=True,
                 role_type=None, specific_role_id=None):
        self.id = int(user_id) # Ensure id is an integer for Flask-Login
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.password_hash = password_hash
        self.is_active = bool(is_active) # Ensure boolean
        self.role_type = role_type # This will hold specific ENUM like 'SalesManager', 'Admin', 'Candidate', 'AccountManager'
        self.specific_role_id = int(specific_role_id) if specific_role_id is not None else None # Ensure int or None

    def set_password(self, password):
        """Generates a hash for the given password and stores it."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password_to_check):
        """Checks if the given password matches the stored hash."""
        if self.password_hash is None:
            # print(f"User {self.email} has no password hash set.") # Debugging
            return False
        return check_password_hash(self.password_hash, password_to_check)

    @staticmethod
    def get_by_id(user_id):
        """Retrieves a user by their UserID and instantiates the User object."""
        conn = get_db_connection()
        if not conn:
            # current_app.logger.error("get_by_id: Database connection failed.") # Use if app context available
            print("get_by_id: Database connection failed.")
            return None
        
        cursor = conn.cursor(dictionary=True)
        user_object = None
        try:
            cursor.execute("SELECT * FROM Users WHERE UserID = %s", (int(user_id),)) # Ensure user_id is int
            user_data = cursor.fetchone()
            if user_data:
                # Pass the connection to determine_user_role to avoid re-opening
                role_type_from_db, specific_role_id_from_db = User.determine_user_role(user_data['UserID'], conn)
                user_object = User(
                    user_id=user_data['UserID'], 
                    email=user_data['Email'],
                    first_name=user_data['FirstName'], 
                    last_name=user_data['LastName'],
                    password_hash=user_data['PasswordHash'], 
                    is_active=user_data['IsActive'],
                    role_type=role_type_from_db,
                    specific_role_id=specific_role_id_from_db
                )
                # print(f"User.get_by_id: Loaded user {user_object.email} with role {user_object.role_type}") # Debugging
        except Exception as e:
            # current_app.logger.error(f"Error in User.get_by_id for {user_id}: {e}", exc_info=True)
            print(f"Error in User.get_by_id for {user_id}: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
        return user_object

    @staticmethod
    def get_by_email(email):
        """Retrieves a user by their email and instantiates the User object."""
        conn = get_db_connection()
        if not conn:
            # current_app.logger.error("get_by_email: Database connection failed.")
            print("get_by_email: Database connection failed.")
            return None
            
        cursor = conn.cursor(dictionary=True)
        user_object = None
        try:
            cursor.execute("SELECT * FROM Users WHERE Email = %s", (email,))
            user_data = cursor.fetchone()
            if user_data:
                # Pass the connection to determine_user_role
                role_type_from_db, specific_role_id_from_db = User.determine_user_role(user_data['UserID'], conn)
                user_object = User(
                    user_id=user_data['UserID'], 
                    email=user_data['Email'],
                    first_name=user_data['FirstName'], 
                    last_name=user_data['LastName'],
                    password_hash=user_data['PasswordHash'], 
                    is_active=user_data['IsActive'],
                    role_type=role_type_from_db,
                    specific_role_id=specific_role_id_from_db
                )
                # print(f"User.get_by_email: Loaded user {user_object.email} with role {user_object.role_type}") # Debugging
        except Exception as e:
            # current_app.logger.error(f"Error in User.get_by_email for {email}: {e}", exc_info=True)
            print(f"Error in User.get_by_email for {email}: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
        return user_object
    
    @staticmethod
    def determine_user_role(user_id, db_connection):
        """
        Determines the specific role ENUM value of a user and their ID in that role's table.
        Requires an active database connection to be passed.
        The order of queries matters for precedence if a user could exist in multiple role tables (not typical).
        """
        if not db_connection or not db_connection.is_connected():
            # current_app.logger.error(f"determine_user_role: Invalid or closed DB connection for UserID {user_id}")
            print(f"Error: Invalid or closed DB connection in determine_user_role for UserID {user_id}")
            return "Unknown", None

        cursor = db_connection.cursor(dictionary=True)
        role_type_to_return = "User" # Default role if not found in specific role tables
        specific_id_to_return = None

        try:
            # 1. Admins (System Administrators)
            cursor.execute("SELECT AdminID FROM Admins WHERE UserID = %s", (user_id,))
            if record := cursor.fetchone():
                return "Admin", record['AdminID']

            # 2. Recruiters (SourcingRecruiter, SourcingTeamLead, OperationsManager, CEO, SalesManager)
            cursor.execute("SELECT RecruiterID, RecruiterRole FROM Recruiters WHERE UserID = %s", (user_id,))
            if record := cursor.fetchone():
                return record['RecruiterRole'], record['RecruiterID'] # Returns the specific ENUM value

            # 3. AccountManagers (AccountManager, SeniorAccountManager)
            cursor.execute("SELECT AccountManagerID, AMRole FROM AccountManagers WHERE UserID = %s", (user_id,))
            if record := cursor.fetchone():
                return record['AMRole'], record['AccountManagerID'] # Returns the specific ENUM value
            
            # 4. Candidates
            cursor.execute("SELECT CandidateID FROM Candidates WHERE UserID = %s", (user_id,))
            if record := cursor.fetchone():
                return "Candidate", record['CandidateID']
                
        except Exception as e:
            # current_app.logger.error(f"Error determining role for UserID {user_id}: {e}", exc_info=True)
            print(f"Error determining role for UserID {user_id} in determine_user_role: {e}")
            return "ErrorDeterminingRole", None
        # The cursor will be closed by the calling function (get_by_id or get_by_email)
        # as the db_connection is passed in and managed by them.
        
        return role_type_to_return, specific_id_to_return


    @staticmethod
    def create_user(email, password, first_name, last_name, phone_number=None, profile_picture_url=None):
        """Creates a new user in the Users table with a hashed password."""
        conn = get_db_connection()
        if not conn:
            # current_app.logger.error("create_user: Database connection failed.")
            print("Database connection failed in create_user.")
            return None

        cursor = conn.cursor()
        hashed_password = generate_password_hash(password) # Hashing the password
        user_id = None
        try:
            cursor.execute("""
                INSERT INTO Users (Email, PasswordHash, FirstName, LastName, PhoneNumber, ProfilePictureURL, RegistrationDate, LastLoginDate)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (email, hashed_password, first_name, last_name, phone_number, profile_picture_url, 
                  datetime.datetime.now(datetime.timezone.utc), # Use timezone-aware datetime
                  datetime.datetime.now(datetime.timezone.utc))) 
            conn.commit()
            user_id = cursor.lastrowid
            # current_app.logger.info(f"User created successfully: {email}, UserID: {user_id}")
            print(f"User created with ID: {user_id}, Email: {email}")
        except mysql.connector.Error as err:
            # current_app.logger.error(f"MySQL Error creating user {email}: {err}")
            print(f"MySQL Error creating user {email}: {err}")
            conn.rollback()
        except Exception as e:
            # current_app.logger.error(f"Unexpected error creating user {email}: {e}", exc_info=True)
            print(f"Unexpected error creating user {email}: {e}")
            conn.rollback()
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
        return user_id

    def __repr__(self):
        return f'<User id={self.id} email={self.email} role={self.role_type} specific_id={self.specific_role_id}>'