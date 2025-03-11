import pandas as pd
import numpy as np
import random
import re
from collections import defaultdict

class NERDataAugmenter:
    """
    Class for augmenting NER datasets to improve entity recognition, especially for attendees
    """
    
    def __init__(self, name_list=None):
        """
        Initialize with optional list of names for generating attendee variations
        """
        # Sample names if none provided
        self.first_names = name_list or [
            "John", "Mary", "Robert", "Patricia", "Michael", "Jennifer", "William", "Linda", 
            "David", "Elizabeth", "Richard", "Barbara", "Joseph", "Susan", "Thomas", "Jessica",
            "Charles", "Sarah", "Christopher", "Karen", "Daniel", "Nancy", "Matthew", "Lisa",
            "Anthony", "Margaret", "Mark", "Betty", "Donald", "Sandra", "Steven", "Ashley",
            "Paul", "Dorothy", "Andrew", "Kimberly", "Joshua", "Emily", "Kenneth", "Donna",
            "Kevin", "Michelle", "Brian", "Carol", "George", "Amanda", "Edward", "Melissa",
            "Manish", "Diya", "Mithil", "Love", "Jack", "Jill", "Jim", "Jane", "Alex", "Emma",
            "Ankit", "Ashish", "Monika"
        ]
        
        # Common attendee patterns
        self.attendee_patterns = [
            "add {names}",
            "with {names}",
            "invite {names}",
            "include {names}",
            "schedule with {names}",
            "set up meeting with {names}",
            "create meeting with {names}",
            "book meeting with {names}",
            "arrange meeting for {names}",
            "schedule for {names}",
            "add {names} to the meeting",
            "invite {names} to join",
            "{names} should attend",
            "need {names} in this meeting",
            "get {names} on this call"
        ]
        
        # Date patterns
        self.date_patterns = [
            "tomorrow",
            "next Monday",
            "on Friday",
            "on {day}",
            "{month} {day_num}",
            "next week",
            "this {day}",
            "day after tomorrow",
            "{day_num}/{month_num}",
            "{month_num}/{day_num}/{year}",
            "{year}-{month_num}-{day_num}"
        ]
        
        # Time patterns
        self.time_patterns = [
            "at {hour} {am_pm}",
            "at {hour}:{minute} {am_pm}",
            "{hour} {am_pm}",
            "{hour}:{minute} {am_pm}",
            "at {hour}",
            "around {hour} {am_pm}",
            "{hour} o'clock",
            "at {hour}:{minute}"
        ]
        
        # Duration patterns
        self.duration_patterns = [
            "{num} hour",
            "{num} hours",
            "{num} minute",
            "{num} minutes",
            "half an hour",
            "an hour and a half",
            "{num} hour and {num2} minutes",
            "for {num} hours",
            "for {num} minutes"
        ]
        
        # Day and month data
        self.days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        self.months = ["January", "February", "March", "April", "May", "June", "July", 
                      "August", "September", "October", "November", "December"]
        self.month_abbrevs = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", 
                             "Aug", "Sep", "Oct", "Nov", "Dec"]
        
    def generate_names_variation(self, min_names=1, max_names=3, separators=None):
        """
        Generate a variation of names with different separators
        """
        # Default separators if none provided
        separators = separators or [", ", " and ", ", and ", " "]
        
        # Pick random number of names
        num_names = random.randint(min_names, max_names)
        names = random.sample(self.first_names, num_names)
        
        # For single name, just return it
        if num_names == 1:
            return names[0]
            
        # For multiple names, use different separator strategies
        separator_strategy = random.choice([
            "comma_and",  # "John, Mary, and Bob"
            "and_only",   # "John and Mary"
            "comma_only", # "John, Mary"
            "space_only"  # "John Mary Bob"
        ])
        
        if separator_strategy == "comma_and" and num_names >= 3:
            result = ", ".join(names[:-1]) + ", and " + names[-1]
        elif separator_strategy == "and_only" and num_names == 2:
            result = f"{names[0]} and {names[1]}"
        elif separator_strategy == "comma_only":
            result = ", ".join(names)
        elif separator_strategy == "space_only":
            result = " ".join(names)
        else:
            # Fallback to simple comma separation
            result = ", ".join(names)
            
        return result
    
    def generate_date_variation(self):
        """Generate a random date in various formats"""
        pattern = random.choice(self.date_patterns)
        
        # Replace placeholders
        if "{day}" in pattern:
            pattern = pattern.replace("{day}", random.choice(self.days))
        if "{month}" in pattern:
            pattern = pattern.replace("{month}", random.choice(self.months + self.month_abbrevs))
        if "{day_num}" in pattern:
            day_num = random.randint(1, 28)
            # Optionally add suffix
            if random.random() < 0.3:
                suffix = "th"
                if day_num == 1 or day_num == 21:
                    suffix = "st"
                elif day_num == 2 or day_num == 22:
                    suffix = "nd"
                elif day_num == 3 or day_num == 23:
                    suffix = "rd"
                pattern = pattern.replace("{day_num}", f"{day_num}{suffix}")
            else:
                pattern = pattern.replace("{day_num}", str(day_num))
        if "{month_num}" in pattern:
            pattern = pattern.replace("{month_num}", str(random.randint(1, 12)))
        if "{year}" in pattern:
            pattern = pattern.replace("{year}", str(random.randint(2023, 2025)))
            
        return pattern
    
    def generate_time_variation(self):
        """Generate a random time in various formats"""
        pattern = random.choice(self.time_patterns)
        
        # Replace placeholders
        if "{hour}" in pattern:
            pattern = pattern.replace("{hour}", str(random.randint(1, 12)))
        if "{minute}" in pattern:
            minutes = random.choice(["00", "15", "30", "45"])
            pattern = pattern.replace("{minute}", minutes)
        if "{am_pm}" in pattern:
            pattern = pattern.replace("{am_pm}", random.choice(["am", "AM", "pm", "PM"]))
            
        return pattern
    
    def generate_duration_variation(self):
        """Generate a random duration in various formats"""
        pattern = random.choice(self.duration_patterns)
        
        # Replace placeholders
        if "{num}" in pattern:
            pattern = pattern.replace("{num}", str(random.randint(1, 3)))
        if "{num2}" in pattern:
            pattern = pattern.replace("{num2}", str(random.choice([15, 30, 45])))
            
        return pattern
    
    def generate_meeting_request(self, include_entities=None):
        """
        Generate a complete meeting request with different combinations of entities
        
        Args:
            include_entities: List of entities to include (default: all)
        
        Returns:
            Tuple of (text, entities_dict)
        """
        include_entities = include_entities or ["attendee", "date", "time", "duration"]
        
        # Templates for meeting requests
        templates = [
            "Schedule a meeting {date} {time} {duration} {attendee}",
            "Set up a meeting {attendee} {date} {time} for {duration}",
            "Book a {duration} meeting {date} {time} {attendee}",
            "I need a meeting {date} {attendee} {time} {duration}",
            "{attendee} {date} {time} {duration}",
            "Can you schedule {attendee} {date} {time} {duration}?",
            "Create a meeting {attendee} for {duration} {date} {time}",
            "Meeting {attendee} {date} {time} {duration}",
            "New meeting {date} {time} {duration} {attendee}",
            "Please add a meeting to my calendar {date} {time} {attendee} {duration}"
        ]
        
        # Core intents are more focused
        core_intent_templates = [
            "Schedule a meeting {date} {time} {duration} {attendee}",
            "Set up a meeting {attendee} {date} {time}",
            "{attendee} {date} {time}",
            "Add {attendee} to the meeting",
            "Change the time to {time}",
            "Move the meeting to {date}",
            "Make it {duration}",
            "Cancel the meeting",
            "Is the meeting still {date} {time}?",
            "Confirm the meeting {date} {time} {attendee}",
            "Update attendees to {attendee}",
            "Can you make it {duration} instead?"
        ]
        
        template = random.choice(core_intent_templates if random.random() < 0.7 else templates)
        entities_dict = {}
        
        # Generate values for each included entity
        entity_values = {}
        
        if "attendee" in include_entities:
            attendee_pattern = random.choice(self.attendee_patterns)
            names = self.generate_names_variation()
            entity_values["attendee"] = attendee_pattern.replace("{names}", names)
            entities_dict["ATTENDEE"] = [names]
        
        if "date" in include_entities:
            date_value = self.generate_date_variation()
            entity_values["date"] = date_value
            entities_dict["DATE"] = [date_value]
        
        if "time" in include_entities:
            time_value = self.generate_time_variation()
            entity_values["time"] = time_value
            entities_dict["TIME"] = [time_value]
        
        if "duration" in include_entities:
            duration_value = self.generate_duration_variation()
            entity_values["duration"] = duration_value
            entities_dict["DURATION"] = [duration_value]
        
        # Fill in the template
        for entity, value in entity_values.items():
            template = template.replace(f"{{{entity}}}", value)
        
        # Remove any unfilled placeholders
        template = re.sub(r'\{[^}]+\}', '', template)
        # Clean up extra spaces
        template = re.sub(r'\s+', ' ', template).strip()
        
        return template, entities_dict
    
    def generate_dataset(self, num_samples=1000, output_file=None):
        """
        Generate a dataset of meeting requests with entity annotations
        
        Args:
            num_samples: Number of samples to generate
            output_file: Optional file path to save the dataset
            
        Returns:
            DataFrame with the generated dataset
        """
        data = []
        
        for i in range(num_samples):
            # For some samples, only include a subset of entities
            if random.random() < 0.3:
                # Generate single-entity examples for better learning
                entities = [random.choice(["attendee", "date", "time", "duration"])]
            else:
                # Choose a random subset of entities (at least one)
                all_entities = ["attendee", "date", "time", "duration"]
                random.shuffle(all_entities)
                entities = all_entities[:random.randint(1, 4)]
                
            text, entity_dict = self.generate_meeting_request(include_entities=entities)
            
            # Add variation in capitalization and spacing
            if random.random() < 0.3:
                # First letter capitalized
                text = text[0].lower() + text[1:]
            elif random.random() < 0.1:
                # All lowercase
                text = text.lower()
            
            # Add the sample to our dataset
            data.append({
                "text": text,
                "entities": entity_dict
            })
            
        # Create a DataFrame
        df = pd.DataFrame(data)
        
        # Optionally save to file
        if output_file:
            df.to_csv(output_file, index=False)
            print(f"Dataset saved to {output_file}")
        
        return df
    
    def convert_to_ner_format(self, df, output_file=None):
        """
        Convert a dataset with entity dictionaries to the format needed for NER training
        
        Args:
            df: DataFrame with 'text' and 'entities' columns
            output_file: Optional file path to save the NER dataset
            
        Returns:
            DataFrame in NER format (word, label, sentence_id)
        """
        ner_data = []
        sentence_id = 0
        
        for _, row in df.iterrows():
            text = row['text']
            entities = row['entities']
            
            # Create a mapping of token positions to entity labels
            token_labels = defaultdict(lambda: 'O')  # Default to Outside tag
            
            # Process each entity type
            for entity_type, entity_values in entities.items():
                for entity_value in entity_values:
                    # Skip empty entities
                    if not entity_value:
                        continue
                        
                    # Find all occurrences of this entity in the text
                    for match in re.finditer(re.escape(entity_value), text, re.IGNORECASE):
                        start, end = match.span()
                        
                        # Get the tokens in this span
                        entity_text = text[start:end]
                        entity_tokens = entity_text.split()
                        
                        # Calculate token position in the full text
                        left_text = text[:start]
                        left_tokens = left_text.split()
                        token_position = len(left_tokens)
                        
                        # Label the first token as B-ENTITY
                        token_labels[token_position] = f'B-{entity_type}'
                        
                        # Label remaining tokens as I-ENTITY
                        for i in range(1, len(entity_tokens)):
                            token_labels[token_position + i] = f'I-{entity_type}'
            
            # Split text into tokens
            tokens = text.split()
            
            # Create NER format entries
            for i, token in enumerate(tokens):
                ner_data.append({
                    'sentence_id': sentence_id,
                    'word': token,
                    'label': token_labels[i]
                })
            
            sentence_id += 1
        
        # Create a DataFrame
        ner_df = pd.DataFrame(ner_data)
        
        # Optionally save to file
        if output_file:
            ner_df.to_csv(output_file, index=False)
            print(f"NER dataset saved to {output_file}")
        
        return ner_df
    
    def augment_existing_dataset(self, existing_df, multiplier=2, output_file=None):
        """
        Augment an existing dataset with generated examples
        
        Args:
            existing_df: Existing DataFrame with NER data (word, label, sentence_id)
            multiplier: How many times to multiply the dataset size
            output_file: Optional file path to save the augmented dataset
            
        Returns:
            DataFrame with augmented dataset
        """
        # Get unique sentence_ids
        sentence_ids = existing_df['sentence_id'].unique()
        max_sentence_id = max(sentence_ids)
        
        # Generate new examples
        num_new_examples = len(sentence_ids) * (multiplier - 1)
        new_df = self.generate_dataset(num_samples=num_new_examples)
        
        # Convert to NER format
        new_ner_df = self.convert_to_ner_format(new_df)
        
        # Update sentence_ids to continue from existing data
        new_ner_df['sentence_id'] = new_ner_df['sentence_id'] + max_sentence_id + 1
        
        # Combine datasets
        combined_df = pd.concat([existing_df, new_ner_df], ignore_index=True)
        
        # Optionally save to file
        if output_file:
            combined_df.to_csv(output_file, index=False)
            print(f"Augmented dataset saved to {output_file}")
        
        return combined_df
    
    def analyze_dataset(self, df):
        """
        Analyze a dataset to show distribution of entities and examples
        
        Args:
            df: DataFrame with NER data (word, label, sentence_id)
            
        Returns:
            Dictionary with analysis results
        """
        # Count entity types
        entity_counts = defaultdict(int)
        
        # Get labels that aren't 'O'
        entity_labels = df[df['label'] != 'O']['label'].tolist()
        
        for label in entity_labels:
            # Extract entity type from B-ENTITY or I-ENTITY
            if label.startswith('B-') or label.startswith('I-'):
                entity_type = label.split('-', 1)[1]
                entity_counts[entity_type] += 1
        
        # Count sentences
        sentence_count = len(df['sentence_id'].unique())
        
        # Count words
        word_count = len(df)
        
        # Count sentences with each entity type
        sentences_with_entity = defaultdict(set)
        for _, row in df.iterrows():
            if row['label'] != 'O':
                entity_type = row['label'].split('-', 1)[1]
                sentences_with_entity[entity_type].add(row['sentence_id'])
        
        entity_sentence_counts = {entity: len(sentences) 
                                 for entity, sentences in sentences_with_entity.items()}
        
        return {
            'entity_token_counts': dict(entity_counts),
            'entity_sentence_counts': entity_sentence_counts,
            'total_sentences': sentence_count,
            'total_words': word_count
        }

# Example usage:
if __name__ == '__main__':
    augmenter = NERDataAugmenter()
    
    # Generate a new dataset
    df = augmenter.generate_dataset(num_samples=100)
    
    # Convert to NER format
    ner_df = augmenter.convert_to_ner_format(df)
    
    print(f"Generated {len(df)} new examples")
    print(ner_df.head(20))
    
    # Analyze the dataset
    analysis = augmenter.analyze_dataset(ner_df)
    print("\nDataset Analysis:")
    print(f"Total sentences: {analysis['total_sentences']}")
    print(f"Total words: {analysis['total_words']}")
    print("\nEntity token counts:")
    for entity, count in analysis['entity_token_counts'].items():
        print(f"  {entity}: {count}")
    print("\nSentences with entity:")
    for entity, count in analysis['entity_sentence_counts'].items():
        print(f"  {entity}: {count}")