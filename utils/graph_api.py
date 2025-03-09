import os
import json
import requests
import datetime
from msal import ConfidentialClientApplication
import uuid

class MicrosoftGraphClient:
    """
    Client for Microsoft Graph API integration with OAuth 2.0 Authorization Code Flow
    """
    
    def __init__(self, config_path=None):
        # Load configuration
        self.config = self._load_config(config_path)
        self.access_token = None
        self.token_expires = None
        self.token_cache = {}  # Cache tokens by user ID
        
        # Initialize MSAL application
        self.app = ConfidentialClientApplication(
            client_id=self.config.get('client_id'),
            client_credential=self.config.get('client_secret'),
            authority=f"https://login.microsoftonline.com/common",  # Use common endpoint for personal accounts
        )
    
    def _load_config(self, config_path=None):
        """Load configuration from file or environment variables"""
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        
        # Fallback to environment variables
        return {
            'client_id': os.environ.get('MS_GRAPH_CLIENT_ID'),
            'client_secret': os.environ.get('MS_GRAPH_CLIENT_SECRET'),
            'tenant_id': os.environ.get('MS_GRAPH_TENANT_ID'),
            'redirect_uri': os.environ.get('MS_GRAPH_REDIRECT_URI')
        }
    
    def get_auth_url(self):
        """
        Get authorization URL for OAuth consent flow
        
        Returns:
        - Tuple of (auth_url, state) where state should be stored in session
        """
        # Generate a random state value for CSRF protection
        state = str(uuid.uuid4())
        
        # Generate the authorization URL
        auth_url = self.app.get_authorization_request_url(
            scopes=["Calendars.ReadWrite", "User.Read"],
            state=state,
            redirect_uri=self.config.get('redirect_uri')
        )
        
        return auth_url, state
    
    def get_token_from_code(self, code):
        """
        Exchange authorization code for access token
        
        Parameters:
        - code: Authorization code from callback
        
        Returns:
        - Token response including access_token and refresh_token
        """
        result = self.app.acquire_token_by_authorization_code(
            code=code,
            scopes=["Calendars.ReadWrite", "User.Read"],
            redirect_uri=self.config.get('redirect_uri')
        )
        
        if "access_token" in result:
            # Extract user info
            user_id = result.get("id_token_claims", {}).get("oid") or result.get("id_token_claims", {}).get("sub")
            
            # Store token in cache
            self.token_cache[user_id] = {
                "access_token": result["access_token"],
                "refresh_token": result.get("refresh_token"),
                "expires_in": result.get("expires_in", 3600),
                "expires_at": datetime.datetime.now() + datetime.timedelta(seconds=result.get("expires_in", 3600)),
                "user_id": user_id
            }
            
            return {
                "success": True,
                "user_id": user_id,
                "expires_in": result.get("expires_in", 3600)
            }
        else:
            error = result.get("error")
            error_description = result.get("error_description")
            return {
                "success": False,
                "error": error,
                "error_description": error_description
            }
    
    def get_token_for_user(self, user_id):
        """
        Get a valid token for a specific user, refreshing if necessary
        
        Parameters:
        - user_id: The user's ID
        
        Returns:
        - Access token or None if no valid token available
        """
        # Check if we have a token for this user
        if user_id not in self.token_cache:
            return None
        
        token_info = self.token_cache[user_id]
        now = datetime.datetime.now()
        
        # Check if token is expired or about to expire
        if now >= token_info["expires_at"] - datetime.timedelta(minutes=5):
            # Token is expired, try to refresh
            if "refresh_token" in token_info:
                result = self.app.acquire_token_by_refresh_token(
                    refresh_token=token_info["refresh_token"],
                    scopes=["Calendars.ReadWrite", "User.Read"]
                )
                
                if "access_token" in result:
                    # Update token in cache
                    token_info["access_token"] = result["access_token"]
                    token_info["refresh_token"] = result.get("refresh_token", token_info["refresh_token"])
                    token_info["expires_in"] = result.get("expires_in", 3600)
                    token_info["expires_at"] = now + datetime.timedelta(seconds=result.get("expires_in", 3600))
                    
                    return token_info["access_token"]
                else:
                    # Refresh failed
                    return None
            else:
                # No refresh token
                return None
        
        # Token is still valid
        return token_info["access_token"]
    
    def _make_request(self, method, endpoint, data=None, user_id=None):
        """
        Make a request to Microsoft Graph API
        
        Parameters:
        - method: HTTP method (get, post, patch, delete)
        - endpoint: API endpoint
        - data: Request data (for POST/PATCH)
        - user_id: User ID to use for the request
        
        Returns:
        - API response
        """
        token = self.get_token_for_user(user_id)
        if not token:
            raise Exception("No valid token available for this user")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://graph.microsoft.com/v1.0/{endpoint}"
        
        if method.lower() == "get":
            response = requests.get(url, headers=headers)
        elif method.lower() == "post":
            response = requests.post(url, headers=headers, json=data)
        elif method.lower() == "patch":
            response = requests.patch(url, headers=headers, json=data)
        elif method.lower() == "delete":
            response = requests.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if response.status_code >= 400:
            raise Exception(f"Error {response.status_code}: {response.text}")
        
        return response.json() if response.content else None
    
    def create_meeting(self, user_id, meeting_data):
        """
        Create a meeting in the user's calendar
        
        Parameters:
        - user_id: User's ID (from token)
        - meeting_data: Dictionary with meeting details
        
        Returns:
        - Meeting object from Graph API
        """
        # Format the meeting data for Microsoft Graph
        start_time = f"{meeting_data['date']}T{meeting_data['time']}:00"
        
        # Calculate end time based on duration (in minutes)
        start_datetime = datetime.datetime.fromisoformat(start_time)
        duration_minutes = meeting_data.get('duration_minutes', 30)  # Default to 30 minutes
        end_datetime = start_datetime + datetime.timedelta(minutes=duration_minutes)
        end_time = end_datetime.isoformat()
        
        # Format attendees
        attendees = []
        for attendee in meeting_data.get('attendees', []):
            # Check if attendee is an email or just a name
            if '@' in attendee:
                email = attendee
            else:
                # This is just a placeholder - in a real app, you'd look up the email
                email = f"{attendee.lower().replace(' ', '.')}@example.com"
            
            attendees.append({
                "emailAddress": {
                    "address": email,
                    "name": attendee
                },
                "type": "required"
            })
        
        # Create event object
        event = {
            "subject": meeting_data.get('title', 'Meeting'),
            "body": {
                "contentType": "HTML",
                "content": meeting_data.get('description', '')
            },
            "start": {
                "dateTime": start_time,
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end_time,
                "timeZone": "UTC"
            },
            "location": {
                "displayName": meeting_data.get('location', '')
            },
            "attendees": attendees,
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness"
        }
        
        # Make the API call (use /me endpoint with delegated permissions)
        endpoint = "me/events"
        return self._make_request("post", endpoint, event, user_id)
    
    def update_meeting(self, user_id, meeting_id, meeting_data):
        """
        Update an existing meeting
        
        Parameters:
        - user_id: User's ID (from token)
        - meeting_id: ID of the meeting to update
        - meeting_data: Dictionary with updated meeting details
        
        Returns:
        - Updated meeting object from Graph API
        """
        # Prepare the update payload (only include fields that are changing)
        update = {}
        
        if 'title' in meeting_data:
            update["subject"] = meeting_data['title']
        
        if 'description' in meeting_data:
            update["body"] = {
                "contentType": "HTML",
                "content": meeting_data['description']
            }
        
        if 'date' in meeting_data and 'time' in meeting_data:
            start_time = f"{meeting_data['date']}T{meeting_data['time']}:00"
            start_datetime = datetime.datetime.fromisoformat(start_time)
            
            # Calculate end time
            duration_minutes = meeting_data.get('duration_minutes', 30)
            end_datetime = start_datetime + datetime.timedelta(minutes=duration_minutes)
            end_time = end_datetime.isoformat()
            
            update["start"] = {
                "dateTime": start_time,
                "timeZone": "UTC"
            }
            update["end"] = {
                "dateTime": end_time,
                "timeZone": "UTC"
            }
        
        if 'location' in meeting_data:
            update["location"] = {
                "displayName": meeting_data['location']
            }
        
        if 'attendees' in meeting_data:
            attendees = []
            for attendee in meeting_data['attendees']:
                # Check if attendee is an email or just a name
                if '@' in attendee:
                    email = attendee
                else:
                    # This is just a placeholder - in a real app, you'd look up the email
                    email = f"{attendee.lower().replace(' ', '.')}@example.com"
                
                attendees.append({
                    "emailAddress": {
                        "address": email,
                        "name": attendee
                    },
                    "type": "required"
                })
            
            update["attendees"] = attendees
        
        # Make the API call
        endpoint = f"me/events/{meeting_id}"
        return self._make_request("patch", endpoint, update, user_id)
    
    def cancel_meeting(self, user_id, meeting_id, comment="Meeting cancelled"):
        """
        Cancel a meeting
        
        Parameters:
        - user_id: User's ID (from token)
        - meeting_id: ID of the meeting to cancel
        - comment: Optional cancellation comment
        
        Returns:
        - API response
        """
        endpoint = f"me/events/{meeting_id}/cancel"
        data = {
            "comment": comment
        }
        return self._make_request("post", endpoint, data, user_id)
    
    def get_user_availability(self, user_id, attendees, start_time, end_time):
        """
        Check availability for a list of users in a time window
        
        Parameters:
        - user_id: User's ID (from token) making the request
        - attendees: List of attendee emails
        - start_time: Start time in ISO format
        - end_time: End time in ISO format
        
        Returns:
        - Availability information
        """
        endpoint = "me/calendar/getSchedule"
        schedules = [{"emailAddress": {"address": attendee}} for attendee in attendees]
        
        data = {
            "schedules": schedules,
            "startTime": {
                "dateTime": start_time,
                "timeZone": "UTC"
            },
            "endTime": {
                "dateTime": end_time,
                "timeZone": "UTC"
            },
            "availabilityViewInterval": 15  # 15-minute intervals
        }
        
        return self._make_request("post", endpoint, data, user_id)
    
    def get_user_profile(self, user_id):
        """
        Get user information from Microsoft Graph
        
        Parameters:
        - user_id: User's ID (from token)
        
        Returns:
        - User profile information
        """
        endpoint = "me"
        return self._make_request("get", endpoint, None, user_id)
    
    def get_user_meetings(self, user_id, start_date=None, end_date=None):
        """
        Get a user's meetings in a date range
        
        Parameters:
        - user_id: User's ID (from token)
        - start_date: Start date in ISO format (optional)
        - end_date: End date in ISO format (optional)
        
        Returns:
        - List of meetings
        """
        endpoint = "me/events"
        
        # Add filter for date range if provided
        if start_date and end_date:
            filter_query = f"?$filter=start/dateTime ge '{start_date}T00:00:00' and end/dateTime le '{end_date}T23:59:59'"
            endpoint += filter_query
        
        return self._make_request("get", endpoint, None, user_id)