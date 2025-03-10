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
        
        # Rule-based overrides for common scheduling phrases
        lower_msg = user_message.lower()
        if ("schedule" in lower_msg or "set up" in lower_msg or "book" in lower_msg or "arrange" in lower_msg) and (
            "meeting" in lower_msg or "call" in lower_msg or "appointment" in lower_msg
        ):
            print("Rule-based override: Forcing Schedule_Meeting intent")
            intent = "Schedule_Meeting"
        else:
            # Classify intent
            intent_result = self.intent_model.predict(user_message)
            intent = intent_result['intent']
            print(f"Detected intent: {intent}")
            print(f"Intent probabilities: {intent_result['probabilities']}")
        
        # Extract entities
        entities = self.entity_model.predict(user_message)
        print(f"Extracted entities: {entities}")
        
        # Generate response based on intent and entities
        response = self.state.handle_intent(intent, entities, user_message)
        
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
        
        return "Meeting context has been reset. I'm ready to start over. How can I help you schedule a meeting?"