# utils/template_helpers.py
import datetime
import decimal
import re
from markupsafe import Markup, escape # For safe HTML rendering

# --- Date and Time Formatters ---
def format_datetime(value, format="%Y-%m-%d %H:%M:%S"):
    """Format a datetime object to a string. Handles None."""
    if not isinstance(value, (datetime.datetime, datetime.date)):
        return "" # Or "N/A", or raise error, or try to parse
    if value is None:
        return ""
    return value.strftime(format)

def format_date(value, format="%Y-%m-%d"):
    """Format a date object or datetime object to a date string. Handles None."""
    if not isinstance(value, (datetime.datetime, datetime.date)):
        return ""
    if value is None:
        return ""
    return value.strftime(format)

def friendly_date(value, format="%B %d, %Y"): # e.g., "June 15, 2024"
    """Formats date to a more human-readable string."""
    return format_date(value, format)

def time_ago(timestamp):
    """Converts a datetime object or UNIX timestamp to a human-readable 'time ago' string."""
    if not timestamp:
        return "Never"

    now = datetime.datetime.now(datetime.timezone.utc) # Always use UTC for 'now' in this context

    if isinstance(timestamp, (int, float)): # Assuming UNIX timestamp
        timestamp = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
    elif isinstance(timestamp, datetime.datetime):
        if timestamp.tzinfo is None: # If naive, assume it's UTC
            timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
        else: # Convert to UTC if it's aware but not UTC
            timestamp = timestamp.astimezone(datetime.timezone.utc)
    else: # Not a recognized timestamp type
        return "Invalid date"


    diff = now - timestamp
    seconds = diff.total_seconds()

    if seconds < 0:
        # Handle future dates more gracefully
        # For example, show the date or "in X days"
        days_future = abs(int(seconds / 86400))
        if days_future == 0:
            return "Later today"
        elif days_future == 1:
            return "Tomorrow"
        else:
            return f"In {days_future} days" # Or format_date(timestamp)
        # return "In the future" # Original
    elif seconds < 5:
        return "Just now"
    elif seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif seconds < 3600: # < 1 hour
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif seconds < 86400: # < 1 day
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif seconds < 604800: # < 7 days
        days = int(seconds / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"
    elif seconds < 2592000: # < 30 days (approx)
        weeks = int(seconds / 604800)
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif seconds < 31536000: # < 1 year
        months = int(seconds / 2592000)
        return f"{months} month{'s' if months > 1 else ''} ago"
    else:
        years = int(seconds / 31536000)
        return f"{years} year{'s' if years > 1 else ''} ago"

# --- Text Formatters and Utilities ---
def nl2br(value):
    """Converts newlines in a string to HTML <br> tags."""
    if not isinstance(value, str):
        return value
    return Markup(escape(value).replace('\r\n', '<br>\n').replace('\n', '<br>\n').replace('\r', '<br>\n'))

def truncate_text(text, length=100, suffix='...'):
    """Truncates text to a specified length, adding a suffix if truncated."""
    if not isinstance(text, str):
        return text
    if len(text) <= length:
        return text
    else:
        return text[:length].rsplit(' ', 1)[0] + suffix # Try to cut at word boundary

def strip_html_tags(html_string):
    """Removes HTML tags from a string."""
    if not isinstance(html_string, str):
        return html_string
    clean = re.compile('<.*?>')
    return Markup(re.sub(clean, '', html_string)).unescape() # Use Markup.unescape for & etc.

def to_title_case(value):
    """Converts a string to title case."""
    if not isinstance(value, str):
        return value
    return value.title()

def to_sentence_case(value):
    """Converts a string to sentence case (first letter capitalized)."""
    if not isinstance(value, str) or not value:
        return value
    return value[0].upper() + value[1:].lower()


# --- Number Formatters ---
def format_currency(value, currency_symbol='EGP', decimal_places=2, show_symbol_first=True):
    """Formats a number as currency. Handles None and non-numeric input gracefully."""
    if value is None:
        return "N/A" # Or "" or "0.00"
    try:
        num_value = decimal.Decimal(value)
        formatted_num = f"{num_value:,.{decimal_places}f}"
        if show_symbol_first:
            return f"{currency_symbol} {formatted_num}"
        else:
            return f"{formatted_num} {currency_symbol}"
    except (ValueError, decimal.InvalidOperation, TypeError):
        return str(value) # Return original if not a valid number

def format_percentage(value, decimal_places=1):
    """Formats a number as a percentage string. Assumes value is 0.0 to 1.0 or 0 to 100."""
    if value is None:
        return "N/A"
    try:
        num_value = float(value)
        # If value is already a percentage (e.g., 75 for 75%)
        # if num_value > 1 and num_value <= 100: # Heuristic
        #     pass # Already a percentage
        # else: # Assume it's a fraction (0.75 for 75%)
        #     num_value *= 100
        # Simpler: assume it's passed as a ready percentage value.
        return f"{num_value:.{decimal_places}f}%"
    except (ValueError, TypeError):
        return str(value)

# --- List/Dictionary Utilities ---
def get_dict_value(dictionary, key, default=None):
    """Safely get a value from a dictionary, returning a default if key is missing."""
    if not isinstance(dictionary, dict):
        return default
    return dictionary.get(key, default)

def list_join(value_list, separator=', '):
    """Joins a list of items into a string with a separator."""
    if not isinstance(value_list, (list, tuple)):
        return str(value_list)
    return separator.join(map(str, value_list))

# --- Conditional Class Helper ---
def active_class(condition, class_name="active"):
    """Returns the class_name if the condition is true, otherwise an empty string."""
    return class_name if condition else ""

# --- Miscellaneous ---
def get_current_year():
    return datetime.datetime.now().year

def default_if_none(value, default_value="N/A"):
    """Returns a default value if the input value is None."""
    return default_value if value is None else value

# --- Registration Function ---
def register_template_helpers(app):
    """Registers custom filters and context processors with the Flask app."""
    
    # Register Jinja Filters
    app.jinja_env.filters['datetime'] = format_datetime
    app.jinja_env.filters['date'] = format_date
    app.jinja_env.filters['friendlydate'] = friendly_date
    app.jinja_env.filters['timeago'] = time_ago
    app.jinja_env.filters['nl2br'] = nl2br
    app.jinja_env.filters['truncate'] = truncate_text
    app.jinja_env.filters['striptags'] = strip_html_tags
    app.jinja_env.filters['titlecase'] = to_title_case
    app.jinja_env.filters['sentencecase'] = to_sentence_case
    app.jinja_env.filters['currency'] = format_currency
    app.jinja_env.filters['percentage'] = format_percentage
    app.jinja_env.filters['get'] = get_dict_value # For dicts: my_dict|get('key', 'default')
    app.jinja_env.filters['joinlist'] = list_join
    app.jinja_env.filters['default'] = default_if_none # Overwrites Jinja's default filter, be careful. Maybe name it 'none_to_default'


    # Register Context Processors (available in all templates globally)
    @app.context_processor
    def inject_utility_functions():
        return dict(
            current_year=get_current_year(),
            datetime_now=datetime.datetime.now,         # Access as {{ datetime_now() }}
            utc_datetime_now=lambda: datetime.datetime.now(datetime.timezone.utc), # Access as {{ utc_datetime_now() }}
            active_class=active_class,                  # Use as: class="{{ active_class(condition) }}"
            # You can add more simple constants or functions here
            # SITE_NAME="Mosla Pioneers", # Example constant
        )

    # Make some functions available directly in templates as global functions (alternative to context_processor for functions)
    # app.jinja_env.globals.update(
    #     format_currency=format_currency, # Use as {{ format_currency(value, 'USD') }}
    #     # Be selective with globals to avoid polluting the namespace
    # )

    app.logger.info("Custom template helpers and filters registered.")