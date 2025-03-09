import json
import os
import random
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

def load_json_data(file_path):
    """Load data from JSON file."""
    with open(file_path, 'r') as f:
        data = json.load(f)
    return data

def generate_intent_data():
    """Generate training data for intent classification."""
    # Load intents data
    intents_data = load_json_data('data/intents.json')
    
    texts = []
    labels = []
    
    for intent_category in intents_data['intents']:
        intent_name = intent_category['intent']
        for example in intent_category['examples']:
            texts.append(example)
            labels.append(intent_name)
    
    # Create a DataFrame
    df = pd.DataFrame({
        'text': texts,
        'intent': labels
    })
    
    # Split into train and validation sets
    train_df, val_df = train_test_split(df, test_size=0.2, random_state=42, stratify=df['intent'])
    
    # Save to CSV files
    os.makedirs('data/processed', exist_ok=True)
    train_df.to_csv('data/processed/intent_train.csv', index=False)
    val_df.to_csv('data/processed/intent_val.csv', index=False)
    
    print(f"Generated intent data: {len(train_df)} training samples, {len(val_df)} validation samples")
    return train_df, val_df

def generate_entity_data():
    """Generate training data for entity extraction."""
    # Load entities data
    entities_data = load_json_data('data/entities.json')
    
    # Load intents for context
    intents_data = load_json_data('data/intents.json')
    
    # We'll create synthetic sentences with labeled entities for NER
    sentences = []
    entity_labels = []
    
    # Generate synthetic data by combining intents with entities
    schedule_intents = [ex for intent in intents_data['intents'] 
                       if intent['intent'] == 'Schedule_Meeting' 
                       for ex in intent['examples']]
    
    # Extract entity examples by type
    entity_examples = {}
    for entity in entities_data['entities']:
        entity_examples[entity['entity']] = entity['examples']
    
    # Create 500 synthetic examples
    sentence_id = 0
    entity_data = []
    
    for _ in range(500):
        # Start with a schedule intent
        schedule_intent = random.choice(schedule_intents)
        words = schedule_intent.split()
        labels = ['O'] * len(words)
        
        # Add date
        if random.random() > 0.2:  # 80% chance to include date
            date = random.choice(entity_examples['DATE'])
            date_words = date.split()
            words.extend(date_words)
            labels.extend(['B-DATE'] if len(date_words) > 0 else [])
            labels.extend(['I-DATE'] * (len(date_words) - 1) if len(date_words) > 1 else [])
        
        # Add time
        if random.random() > 0.3:  # 70% chance to include time
            time = random.choice(entity_examples['TIME'])
            time_words = time.split()
            words.extend(time_words)
            labels.extend(['B-TIME'] if len(time_words) > 0 else [])
            labels.extend(['I-TIME'] * (len(time_words) - 1) if len(time_words) > 1 else [])
        
        # Add duration
        if random.random() > 0.5:  # 50% chance to include duration
            duration = random.choice(entity_examples['DURATION'])
            duration_words = duration.split()
            words.extend(duration_words)
            labels.extend(['B-DURATION'] if len(duration_words) > 0 else [])
            labels.extend(['I-DURATION'] * (len(duration_words) - 1) if len(duration_words) > 1 else [])
        
        # Add attendees
        if random.random() > 0.4:  # 60% chance to include attendees
            attendees = random.choice(entity_examples['ATTENDEE'])
            attendee_words = attendees.split()
            words.extend(attendee_words)
            labels.extend(['B-ATTENDEE'] if len(attendee_words) > 0 else [])
            labels.extend(['I-ATTENDEE'] * (len(attendee_words) - 1) if len(attendee_words) > 1 else [])
        
        # Store the sentence data
        if len(words) == len(labels):
            for word, label in zip(words, labels):
                entity_data.append({
                    'sentence_id': sentence_id,
                    'word': word,
                    'label': label
                })
            sentence_id += 1
    
    entity_df = pd.DataFrame(entity_data)
    
    # Split into train and validation sets
    sentence_ids = entity_df['sentence_id'].unique()
    train_ids, val_ids = train_test_split(sentence_ids, test_size=0.2, random_state=42)
    
    train_entity_df = entity_df[entity_df['sentence_id'].isin(train_ids)]
    val_entity_df = entity_df[entity_df['sentence_id'].isin(val_ids)]
    
    # Save to CSV files
    os.makedirs('data/processed', exist_ok=True)
    train_entity_df.to_csv('data/processed/entity_train.csv', index=False)
    val_entity_df.to_csv('data/processed/entity_val.csv', index=False)
    
    print(f"Generated entity data: {len(train_ids)} training sentences, {len(val_ids)} validation sentences")
    return train_entity_df, val_entity_df

def generate_conversation_samples():
    """Generate example conversations for testing."""
    # Create some example conversation flows
    conversations = [
        [
            {"role": "user", "text": "Hi"},
            {"role": "bot", "text": "Hello! How can I help you today?"},
            {"role": "user", "text": "Schedule a meeting for tomorrow"},
            {"role": "bot", "text": "Got it. What time should I schedule it for?"},
            {"role": "user", "text": "Schedule it at 2pm for 1 hour"},
            {"role": "bot", "text": "Sure! Who should I add to this meeting?"},
            {"role": "user", "text": "Add John and Sarah to this meeting"},
            {"role": "bot", "text": "Okay! Let me confirm:\n* Date: Tomorrow\n* Time: 2 PM\n* Duration: 1 hour\n* Attendees: John, Sarah\nIs that correct?"},
            {"role": "user", "text": "Yes, confirm the meeting"},
            {"role": "bot", "text": "✅ Meeting scheduled successfully!"}
        ],
        [
            {"role": "user", "text": "Hi"},
            {"role": "bot", "text": "Hello! How can I help you today?"},
            {"role": "user", "text": "Schedule a meeting for tomorrow"},
            {"role": "bot", "text": "What time should I schedule it for?"},
            {"role": "user", "text": "Schedule it at 2pm for 1 hour"},
            {"role": "bot", "text": "Who should I add to this meeting?"},
            {"role": "user", "text": "Add John and Sarah"},
            {"role": "bot", "text": "Got it. Confirm the meeting?"},
            {"role": "user", "text": "Actually, change the time to 3pm"},
            {"role": "bot", "text": "No problem. Time changed to 3 PM.\n* Date: Tomorrow\n* Time: 3 PM\n* Duration: 1 hour\n* Attendees: John, Sarah\nIs that correct?"},
            {"role": "user", "text": "Yes, confirm"},
            {"role": "bot", "text": "✅ Meeting scheduled successfully!"}
        ],
        [
            {"role": "user", "text": "Add Alex to the meeting"},
            {"role": "bot", "text": "✅ Alex has been added.\n* Attendees: John, Sarah, Alex\nIs there anything else you'd like to change?"},
            {"role": "user", "text": "Actually, make it 30 minutes"},
            {"role": "bot", "text": "✅ Duration changed to 30 minutes.\n* Time: 3 PM\n* Duration: 30 minutes\nIs that correct?"},
            {"role": "user", "text": "Yes"},
            {"role": "bot", "text": "✅ Meeting scheduled successfully!"}
        ]
    ]
    
    # Save conversation samples
    with open('data/conversation_samples.json', 'w') as f:
        json.dump(conversations, f, indent=2)
    
    print(f"Generated {len(conversations)} conversation samples.")

if __name__ == "__main__":
    # Generate all training data
    generate_intent_data()
    generate_entity_data()
    generate_conversation_samples()
    print("All training data generated successfully!")