# forms/auth_forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField, FileField, TextAreaField, URLField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, ValidationError
from flask_wtf.file import FileAllowed # For file uploads

# You might want to create a User model later to check for existing emails
# from models.user import User # Placeholder

class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me') # This is the crucial field
    submit = SubmitField('Log In')

class RegistrationFormBase(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=100)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    phone_number = StringField('Phone Number', validators=[Optional(), Regexp(r'^\+?[0-9\s\-]{7,20}$', message="Invalid phone number format")])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    profile_picture = FileField('Profile Picture (Optional)', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png'], 'Images only!')
    ])

    # def validate_email(self, email):
    #     # user = User.query.filter_by(email=email.data).first()
    #     # if user:
    #     #     raise ValidationError('That email is already taken. Please choose a different one.')
    #     pass # Placeholder for DB check

class CandidateRegistrationForm(RegistrationFormBase):
    # Candidate-specific fields
    cv = FileField('Resume/CV', validators=[
        DataRequired(message="CV is required for candidates."),
        FileAllowed(['pdf', 'doc', 'docx'], 'PDF or Word documents only!')
    ])
    linkedin_profile_url = URLField('LinkedIn Profile URL (Optional)', validators=[Optional(), Length(max=255)])
    # Add other candidate-specific fields from your DB schema as needed
    # e.g., years_of_experience, expected_salary, etc.
    submit = SubmitField('Create Candidate Account')

class ClientRegistrationForm(RegistrationFormBase):
    company_name = StringField('Company Name', validators=[DataRequired(), Length(min=2, max=255)])
    company_website = URLField('Company Website', validators=[DataRequired(), Length(max=255)])
    company_size = SelectField('Company Size', choices=[
        ('', 'Select Company Size'),
        ('1-10', '1-10 employees'),
        ('11-50', '11-50 employees'),
        ('51-200', '51-200 employees'),
        ('201-1000', '201-1,000 employees'),
        ('1001+', '1,001+ employees')
    ], validators=[DataRequired()])
    company_logo = FileField('Company Logo (Optional)', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'svg'], 'Images only!')
    ])
    # contact_name is covered by first_name, last_name
    # work_email is covered by email
    submit = SubmitField('Create Company Account')


class RecruiterRegistrationForm(RegistrationFormBase):
    # Recruiter-specific fields
    linkedin_profile_url = URLField('LinkedIn Profile URL (Optional)', validators=[Optional(), Length(max=255)])
    cv = FileField('Resume/CV (Optional)', validators=[ # Making CV optional for recruiters for now
        Optional(),
        FileAllowed(['pdf', 'doc', 'docx'], 'PDF or Word documents only!')
    ])
    # Specialization might be a dropdown or free text depending on requirements
    specialization = StringField('Specialization (e.g., Tech Sourcing)', validators=[Optional(), Length(max=255)])
    bio = TextAreaField('Short Bio (Optional)', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Apply as Recruiter')