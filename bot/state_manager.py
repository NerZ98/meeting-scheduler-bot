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
        
        print(f"DEBUG: Processing disambiguation response: '{user_message}'")
        print(f"DEBUG: Current disambiguation session: {self.disambiguation_session}")
        
        # Get current meeting and preserve non-ambiguous attendees
        meeting = self.get_current_meeting()
        
        # CRITICAL FIX: Build a complete list of attendees to preserve, including already resolved ones
        preserved_attendees = []
        preserved_emails = {}
        
        # Add currently resolved attendees with their emails
        for attendee in self.resolved_attendees:
            if attendee in meeting.attendee_emails:
                preserved_attendees.append(attendee)
                preserved_emails[attendee] = meeting.attendee_emails[attendee]
        
        # Add other attendees that aren't being disambiguated
        for attendee in meeting.attendees:
            if attendee not in self.pending_attendees or attendee in self.resolved_attendees:
                if attendee not in preserved_attendees:  # Avoid duplicates
                    preserved_attendees.append(attendee)
                    if attendee in meeting.attendee_emails:
                        preserved_emails[attendee] = meeting.attendee_emails[attendee]
        
        print(f"DEBUG: Preserved attendees before processing: {preserved_attendees}")
        print(f"DEBUG: Preserved emails: {preserved_emails}")
        
        # Clean the user message thoroughly
        clean_message = user_message.strip()
        
        # Remove any special tokens or markdown
        clean_message = re.sub(r'\[.*?\]', '', clean_message).strip()
        
        print(f"DEBUG: Cleaned disambiguation response: '{clean_message}'")
        
        # Handle "both" or "all" responses
        if clean_message.lower() in ['both', 'all']:
            # Select all options
            ambiguous_name = self.disambiguation_session['current_name']
            options = self.disambiguation_session['options']
            
            # Add all options to resolved attendees
            for i, option in enumerate(options):
                _, _, email = option
                
                # Use suffixed names for multiple attendees with the same name
                if i == 0:
                    name_to_use = ambiguous_name
                else:
                    name_to_use = f"{ambiguous_name} {i+1}"
                    
                # Store the resolved email
                meeting.attendee_emails[name_to_use] = email
                # Add to the final attendee list
                if name_to_use not in preserved_attendees:
                    preserved_attendees.append(name_to_use)
            
            # Reset the attendee list with all preserved and resolved attendees
            meeting.attendees = preserved_attendees
            
            # FIX: Check if there are more attendees to disambiguate
            self.resolved_attendees.append(ambiguous_name)
            
            # Move to the next ambiguous attendee if there is one
            remaining_pending = [a for a in self.pending_attendees if a not in self.resolved_attendees]
            
            if remaining_pending:
                # Get the next attendee to disambiguate
                next_attendee = remaining_pending[0]
                print(f"DEBUG: Moving to next ambiguous attendee: {next_attendee}")
                
                # Start a new disambiguation session for this attendee
                result = self.attendee_resolver.resolve_single_attendee(next_attendee)
                if result['status'] == 'ambiguous':
                    self.disambiguation_session = {
                        'session_id': str(uuid.uuid4()),
                        'current_name': next_attendee,
                        'options': result['options']
                    }
                    
                    # Show disambiguation options for the next attendee
                    options_message = self.attendee_resolver.format_disambiguation_options(
                        next_attendee,
                        result['options']
                    )
                    return options_message, True
            else:
                # No more attendees to disambiguate
                self.disambiguation_session = None
                self.pending_attendees = []
                self.resolved_attendees = []
                
                print(f"DEBUG: All attendees disambiguated, final list: {meeting.attendees}")
                
                # Show confirmation
                if meeting.is_complete():
                    return self._generate_confirmation_message(meeting), True
                else:
                    # Check if anything else is missing
                    missing = meeting.get_missing_info()
                    if missing:
                        missing_str = ", ".join(missing)
                        return f"All attendees added. I still need the following details: {missing_str.capitalize()}.", True
                    else:
                        return "All attendees added. What else would you like to add to this meeting?", True
        
        # CRITICAL FIX: Handle single number selection
        if clean_message.isdigit():
            try:
                selection = int(clean_message)
                # Adjust to 0-based index
                index = selection - 1
                
                ambiguous_name = self.disambiguation_session['current_name']
                options = self.disambiguation_session['options']
                
                print(f"DEBUG: Handling numeric selection: {selection} for {ambiguous_name}")
                print(f"DEBUG: Available options: {options}")
                
                if 0 <= index < len(options):
                    _, _, email = options[index]
                    
                    # Store the resolved email
                    meeting.attendee_emails[ambiguous_name] = email
                    
                    # Add to final attendee list if not already there
                    if ambiguous_name not in preserved_attendees:
                        preserved_attendees.append(ambiguous_name)
                    
                    # Set final attendee list with all preserved and resolved
                    meeting.attendees = preserved_attendees
                    
                    print(f"DEBUG: Selected attendee at index {index}, preserved list: {preserved_attendees}")
                    print(f"DEBUG: Resolved email: {email}")
                    
                    # FIX: Track that we've resolved this attendee
                    self.resolved_attendees.append(ambiguous_name)
                    
                    # FIX: Check if there are more attendees to disambiguate
                    remaining_pending = [a for a in self.pending_attendees if a not in self.resolved_attendees]
                    
                    if remaining_pending:
                        # Get the next attendee to disambiguate
                        next_attendee = remaining_pending[0]
                        print(f"DEBUG: Moving to next ambiguous attendee: {next_attendee}")
                        
                        # Start a new disambiguation session for this attendee
                        result = self.attendee_resolver.resolve_single_attendee(next_attendee)
                        if result['status'] == 'ambiguous':
                            self.disambiguation_session = {
                                'session_id': str(uuid.uuid4()),
                                'current_name': next_attendee,
                                'options': result['options']
                            }
                            
                            # Show disambiguation options for the next attendee
                            options_message = self.attendee_resolver.format_disambiguation_options(
                                next_attendee,
                                result['options']
                            )
                            return options_message, True
                    
                    # CRITICAL FIX: Ensure we pass the complete attendee list back to the meeting
                    print(f"DEBUG: Updated attendee list after disambiguation: {preserved_attendees}")
                    meeting.attendees = preserved_attendees
                    
                    # If no more attendees to disambiguate, clear the disambiguation state
                    self.disambiguation_session = None
                    self.pending_attendees = []
                    self.resolved_attendees = []
                    
                    print(f"DEBUG: All attendees disambiguated, final list: {meeting.attendees}")
                    
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
                            return f"Attendees added. What else would you like to add to this meeting?", True
                else:
                    print(f"DEBUG: Invalid selection {selection}, options range: 1-{len(options)}")
                    return f"Invalid selection. Please enter a number between 1 and {len(options)}.", True
            except ValueError as e:
                print(f"DEBUG: Error processing selection: {e}")
                pass  # Fall through to the next checks
        
        # Not a number, maybe user wants to cancel disambiguation
        if clean_message.lower() in ['cancel', 'stop', 'exit']:
            if self.disambiguation_session:
                self.attendee_resolver.cancel_disambiguation_session(
                    self.disambiguation_session['session_id']
                )
                self.disambiguation_session = None
                self.pending_attendees = []
                self.resolved_attendees = []
                
                return "Attendee selection cancelled. What would you like to do?", True
        
        print("DEBUG: Could not process disambiguation response, sending help message")
        return "Please enter a number to select an attendee, 'both' to select all, or 'cancel' to stop the selection process.", True

    def resolve_attendees(self, meeting, attendee_names):
        """
        Resolve attendee names to email addresses with comprehensive deduplication
        Returns True if all attendees were resolved, False if disambiguation is needed
        Returns a tuple of (success, message) if there are attendees not found in the database
        """
        # Debug statement
        print(f"DEBUG: resolve_attendees called with: {attendee_names}")
        
        ambiguous_attendees = {}
        resolved_pairs = []
        not_found_names = []
        pending_for_disambiguation = []
        
        unique_emails = set()
        duplicate_names = []
        
        # First identify all full names (first + last name format)
        full_names = [name for name in attendee_names if ' ' in name]
        # Then partial names
        partial_names = [name for name in attendee_names if ' ' not in name]
        
        # Process full names first, as they're more specific
        for name in full_names:
            # Skip if already has an email assigned
            if name in meeting.attendee_emails:
                email = meeting.attendee_emails[name]
                # Check if this email is already in our list
                if email in unique_emails:
                    duplicate_names.append(name)
                    continue
                else:
                    unique_emails.add(email)
                    continue
                
            # Try to resolve full name
            result = self.attendee_resolver.resolve_single_attendee(name)
            
            if result['status'] == 'resolved':
                # Full name resolved successfully
                email = result['email']
                
                # Check if this email is already in our list
                if email in unique_emails:
                    duplicate_names.append(name)
                    continue
                    
                # Add to unique emails and resolved pairs
                unique_emails.add(email)
                resolved_pairs.append((name, email))
                
            elif result['status'] == 'ambiguous':
                # Full name needs disambiguation
                ambiguous_attendees[name] = result['options']
                pending_for_disambiguation.append(name)
                
            elif result['status'] == 'not_found':
                # Full name not found
                not_found_names.append(name)
        
        # Now process partial names, but only if they don't overlap with full names
        for name in partial_names:
            # Check if this partial name is part of an already resolved full name
            is_part_of_full_name = False
            for full_name in full_names:
                if name.lower() in full_name.lower().split():
                    is_part_of_full_name = True
                    duplicate_names.append(name)
                    break
                    
            if is_part_of_full_name:
                continue
                
            # Continue with regular processing
            if name in meeting.attendee_emails:
                email = meeting.attendee_emails[name]
                # Check if this email is already in our list
                if email in unique_emails:
                    duplicate_names.append(name)
                    continue
                else:
                    unique_emails.add(email)
                    continue
            
            # Try to resolve partial name
            result = self.attendee_resolver.resolve_single_attendee(name)
            
            if result['status'] == 'resolved':
                email = result['email']
                
                # Check if this email is already in our list
                if email in unique_emails:
                    duplicate_names.append(name)
                    continue
                    
                # Add to unique emails and resolved pairs
                unique_emails.add(email)
                resolved_pairs.append((name, email))
                
            elif result['status'] == 'ambiguous':
                # Name needs disambiguation
                ambiguous_attendees[name] = result['options']
                pending_for_disambiguation.append(name)
                
            elif result['status'] == 'not_found':
                # Name not found
                not_found_names.append(name)
        
        # Report duplicates for debugging
        if duplicate_names:
            print(f"DEBUG: Removed duplicate/partial attendees: {duplicate_names}")
        
        # If we have attendees not found in the database, return error message
        if not_found_names:
            not_found_names_str = ", ".join(not_found_names)
            
            # Keep the attendees we did find and inform about the ones we didn't
            # Add the resolved attendees to the meeting
            for name, email in resolved_pairs:
                # Store the email
                meeting.attendee_emails[name] = email
                
            error_message = f"I couldn't find the following attendee(s) in the organization: {not_found_names_str}. However, I've added the attendees I could find."
            return (False, error_message)
        
        # Add resolved attendees to the meeting
        for name, email in resolved_pairs:
            # Store the email
            meeting.attendee_emails[name] = email
        
        # If we have ambiguous attendees, start disambiguation
        if ambiguous_attendees:
            # Debug statement
            print(f"DEBUG: Starting disambiguation for ambiguous attendees: {list(ambiguous_attendees.keys())}")
            
            # Store ALL ambiguous attendees for sequential processing
            self.pending_attendees = pending_for_disambiguation
            self.resolved_attendees = []  # Reset resolved list
            
            # Get the first attendee to disambiguate
            first_ambiguous = pending_for_disambiguation[0]
            
            # Start disambiguation session for the first ambiguous attendee
            self.disambiguation_session = {
                'session_id': str(uuid.uuid4()),
                'current_name': first_ambiguous,
                'options': ambiguous_attendees[first_ambiguous]
            }
            
            # Debug
            print(f"DEBUG: Disambiguation session created: {self.disambiguation_session}")
            
            return (False, None)  # No error message, but we need disambiguation
        
        # Debug statement
        print(f"DEBUG: All attendees resolved successfully. Final list: {meeting.attendees}")
        return (True, None)  # All resolved successfully

    def _consolidate_attendees(self, meeting):
        """
        Consolidate attendees to ensure the best names are used
        and duplicates are removed based on email addresses
        """
        if not meeting.attendees or not hasattr(meeting, 'attendee_emails'):
            return
        
        print("DEBUG: Consolidating attendees...")
        print(f"DEBUG: Before consolidation: {meeting.attendees}")
        print(f"DEBUG: Emails: {meeting.attendee_emails}")
        
        # Group attendees by email address
        email_to_names = {}
        
        # First, collect all names that map to the same email
        for name, email in meeting.attendee_emails.items():
            if email not in email_to_names:
                email_to_names[email] = []
            email_to_names[email].append(name)
        
        # For each email, create the best representation
        best_names = {}
        for email, names in email_to_names.items():
            # Prioritize full names (with spaces)
            full_names = [name for name in names if ' ' in name]
            partial_names = [name for name in names if ' ' not in name]
            
            # If full names exist, prefer those
            if full_names:
                best_name = full_names[0]
            elif partial_names:
                # If multiple partial names exist for the same email, combine them
                if len(partial_names) > 1:
                    best_name = ' '.join(partial_names)
                else:
                    best_name = partial_names[0]
            else:
                # Fallback (this should rarely happen)
                best_name = names[0]
            
            best_names[email] = best_name
            print(f"DEBUG: For email {email}, selected best name: {best_name} from {names}")
        
        # Create final attendees list
        final_attendees = list(best_names.values())
        final_emails = {name: email for email, name in zip(best_names.keys(), final_attendees)}
        
        # Update the meeting attendees list and emails
        meeting.attendees = final_attendees
        meeting.attendee_emails = final_emails
        
        print(f"DEBUG: After consolidation: {meeting.attendees}")
        print(f"DEBUG: New emails: {meeting.attendee_emails}")
            
    def handle_attendee_disambiguation(self, user_message):
        """
        Handle disambiguation for attendees with multiple possible email matches
        Returns a response message and True if the message was handled, False otherwise
        """
        if not self.disambiguation_session:
            return None, False
        
        print(f"DEBUG: Processing disambiguation response: '{user_message}'")
        print(f"DEBUG: Current disambiguation session: {self.disambiguation_session}")
        
        # Get current meeting and preserve non-ambiguous attendees
        meeting = self.get_current_meeting()
        
        # CRITICAL: Build a complete list of attendees to preserve, including already resolved ones
        preserved_attendees = []
        preserved_emails = {}
        
        # Add currently resolved attendees with their emails
        for attendee in self.resolved_attendees:
            if attendee in meeting.attendee_emails:
                preserved_attendees.append(attendee)
                preserved_emails[attendee] = meeting.attendee_emails[attendee]
        
        # Add other attendees that aren't being disambiguated
        for attendee in meeting.attendees:
            if attendee not in self.pending_attendees or attendee in self.resolved_attendees:
                if attendee not in preserved_attendees:  # Avoid duplicates
                    preserved_attendees.append(attendee)
                    if attendee in meeting.attendee_emails:
                        preserved_emails[attendee] = meeting.attendee_emails[attendee]
        
        print(f"DEBUG: Preserved attendees before processing: {preserved_attendees}")
        print(f"DEBUG: Preserved emails: {preserved_emails}")
        
        # Clean the user message thoroughly
        clean_message = user_message.strip()
        
        # Remove any special tokens or markdown
        clean_message = re.sub(r'\[.*?\]', '', clean_message).strip()
        
        print(f"DEBUG: Cleaned disambiguation response: '{clean_message}'")
        
        # Handle "both" or "all" responses
        if clean_message.lower() in ['both', 'all']:
            # Select all options
            ambiguous_name = self.disambiguation_session['current_name']
            options = self.disambiguation_session['options']
            
            # Add all options to resolved attendees
            for i, option in enumerate(options):
                _, _, email = option
                
                # Use suffixed names for multiple attendees with the same name
                if i == 0:
                    name_to_use = ambiguous_name
                else:
                    name_to_use = f"{ambiguous_name} {i+1}"
                    
                # Store the resolved email
                meeting.attendee_emails[name_to_use] = email
                # Add to the final attendee list
                if name_to_use not in preserved_attendees:
                    preserved_attendees.append(name_to_use)
            
            # Reset the attendee list with all preserved and resolved attendees
            meeting.attendees = preserved_attendees
            
            # FIX: Check if there are more attendees to disambiguate
            self.resolved_attendees.append(ambiguous_name)
            
            # Move to the next ambiguous attendee if there is one
            remaining_pending = [a for a in self.pending_attendees if a not in self.resolved_attendees]
            
            if remaining_pending:
                # Get the next attendee to disambiguate
                next_attendee = remaining_pending[0]
                print(f"DEBUG: Moving to next ambiguous attendee: {next_attendee}")
                
                # Start a new disambiguation session for this attendee
                result = self.attendee_resolver.resolve_single_attendee(next_attendee)
                if result['status'] == 'ambiguous':
                    self.disambiguation_session = {
                        'session_id': str(uuid.uuid4()),
                        'current_name': next_attendee,
                        'options': result['options']
                    }
                    
                    # Show disambiguation options for the next attendee
                    options_message = self.attendee_resolver.format_disambiguation_options(
                        next_attendee,
                        result['options']
                    )
                    return options_message, True
            else:
                # No more attendees to disambiguate
                self.disambiguation_session = None
                self.pending_attendees = []
                self.resolved_attendees = []
                
                # CRITICAL: Consolidate attendees before generating a response
                self._consolidate_attendees(meeting)
                print(f"DEBUG: All attendees disambiguated, final list: {meeting.attendees}")
                
                # Show confirmation
                if meeting.is_complete():
                    return self._generate_confirmation_message(meeting), True
                else:
                    # Check if anything else is missing
                    missing = meeting.get_missing_info()
                    if missing:
                        missing_str = ", ".join(missing)
                        return f"All attendees added. I still need the following details: {missing_str.capitalize()}.", True
                    else:
                        return "All attendees added. What else would you like to add to this meeting?", True
        
        # CRITICAL FIX: Handle single number selection
        if clean_message.isdigit():
            try:
                selection = int(clean_message)
                # Adjust to 0-based index
                index = selection - 1
                
                ambiguous_name = self.disambiguation_session['current_name']
                options = self.disambiguation_session['options']
                
                print(f"DEBUG: Handling numeric selection: {selection} for {ambiguous_name}")
                print(f"DEBUG: Available options: {options}")
                
                if 0 <= index < len(options):
                    _, _, email = options[index]
                    
                    # Store the resolved email
                    meeting.attendee_emails[ambiguous_name] = email
                    
                    # Add to final attendee list if not already there
                    if ambiguous_name not in preserved_attendees:
                        preserved_attendees.append(ambiguous_name)
                    
                    # Set final attendee list with all preserved and resolved
                    meeting.attendees = preserved_attendees
                    
                    print(f"DEBUG: Selected attendee at index {index}, preserved list: {preserved_attendees}")
                    print(f"DEBUG: Resolved email: {email}")
                    
                    # FIX: Track that we've resolved this attendee
                    self.resolved_attendees.append(ambiguous_name)
                    
                    # FIX: Check if there are more attendees to disambiguate
                    remaining_pending = [a for a in self.pending_attendees if a not in self.resolved_attendees]
                    
                    if remaining_pending:
                        # Get the next attendee to disambiguate
                        next_attendee = remaining_pending[0]
                        print(f"DEBUG: Moving to next ambiguous attendee: {next_attendee}")
                        
                        # Start a new disambiguation session for this attendee
                        result = self.attendee_resolver.resolve_single_attendee(next_attendee)
                        if result['status'] == 'ambiguous':
                            self.disambiguation_session = {
                                'session_id': str(uuid.uuid4()),
                                'current_name': next_attendee,
                                'options': result['options']
                            }
                            
                            # Show disambiguation options for the next attendee
                            options_message = self.attendee_resolver.format_disambiguation_options(
                                next_attendee,
                                result['options']
                            )
                            return options_message, True
                    
                    # CRITICAL: If this is the last disambiguation, consolidate attendees
                    if not remaining_pending:
                        self.disambiguation_session = None
                        self.pending_attendees = []
                        self.resolved_attendees = []
                        
                        # Update the attendee list with the consolidated names
                        self._consolidate_attendees(meeting)
                        
                        print(f"DEBUG: All attendees disambiguated, final list: {meeting.attendees}")
                        
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
                else:
                    print(f"DEBUG: Invalid selection {selection}, options range: 1-{len(options)}")
                    return f"Invalid selection. Please enter a number between 1 and {len(options)}.", True
            except ValueError as e:
                print(f"DEBUG: Error processing selection: {e}")
                pass  # Fall through to the next checks
        
        # Not a number, maybe user wants to cancel disambiguation
        if clean_message.lower() in ['cancel', 'stop', 'exit']:
            if self.disambiguation_session:
                self.attendee_resolver.cancel_disambiguation_session(
                    self.disambiguation_session['session_id']
                )
                self.disambiguation_session = None
                self.pending_attendees = []
                self.resolved_attendees = []
                
                return "Attendee selection cancelled. What would you like to do?", True
        
        print("DEBUG: Could not process disambiguation response, sending help message")
        return "Please enter a number to select an attendee, 'both' to select all, or 'cancel' to stop the selection process.", True

    def _generate_confirmation_message(self, meeting):
        """
        Generate a confirmation message based on the meeting state 
        with comprehensive deduplication and attendee formatting
        """
        # CRITICAL: Consolidate attendees first to ensure best name representation
        self._consolidate_attendees(meeting)
        
        message = "Okay! Let me confirm:\n"
        
        if meeting.date:
            # Always use full date format instead of relative terms
            date_str = meeting.date.strftime("%A, %B %d, %Y")
            message += f"* Date: {date_str}\n"
        
        if meeting.time:
            message += f"* Time: {meeting.date_parser.format_time(meeting.time)}\n"
        
        if meeting.duration:
            message += f"* Duration: {meeting.date_parser.format_duration(meeting.duration)}\n"
        
        # Format attendees with full names and emails
        if meeting.attendees and hasattr(meeting, 'attendee_emails') and meeting.attendee_emails:
            formatted_attendees = []
            for attendee in meeting.attendees:
                if attendee in meeting.attendee_emails:
                    email = meeting.attendee_emails[attendee]
                    
                    # Try to get full name from database
                    try:
                        full_name = self.attendee_resolver.db.get_full_name_by_email(email)
                        if full_name:
                            formatted_attendees.append(f"{full_name} ({email})")
                        else:
                            # Fallback to current name if full name not found
                            formatted_attendees.append(f"{attendee} ({email})")
                    except Exception:
                        # If any error occurs, use the current name
                        formatted_attendees.append(f"{attendee} ({email})")
                else:
                    formatted_attendees.append(attendee)
            
            if formatted_attendees:
                attendees_str = ", ".join(formatted_attendees)
                message += f"* Attendees: {attendees_str}\n"
        
        message += "Is that correct?"
        return message

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
        # CRITICAL FIX: First process all entities regardless of intent
        # This ensures we capture everything the user mentioned
        if entities:
            meeting = self.get_current_meeting()
            if meeting:
                updates = meeting.update_from_entities(entities)
                print(f"Processed all entities first: {updates}")
                
                # Validate date is not in the past (NEW)
                if meeting.date and not self.validate_date(meeting.date):
                    meeting.date = None  # Reset the invalid date
                    return "Sorry, you can't schedule a meeting for a date in the past. Please choose a future date."
                
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
        confirmation_phrases = ['yes', 'confirm', 'ok', 'okay', 'correct', 'that is correct', 'looks good']
        
        if meeting.is_complete() and any(phrase == original_message for phrase in confirmation_phrases):
            # Explicit confirmation - avoid processing as an entity
            meeting.is_confirmed = True
            return "✅ Meeting scheduled successfully!"
        
        if any(phrase == original_message for phrase in restart_phrases):
            # Completely reset the meeting
            meeting = self.start_new_meeting()
            return "Meeting context has been reset. I'm ready to start over. How can I help you schedule a meeting?"
                
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
                    # Validate date is not in the past (NEW)
                    if not self.validate_date(parsed_date):
                        return "Sorry, you can't schedule a meeting for a date in the past. Please choose a future date."
                        
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
                    # Validate date is not in the past (should not happen, but just in case)
                    if not self.validate_date(next_date):
                        return "Sorry, there was an issue with the date. Please choose a future date."
                        
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
                    # Validate date is not in the past (NEW)
                    if not self.validate_date(parsed_date):
                        return "Sorry, you can't schedule a meeting for a date in the past. Please choose a future date."
                        
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
            
            # CRITICAL FIX: Check if date is in the past (NEW)
            if meeting.date and not self.validate_date(meeting.date):
                meeting.date = None  # Reset the invalid date
                return "Sorry, you can't schedule a meeting for a date in the past. Please choose a future date."
            
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
                response = f"Time set to {time_str}."
                
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
        
        elif intent == "Change_Date":
            # Update date
            meeting.update_from_entities(entities)
            meeting.last_update = "date"
            
            if "DATE" in entities and entities["DATE"]:
                if meeting.date:
                    # Validate date is not in the past (NEW)
                    if not self.validate_date(meeting.date):
                        return "Sorry, you can't schedule a meeting for a date in the past. Please choose a future date."
                    
                    date_str = meeting.date.strftime("%A, %B %d, %Y")
                    response = f"Date changed to {date_str}."
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
                self.waiting_for = "date"
                return "What date would you like to change it to?"
        
        elif intent == "Change_Duration":
            # Update duration
            meeting.update_from_entities(entities)
            meeting.last_update = "duration"
            
            if "DURATION" in entities and entities["DURATION"]:
                duration_str = meeting.date_parser.format_duration(meeting.duration)
                response = f"Duration changed to {duration_str}."
                
                # If meeting is otherwise complete, show confirmation
                if meeting.is_complete():
                    response += "\n\n" + self._generate_confirmation_message(meeting)
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
                    # Check if date is in the past (NEW)
                    if not self.validate_date(meeting.date):
                        meeting.date = None # Reset invalid date
                        return "Sorry, you can't schedule a meeting for a date in the past. Please choose a future date."
                    
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

    # def _generate_confirmation_message(self, meeting):
    #     """Generate a confirmation message based on the meeting state with strong deduplication"""
    #     message = "Okay! Let me confirm:\n"
        
    #     if meeting.date:
    #         # Always use full date format instead of relative terms like "Tomorrow"
    #         date_str = meeting.date.strftime("%A, %B %d, %Y")  # Example: "Tuesday, March 12, 2025"
    #         message += f"* Date: {date_str}\n"
            
    #     if meeting.time:
    #         message += f"* Time: {meeting.date_parser.format_time(meeting.time)}\n"
            
    #     if meeting.duration:
    #         message += f"* Duration: {meeting.date_parser.format_duration(meeting.duration)}\n"
            
    #     # CRITICAL FIX: Completely overhaul attendee deduplication 
    #     if meeting.attendees and hasattr(meeting, 'attendee_emails') and meeting.attendee_emails:
    #         # First, group attendees by email
    #         attendees_by_email = {}
            
    #         # Group all attendees with the same email
    #         for attendee in meeting.attendees:
    #             email = meeting.attendee_emails.get(attendee, "")
    #             if email:
    #                 if email not in attendees_by_email:
    #                     attendees_by_email[email] = []
    #                 attendees_by_email[email].append(attendee)
            
    #         # For each email, select the best attendee name (prioritize full names)
    #         best_attendees = []
    #         for email, names in attendees_by_email.items():
    #             # Sort names by length and prefer names with spaces (usually full names)
    #             sorted_names = sorted(names, key=lambda x: (-len(x), -x.count(' ')))
    #             # Take the first (best) name
    #             if sorted_names:
    #                 best_name = sorted_names[0]
    #                 best_attendees.append((best_name, email))
            
    #         # Include attendees without emails
    #         for attendee in meeting.attendees:
    #             if attendee not in meeting.attendee_emails:
    #                 best_attendees.append((attendee, ""))
            
    #         # Format the attendees for display
    #         if best_attendees:
    #             formatted_attendees = []
    #             for name, email in best_attendees:
    #                 if email:
    #                     formatted_attendees.append(f"{name} ({email})")
    #                 else:
    #                     formatted_attendees.append(name)
                
    #             attendees_str = ", ".join(formatted_attendees)
    #             message += f"* Attendees: {attendees_str}\n"
        
    #     message += "Is that correct?"
    #     return message

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
    
    def validate_date(self, date_obj):
        """Validate that a date is not in the past"""
        today = datetime.datetime.now().date()
        
        if date_obj < today:
            return False
        return True