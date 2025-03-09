import random

class ResponseGenerator:
    """
    Class to generate natural language responses for the bot
    """
    
    def __init__(self):
        # Templates for various response types
        self.greeting_templates = [
            "Hello! How can I help you today?",
            "Hi there! Need help scheduling a meeting?",
            "Hello! I'm your meeting scheduling assistant. How can I help?",
            "Hi! I can help you schedule, modify, or cancel meetings. What would you like to do?"
        ]
        
        self.time_request_templates = [
            "What time should I schedule it for?",
            "At what time would you like to have this meeting?",
            "When should the meeting start?",
            "Got it. What time works for you?"
        ]
        
        self.date_request_templates = [
            "On what date should I schedule this meeting?",
            "What day works for you?",
            "When would you like to have this meeting?",
            "Which date should I put on the calendar?"
        ]
        
        self.attendee_request_templates = [
            "Who should I add to this meeting?",
            "Who will be attending?",
            "Who would you like to invite?",
            "Which people should I include in the meeting?"
        ]
        
        self.confirmation_templates = [
            "Is that correct?",
            "Does that look right?",
            "Should I go ahead with these details?",
            "Is this what you're looking for?"
        ]
        
        self.success_templates = [
            "✅ Meeting scheduled successfully!",
            "✅ Your meeting has been scheduled!",
            "✅ Meeting is all set!",
            "✅ Meeting has been booked successfully!"
        ]
        
        self.cancel_templates = [
            "❌ Meeting cancelled.",
            "❌ I've cancelled the meeting.",
            "❌ The meeting has been removed from your schedule.",
            "❌ Meeting cancelled as requested."
        ]
        
        self.change_templates = [
            "No problem. I've updated that for you.",
            "Done! I've made that change.",
            "Updated successfully.",
            "Change confirmed."
        ]
        
        self.fallback_templates = [
            "I'm a meeting scheduling assistant. I can help you schedule, modify, or cancel meetings. How can I assist you today?",
            "Sorry, I didn't understand that. I'm designed to help with scheduling meetings. What would you like me to do?",
            "I can help you schedule meetings, add participants, change times, or cancel appointments. What do you need?",
            "Sorry, I'm focused on meeting scheduling. How can I help you with that?"
        ]
    
    def get_greeting(self):
        """Return a random greeting"""
        return random.choice(self.greeting_templates)
    
    def get_time_request(self):
        """Return a request for time"""
        return random.choice(self.time_request_templates)
    
    def get_date_request(self):
        """Return a request for date"""
        return random.choice(self.date_request_templates)
    
    def get_attendee_request(self):
        """Return a request for attendees"""
        return random.choice(self.attendee_request_templates)
    
    def get_confirmation(self):
        """Return a confirmation request"""
        return random.choice(self.confirmation_templates)
    
    def get_success_message(self):
        """Return a success message"""
        return random.choice(self.success_templates)
    
    def get_cancel_message(self):
        """Return a cancellation message"""
        return random.choice(self.cancel_templates)
    
    def get_change_acknowledgment(self):
        """Return an acknowledgment of a change"""
        return random.choice(self.change_templates)
    
    def get_fallback(self):
        """Return a fallback message"""
        return random.choice(self.fallback_templates)
    
    def format_meeting_summary(self, meeting_data):
        """Format a summary of the meeting data"""
        summary = ""
        
        if meeting_data.get('date'):
            summary += f"* Date: {meeting_data['date']}\n"
            
        if meeting_data.get('time'):
            summary += f"* Time: {meeting_data['time']}\n"
            
        if meeting_data.get('duration'):
            summary += f"* Duration: {meeting_data['duration']}\n"
            
        if meeting_data.get('attendees'):
            attendees = ", ".join(meeting_data['attendees'])
            summary += f"* Attendees: {attendees}\n"
            
        return summary
    
    def get_change_response(self, changed_field, new_value):
        """Get a response acknowledging a specific change"""
        templates = {
            "time": [
                f"No problem. Time changed to {new_value}.",
                f"I've updated the time to {new_value}.",
                f"Time is now set to {new_value}.",
                f"Meeting time changed to {new_value}."
            ],
            "date": [
                f"No problem. Date changed to {new_value}.",
                f"I've updated the date to {new_value}.",
                f"Date is now set to {new_value}.",
                f"Meeting date changed to {new_value}."
            ],
            "duration": [
                f"✅ Duration changed to {new_value}.",
                f"I've set the duration to {new_value}.",
                f"Meeting will now last for {new_value}.",
                f"Duration updated to {new_value}."
            ],
            "attendees": [
                f"✅ {new_value} has been added.",
                f"I've added {new_value} to the meeting.",
                f"{new_value} will now be included in the meeting.",
                f"Added {new_value} to the attendee list."
            ]
        }
        
        if changed_field in templates:
            return random.choice(templates[changed_field])
        else:
            return self.get_change_acknowledgment() 
