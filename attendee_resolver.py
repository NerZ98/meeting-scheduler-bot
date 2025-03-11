import logging
from user_database import UserDatabase

class AttendeeResolver:
    """Service to resolve attendee names to email addresses"""
    
    def __init__(self, db_path='users.db'):
        self.db = UserDatabase(db_path)
        self.logger = logging.getLogger(__name__)
        self.pending_resolution = {}  # Dictionary to store pending resolution state
        
    def resolve_attendees(self, attendee_names):
        """
        Resolve a list of attendee names to email addresses
        
        Returns a tuple:
        (resolved_attendees, ambiguous_attendees, not_found_attendees)
        
        - resolved_attendees: List of tuples (name, email) for attendees that were resolved
        - ambiguous_attendees: Dictionary of {name: [(first_name, last_name, email), ...]} for attendees with multiple matches
        - not_found_attendees: List of names that weren't found in the database
        """
        resolved_attendees = []
        ambiguous_attendees = {}
        not_found_attendees = []
        
        for name in attendee_names:
            result = self.resolve_single_attendee(name)
            
            if result['status'] == 'resolved':
                resolved_attendees.append((name, result['email']))
            elif result['status'] == 'ambiguous':
                ambiguous_attendees[name] = result['options']
            elif result['status'] == 'not_found':
                not_found_attendees.append(name)
        
        return resolved_attendees, ambiguous_attendees, not_found_attendees
    
    def resolve_single_attendee(self, name):
        """
        Resolve a single attendee name to an email address
        
        Returns a dictionary with status and additional information:
        - {'status': 'resolved', 'email': email} if exactly one match is found
        - {'status': 'ambiguous', 'options': [(first_name, last_name, email), ...]} if multiple matches are found
        - {'status': 'not_found'} if no matches are found
        """
        name = name.strip()
        
        # Try to find users by this name
        matching_users = self.db.find_users_by_name(name)
        
        if not matching_users:
            self.logger.info(f"No users found for name '{name}'")
            return {'status': 'not_found', 'name': name}  # Added name to make it clear which name wasn't found
        
        if len(matching_users) == 1:
            # Exactly one match found
            first_name, last_name, email = matching_users[0]
            self.logger.info(f"Resolved '{name}' to {email}")
            return {'status': 'resolved', 'email': email}
        
        # Multiple matches found - check for exact match
        name_parts = name.split()
        if len(name_parts) >= 2:
            first_name = name_parts[0]
            last_name = name_parts[-1]
            
            exact_matches = self.db.find_exact_user(first_name, last_name)
            
            if len(exact_matches) == 1:
                # Exactly one exact match found
                _, _, email = exact_matches[0]
                self.logger.info(f"Resolved '{name}' to {email} (exact match)")
                return {'status': 'resolved', 'email': email}
        
        # Multiple matches, need user to disambiguate
        self.logger.info(f"Found {len(matching_users)} possible matches for '{name}'")
        return {'status': 'ambiguous', 'options': matching_users}
    
    def start_disambiguation_session(self, ambiguous_attendees):
        """
        Start a disambiguation session for resolving ambiguous attendees
        
        Returns a dictionary with session_id and the first name to disambiguate
        """
        import uuid
        
        session_id = str(uuid.uuid4())
        self.pending_resolution[session_id] = {
            'ambiguous_attendees': ambiguous_attendees,
            'current_index': 0,
            'resolved_attendees': [],
            'names_list': list(ambiguous_attendees.keys())
        }
        
        return {
            'session_id': session_id,
            'current_name': self.pending_resolution[session_id]['names_list'][0],
            'options': ambiguous_attendees[self.pending_resolution[session_id]['names_list'][0]]
        }
    
    def resolve_disambiguation_selection(self, session_id, option_index):
        """
        Process a user's selection to disambiguate a name
        
        Returns a dictionary with the next name to disambiguate or completion status
        """
        if session_id not in self.pending_resolution:
            return {'status': 'error', 'message': 'Invalid session ID'}
        
        session = self.pending_resolution[session_id]
        current_name = session['names_list'][session['current_index']]
        options = session['ambiguous_attendees'][current_name]
        
        # Validate the option index
        if option_index < 0 or option_index >= len(options):
            return {'status': 'error', 'message': 'Invalid option index'}
        
        # Get the selected option
        selected_option = options[option_index]
        _, _, email = selected_option
        
        # Add to resolved attendees
        session['resolved_attendees'].append((current_name, email))
        
        # Move to the next name
        session['current_index'] += 1
        
        # Check if we've resolved all names
        if session['current_index'] >= len(session['names_list']):
            # Done with disambiguation
            resolved_attendees = session['resolved_attendees']
            del self.pending_resolution[session_id]
            
            return {
                'status': 'completed',
                'resolved_attendees': resolved_attendees
            }
        
        # Return the next name to disambiguate
        next_name = session['names_list'][session['current_index']]
        next_options = session['ambiguous_attendees'][next_name]
        
        return {
            'status': 'in_progress',
            'session_id': session_id,
            'current_name': next_name,
            'options': next_options
        }
    
    def format_disambiguation_options(self, name, options):
        """Format disambiguation options for display to the user"""
        message = f"Multiple people found with the name '{name}'. Please select one:\n\n"
        
        for i, (first_name, last_name, email) in enumerate(options):
            message += f"{i+1}. {first_name} {last_name} - {email}\n"
        
        message += "\nReply with just the number of your selection."
        
        return message
    
    def cancel_disambiguation_session(self, session_id):
        """Cancel a disambiguation session"""
        if session_id in self.pending_resolution:
            del self.pending_resolution[session_id]
            return {'status': 'cancelled'}
        
        return {'status': 'error', 'message': 'Invalid session ID'}