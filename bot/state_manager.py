import datetime
import uuid
import re
from utils.context_manager import MeetingContext
from bot.response_generator import ResponseGenerator
from utils.date_parser import DateTimeParser
from attendee_resolver import AttendeeResolver

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
        self.change_mode = None  # What we're changing in change mode
        self.response_generator = ResponseGenerator()
        self.date_parser = DateTimeParser()  # Add a date parser instance for direct extraction
        
        # Attendee resolution
        self.attendee_resolver = AttendeeResolver()
        self.disambiguation_session = None  # Track active disambiguation session
        self.pending_attendees = []  # Store attendees waiting for resolution
        self.resolved_attendees = []  # Store resolved attendees
        
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
    
    def handle_attendee_disambiguation(self, user_message):
        """
        Handle disambiguation for attendees with multiple possible email matches
        Returns a response message and True if the message was handled, False otherwise
        """
        if not self.disambiguation_session:
            return None, False
        
        # Check if the user input is a number
        try:
            selection = int(user_message.strip())
            # Adjust to 0-based index
            selection -= 1
            
            # Process the selection
            result = self.attendee_resolver.resolve_disambiguation_selection(
                self.disambiguation_session['session_id'], 
                selection
            )
            
            if result['status'] == 'error':
                return f"Error: {result['message']}. Please try again.", True
            
            if result['status'] == 'completed':
                # All ambiguous attendees have been resolved
                self.resolved_attendees.extend(result['resolved_attendees'])
                
                # Update the meeting attendees
                meeting = self.get_current_meeting()
                
                # Update attendee list with resolved names
                updated_attendees = []
                
                # Add previously resolved attendees
                for attendee in meeting.attendees:
                    # Check if this is a pending attendee
                    if attendee not in self.pending_attendees:
                        updated_attendees.append(attendee)
                
                # Add newly resolved attendees
                for name, email in self.resolved_attendees:
                    # Store the resolved email in the attendee object
                    meeting.attendee_emails[name] = email
                    updated_attendees.append(name)
                
                meeting.attendees = updated_attendees
                
                # Clear disambiguation state
                self.disambiguation_session = None
                self.pending_attendees = []
                self.resolved_attendees = []
                
                # Show confirmation
                if meeting.is_complete():
                    return self._generate_confirmation_message(meeting), True
                else:
                    # Check if anything else is missing
                    missing = meeting.get_missing_info()
                    if missing:
                        missing_str = ", ".join(missing)
                        return f"Attendees added. I still need the following details: {missing_str.capitalize()}.", True
                    else:
                        return "Attendees added. What else would you like to add to this meeting?", True
            
            if result['status'] == 'in_progress':
                # Continue with the next ambiguous attendee
                self.disambiguation_session = result
                
                # Generate the options message
                options_message = self.attendee_resolver.format_disambiguation_options(
                    result['current_name'],
                    result['options']
                )
                
                return options_message, True
        
        except ValueError:
            # Not a number, maybe user wants to cancel disambiguation
            if user_message.lower() in ['cancel', 'stop', 'exit']:
                if self.disambiguation_session:
                    self.attendee_resolver.cancel_disambiguation_session(
                        self.disambiguation_session['session_id']
                    )
                    self.disambiguation_session = None
                    self.pending_attendees = []
                    self.resolved_attendees = []
                    
                    return "Attendee selection cancelled. What would you like to do?", True
            
            return "Please enter a number to select an attendee, or 'cancel' to stop.", True
        
        return None, False
    
    def resolve_attendees(self, meeting, attendee_names):
        """
        Resolve attendee names to email addresses
        Returns True if all attendees were resolved, False if disambiguation is needed
        Returns a tuple of (success, message) if there are attendees not found in the database
        """
        # Debug statement
        print(f"DEBUG: resolve_attendees called with: {attendee_names}")
        
        # Try to resolve the attendees
        resolved, ambiguous, not_found = self.attendee_resolver.resolve_attendees(attendee_names)
        
        # Debug
        print(f"DEBUG: Resolution results - resolved: {resolved}, ambiguous: {ambiguous}, not_found: {not_found}")
        
        # If we have attendees not found in the database, return error message
        if not_found:
            not_found_names = ", ".join(not_found)
            error_message = f"I couldn't find the following attendee(s) in the organization: {not_found_names}. Please choose employees from your organization only."
            return (False, error_message)
        
        # Add resolved attendees to the meeting
        for name, email in resolved:
            # Check if already in the list
            if name not in meeting.attendees:
                meeting.attendees.append(name)
            
            # Store the email
            meeting.attendee_emails[name] = email
        
        # If we have ambiguous attendees, start disambiguation
        if ambiguous:
            # Debug statement
            print(f"DEBUG: Starting disambiguation for ambiguous attendees: {list(ambiguous.keys())}")
            
            # Store the ambiguous attendees for later
            self.pending_attendees = list(ambiguous.keys())
            
            # Start disambiguation session
            self.disambiguation_session = self.attendee_resolver.start_disambiguation_session(ambiguous)
            
            # Debug
            print(f"DEBUG: Disambiguation session created: {self.disambiguation_session}")
            
            return (False, None)  # No error message, but we need disambiguation
        
        # Debug statement
        print("DEBUG: All attendees resolved successfully")
        return (True, None)  # All resolved successfully
    
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
        # Check if we're in disambiguation mode
        if self.disambiguation_session:
            response, handled = self.handle_attendee_disambiguation(user_message)
            if handled:
                return response
                
        print(f"Handling intent: {intent}")
        print(f"Entities extracted: {entities}")
        print(f"User message: {user_message}")
        
        meeting = self.get_current_meeting()
        original_message = user_message.lower().strip()
        
        # Handling restart and change scenarios
        restart_phrases = ['nope', 'no', 'not correct', 'start over', 'reset', 'cancel']
        confirmation_phrases = ['yes', 'confirm', 'ok', 'okay', 'correct', 'that is correct', 'looks good']
        
        # ADD HERE: Check for confirmation before entity processing
        if meeting.is_complete() and any(phrase == original_message for phrase in confirmation_phrases):
            # Explicit confirmation - avoid processing as an entity
            meeting.is_confirmed = True
            return "✅ Meeting scheduled successfully!"
            
        if any(phrase == original_message for phrase in restart_phrases):
            # Completely reset the meeting
            meeting = self.start_new_meeting()
            return "Meeting context has been reset. I'm ready to start over. How can I help you schedule a meeting?"
        # CRITICAL FIX: First process all entities regardless of intent
        # This ensures we capture everything the user mentioned
        if entities:
            meeting = self.get_current_meeting()
            if meeting:
                updates = meeting.update_from_entities(entities)
                print(f"Processed all entities first: {updates}")
                
                # NEW: Always check for attendee resolution when attendees are updated
                if 'attendees' in updates or getattr(meeting, 'needs_attendee_resolution', False):
                    print("DEBUG: Attendees were updated, checking if resolution is needed")
                    # Try to resolve attendees if any were extracted
                    if meeting.attendees:
                        result = self.resolve_attendees(meeting, meeting.attendees)
                        
                        # Check for disambiguation or errors
                        if isinstance(result, tuple):
                            success, message = result
                            
                            # If there's an error message, return it early
                            if not success and message is not None:
                                return message
                                
                            # If disambiguation is needed, interrupt normal flow
                            if not success and self.disambiguation_session:
                                print("DEBUG: Disambiguation session active, showing options")
                                # We have ambiguous attendees, show disambiguation options
                                options_message = self.attendee_resolver.format_disambiguation_options(
                                    self.disambiguation_session['current_name'],
                                    self.disambiguation_session['options']
                                )
                                # Reset the flag
                                if hasattr(meeting, 'needs_attendee_resolution'):
                                    meeting.needs_attendee_resolution = False
                                
                                return options_message
                    
                    # Clear the flag if we got here (all attendees resolved)
                    if hasattr(meeting, 'needs_attendee_resolution'):
                        meeting.needs_attendee_resolution = False
        
        # Check if we're in disambiguation mode
        if self.disambiguation_session:
            response, handled = self.handle_attendee_disambiguation(user_message)
            if handled:
                return response
                
        print(f"Handling intent: {intent}")
        print(f"Entities extracted: {entities}")
        print(f"User message: {user_message}")
        
        meeting = self.get_current_meeting()
        original_message = user_message.lower().strip()
        
        # Handling restart and change scenarios
        restart_phrases = ['nope', 'no', 'not correct', 'start over', 'reset', 'cancel']
        confirmation_phrases = ['yes', 'confirm', 'ok', 'okay']
        
        # Direct duration extraction - catch "Make the duration 2 hours"
        if "DURATION" in entities and entities["DURATION"]:
            duration_text = entities["DURATION"][0]
            parsed_duration = self.date_parser.parse_duration(duration_text)
            if parsed_duration:
                meeting.duration = parsed_duration
                duration_str = meeting.date_parser.format_duration(parsed_duration)
                
                # Build response acknowledging all changes, not just duration
                response_parts = []
                
                # Include time if it was updated in this message
                if 'TIME' in entities and meeting.time:
                    time_str = meeting.date_parser.format_time(meeting.time)
                    response_parts.append(f"Time set to {time_str}")
                    
                response_parts.append(f"Duration set to {duration_str}")
                
                response = ". ".join(response_parts) + "."
                
                # Check if meeting is now complete
                if meeting.is_complete():
                    response += "\n\n" + self._generate_confirmation_message(meeting)
                else:
                    # Show what's still missing
                    missing = meeting.get_missing_info()
                    if missing:
                        missing_str = ", ".join(missing)
                        response += f"\n\nI still need the following details: {missing_str.capitalize()}."
                
                return response

        # Check if we're in change mode
        if self.change_mode:
            # Process the change based on the current change_mode
            if self.change_mode == 'date':
                # Try to parse the date
                parsed_date = self.date_parser.parse_date(user_message)
                if parsed_date:
                    meeting.date = parsed_date
                    self.change_mode = None
                    date_str = meeting.date.strftime("%A, %B %d, %Y")
                    response = f"Date changed to {date_str}."
                    
                    # Do NOT automatically generate confirmation
                    return response
            
            # Handle simple day names like "Thursday" as date updates
            day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            if original_message.lower() in day_names:
                try:
                    # Get the next occurrence of this day
                    day_idx = day_names.index(original_message.lower())
                    today_idx = self.reference_date.weekday()
                    days_ahead = (day_idx - today_idx) % 7
                    if days_ahead == 0:
                        days_ahead = 7  # If today, get next week
                        
                    next_date = self.reference_date + datetime.timedelta(days=days_ahead)
                    meeting.date = next_date
                    date_str = next_date.strftime("%A, %B %d, %Y")
                    return f"Date set to {date_str}."
                except Exception as e:
                    print(f"Error parsing day name: {e}")
        
            elif self.change_mode == 'time':
                # Try to parse the time
                parsed_time = self.date_parser.parse_time(user_message)
                if parsed_time:
                    meeting.time = parsed_time
                    self.change_mode = None
                    response = f"Time changed to {self.date_parser.format_time(parsed_time)}."
                    
                    # Show confirmation if meeting is complete
                    if meeting.is_complete():
                        response += "\n\n" + self._generate_confirmation_message(meeting)
                    
                    return response
            
            elif self.change_mode == 'duration':
                # Try to parse duration
                parsed_duration = self.date_parser.parse_duration(user_message)
                if parsed_duration:
                    meeting.duration = parsed_duration
                    self.change_mode = None
                    response = f"Duration changed to {self.date_parser.format_duration(parsed_duration)}."
                    
                    # Show confirmation if meeting is complete
                    if meeting.is_complete():
                        response += "\n\n" + self._generate_confirmation_message(meeting)
                    
                    return response
            
            elif self.change_mode == 'attendees':
                # Update attendees
                meeting.update_from_entities({'ATTENDEE': [user_message]})
                
                # Resolve attendees to emails
                attendee_names = meeting.attendees
                result = self.resolve_attendees(meeting, attendee_names)
                
                # Check if we got a tuple result (indicating potential error)
                if isinstance(result, tuple):
                    success, message = result
                    
                    # If there's an error message, return it (don't change mode yet)
                    if not success and message is not None:
                        return message
                        
                    # Otherwise, if disambiguation is needed
                    if not success and self.disambiguation_session:
                        # Exit change mode as we're now in disambiguation mode
                        self.change_mode = None
                        # We have ambiguous attendees, show disambiguation options
                        options_message = self.attendee_resolver.format_disambiguation_options(
                            self.disambiguation_session['current_name'],
                            self.disambiguation_session['options']
                        )
                        return options_message
                
                # All resolved successfully
                self.change_mode = None
                response = f"Attendees updated to: {', '.join(meeting.attendees)}."
                
                # Show confirmation if meeting is complete
                if meeting.is_complete():
                    response += "\n\n" + self._generate_confirmation_message(meeting)
                
                return response
        
        # Handling specific change requests
        change_options = {
            'date': "Ok, let me know the new value for date",
            'time': "Ok, let me know the new value for time",
            'duration': "Ok, let me know the new value for duration",
            'attendees': "Ok, let me know the new attendees"
        }
        
        # Check if the message is a request to change a specific attribute
        for option, prompt in change_options.items():
            if option in original_message:
                self.change_mode = option
                return prompt
        
        # When receiving a date, do not automatically confirm
        if (intent == 'Confirm_Meeting' or intent == 'Other') and 'DATE' in entities:
            # Parse the date
            if entities['DATE']:
                parsed_date = self.date_parser.parse_date(entities['DATE'][0])
                if parsed_date:
                    meeting.date = parsed_date
                    
                    # Return a confirmation request instead of auto-confirming
                    return self._generate_confirmation_message(meeting)
        
        # Restart and rejection scenarios
        if (intent == 'Other' or intent == 'Confirm_Meeting') and any(phrase in original_message for phrase in restart_phrases):
            # Completely reset the meeting
            meeting = self.start_new_meeting()
            return "Meeting context has been reset. I'm ready to start over. How can I help you schedule a meeting?"
        
        # Explicit confirmation
        if (intent == 'Confirm_Meeting' or intent == 'Other') and any(phrase in original_message for phrase in confirmation_phrases):
            # Check if meeting is complete before confirming
            if meeting.is_complete():
                meeting.is_confirmed = True
                return "✅ Meeting scheduled successfully!"
            else:
                missing = meeting.get_missing_info()
                missing_str = ", ".join(missing)
                return f"The meeting is not complete. Please provide these missing details: {missing_str.capitalize()}."
        
        if intent == "Schedule_Meeting":
            # Start new meeting if needed
            if meeting.is_confirmed or meeting.is_cancelled:
                meeting = self.start_new_meeting()
            
            # Reset cancelled state if it was previously cancelled
            meeting.is_cancelled = False
            
            # CRITICAL FIX: Process all entities at once (done at the beginning now)
            meeting.last_update = "intent"
            
            # Debug output to see what's in the meeting context after update
            print(f"DEBUG: After update, meeting state: {meeting.to_dict()}")
            
            # CRITICAL FIX: Resolve attendees if any were extracted
            if meeting.attendees:
                result = self.resolve_attendees(meeting, meeting.attendees)
                if isinstance(result, tuple):
                    success, message = result
                    if not success and message is not None:
                        return message
                    if not success and self.disambiguation_session:
                        options_message = self.attendee_resolver.format_disambiguation_options(
                            self.disambiguation_session['current_name'],
                            self.disambiguation_session['options']
                        )
                        return options_message
            
            # CRITICAL FIX: Check if we have everything we need first!
            if meeting.is_complete():
                return self._generate_confirmation_message(meeting)
            
            # Get missing info after updating
            missing = meeting.get_missing_info()
            print(f"DEBUG: Missing info: {missing}")
            
            # Prepare response acknowledging what we have
            response_parts = []

            # Acknowledge what's been set
            if meeting.date:
                date_str = meeting.date.strftime("%A, %B %d, %Y")
                response_parts.append(f"Date set to {date_str}")

            if meeting.time:
                time_str = self.date_parser.format_time(meeting.time)
                response_parts.append(f"Time set to {time_str}")

            if meeting.duration:
                duration_str = self.date_parser.format_duration(meeting.duration)
                response_parts.append(f"Duration set to {duration_str}")

            if meeting.attendees:
                attendee_str = ", ".join(meeting.attendees)
                response_parts.append(f"Attendees: {attendee_str}")

            # Combine what we know so far
            if response_parts:
                response = ". ".join(response_parts) + "."
            else:
                response = "I'll help you schedule a meeting."
            
            # CRITICAL FIX: Check if we got everything we need
            if not missing:
                return self._generate_confirmation_message(meeting)
            
            # Ask for what's missing
            missing_str = ", ".join(missing)
            response += f"\nI still need the following details: {missing_str.capitalize()}."
            
            # Set what we're waiting for based on missing info
            if "date" in missing:
                self.waiting_for = "date"
            elif "time" in missing:
                self.waiting_for = "time"
            elif "duration" in missing:
                self.waiting_for = "duration"
            elif "attendees" in missing:
                self.waiting_for = "attendees"
                
            return response
        
        elif intent == "Add_Attendee":
            # Update attendees
            meeting.update_from_entities(entities)
            meeting.last_update = "attendees"
            
            # Resolve attendees to emails
            if 'ATTENDEE' in entities and entities['ATTENDEE']:
                attendee_names = meeting.attendees
                
                # If disambiguation is needed, it will start a session
                result = self.resolve_attendees(meeting, attendee_names)
                
                # Check if we got a tuple result (indicating potential error)
                if isinstance(result, tuple):
                    success, message = result
                    
                    # If there's an error message, return it
                    if not success and message is not None:
                        return message
                        
                    # Otherwise, if disambiguation is needed
                    if not success and self.disambiguation_session:
                        # We have ambiguous attendees, show disambiguation options
                        options_message = self.attendee_resolver.format_disambiguation_options(
                            self.disambiguation_session['current_name'],
                            self.disambiguation_session['options']
                        )
                        
                        return options_message
            
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
                    potential_attendees = []
                    for name in potential_names:
                        # Capitalize the first letter of each name
                        name = name.strip().capitalize()
                        if name and len(name) > 1:
                            potential_attendees.append(name)
                    
                    if potential_attendees:
                        # Try to resolve these potential names
                        result = self.resolve_attendees(meeting, potential_attendees)
                        
                        # Check for errors
                        if isinstance(result, tuple):
                            success, message = result
                            if not success and message is not None:
                                return message
            
            # Check if this completes the meeting info
            if meeting.is_complete():
                return self._generate_confirmation_message(meeting)
            else:
                missing = meeting.get_missing_info()
                missing_str = ", ".join(missing)
                # FIX: Better response that acknowledges the attendee update and prompts for next detail
                response = f"Attendees updated to: {', '.join(meeting.attendees)}."
                
                if "time" in missing:
                    self.waiting_for = "time"
                    return f"{response}What time should I schedule the meeting for?"
                elif "date" in missing:
                    self.waiting_for = "date"
                    return f"{response}What date should I schedule this meeting for?"
                elif "duration" in missing:
                    self.waiting_for = "duration"
                    return f"{response}How long should the meeting last?"
                else:
                    return f"{response}I still need the following details: {missing_str.capitalize()}."
        
        elif intent == "Change_Time":
            # Update time
            meeting.update_from_entities(entities)
            meeting.last_update = "time"
            
            # First check if attendees were added and handle disambiguation
            if 'ATTENDEE' in entities and entities['ATTENDEE'] and meeting.attendees:
                # If we have attendees, resolve them now before proceeding
                attendee_names = meeting.attendees
                result = self.resolve_attendees(meeting, attendee_names)
                
                # Check if we need disambiguation
                if isinstance(result, tuple):
                    success, message = result
                    
                    # If there's an error message, return it
                    if not success and message is not None:
                        return message
                        
                    # If disambiguation is needed
                    if not success and self.disambiguation_session:
                        # We have ambiguous attendees, show disambiguation options
                        # This should break the flow and show options instead
                        options_message = self.attendee_resolver.format_disambiguation_options(
                            self.disambiguation_session['current_name'],
                            self.disambiguation_session['options']
                        )
                        return options_message
            
            if "TIME" in entities and entities["TIME"]:
                time_str = meeting.date_parser.format_time(meeting.time)
                response = f"No problem. Time changed to {time_str}."
                
                # If meeting is otherwise complete, show confirmation
                if meeting.is_complete():
                    response += "\n" + self._generate_confirmation_message(meeting)
                else:
                    missing = meeting.get_missing_info()
                    missing_str = ", ".join(missing)
                    response += f"\nI still need the following details: {missing_str.capitalize()}."
                return response
            else:
                self.waiting_for = "time"
                return "What time would you like to change it to?"
        
        elif intent == "Change_Date":
            # Update date
            meeting.update_from_entities(entities)
            meeting.last_update = "date"
            
            if "DATE" in entities and entities["DATE"]:
                if meeting.date:
                    date_str = meeting.date.strftime("%A, %B %d, %Y")
                    response = f"No problem. Date changed to {date_str}."
                else:
                    response = "I couldn't parse that date. Please try a different format."
                    
                # If meeting is otherwise complete, show confirmation
                if meeting.is_complete():
                    response += "\n\n" + self._generate_confirmation_message(meeting)
                else:
                    missing = meeting.get_missing_info()
                    missing_str = ", ".join(missing)
                    response += f"\nI still need the following details: {missing_str.capitalize()}."
                return response
            else:
                self.waiting_for = "time"
                return "What time would you like to change it to?"
        
        elif intent == "Change_Duration":
            # Update duration
            meeting.update_from_entities(entities)
            meeting.last_update = "duration"
            
            if "DURATION" in entities and entities["DURATION"]:
                duration_str = meeting.date_parser.format_duration(meeting.duration)
                response = f"No problem. Duration changed to {duration_str}."
                
                # If meeting is otherwise complete, show confirmation
                if meeting.is_complete():
                    response += "\n" + self._generate_confirmation_message(meeting)
                else:
                    missing = meeting.get_missing_info()
                    missing_str = ", ".join(missing)
                    response += f"\nI still need the following details: {missing_str.capitalize()}."
                return response
            else:
                self.waiting_for = "duration"
                return "How long should the meeting be?"
        
        elif intent == "Cancel_Meeting":
            # Mark the meeting as cancelled
            meeting.is_cancelled = True
            meeting.is_confirmed = False
            
            return "Meeting cancelled."
        
        elif intent == "Get_Meeting_Info":
            # Check if we have a meeting to show
            if not meeting.date and not meeting.time and not meeting.attendees:
                return "I don't have any meeting details yet. Would you like to schedule a meeting?"
            
            return self._generate_confirmation_message(meeting)
        
        # Process other intents or fallback
        # Depending on what we're waiting for, try to extract relevant info
        if self.waiting_for:
            if self.waiting_for == "date":
                # Try to extract date from the message
                if self._extract_date_from_message(meeting, user_message):
                    self.waiting_for = None
                    
                    # Build response acknowledging the date
                    date_str = meeting.date.strftime("%A, %B %d, %Y")
                    response = f"Great! I've set the date to {date_str}."
                    
                    # If we still need information, ask for it
                    missing = meeting.get_missing_info()
                    if "time" in missing:
                        self.waiting_for = "time"
                        return f"{response}\n\nWhat time would work for this meeting?"
                    elif "duration" in missing:
                        self.waiting_for = "duration"
                        return f"{response}\n\nHow long should the meeting last?"
                    elif "attendees" in missing:
                        self.waiting_for = "attendees"
                        return f"{response}\n\nWho would you like to invite to this meeting?"
                    else:
                        # We have all required info
                        return self._generate_confirmation_message(meeting)
                else:
                    date_examples = "Examples: tomorrow, next Monday, March 15, etc."
                    return f"I still need a date for the meeting. {date_examples}"
            
            elif self.waiting_for == "time":
                # Try to extract time directly
                try:
                    parsed_time = self.date_parser.parse_time(user_message)
                    if parsed_time:
                        meeting.time = parsed_time
                        self.waiting_for = None
                        
                        # Build response acknowledging the time
                        time_str = meeting.date_parser.format_time(parsed_time)
                        response = f"Great! I've set the time to {time_str}."
                        
                        # Check what's missing now
                        missing = meeting.get_missing_info()
                        if "date" in missing:
                            self.waiting_for = "date"
                            return f"{response}\n\nWhat date would you like to schedule this meeting for?"
                        elif "duration" in missing:
                            self.waiting_for = "duration"
                            return f"{response}\n\nHow long should the meeting last?"
                        elif "attendees" in missing:
                            self.waiting_for = "attendees"
                            return f"{response}\n\nWho would you like to invite to this meeting?"
                        else:
                            # We have all required info
                            return self._generate_confirmation_message(meeting)
                except:
                    pass
                
                time_examples = "Examples: 2pm, 14:30, 3 o'clock, etc."
                return f"I still need a time for the meeting. {time_examples}"
                
            elif self.waiting_for == "duration":
                # Try to parse duration
                parsed_duration = self.date_parser.parse_duration(user_message)
                if parsed_duration:
                    meeting.duration = parsed_duration
                    self.waiting_for = None
                        
                    # Build response acknowledging the duration
                    duration_str = meeting.date_parser.format_duration(parsed_duration)
                    response = f"Great! I've set the duration to {duration_str}."
                        
                    # Check what's missing now
                    missing = meeting.get_missing_info()
                    if "date" in missing:
                        self.waiting_for = "date"
                        return f"{response}\n\nWhat date would you like to schedule this meeting for?"
                    elif "time" in missing:
                        self.waiting_for = "time"
                        return f"{response}\n\nWhat time would work for this meeting?"
                    elif "attendees" in missing:
                        self.waiting_for = "attendees"
                        return f"{response}\n\nWho would you like to invite to this meeting?"
                    else:
                        # We have all required info
                        return self._generate_confirmation_message(meeting)
                    
                duration_examples = "Examples: 30 minutes, 1 hour, 45 mins, etc."
                return f"I still need a duration for the meeting. {duration_examples}"
            
            elif self.waiting_for == "attendees":
                # Try updating attendees directly from the message
                meeting.update_from_entities({'ATTENDEE': [user_message]})
                
                # Resolve attendees to emails if we have any
                if meeting.attendees:
                    result = self.resolve_attendees(meeting, meeting.attendees)
                    
                    # Check if we got a tuple result (indicating potential error)
                    if isinstance(result, tuple):
                        success, message = result
                        
                        # If there's an error message, return it
                        if not success and message is not None:
                            return message
                            
                        # Otherwise, if disambiguation is needed
                        if not success and self.disambiguation_session:
                            # We have ambiguous attendees, show disambiguation options
                            options_message = self.attendee_resolver.format_disambiguation_options(
                                self.disambiguation_session['current_name'],
                                self.disambiguation_session['options']
                            )
                            return options_message
                    
                    # Acknowledge the attendees added
                    attendee_str = ", ".join(meeting.attendees)
                    response = f"Great! I've added {attendee_str} to the meeting."
                        
                    # Check if meeting is now complete
                    if meeting.is_complete():
                        self.waiting_for = None
                        return f"{response}\n\n{self._generate_confirmation_message(meeting)}"
                    else:
                        # Check if anything else is missing
                        missing = meeting.get_missing_info()
                        if "date" in missing:
                            self.waiting_for = "date"
                            return f"{response}\n\nWhat date would you like to schedule this meeting for?"
                        elif "time" in missing:
                            self.waiting_for = "time"
                            return f"{response}\n\nWhat time would work for this meeting?"
                        elif "duration" in missing:
                            self.waiting_for = "duration"
                            return f"{response}\n\nHow long should the meeting last?"
                
                attendee_examples = "Examples: John Smith, Sarah from Marketing, etc."
                return f"I still need attendees for the meeting. {attendee_examples}"
        
        # Fallback response
        return self.response_generator.get_fallback()

    def _generate_confirmation_message(self, meeting):
        """Generate a confirmation message based on the meeting state"""
        message = "Okay! Let me confirm:\n"
        
        if meeting.date:
            # Always use full date format instead of relative terms like "Tomorrow"
            date_str = meeting.date.strftime("%A, %B %d, %Y")  # Example: "Tuesday, March 12, 2025"
            message += f"* Date: {date_str}\n"
            
        if meeting.time:
            message += f"* Time: {meeting.date_parser.format_time(meeting.time)}\n"
            
        if meeting.duration:
            message += f"* Duration: {meeting.date_parser.format_duration(meeting.duration)}\n"
            
        if meeting.attendees:
            # Format attendees with their email addresses
            formatted_attendees = []
            for attendee in meeting.attendees:
                # Get email if available
                email = meeting.attendee_emails.get(attendee, "")
                if email:
                    formatted_attendees.append(f"{attendee} ({email})")
                else:
                    formatted_attendees.append(attendee)
                    
            attendees_str = ", ".join(formatted_attendees)
            message += f"* Attendees: {attendees_str}\n"
            
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
            
    def handle_time_in_message(self, meeting, text):
        """Special handler to extract time information from messages with improved AM/PM handling"""
        # First try direct time patterns
        parsed_time = self.date_parser.parse_time(text)
        if parsed_time:
            meeting.time = parsed_time
            print(f"Successfully parsed time: {parsed_time} from '{text}'")
            return True
                
        # Next try to find time patterns in the text
        time_patterns = [
            r'at\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?',
            r'at\s+(\d{1,2})\s*([ap]\.?m\.?)?',
            r'(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)',
            r'(\d{1,2})\s*([ap]\.?m\.?)',
        ]
            
        for pattern in time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                hour = int(match.group(1))
                    
                # Check if minutes are captured
                minute = 0
                if len(match.groups()) > 1 and match.group(2) and match.group(2).isdigit():
                    try:
                        minute = int(match.group(2))
                    except (ValueError, TypeError):
                        minute = 0
                    
                # Check for AM/PM
                ampm = None
                if len(match.groups()) > 2 and match.group(3):
                    ampm = match.group(3)
                elif len(match.groups()) > 1 and match.group(2) and not match.group(2).isdigit():
                    ampm = match.group(2)
                        
                # If no AM/PM is specified, check for it in the text
                if not ampm:
                    am_match = re.search(r'\b[aA]\.?[mM]\.?\b', text)
                    pm_match = re.search(r'\b[pP]\.?[mM]\.?\b', text)
                        
                    if pm_match and not am_match:
                        ampm = 'pm'
                    elif am_match and not pm_match:
                        ampm = 'am'
                    # IMPORTANT FIX: For business hours (8-6), default to PM for 1-6, AM for 7-12
                    # This is a reasonable default for meeting times
                    elif not am_match and not pm_match:
                        if 1 <= hour <= 6:
                            ampm = 'pm'  # Default 1-6 to PM
                    
                # Adjust hour based on AM/PM
                if ampm and ('p' in ampm.lower()) and hour < 12:
                    hour += 12
                elif ampm and ('a' in ampm.lower()) and hour == 12:
                    hour = 0
                        
                meeting.time = datetime.time(hour, minute)
                print(f"Extracted time from pattern: {meeting.time} from '{text}', AM/PM context: {ampm}")
                return True
            
        return False