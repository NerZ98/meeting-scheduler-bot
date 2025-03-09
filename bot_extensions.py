from utils.graph_api import MicrosoftGraphClient
import datetime
import os
import json
import logging

class MeetingSchedulerWithGraphAPI:
    """
    Extension class that adds Microsoft Graph API capabilities to the Meeting Scheduler Bot
    with OAuth 2.0 Authorization Code Flow
    """
    def __init__(self, config_path=None):
        # Initialize the Graph client
        self.graph_client = MicrosoftGraphClient(config_path)
        self.logger = logging.getLogger(__name__)
        
        # Store meeting IDs for update/cancel operations
        self.meeting_id_map = {}
        self._load_meeting_id_map()
    
    def get_auth_url(self):
        """
        Get authorization URL for OAuth consent flow
        
        Returns:
        - Tuple of (auth_url, state) where state should be stored in session
        """
        return self.graph_client.get_auth_url()
    
    def handle_auth_callback(self, code):
        """
        Handle the OAuth callback and exchange code for token
        
        Parameters:
        - code: Authorization code from callback
        
        Returns:
        - Result of token exchange
        """
        return self.graph_client.get_token_from_code(code)
    
    def schedule_meeting(self, meeting_context, user_id=None):
        """
        Schedule a meeting using the Microsoft Graph API
        
        Parameters:
        - meeting_context: MeetingContext object from the bot
        - user_id: User's ID for authentication (from token)
        
        Returns:
        - Dictionary with meeting details and Graph API response
        """
        try:
            # Convert meeting context to meeting data for Graph API
            meeting_data = self._convert_meeting_context_to_graph_data(meeting_context)
            
            # Call the Graph API to create the meeting
            graph_response = self.graph_client.create_meeting(user_id, meeting_data)
            
            # Store the meeting ID for future reference
            meeting_id = graph_response.get('id')
            if meeting_id:
                self.meeting_id_map[meeting_context.meeting_id] = {
                    'graph_meeting_id': meeting_id,
                    'user_id': user_id
                }
                self._save_meeting_id_map()  # Persist the ID mapping
            
            return {
                'success': True,
                'meeting_id': meeting_id,
                'response': graph_response
            }
        
        except Exception as e:
            self.logger.error(f"Error scheduling meeting: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_meeting(self, meeting_context):
        """
        Update an existing meeting using the Microsoft Graph API
        
        Parameters:
        - meeting_context: MeetingContext object from the bot
        
        Returns:
        - Dictionary with meeting details and Graph API response
        """
        try:
            # Get the Graph API meeting ID and user ID
            meeting_info = self.meeting_id_map.get(meeting_context.meeting_id)
            if not meeting_info:
                raise ValueError("Meeting ID not found. This meeting may not have been scheduled in Microsoft Graph.")
            
            graph_meeting_id = meeting_info.get('graph_meeting_id')
            user_id = meeting_info.get('user_id')
            
            # Convert meeting context to meeting data for Graph API
            meeting_data = self._convert_meeting_context_to_graph_data(meeting_context)
            
            # Call the Graph API to update the meeting
            graph_response = self.graph_client.update_meeting(
                user_id, graph_meeting_id, meeting_data
            )
            
            return {
                'success': True,
                'meeting_id': graph_meeting_id,
                'response': graph_response
            }
        
        except Exception as e:
            self.logger.error(f"Error updating meeting: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_meeting(self, meeting_context, comment="Meeting cancelled"):
        """
        Cancel a meeting using the Microsoft Graph API
        
        Parameters:
        - meeting_context: MeetingContext object from the bot
        - comment: Optional cancellation comment
        
        Returns:
        - Dictionary with meeting details and Graph API response
        """
        try:
            # Get the Graph API meeting ID and user ID
            meeting_info = self.meeting_id_map.get(meeting_context.meeting_id)
            if not meeting_info:
                raise ValueError("Meeting ID not found. This meeting may not have been scheduled in Microsoft Graph.")
            
            graph_meeting_id = meeting_info.get('graph_meeting_id')
            user_id = meeting_info.get('user_id')
            
            # Call the Graph API to cancel the meeting
            graph_response = self.graph_client.cancel_meeting(
                user_id, graph_meeting_id, comment
            )
            
            # Remove the meeting ID from the map
            if meeting_context.meeting_id in self.meeting_id_map:
                del self.meeting_id_map[meeting_context.meeting_id]
                self._save_meeting_id_map()  # Persist the ID mapping
            
            return {
                'success': True,
                'meeting_id': graph_meeting_id,
                'response': graph_response
            }
        
        except Exception as e:
            self.logger.error(f"Error cancelling meeting: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_attendee_availability(self, meeting_context, user_id):
        """
        Check availability of attendees for a meeting time
        
        Parameters:
        - meeting_context: MeetingContext object from the bot
        - user_id: User's ID for authentication (from token)
        
        Returns:
        - Dictionary with availability information
        """
        try:
            # Only proceed if we have date, time, and attendees
            if not (meeting_context.date and meeting_context.time and meeting_context.attendees):
                return {
                    'success': False,
                    'error': 'Missing date, time, or attendees'
                }
            
            # Convert attendee names to emails
            attendee_emails = []
            for attendee in meeting_context.attendees:
                # In a real app, you'd look up emails from your system or a directory
                # This is a simplified placeholder approach
                attendee_email = f"{attendee.lower().replace(' ', '.')}@example.com"
                attendee_emails.append(attendee_email)
            
            # Convert date and time to ISO format
            date_string = meeting_context.date.isoformat()
            time_string = meeting_context.time.strftime("%H:%M:%S")
            
            start_time = f"{date_string}T{time_string}"
            start_datetime = datetime.datetime.fromisoformat(start_time)
            
            # Calculate end time based on duration
            duration_minutes = meeting_context.duration or 30  # Default to 30 minutes
            end_datetime = start_datetime + datetime.timedelta(minutes=duration_minutes)
            end_time = end_datetime.isoformat()
            
            # Call the Graph API to check availability
            availability = self.graph_client.get_user_availability(
                user_id,
                attendee_emails, 
                start_time, 
                end_time
            )
            
            # Process the results
            available_attendees = []
            unavailable_attendees = []
            
            for i, schedule in enumerate(availability.get('value', [])):
                view = schedule.get('availabilityView', '')
                # If the view contains '0', the attendee is available
                if '0' in view and '1' not in view and '2' not in view and '3' not in view:
                    available_attendees.append(meeting_context.attendees[i])
                else:
                    unavailable_attendees.append(meeting_context.attendees[i])
            
            return {
                'success': True,
                'available_attendees': available_attendees,
                'unavailable_attendees': unavailable_attendees,
                'response': availability
            }
        
        except Exception as e:
            self.logger.error(f"Error checking availability: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_user_profile(self, user_id):
        """
        Get the user's profile information
        
        Parameters:
        - user_id: User's ID for authentication (from token)
        
        Returns:
        - User profile information
        """
        try:
            return self.graph_client.get_user_profile(user_id)
        except Exception as e:
            self.logger.error(f"Error getting user profile: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _convert_meeting_context_to_graph_data(self, meeting_context):
        """
        Convert a MeetingContext object to the format expected by the Graph API
        
        Parameters:
        - meeting_context: MeetingContext object from the bot
        
        Returns:
        - Dictionary with meeting data formatted for Graph API
        """
        # Convert date and time to ISO format
        date_string = meeting_context.date.isoformat() if meeting_context.date else datetime.date.today().isoformat()
        
        if meeting_context.time:
            time_string = meeting_context.time.strftime("%H:%M:%S")
        else:
            # Default to current time if not specified
            time_string = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Convert duration to minutes
        if isinstance(meeting_context.duration, int):
            duration_minutes = meeting_context.duration
        else:
            # Default to 30 minutes
            duration_minutes = 30
        
        # Prepare the meeting data
        meeting_data = {
            'title': meeting_context.title,
            'description': meeting_context.description,
            'date': date_string,
            'time': time_string,
            'duration_minutes': duration_minutes,
            'attendees': meeting_context.attendees
        }
        
        return meeting_data
    
    def _save_meeting_id_map(self):
        """Save the meeting ID map to a file for persistence"""
        try:
            with open('meeting_id_map.json', 'w') as f:
                json.dump(self.meeting_id_map, f)
        except Exception as e:
            self.logger.error(f"Error saving meeting ID map: {str(e)}")
    
    def _load_meeting_id_map(self):
        """Load the meeting ID map from a file"""
        try:
            if os.path.exists('meeting_id_map.json'):
                with open('meeting_id_map.json', 'r') as f:
                    self.meeting_id_map = json.load(f)
            else:
                self.meeting_id_map = {}
        except Exception as e:
            self.logger.error(f"Error loading meeting ID map: {str(e)}")
            self.meeting_id_map = {}