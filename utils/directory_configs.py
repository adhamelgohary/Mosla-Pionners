# utils/directory_configs.py
import os
from werkzeug.utils import secure_filename
from flask import current_app

def configure_directories(app):
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    subfolders_to_create = [
        'candidate_applications/cv',
        'candidate_applications/voice', # Ensure this exists or can be created
        'candidate_cvs',
        'staff_profile_pics',
        'company_logos',
        'general'
    ]
    for subfolder_group in subfolders_to_create: # Create base subfolders
        base_path_parts = subfolder_group.split('/')
        # Create only the top-level parts here, the dynamic <candidate_id> part will be handled by save_file
        if base_path_parts:
             os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], base_path_parts[0]), exist_ok=True)
             if len(base_path_parts) > 1: # e.g. candidate_applications/cv
                 os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], base_path_parts[0], base_path_parts[1]), exist_ok=True)


    app.logger.info(f"UPLOAD_FOLDER configured at: {app.config['UPLOAD_FOLDER']}")
    app.logger.info("Essential directories configured.")

def save_file_from_config(file_storage, subfolder='general', filename_override=None):
    if not current_app:
        raise RuntimeError("Flask current_app context is not available.")
    upload_folder_base = current_app.config.get('UPLOAD_FOLDER')
    if not upload_folder_base:
        current_app.logger.error("UPLOAD_FOLDER is not configured.")
        return None

    if file_storage and (file_storage.filename or filename_override): # Check filename from storage or override
        # Use override if provided, otherwise use the FileStorage's filename
        # Ensure the override is also secured.
        original_filename = file_storage.filename if file_storage.filename else "blob" # Get original if available
        
        if filename_override:
            base_filename_to_secure = filename_override
        elif original_filename:
            base_filename_to_secure = original_filename
        else: # Should not happen if validation is correct, but as a fallback
            current_app.logger.warning("No filename or override provided for file storage.")
            return None

        filename = secure_filename(base_filename_to_secure)
        
        # Construct the full path for the specific subfolder, including dynamic parts like candidate_id
        # The subfolder argument can now be like 'candidate_applications/voice/123'
        specific_upload_path_on_disk = os.path.join(upload_folder_base, subfolder)
        os.makedirs(specific_upload_path_on_disk, exist_ok=True) 
        
        file_path_on_disk = os.path.join(specific_upload_path_on_disk, filename)
        
        try:
            file_storage.save(file_path_on_disk)
            # Web-accessible path starts from 'uploads' as UPLOAD_FOLDER is 'static/uploads'
            relative_path_for_web = os.path.join('uploads', subfolder, filename).replace("\\", "/")
            
            current_app.logger.info(f"File saved: {file_path_on_disk}, Web relative path: {relative_path_for_web}")
            return relative_path_for_web
        except Exception as e:
            current_app.logger.error(f"Error saving file {filename} to {file_path_on_disk}: {e}", exc_info=True)
            return None
    elif file_storage and not file_storage.filename and not filename_override:
        current_app.logger.warning("FileStorage object received but has no filename and no override provided.")
    return None