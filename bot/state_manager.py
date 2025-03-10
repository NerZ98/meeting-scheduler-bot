import datetime
import uuid
import re
from utils.context_manager import MeetingContext
from bot.response_generator import ResponseGenerator
from utils.date_parser import DateTimeParser

class ConversationState:
    """
    Class to manage the overall state of the conversation including multiple meetings
    """
    
    def __init__(self):
        self.meetings = {}  # Dictionary of meeting_id: MeetingContext
        self.current_meeting_id = None
        self.conversation_history = []
        self.last_intent = None
        self.waiting_for = None  # What information we're waiting for from the user
        self.response_generator = ResponseGenerator()
        self.date_parser = DateTimeParser()  # Add a date parser instance for direct extraction
        
    def start_new_meeting(self):
        """Start a new meeting context"""
        meeting = MeetingContext()
        meeting_id = str(uuid.uuid4())
        meeting.meeting_id = meeting_id
        
        self.meetings[meeting_id] = meeting
        self.current_meeting_id = meeting_id
        
        return meeting
    
    def get_current_meeting(self):
        """Get the currently active meeting context"""
        if not self.current_meeting_id:
            return self.start_new_meeting()
        
        return self.meetings.get(self.current_meeting_id)
    
    def _extract_date_from_message(self, meeting, message):
        """
        Try to extract date information directly from the message text
        This is a fallback for when the NER model fails to extract dates
        """
        if not message:
            return False
            
        # Try using the date parser directly on the message
        extracted_date = self.date_parser.parse_date(message)
        if extracted_date and meeting.date is None:
            meeting.date = extracted_date
            print(f"Direct extraction: Updated date to {extracted_date} from message")
            return True
            
        # Check for common date patterns
        date_patterns = [
            # Match "19th of March", "19 March", "March 19th", etc.
            r'(\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)',
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?',
            # Match MM/DD or MM/DD/YYYY
            r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?',
            # Match YYYY-MM-DD
            r'(\d{4})-(\d{1,2})-(\d{1,2})'
        ]
        
        message_lower = message.lower()
        for pattern in date_patterns:
            matches = re.findall(pattern, message_lower)
            if matches:
                # Take the entire matching part and try to parse it
                match_obj = re.search(pattern, message_lower)
                if match_obj:
                    date_text = match_obj.group(0)
                    # Try to parse this text
                    parsed_date = self.date_parser.parse_date(date_text)
                    if parsed_date and meeting.date is None:
                        meeting.date = parsed_date
                        print(f"Pattern match: Updated date to {parsed_date} from '{date_text}'")
                        return True
                        
        return False
    
    def handle_intent(self, intent, entities, user_message=""):
        """
        Handle an intent and update the state accordingly
        Returns a response message
        """
        print(f"Handling intent: {intent}")
        print(f"Entities extracted: {entities}")
        
        meeting = self.get_current_meeting()
        self.last_intent = intent
        
        # Save the original user message for direct processing
        original_message = user_message
        
        # Try direct date parsing on the original message regardless of intent
        if user_message:
            self._extract_date_from_message(meeting, original_message)
        
        # Reset waiting state
        self.waiting_for = None
        
        if intent == "Schedule_Meeting":
            # Start new meeting if needed
            if meeting.is_confirmed or meeting.is_cancelled:
                meeting = self.start_new_meeting()
            
            # Reset cancelled state if it was previously cancelled
            meeting.is_cancelled = False
            
            # We've already tried extracting dates from the message at the start
                
            # Update with any provided entities
            meeting.update_from_entities(entities)
            meeting.last_update = "intent"
            
            # When scheduling with complete time info, prepare a better response
            has_time = 'TIME' in entities and entities['TIME']
            has_date = 'DATE' in entities and entities['DATE']
            has_duration = 'DURATION' in entities and entities['DURATION']
            
            # Additional check for date in the original message
            date_mentioned = meeting.date is not None
            
            if has_time and date_mentioned:
                # The user provided both date and time in the scheduling request
                response = f"I'll schedule a meeting for {meeting.date_parser.format_date(meeting.date)} at {meeting.date_parser.format_time(meeting.time)}."
                
                if has_duration:
                    response += f" The meeting will last for {meeting.date_parser.format_duration(meeting.duration)}."
                
                # Check what's missing
                missing = meeting.get_missing_info()
                if "attendees" in missing:
                    self.waiting_for = "attendees"
                    response += "\n\n" + self.response_generator.get_attendee_request()
                else:
                    # We have all required info
                    response += "\n\n" + self._generate_confirmation_message(meeting)
                
                return response
            
            # Otherwise, handle missing information
            missing = meeting.get_missing_info()
            
            if "date" in missing:
                self.waiting_for = "date"
                return "On what date would you like to schedule the meeting?"
            elif "time" in missing:
                self.waiting_for = "time"
                return self.response_generator.get_time_request()
            elif "attendees" in missing:
                self.waiting_for = "attendees"
                return self.response_generator.get_attendee_request()
            else:
                # We have all required info
                return self._generate_confirmation_message(meeting)
                
        elif intent == "Add_Attendee":
            # Update attendees
            meeting.update_from_entities(entities)
            meeting.last_update = "attendees"
            
            # Direct fallback for attendee extraction if the entity model fails
            if not entities.get('ATTENDEE') and self.waiting_for == "attendees":
                # Try to extract attendees directly from text
                import re
                
                # Look for potential names in the user message
                words = user_message.lower().split()
                
                # Remove common words that aren't likely to be names
                stop_words = ['add', 'the', 'to', 'this', 'meeting', 'please', 'and', 'invite', 'with']
                potential_names = [word for word in words if word not in stop_words]
                
                if potential_names:
                    for name in potential_names:
                        # Capitalize the first letter of each name
                        name = name.strip().capitalize()
                        if name and name not in meeting.attendees:
                            meeting.attendees.append(name)
                            print(f"Fallback: Added attendee: {name}")
            
            # Check if this completes the meeting info
            if meeting.is_complete():
                return self._generate_confirmation_message(meeting)
            else:
                missing = meeting.get_missing_info()
                if "time" in missing:
                    self.waiting_for = "time"
                    return "What time should I schedule the meeting for?"
                elif "date" in missing:
                    self.waiting_for = "date"
                    return "On what date should I schedule this meeting?"
                else:
                    return "Attendees added. Is there anything else you'd like to add?"
                    
        elif intent == "Change_Time":
            # Update time
            meeting.update_from_entities(entities)
            meeting.last_update = "time"
            
            if "TIME" in entities and entities["TIME"]:
                time_str = meeting.date_parser.format_time(meeting.time)
                response = f"No problem. Time changed to {time_str}."
                
                # If meeting is otherwise complete, show confirmation
                if meeting.is_complete():
                    response += "\n" + self._generate_confirmation_message(meeting)
                return response
            else:
                self.waiting_for = "time"
                return "What time would you like to change it to?"
                
        elif intent == "Change_Date":
            # Try direct extraction first
            extracted = self._extract_date_from_message(meeting, original_message)
            
            # Update date from entities
            meeting.update_from_entities(entities)
            meeting.last_update = "date"
            
            if "DATE" in entities and entities["DATE"] or extracted:
                if meeting.date:
                    date_str = meeting.date_parser.format_date(meeting.date)
                    response = f"No problem. Date changed to {date_str}."
                    
                    # If meeting is otherwise complete, show confirmation
                    if meeting.is_complete():
                        response += "\n" + self._generate_confirmation_message(meeting)
                    return response
                
            # If we couldn't extract a date, ask for one
            self.waiting_for = "date"
            return "What date would you like to change it to?"
                
        elif intent == "Change_Duration":
            # Update duration
            meeting.update_from_entities(entities)
            meeting.last_update = "duration"
            
            if "DURATION" in entities and entities["DURATION"]:
                duration_str = meeting.date_parser.format_duration(meeting.duration)
                response = f"✅ Duration changed to {duration_str}."
                
                # Show current state
                response += f"\n* Time: {meeting.date_parser.format_time(meeting.time)}"
                response += f"\n* Duration: {duration_str}"
                response += "\nIs that correct?"
                return response
            else:
                self.waiting_for = "duration"
                return "What duration would you like to set?"
                
        elif intent == "Confirm_Meeting":
            meeting.is_confirmed = True
            return "✅ Meeting scheduled successfully!"
            
        elif intent == "Cancel_Meeting":
            meeting.is_cancelled = True
            return self.response_generator.get_cancel_message()
            
        elif intent == "Other":
            # Try to determine if this is providing requested info
            if self.waiting_for == "time" and "TIME" in entities:
                meeting.update_from_entities(entities)
                meeting.last_update = "time"
                
                if meeting.is_complete():
                    return self._generate_confirmation_message(meeting)
                else:
                    missing = meeting.get_missing_info()
                    if "attendees" in missing:
                        self.waiting_for = "attendees"
                        return "Who should I add to this meeting?"
                    elif "date" in missing:
                        self.waiting_for = "date"
                        return "On what date should I schedule this meeting?"
            
            elif self.waiting_for == "attendees" and "ATTENDEE" in entities:
                meeting.update_from_entities(entities)
                meeting.last_update = "attendees"
                
                if meeting.is_complete():
                    return self._generate_confirmation_message(meeting)
                else:
                    missing = meeting.get_missing_info()
                    if "time" in missing:
                        self.waiting_for = "time"
                        return "What time should I schedule the meeting for?"
                    elif "date" in missing:
                        self.waiting_for = "date"
                        return "On what date should I schedule this meeting?"
            
            elif self.waiting_for == "date":
                # Try direct extraction for dates since entity extraction might have failed
                extracted = self._extract_date_from_message(meeting, original_message)
                
                if "DATE" in entities or extracted:
                    meeting.update_from_entities(entities)
                    meeting.last_update = "date"
                    
                    if meeting.is_complete():
                        return self._generate_confirmation_message(meeting)
                    else:
                        missing = meeting.get_missing_info()
                        if "time" in missing:
                            self.waiting_for = "time"
                            return "What time should I schedule the meeting for?"
                        elif "attendees" in missing:
                            self.waiting_for = "attendees"
                            return "Who should I add to this meeting?"
                else:
                    # Still waiting for a date
                    return "I need a date for this meeting. What date works for you?"
            
            # Default response for other intents
            return "I'm a meeting scheduling assistant. I can help you schedule, modify, or cancel meetings. How can I assist you today?"
    
    def _generate_confirmation_message(self, meeting):
        """Generate a confirmation message based on the meeting state"""
        message = "Okay! Let me confirm:\n"
        
        if meeting.date:
            message += f"* Date: {meeting.date_parser.format_date(meeting.date)}\n"
            
        if meeting.time:
            message += f"* Time: {meeting.date_parser.format_time(meeting.time)}\n"
            
        if meeting.duration:
            message += f"* Duration: {meeting.date_parser.format_duration(meeting.duration)}\n"
            
        if meeting.attendees:
            # Format attendees with proper capitalization and join with commas
            # Ensure we don't have any duplicates in the final display
            unique_attendees = []
            seen_lower = set()
            
            for attendee in meeting.attendees:
                # Convert to lowercase for comparison
                attendee_lower = attendee.lower()
                
                # Check if this is a duplicate (case-insensitive)
                if attendee_lower not in seen_lower:
                    seen_lower.add(attendee_lower)
                    unique_attendees.append(attendee)
            
            # Format the unique attendees
            formatted_attendees = ", ".join(unique_attendees)
            message += f"* Attendees: {formatted_attendees}\n"
            
        message += "Is that correct?"
        return message
    
    def log_conversation(self, user_message, bot_response):
        """Log the conversation for context maintenance"""
        self.conversation_history.append({
            "user": user_message,
            "bot": bot_response,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        # If we have a current meeting, also log there
        if self.current_meeting_id:
            meeting = self.meetings[self.current_meeting_id]
            meeting.conversation_history.append({
                "user": user_message,
                "bot": bot_response,
                "timestamp": datetime.datetime.now().isoformat()
            })