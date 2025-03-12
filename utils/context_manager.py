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
        
    def update_from_entities(self, entities, user_message=''):
        """
        Comprehensive method to update meeting context from extracted entities
        with robust parsing, filtering, and intelligent processing
        
        Args:
            entities (dict): Extracted entities from the NER model
            user_message (str, optional): Original user message for additional context
        
        Returns:
            dict: Updates made to the meeting context
        """
        import re
        entity_updates = {}

        # Exclude words and tokens that shouldn't be considered for various entity types
        EXCLUDE_WORDS = {
            'attendees': {
                'min', 'at', 'for', 'the', 'a', 'an', 'this', 'that', 
                'make', 'sure', 'also', 'please', 'with', 'call', 
                'meeting', 'schedule', 'duration', 'tomorrow', 'today', 
                'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 
                'saturday', 'sunday', 'to', 'it', 'yes', 'no', 'ok', 
                'okay', 'sure', 'confirm', 'correct', 'sep', 'cls', 
                'pm', 'am', '.'
            },
            'time': {
                'meeting', 'schedule', 'tomorrow', 'today', 
                'add', 'please', 'with', 'for', 'invite'
            },
            'date': {
                'meeting', 'schedule', 'at', 'pm', 'am', 
                'add', 'please', 'with', 'for', 'invite'
            }
        }

        # Action words that should never be part of an entity
        ACTION_WORDS = {
            'add', 'invite', 'include', 'get', 'bring', 
            'ask', 'call', 'schedule', 'book', 'arrange'
        }

        def clean_entity_text(text, entity_type='attendees'):
            """
            Clean and validate entity text based on type
            
            Args:
                text (str): Text to clean
                entity_type (str): Type of entity being cleaned
            
            Returns:
                str or None: Cleaned text
            """
            # Remove special tokens and markers
            text = re.sub(r'\[.*?\]', '', text).strip()
            
            # Remove problematic tokens
            text = re.sub(r'\b(Pm\b|Am\b|\.)', '', text).strip()
            
            # Convert to list of words
            words = text.lower().split()
            
            # Filter out excluded words and action words
            valid_words = [
                word for word in words 
                if word not in EXCLUDE_WORDS.get(entity_type, set()) 
                and word not in ACTION_WORDS
            ]
            
            # Reconstruct cleaned text
            cleaned_text = ' '.join(valid_words)
            
            # Capitalize words
            return ' '.join(word.capitalize() for word in cleaned_text.split()) if cleaned_text else None

        def extract_duration(entities, text):
            """
            Extract duration from entities or text
            
            Args:
                entities (dict): Extracted entities
                text (str): Original user message
            
            Returns:
                int or None: Duration in minutes
            """
            # Predefined duration mappings
            duration_map = {
                '30 min': 30,
                '45 min': 45,
                '1 hour': 60,
                '60 min': 60,
                '1.5 hours': 90,
                '90 min': 90,
                '2 hours': 120
            }
            
            # Check entities first
            if 'DURATION' in entities and entities['DURATION']:
                for duration_text in entities['DURATION']:
                    cleaned_duration = clean_entity_text(duration_text)
                    if cleaned_duration:
                        parsed_duration = self.date_parser.parse_duration(cleaned_duration)
                        if parsed_duration:
                            return parsed_duration
            
            # Fallback to text parsing
            if text:
                # Direct text parsing
                parsed_duration = self.date_parser.parse_duration(text)
                if parsed_duration:
                    return parsed_duration
                
                # Specific patterns
                duration_patterns = [
                    r'(\d+)-minute\s*meeting',
                    r'(\d+)\s*(?:hour|hr)s?\s*meeting',
                    r'(\d+)\s*min\s*meeting'
                ]
                
                for pattern in duration_patterns:
                    match = re.search(pattern, text.lower())
                    if match:
                        return int(match.group(1))
            
            # Contextual defaults
            return None

        # Process DATE entities
        if 'DATE' in entities and entities['DATE']:
            date_candidates = []
            for date_text in entities['DATE']:
                cleaned_date = clean_entity_text(date_text, 'date')
                if cleaned_date:
                    parsed_date = self.date_parser.parse_date(cleaned_date)
                    if parsed_date:
                        # Calculate specificity
                        specificity = (
                            len(date_text.split()) + 
                            (5 if any(char.isdigit() for char in date_text) else 0)
                        )
                        date_candidates.append((parsed_date, specificity, date_text))
            
            # Select most specific date
            if date_candidates:
                self.date = max(date_candidates, key=lambda x: x[1])[0]
                entity_updates['date'] = date_text  # Store original text for reference
                print(f"Updated date to: {self.date} from {date_text}")

        # Process TIME entities
        if 'TIME' in entities and entities['TIME']:
            time_candidates = []
            for time_text in entities['TIME']:
                cleaned_time = clean_entity_text(time_text, 'time')
                if cleaned_time:
                    parsed_time = self.date_parser.parse_time(cleaned_time)
                    if parsed_time:
                        # Calculate time specificity
                        specificity = (
                            10 if 'am' in time_text.lower() or 'pm' in time_text.lower() else 0 +
                            5 if ':' in time_text else 0 +
                            len(time_text.split())
                        )
                        time_candidates.append((parsed_time, time_text, specificity))
            
            # Select most specific time
            if time_candidates:
                self.time = max(time_candidates, key=lambda x: x[2])[0]
                entity_updates['time'] = time_text
                print(f"Updated time to: {self.time} from {time_text}")

        # Process DURATION entities
        duration = extract_duration(entities, user_message)
        if duration:
            self.duration = duration
            entity_updates['duration'] = duration
            print(f"Updated duration to: {duration} minutes")

        # Process ATTENDEE entities with advanced filtering
        if 'ATTENDEE' in entities and entities['ATTENDEE']:
            unique_attendees = set()
            full_names = []
            partial_names = []

            for attendee_text in entities['ATTENDEE']:
                # Clean and validate attendee name
                cleaned_name = clean_entity_text(attendee_text)
                
                if cleaned_name:
                    # Distinguish between full and partial names
                    if ' ' in cleaned_name:
                        full_names.append(cleaned_name)
                    else:
                        partial_names.append(cleaned_name)

            # Prioritize full names
            for full_name in full_names:
                name_parts = full_name.split()
                unique_attendees.add(full_name)
                
                # Remove partial names that are part of this full name
                partial_names = [p for p in partial_names if p not in name_parts]

            # Add remaining unique partial names
            unique_attendees.update(partial_names)

            # Update attendees
            self.attendees = list(unique_attendees)
            entity_updates['attendees'] = self.attendees

            # Debugging
            print(f"DEBUG: Final attendee list: {self.attendees}")

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