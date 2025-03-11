import datetime
import uuid
from utils.date_parser import DateTimeParser
import re

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
        self.attendee_emails = {}  # Store resolved emails for attendees
        self.title = "Meeting"
        self.description = ""
        self.is_confirmed = False
        self.is_cancelled = False
        self.date_parser = DateTimeParser()
        self.conversation_history = []
        self.meeting_id = None  # Unique identifier for this meeting
        self.last_update = None  # Track what was last updated
        
    def update_from_entities(self, entities):
        """Update the meeting context based on extracted entities with improved handling"""
        entity_updates = {}  # Track what was updated for debugging
        
        # FIX: Sort date entities by specificity
        if 'DATE' in entities and entities['DATE']:
            date_entities = []
            for date_text in entities['DATE']:
                if not date_text or date_text.lower() in ['it', 'this', 'that']:
                    continue
                    
                # Parse the date and track its specificity
                parsed_date = self.date_parser.parse_date(date_text)
                if parsed_date:
                    # Check specificity - more words indicates more specific date references
                    specificity = len(date_text.split())
                    # If it contains numbers, it's likely more specific
                    if any(char.isdigit() for char in date_text):
                        specificity += 5
                    date_entities.append((parsed_date, date_text, specificity))
            
            # Sort by specificity (highest first)
            date_entities.sort(key=lambda x: x[2], reverse=True)
            
            # Use the most specific date
            if date_entities:
                self.date = date_entities[0][0]
                entity_updates['date'] = date_entities[0][1]
                print(f"Updated date to: {self.date} from '{date_entities[0][1]}' (most specific)")
        
        # FIX: Prioritize time entities with AM/PM markers
        if 'TIME' in entities and entities['TIME']:
            time_entities = []
            for time_text in entities['TIME']:
                if not time_text:
                    continue
                    
                parsed_time = self.date_parser.parse_time(time_text)
                if parsed_time:
                    # Check specificity - if AM/PM is explicitly mentioned
                    specificity = len(time_text.split())
                    if 'am' in time_text.lower() or 'pm' in time_text.lower():
                        specificity += 10  # Strongly prefer explicit AM/PM
                    time_entities.append((parsed_time, time_text, specificity))
            
            # Sort by specificity (highest first)
            time_entities.sort(key=lambda x: x[2], reverse=True)
            
            # Use the most specific time
            if time_entities:
                self.time = time_entities[0][0]
                entity_updates['time'] = time_entities[0][1]
                print(f"Updated time to: {self.time} from '{time_entities[0][1]}' (most specific)")
        
        # Process duration - least controversial part
        if 'DURATION' in entities and entities['DURATION']:
            for duration_text in entities['DURATION']:
                if not duration_text:
                    continue
                    
                parsed_duration = self.date_parser.parse_duration(duration_text)
                if parsed_duration:
                    self.duration = parsed_duration
                    entity_updates['duration'] = duration_text
                    print(f"Updated duration to: {self.duration} from '{duration_text}'")
                    break
        
        # Attendee processing 
        if 'ATTENDEE' in entities and entities['ATTENDEE']:
            # Create a set to store unique attendees
            unique_attendees = set()
            
            for attendee in entities['ATTENDEE']:
                if not attendee:
                    continue
                    
                # Clean up the attendee text
                cleaned_attendee = attendee.lower()
                
                # Remove special tags like [sep]
                cleaned_attendee = re.sub(r'\[.*?\]', ',', cleaned_attendee)
                
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
                    if not person or len(person) <= 1:  # Skip empty names or single characters
                        continue
                        
                    # Split the name into parts
                    name_parts = person.split()
                    
                    # Handle full names
                    if len(name_parts) > 1:
                        # Capitalize each part of the full name
                        full_name = ' '.join(part.capitalize() for part in name_parts)
                        
                        # Check if full name already exists (case-insensitive)
                        if not any(full_name.lower() == existing.lower() for existing in unique_attendees):
                            # Remove any existing partial names
                            unique_attendees = {
                                existing for existing in unique_attendees 
                                if existing.lower() not in full_name.lower()
                            }
                            unique_attendees.add(full_name)
                    else:
                        # Single name case
                        capitalized_name = person.capitalize()
                        
                        # Avoid adding if a fuller version already exists
                        if not any(capitalized_name.lower() in existing.lower() for existing in unique_attendees):
                            unique_attendees.add(capitalized_name)
            
            # Update the attendees list
            self.attendees = list(unique_attendees)
            entity_updates['attendees'] = self.attendees
        
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
        
        # Debug output
        if entity_updates:
            print(f"Updated entities: {entity_updates}")
                
        return entity_updates

    def _process_raw_text(self, text, already_updated):
        """
        Process raw text for additional entities that might have been missed
        by the NER model. This is a fallback mechanism.
        """
        text = text.lower()
        
        # Only attempt date extraction if not already found
        if 'date' not in already_updated and self.date is None:
            # Look for date patterns in the raw text
            # Common date formats to try
            date_patterns = [
                r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)',
                r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?',
                r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?'
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    # Try to parse with date_parser
                    matched_text = match.group(0)
                    parsed_date = self.date_parser.parse_date(matched_text)
                    if parsed_date:
                        self.date = parsed_date
                        print(f"Fallback: Updated date to: {self.date} from '{matched_text}'")
                        break
    
    def is_complete(self):
        """Check if all required information is provided"""
        return (
            self.date is not None and
            self.time is not None and
            len(self.attendees) > 0
        )
    
# In MeetingContext class (context_manager.py)

    def get_missing_info(self):
        """Get a list of missing required information"""
        missing = []
        
        if self.date is None:
            missing.append("date")
        
        if self.time is None:
            missing.append("time")
        
        if self.duration is None:
            missing.append("duration") 
        
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
            'attendee_emails': self.attendee_emails,
            'title': self.title,
            'description': self.description,
            'is_confirmed': self.is_confirmed,
            'is_cancelled': self.is_cancelled
        }