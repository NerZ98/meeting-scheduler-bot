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
                    
                # Skip if it looks like it has a parsing issue (like "at 1 :pm" which should be "at 1pm")
                if ':' in time_text and ' :' in time_text:
                    continue
                    
                parsed_time = self.date_parser.parse_time(time_text)
                if parsed_time:
                    # Calculate specificity score - prioritize complete time expressions
                    specificity = 0
                    
                    # Having a colon (like "1:30") increases specificity
                    if ':' in time_text:
                        specificity += 5
                    
                    # Having AM/PM explicitly mentioned is highest priority
                    if 'am' in time_text.lower() or 'pm' in time_text.lower():
                        specificity += 15
                        
                    # Having minutes specified increases specificity
                    minute_pattern = r':\d{2}'
                    if re.search(minute_pattern, time_text):
                        specificity += 8
                        
                    # Having "at" prefix makes it more likely to be a valid time reference
                    if time_text.lower().startswith('at'):
                        specificity += 3
                    
                    # Length of text (more detailed expressions get higher score)
                    specificity += len(time_text.split())
                    
                    # Check if this time seems reasonable for a meeting (7am-10pm)
                    hour = parsed_time.hour
                    if 7 <= hour <= 22:
                        specificity += 2  # Slightly prefer business hours
                    
                    time_entities.append((parsed_time, time_text, specificity))
            
            # Sort by specificity (highest first)
            time_entities.sort(key=lambda x: x[2], reverse=True)
            
            # Print debug info for all time candidates
            print("DEBUG: Time candidates sorted by specificity:")
            for time, text, score in time_entities:
                print(f"  - '{text}' -> {time} (score: {score})")
            
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
        
        # CRITICAL FIX: Improved attendee filtering with rigorous validation and action word filtering
        if 'ATTENDEE' in entities and entities['ATTENDEE']:
            # Start with existing attendees (if any)
            unique_attendees = set(self.attendees) if hasattr(self, 'attendees') else set()
            
            # Debug: print existing attendees
            print(f"DEBUG: Existing attendees before update: {unique_attendees}")
            
            # Define words that should never be attendees
            non_attendee_words = [
                'min', 'at', 'for', 'the', 'a', 'an', 'this', 'that', 'make', 'sure', 
                'also', 'please', 'with', 'call', 'meeting', 'schedule', 'duration',
                'tomorrow', 'today', 'monday', 'tuesday', 'wednesday', 'thursday', 
                'friday', 'saturday', 'sunday', 'to', 'it', 'yes', 'no', 'ok',
                'okay', 'sure', 'confirm', 'correct', 'sep', 'cls'
            ]
            
            # Action words that should never be part of an attendee name
            action_words = [
                'add', 'invite', 'include', 'with', 'and', 'get', 'bring', 'ask', 
                'call', 'schedule', 'book', 'arrange', 'set', 'up', 'for', 'to'
            ]
            
            # First identify full names vs partial names
            full_names = []
            partial_names = []
            
            for attendee_name in entities['ATTENDEE']:
                # Skip empty names
                if not attendee_name:
                    continue
                    
                # Clean the name
                clean_name = re.sub(r'\[.*?\]', '', attendee_name).strip()
                
                # Skip short names
                if len(clean_name) <= 2:
                    continue
                    
                # CRITICAL FIX: Check if this name starts with an action word
                words = clean_name.lower().split()
                if words and words[0] in action_words:
                    # Skip this entire name if it starts with an action word
                    continue
                    
                # Check if the name has spaces (indicating a full name)
                if ' ' in clean_name:
                    # Capitalize properly
                    capitalized_name = ' '.join(word.capitalize() for word in clean_name.split())
                    full_names.append(capitalized_name)
                else:
                    # Just a single name
                    capitalized_name = clean_name.capitalize()
                    partial_names.append(capitalized_name)
            
            # Process full names first
            for full_name in full_names:
                unique_attendees.add(full_name)
                
                # Extract parts of this full name
                name_parts = full_name.split()
                
                # Remove any partial names that match parts of this full name
                for partial in partial_names[:]:
                    if partial in name_parts:
                        # This partial name is already covered by a full name
                        partial_names.remove(partial)
            
            # Add remaining partial names
            for partial in partial_names:
                unique_attendees.add(partial)
            
            # Update the attendees list
            self.attendees = list(unique_attendees)
            entity_updates['attendees'] = self.attendees
            print(f"DEBUG: Final attendee list: {self.attendees}")
            
            # Flag that we need attendee resolution
            self.needs_attendee_resolution = True
        
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