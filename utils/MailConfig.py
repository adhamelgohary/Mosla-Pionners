# utils/MailConfig.py
import os

class MailConfig:
    @staticmethod
    def init_app(app):
        """Initializes Flask app with mail configuration settings."""
        app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
        app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587)) # Gmail uses 587 for TLS
        app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1', 't']
        app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() in ['true', '1', 't']
        app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME') # e.g., your_email@gmail.com
        app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD') # e.g., your_app_password for Gmail
        app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])
        # For Gmail, you might need to enable "Less secure app access"
        # or use an "App Password" if 2-Step Verification is enabled.

        if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
            app.logger.warning("MAIL_USERNAME or MAIL_PASSWORD not set. Email sending will likely fail.")