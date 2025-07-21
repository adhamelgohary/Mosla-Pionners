# routes/Recruiter_Team_Portal/__init__.py
from flask import Blueprint

# 1. Define the main blueprint for the entire Recruiter Portal section.
# This blueprint will be registered with the Flask app.
recruiter_bp = Blueprint('recruiter_bp', __name__,
                         url_prefix='/recruiter-portal',
                         template_folder='../../../templates')

# 2. Import the individual route modules.
# The routes are defined in their own files using their own blueprints.
from . import dashboard_routes
from . import organization_routes
from . import staff_routes
from . import jobs_routes

# 3. Register the modular blueprints onto the main recruiter_bp.
# This attaches all the routes from the other files to our main blueprint,
# preserving the URL prefix and template folder settings.
recruiter_bp.register_blueprint(dashboard_routes.dashboard_bp)
recruiter_bp.register_blueprint(organization_routes.organization_bp)
recruiter_bp.register_blueprint(staff_routes.staff_bp)
recruiter_bp.register_blueprint(jobs_routes.jobs_bp)

# 4. Also import any shared constants or functions if you have them.
# For simplicity, we'll keep constants in the files where they are most used,
# but a shared `constants.py` or `utils.py` inside this folder would also be a good pattern.