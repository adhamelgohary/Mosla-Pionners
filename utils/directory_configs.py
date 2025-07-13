# utils/directory_configs.py
import os
from werkzeug.utils import secure_filename
from flask import current_app

def configure_directories(app):
    """Initializes upload directories when the Flask app starts."""
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    subfolders_to_create = [
        'candidate_applications/cv',
        'candidate_applications/voice',
        'candidate_cvs',
        'staff_profile_pics',
        'company_logos',
        'general'
    ]
    for subfolder_group in subfolders_to_create:
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], *subfolder_group.split('/'))
        os.makedirs(full_path, exist_ok=True)

    app.logger.info(f"UPLOAD_FOLDER configured at: {app.config['UPLOAD_FOLDER']}")
    app.logger.info("Essential directories configured.")

def save_file_from_config(file_storage, subfolder='general', filename_override=None, allowed_extensions=None):
    """
    Saves a file from a FileStorage object to a configured subfolder with extension validation.

    Args:
        file_storage (FileStorage): The file object from Flask's request.files.
        subfolder (str): The destination subfolder path relative to the UPLOAD_FOLDER.
                         Can include dynamic parts like 'candidate_cvs/123'.
        filename_override (str, optional): A specific filename to use instead of the original.
        allowed_extensions (set, optional): A set of allowed file extensions (e.g., {'pdf', 'docx'}).
                                             If provided, the file extension will be validated.
    Returns:
        str or None: The web-accessible relative path of the saved file, or None on failure.
    """
    if not current_app:
        raise RuntimeError("Flask current_app context is not available.")
    
    upload_folder_base = current_app.config.get('UPLOAD_FOLDER')
    if not upload_folder_base:
        current_app.logger.error("UPLOAD_FOLDER is not configured.")
        return None

    if not file_storage or not file_storage.filename:
        current_app.logger.warning("No file or filename in the provided FileStorage object.")
        return None

    # Determine the filename and validate its extension
    filename = secure_filename(filename_override or file_storage.filename)
    
    if allowed_extensions:
        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if file_ext not in allowed_extensions:
            current_app.logger.error(f"File upload rejected: Extension '{file_ext}' is not in the allowed set {allowed_extensions}.")
            # Raise a specific error to be caught by the route handler
            raise ValueError(f"File type not allowed: {file_ext}")
            
    # Construct the full path and ensure the directory exists
    specific_upload_path_on_disk = os.path.join(upload_folder_base, subfolder)
    os.makedirs(specific_upload_path_on_disk, exist_ok=True) 
    
    file_path_on_disk = os.path.join(specific_upload_path_on_disk, filename)
    
    try:
        file_storage.save(file_path_on_disk)
        # Create the web-accessible path relative to the 'static' folder
        relative_path_for_web = os.path.join('uploads', subfolder, filename).replace("\\", "/")
        
        current_app.logger.info(f"File saved: {file_path_on_disk}, Web relative path: {relative_path_for_web}")
        return relative_path_for_web
    except Exception as e:
        current_app.logger.error(f"Could not save file {filename} to {file_path_on_disk}: {e}", exc_info=True)
        return None