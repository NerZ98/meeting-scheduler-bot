import torch
from models.intent_model import IntentClassificationModel
from models.entity_model import EntityRecognitionModel
from bot.state_manager import ConversationState
from bot.response_generator import ResponseGenerator

class MeetingSchedulerBot:
    """
    Main class for the Meeting Scheduler Bot
    """
    
    def __init__(self, intent_model_path=None, entity_model_path=None):
        # Initialize models
        self.intent_model = IntentClassificationModel()
        self.entity_model = EntityRecognitionModel()
        
        # Load models if paths provided
        if intent_model_path:
            self.intent_model.load(intent_model_path)
        
        if entity_model_path:
            self.entity_model.load(entity_model_path)
        
        # Initialize conversation state
        self.state = ConversationState()
        
        # Initialize response generator
        self.response_generator = ResponseGenerator()
        
        # Greeting message
        self.greeting = self.response_generator.get_greeting()
    
    def process_message(self, user_message):
        """
        Process a user message and return a response
        """
        # Skip empty messages
        if not user_message or user_message.strip() == "":
            return "I didn't catch that. How can I help you with scheduling a meeting?"
        
        # Check for simple greeting
        if user_message.lower() in ["hi", "hello", "hey"]:
            return self.greeting
        
        # Get the current meeting context
        meeting = self.state.get_current_meeting()
        
        # CRITICAL: Check for disambiguation mode first, before any entity extraction
        if self.state.disambiguation_session:
            # Try to handle the message as a disambiguation response
            response, handled = self.state.handle_attendee_disambiguation(user_message)
            if handled:
                # Log the conversation
                self.state.log_conversation(user_message, response)
                return response
        
        # Preprocess the message to identify and handle special cases
        lower_msg = user_message.lower().strip()
        
        # Direct time processing - this catches statements like "at 2pm" that might be missed
        if "at " in lower_msg and any(term in lower_msg for term in ["am", "pm", "o'clock"]):
            # Try to extract time directly
            try:
                self.state.handle_time_in_message(meeting, user_message)
            except Exception as e:
                print(f"Error processing time: {e}")
        
        # Rule-based overrides for common scheduling phrases
        combined_request = False
        if ("schedule" in lower_msg or "set up" in lower_msg or "book" in lower_msg or "arrange" in lower_msg) and (
            "meeting" in lower_msg or "call" in lower_msg or "appointment" in lower_msg
        ):
            print("Rule-based override: Forcing Schedule_Meeting intent")
            intent = "Schedule_Meeting"
            combined_request = True
        else:
            # Classify intent
            intent_result = self.intent_model.predict(user_message)
            intent = intent_result['intent']
            print(f"Detected intent: {intent}")
            print(f"Intent probabilities: {intent_result['probabilities']}")
        
        # Extract entities
        entities = self.entity_model.predict(user_message)
        print(f"Extracted entities: {entities}")
        
        # Add time entity if we detected it directly 
        if meeting.time and 'TIME' not in entities:
            time_str = meeting.date_parser.format_time(meeting.time)
            entities['TIME'] = [time_str]
            print(f"Added missing TIME entity: {time_str}")
        
        # Special case for follow-up time messages that might be missed
        if not entities and any(term in lower_msg for term in ["pm", "am", "o'clock"]):
            # This might be a time-only message that was missed by the entity extraction
            parsed_time = self.state.handle_time_in_message(meeting, user_message)
            if parsed_time:
                # Force the Change_Time intent
                intent = "Change_Time"
                time_str = meeting.date_parser.format_time(meeting.time)
                entities['TIME'] = [time_str]
                print(f"Forced TIME entity for time-only message: {time_str}")
        
        # For combined scheduling requests, make sure to process all entities at once
        if combined_request:
            meeting.update_from_entities(entities)
            
            # Check if all required info is present before responding
            if meeting.is_complete():
                return self.state.handle_intent(intent, entities, user_message)
        
        # Generate response based on intent and entities
        response = self.state.handle_intent(intent, entities, user_message)
        
        # Special error handling for edge cases
        if "Sorry, I encountered an error" in response:
            # Try to handle the message as a time-only message
            if self.state.handle_time_in_message(meeting, user_message):
                time_str = meeting.date_parser.format_time(meeting.time)
                response = f"Time set to {time_str}."
                
                # Check if we have everything now
                if meeting.is_complete():
                    response += "\n\n" + self.state._generate_confirmation_message(meeting)
                else:
                    missing = meeting.get_missing_info()
                    missing_str = ", ".join(missing)
                    response += f"\nI still need the following details: {missing_str.capitalize()}."
        
        # Log the conversation
        self.state.log_conversation(user_message, response)
        
        return response

    def get_current_meeting_state(self):
        """
        Get the current meeting state as a dictionary
        """
        meeting = self.state.get_current_meeting()
        return meeting.to_dict() if meeting else {}
    
    def reset(self):
        """
        Reset the bot state completely, clearing all meeting context
        """
        # Completely reset the conversation state
        self.state = ConversationState()
        
        # Reset the current meeting context explicitly
        self.state.current_meeting_id = None
        self.state.meetings.clear()
        self.state.conversation_history.clear()
        self.state.last_intent = None
        self.state.waiting_for = None
        self.state.disambiguation_session = None
        
        return "Meeting context has been reset. I'm ready to start over. How can I help you schedule a meeting?"