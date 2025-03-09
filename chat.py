import os
import argparse
from bot.conversation import MeetingSchedulerBot

def chat_loop(bot):
    """
    Main chat loop for interacting with the bot
    """
    print("Starting Meeting Scheduler Bot. Type 'exit' to quit.")
    print("Bot: " + bot.greeting)
    
    while True:
        # Get user input
        user_input = input("You: ").strip()
        
        if user_input.lower() in ['exit', 'quit', 'bye']:
            print("Bot: Goodbye!")
            break
        
        # Process user input
        response = bot.process_message(user_input)
        
        # Display response
        print("Bot:", response)

def main():
    parser = argparse.ArgumentParser(description='Run the Meeting Scheduler Bot')
    parser.add_argument('--intent_model', type=str, default='models/saved/intent_model.pt',
                        help='Path to the intent model')
    parser.add_argument('--entity_model', type=str, default='models/saved/entity_model.pt',
                        help='Path to the entity model')
    
    args = parser.parse_args()
    
    # Check if models exist
    if not os.path.exists(args.intent_model) or not os.path.exists(args.entity_model):
        print("Models not found. Please train the models first using train.py")
        print("python train.py")
        return
    
    # Initialize bot
    bot = MeetingSchedulerBot(
        intent_model_path=args.intent_model,
        entity_model_path=args.entity_model
    )
    
    # Start chat loop
    chat_loop(bot)

if __name__ == "__main__":
    main() 
