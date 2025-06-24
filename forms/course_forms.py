# forms/course_forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, DateField, BooleanField, SubmitField, URLField
from wtforms.validators import DataRequired, Length, Optional, NumberRange, URL, ValidationError # Added ValidationError

class AddCourseForm(FlaskForm):
    course_name = StringField('Course Name', validators=[DataRequired(), Length(max=255)])
    description = TextAreaField('Description', validators=[Optional()])
    duration = StringField('Duration (e.g., 4 Weeks, 30 Hours)', validators=[Optional(), Length(max=100)])
    price = DecimalField('Price', validators=[Optional(), NumberRange(min=0)], places=2)
    currency = StringField('Currency (e.g., USD, EGP)', default='USD', validators=[Optional(), Length(max=10)])
    instructor_name = StringField('Instructor Name', validators=[Optional(), Length(max=255)])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])
    category = StringField('Category (e.g., Sales, CS)', validators=[Optional(), Length(max=100)])
    prerequisites = TextAreaField('Prerequisites', validators=[Optional()])
    syllabus_link = URLField('Syllabus Link (Optional)', validators=[Optional(), URL(), Length(max=255)])
    is_active = BooleanField('Publish Course (Active)', default=True)
    submit = SubmitField('Add Course')

    # Custom validator for end_date
    def validate_end_date(self, end_date_field): # Renamed 'field' to 'end_date_field' for clarity
        if self.start_date.data and end_date_field.data: # Check if both dates are provided
            if end_date_field.data < self.start_date.data:
                raise ValidationError('End date must not be earlier than start date.')

# You might add an EditCourseForm later, often inheriting from AddCourseForm