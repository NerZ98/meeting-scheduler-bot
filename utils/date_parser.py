import re
import datetime
from dateutil.relativedelta import relativedelta
from dateutil import parser

class DateTimeParser:
    """
    Utility class to parse date and time expressions from natural language
    """
    
    def __init__(self):
        # Current date/time as reference
        self.reference_date = datetime.datetime.now()
        
        # Common time patterns
        self.time_patterns = {
            r'(\d{1,2})\s*(?::|\.)\s*(\d{2})\s*([ap]\.?m\.?)?': self._parse_time_with_minutes,
            r'(\d{1,2})\s*([ap]\.?m\.?)?': self._parse_hour_only,
            r'(?:at\s+)?noon': lambda _: datetime.time(12, 0),
            r'(?:at\s+)?midnight': lambda _: datetime.time(0, 0),
            r'morning': lambda _: datetime.time(9, 0),
            r'afternoon': lambda _: datetime.time(14, 0),
            r'evening': lambda _: datetime.time(18, 0),
            r'night': lambda _: datetime.time(20, 0),
        }
        
        # Common date patterns
        self.date_patterns = {
            r'today': self._parse_today,
            r'tomorrow': self._parse_tomorrow,
            r'day after tomorrow': self._parse_day_after_tomorrow,
            r'next (\w+)': self._parse_next_day,
            r'this (\w+)': self._parse_this_day,
            r'(\d{1,2})(?:st|nd|rd|th)? (?:of\s+)?(\w+)(?:\s+(\d{4}))?': self._parse_day_month_year,
            r'(\w+) (\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?': self._parse_month_day_year,
            r'next week': self._parse_next_week,
            r'next month': self._parse_next_month,
        }
        
        # Common duration patterns
        self.duration_patterns = {
            r'(\d+)\s*(?:hour|hr)s?': lambda match: int(match.group(1)) * 60,
            r'(\d+)\s*(?:minute|min)s?': lambda match: int(match.group(1)),
            r'half an hour': lambda _: 30,
            r'an hour and a half': lambda _: 90,
            r'(\d+)\s*and a half\s*hours?': lambda match: int(match.group(1)) * 60 + 30,
            r'quarter of an hour': lambda _: 15,
        }
        
        # Day of week mapping
        self.day_of_week = {
            'monday': 0, 'mon': 0,
            'tuesday': 1, 'tue': 1, 'tues': 1,
            'wednesday': 2, 'wed': 2,
            'thursday': 3, 'thu': 3, 'thurs': 3,
            'friday': 4, 'fri': 4,
            'saturday': 5, 'sat': 5,
            'sunday': 6, 'sun': 6
        }
        
        # Month mapping
        self.month_mapping = {
            'january': 1, 'jan': 1,
            'february': 2, 'feb': 2,
            'march': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'may': 5,
            'june': 6, 'jun': 6,
            'july': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12
        }
    
    def _parse_time_with_minutes(self, match):
        hour = int(match.group(1))
        minute = int(match.group(2))
        am_pm = match.group(3)
        
        if am_pm and ('p' in am_pm.lower()) and hour < 12:
            hour += 12
        elif am_pm and ('a' in am_pm.lower()) and hour == 12:
            hour = 0
        
        return datetime.time(hour, minute)
    
    def _parse_hour_only(self, match):
        hour = int(match.group(1))
        am_pm = match.group(2)
        
        if am_pm and ('p' in am_pm.lower()) and hour < 12:
            hour += 12
        elif am_pm and ('a' in am_pm.lower()) and hour == 12:
            hour = 0
            
        return datetime.time(hour, 0)
    
    def _parse_today(self, _):
        return self.reference_date.date()
    
    def _parse_tomorrow(self, _):
        return (self.reference_date + datetime.timedelta(days=1)).date()
    
    def _parse_day_after_tomorrow(self, _):
        return (self.reference_date + datetime.timedelta(days=2)).date()
    
    def _parse_next_day(self, match):
        day_name = match.group(1).lower()
        if day_name not in self.day_of_week:
            # Try fallback to dateutil parser
            try:
                return parser.parse(f"next {day_name}").date()
            except:
                return None
        
        target_weekday = self.day_of_week[day_name]
        current_weekday = self.reference_date.weekday()
        days_ahead = target_weekday - current_weekday
        
        if days_ahead <= 0:  # Target is today or earlier in the week
            days_ahead += 7
            
        return (self.reference_date + datetime.timedelta(days=days_ahead)).date()
    
    def _parse_this_day(self, match):
        day_name = match.group(1).lower()
        if day_name not in self.day_of_week:
            # Try fallback to dateutil parser
            try:
                return parser.parse(f"this {day_name}").date()
            except:
                return None
                
        target_weekday = self.day_of_week[day_name]
        current_weekday = self.reference_date.weekday()
        days_ahead = target_weekday - current_weekday
        
        if days_ahead < 0:  # Target day already passed this week
            days_ahead += 7
            
        return (self.reference_date + datetime.timedelta(days=days_ahead)).date()
    
    def _parse_day_month_year(self, match):
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year_str = match.group(3)
        
        # Get month number
        if month_name in self.month_mapping:
            month = self.month_mapping[month_name]
        else:
            # Try fallback
            try:
                parsed_date = parser.parse(month_name)
                month = parsed_date.month
            except:
                return None
        
        # Get year
        if year_str:
            year = int(year_str)
        else:
            year = self.reference_date.year
            
        # Handle future/past for current year
        if month < self.reference_date.month and not year_str:
            year += 1
            
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None
    
    def _parse_month_day_year(self, match):
        month_name = match.group(1).lower()
        day = int(match.group(2))
        year_str = match.group(3)
        
        # Get month number
        if month_name in self.month_mapping:
            month = self.month_mapping[month_name]
        else:
            # Try fallback
            try:
                parsed_date = parser.parse(month_name)
                month = parsed_date.month
            except:
                return None
        
        # Get year
        if year_str:
            year = int(year_str)
        else:
            year = self.reference_date.year
            
        # Handle future/past for current year
        if month < self.reference_date.month and not year_str:
            year += 1
            
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None
    
    def _parse_next_week(self, _):
        # Return the same day next week
        return (self.reference_date + datetime.timedelta(weeks=1)).date()
    
    def _parse_next_month(self, _):
        return (self.reference_date + relativedelta(months=1)).date()
    
    def parse_date(self, text):
        """Parse a date from natural language text"""
        if not text:
            return None
            
        text = text.lower().strip()
        
        # Try each pattern
        for pattern, parser_func in self.date_patterns.items():
            match = re.search(pattern, text)
            if match:
                return parser_func(match)
        
        # Fallback to dateutil parser
        try:
            parsed_date = parser.parse(text, fuzzy=True)
            return parsed_date.date()
        except:
            return None
    
    def parse_time(self, text):
        """Parse a time from natural language text"""
        if not text:
            return None
            
        text = text.lower().strip()
        
        # Try each pattern
        for pattern, parser_func in self.time_patterns.items():
            match = re.search(pattern, text)
            if match:
                return parser_func(match)
        
        # Fallback to dateutil parser
        try:
            parsed_time = parser.parse(text, fuzzy=True)
            return parsed_time.time()
        except:
            return None
    
    def parse_duration(self, text):
        """Parse a duration (in minutes) from natural language text"""
        if not text:
            return None
            
        text = text.lower().strip()
        total_minutes = 0
        
        # Try each pattern
        for pattern, parser_func in self.duration_patterns.items():
            match = re.search(pattern, text)
            if match:
                return parser_func(match)
        
        # Check for hour+minute combo
        hour_min_pattern = r'(\d+)\s*(?:hour|hr)s?\s*(?:and\s+)?(\d+)\s*(?:min|minute)s?'
        match = re.search(hour_min_pattern, text)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            return hours * 60 + minutes
        
        # Default to 30 minutes if we just have "meeting" or similar
        if 'meeting' in text or 'call' in text:
            return 30
            
        return None
    
    def format_date(self, date_obj):
        """Format a date object for display"""
        if not date_obj:
            return None
            
        today = self.reference_date.date()
        tomorrow = (self.reference_date + datetime.timedelta(days=1)).date()
        
        if date_obj == today:
            return "Today"
        elif date_obj == tomorrow:
            return "Tomorrow"
        elif (date_obj - today).days < 7:
            # Check if we're on Windows (which doesn't support %-d format)
            import platform
            is_windows = platform.system() == 'Windows'
            
            if is_windows:
                return date_obj.strftime("%A")  # Day name
            else:
                return date_obj.strftime("%A")  # Day name
        else:
            # Check if we're on Windows (which doesn't support %-d format)
            import platform
            is_windows = platform.system() == 'Windows'
            
            if is_windows:
                return date_obj.strftime("%B %#d, %Y")  # Month Day, Year (Windows format)
            else:
                return date_obj.strftime("%B %-d, %Y")  # Month Day, Year (Unix format)
    
    def format_time(self, time_obj):
        """Format a time object for display"""
        if not time_obj:
            return None
            
        # Check if we're on Windows (which doesn't support %-I format)
        import platform
        is_windows = platform.system() == 'Windows'
            
        if time_obj.minute == 0:
            if is_windows:
                return time_obj.strftime("%#I %p").lower()  # 2 pm (Windows format)
            else:
                return time_obj.strftime("%-I %p").lower()  # 2 pm (Unix format)
        else:
            if is_windows:
                return time_obj.strftime("%#I:%M %p").lower()  # 2:30 pm (Windows format)
            else:
                return time_obj.strftime("%-I:%M %p").lower()  # 2:30 pm (Unix format)
    
    def format_duration(self, minutes):
        """Format a duration in minutes for display"""
        if not minutes:
            return None
            
        hours, mins = divmod(minutes, 60)
        
        if hours == 0:
            return f"{mins} minutes"
        elif hours == 1 and mins == 0:
            return "1 hour"
        elif mins == 0:
            return f"{hours} hours"
        else:
            return f"{hours} hour{'s' if hours > 1 else ''} and {mins} minutes"

# Helper function for easy access
def parse_datetime_info(text):
    """
    Parse date, time, and duration from text
    Returns a tuple of (date, time, duration)
    """
    parser = DateTimeParser()
    
    date_obj = parser.parse_date(text)
    time_obj = parser.parse_time(text)
    duration_minutes = parser.parse_duration(text)
    
    return date_obj, time_obj, duration_minutes