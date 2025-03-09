import datetime
from utils.date_parser import DateTimeParser

class MeetingContext:
    """
    Class to maintain the context of a meeting scheduling conversation
    """
    
    def __init__(self):
        self.reset()
        self.active_meeting = None  # Reference to currently active meeting when multiple are in context
    
    def reset(self):
        """Reset the meeting context to default values"""
        self.date = None
        self.time = None
        self.duration = None
        self.attendees = []
        self.title = "Meeting"
        self.description = ""
        self.is_confirmed = False
        self.is_cancelled = False
        self.date_parser = DateTimeParser()
        self.conversation_history = []
        self.meeting_id = None  # Unique identifier for this meeting
        self.last_update = None  # Track what was last updated
    
    def update_from_entities(self, entities):
        """Update the meeting context based on extracted entities"""
        if 'DATE' in entities and entities['DATE']:
            # Take the last date mentioned
            date_text = entities['DATE'][-1]
            parsed_date = self.date_parser.parse_date(date_text)
            if parsed_date:
                self.date = parsed_date
                print(f"Updated date to: {self.date}")
        
        if 'TIME' in entities and entities['TIME']:
            # Take the last time mentioned
            time_text = entities['TIME'][-1]
            parsed_time = self.date_parser.parse_time(time_text)
            if parsed_time:
                self.time = parsed_time
                print(f"Updated time to: {self.time}")
        
        if 'DURATION' in entities and entities['DURATION']:
            # Take the last duration mentioned
            duration_text = entities['DURATION'][-1]
            parsed_duration = self.date_parser.parse_duration(duration_text)
            if parsed_duration:
                self.duration = parsed_duration
                print(f"Updated duration to: {self.duration}")
        
        if 'ATTENDEE' in entities and entities['ATTENDEE']:
            # Clean and deduplicate attendees
            attendee_set = set()  # Use a set to avoid duplicates
            
            for attendee in entities['ATTENDEE']:
                # Split by commas, 'and', etc.
                import re
                
                # First, clean up the attendee text
                cleaned_attendee = attendee.lower()
                
                # Filter out common non-attendee words and phrases
                non_attendee_words = ['to this', 'to the', 'to our', 'for this', 'for the', 
                                      'meeting', 'call', 'hour', 'minute', 'add', 'invite', 
                                      'include', 'with', 'and add', 'and include']
                
                for word in non_attendee_words:
                    cleaned_attendee = cleaned_attendee.replace(word, ',')
                
                # Split by commas, 'and', etc.
                attendee_list = re.split(r',|\band\b', cleaned_attendee)
                
                for person in attendee_list:
                    person = person.strip()
                    if person and len(person) > 1:  # Avoid single character names or empty strings
                        # Capitalize the first letter of each name
                        capitalized_name = person.capitalize()
                        if capitalized_name not in attendee_set:
                            attendee_set.add(capitalized_name)
                            print(f"Added attendee: {capitalized_name}")
            
            # Update the attendees list with the deduplicated set
            self.attendees = list(attendee_set)
                        
        # Check for time in text if TIME entity not detected
        # This is a fallback mechanism
        for entity_type, values in entities.items():
            for value in values:
                if "2pm" in value.lower() or "2 pm" in value.lower():
                    if not self.time:
                        self.time = self.date_parser.parse_time("2 PM")
                        print(f"Fallback: Updated time to: {self.time}")
                        
                if "hour" in value.lower() and not self.duration:
                    self.duration = 60  # 1 hour in minutes
                    print(f"Fallback: Updated duration to: {self.duration}")
    
    def is_complete(self):
        """Check if all required information is provided"""
        return (
            self.date is not None and
            self.time is not None and
            len(self.attendees) > 0
        )
    
    def get_missing_info(self):
        """Get a list of missing required information"""
        missing = []
        
        if self.date is None:
            missing.append("date")
        
        if self.time is None:
            missing.append("time")
        
        if not self.attendees:
            missing.append("attendees")
        
        return missing
    
    def to_dict(self):
        """Convert the meeting context to a dictionary"""
        return {
            'date': self.date_parser.format_date(self.date) if self.date else None,
            'time': self.date_parser.format_time(self.time) if self.time else None,
            'duration': self.date_parser.format_duration(self.duration) if self.duration else None,
            'attendees': self.attendees,
            'title': self.title,
            'description': self.description,
            'is_confirmed': self.is_confirmed,
            'is_cancelled': self.is_cancelled
        }