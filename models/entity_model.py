import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import BertTokenizer, BertModel, BertForTokenClassification
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from tqdm import tqdm
import re
import datetime

class NERDataset(Dataset):
    def __init__(self, df, tokenizer, max_len=128, label_encoder=None):
        self.df = df
        self.tokenizer = tokenizer
        self.max_len = max_len
        self.label_encoder = label_encoder
        
        # Group by sentence_id to get sentences and their tags
        self.sentences = df.groupby('sentence_id')['word'].apply(list).reset_index()
        self.tags = df.groupby('sentence_id')['label'].apply(list).reset_index()
        
        # Merge to ensure alignment
        self.data = pd.merge(self.sentences, self.tags, on='sentence_id')
        
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        words = self.data.loc[idx, 'word']
        tags = self.data.loc[idx, 'label']
        
        # Convert words to sentence
        sentence = ' '.join(words)
        
        # Tokenize the sentence
        encoding = self.tokenizer.encode_plus(
            sentence,
            add_special_tokens=True,
            max_length=self.max_len,
            return_token_type_ids=True,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )
        
        # Create label mapping
        if self.label_encoder:
            tag_ids = [self.label_encoder.transform([tag])[0] for tag in tags]
        else:
            tag_ids = tags
            
        # Create a simple alignment by repeating the label for each token
        # This is a simplified approach since we don't have word_ids
        input_ids = encoding['input_ids'].flatten()
        aligned_labels = []
        token_texts = self.tokenizer.convert_ids_to_tokens(input_ids)
        
        # For CLS token
        aligned_labels.append(-100)
        
        # Align the rest of the tokens (simplified approach)
        word_idx = 0
        for token in token_texts[1:-1]:  # Skip [CLS] and [SEP]
            if word_idx >= len(tag_ids):
                aligned_labels.append(-100)
                continue
                
            if token.startswith('##'):
                # This is a subword, use the same label as the previous token
                aligned_labels.append(tag_ids[word_idx-1] if word_idx > 0 else -100)
            else:
                # This is a new word, use the corresponding label
                if word_idx < len(tag_ids):
                    aligned_labels.append(tag_ids[word_idx])
                    word_idx += 1
                else:
                    aligned_labels.append(-100)
        
        # For SEP token
        aligned_labels.append(-100)
        
        # Ensure length matches
        while len(aligned_labels) < len(input_ids):
            aligned_labels.append(-100)
        
        # Trim if necessary
        aligned_labels = aligned_labels[:len(input_ids)]
        
        return {
            'sentence': sentence,
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'token_type_ids': encoding['token_type_ids'].flatten(),
            'labels': torch.tensor(aligned_labels, dtype=torch.long)
        }

class EntityRecognitionModel:
    def __init__(self, model_name='bert-base-uncased', device=None):
        self.model_name = model_name
        self.tokenizer = BertTokenizer.from_pretrained(model_name, use_fast=True)  # Use the fast tokenizer
        self.device = device if device else torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.label_encoder = LabelEncoder()
        self.n_classes = None
        self.model = None
        
    def prepare_data(self, train_df, val_df=None):
        # Get unique labels and fit encoder
        all_labels = train_df['label'].unique()
        if val_df is not None:
            all_labels = np.concatenate([all_labels, val_df['label'].unique()])
        
        self.label_encoder.fit(all_labels)
        self.n_classes = len(self.label_encoder.classes_)
        print(f"Number of entity classes: {self.n_classes}")
        print(f"Classes: {self.label_encoder.classes_}")
        
        # Initialize the model with correct number of labels
        self.model = BertForTokenClassification.from_pretrained(
            self.model_name, 
            num_labels=self.n_classes
        )
        self.model.to(self.device)
        
        return self.label_encoder
    
    def train(self, train_df, val_df=None, batch_size=16, epochs=5, learning_rate=3e-5):
        # Prepare data and initialize model
        self.prepare_data(train_df, val_df)
        
        # Create datasets
        train_dataset = NERDataset(
            df=train_df,
            tokenizer=self.tokenizer,
            label_encoder=self.label_encoder
        )
        
        train_loader = DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True
        )
        
        if val_df is not None:
            val_dataset = NERDataset(
                df=val_df,
                tokenizer=self.tokenizer,
                label_encoder=self.label_encoder
            )
            
            val_loader = DataLoader(
                val_dataset,
                batch_size=batch_size
            )
        else:
            val_loader = None
        
        # Define optimizer and loss
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=learning_rate)
        
        # Training loop
        best_f1 = 0
        
        for epoch in range(epochs):
            print(f"Epoch {epoch + 1}/{epochs}")
            
            # Training phase
            self.model.train()
            train_losses = []
            
            for batch in tqdm(train_loader, desc="Training"):
                optimizer.zero_grad()
                
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                token_type_ids = batch['token_type_ids'].to(self.device)
                labels = batch['labels'].to(self.device)
                
                outputs = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids,
                    labels=labels
                )
                
                loss = outputs.loss
                train_losses.append(loss.item())
                
                loss.backward()
                optimizer.step()
            
            train_loss = np.mean(train_losses)
            print(f"Train Loss: {train_loss:.4f}")
            
            # Validation phase
            if val_loader:
                metrics = self.evaluate(val_loader)
                print(f"Val Loss: {metrics['loss']:.4f}, F1: {metrics['f1']:.4f}")
                
                if metrics['f1'] > best_f1:
                    torch.save(self.model.state_dict(), 'models/entity_model.pt')
                    best_f1 = metrics['f1']
                    print("Model saved!")
        
    def evaluate(self, data_loader):
        self.model.eval()
        val_losses = []
        predictions = []
        true_labels = []
        
        with torch.no_grad():
            for batch in tqdm(data_loader, desc="Evaluating"):
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                token_type_ids = batch['token_type_ids'].to(self.device)
                labels = batch['labels'].to(self.device)
                
                outputs = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids,
                    labels=labels
                )
                
                loss = outputs.loss
                val_losses.append(loss.item())
                
                # Get predictions
                logits = outputs.logits
                preds = torch.argmax(logits, dim=2)
                
                # Remove ignored index (100) before calculating metrics
                active_accuracy = (labels != -100)
                
                # Store predictions and true labels for metric calculation
                predictions.extend(preds[active_accuracy].cpu().numpy())
                true_labels.extend(labels[active_accuracy].cpu().numpy())
        
        # Calculate F1 score
        f1 = self._compute_f1(true_labels, predictions)
        
        return {
            'loss': np.mean(val_losses),
            'f1': f1
        }
    
    def _compute_f1(self, y_true, y_pred):
        # Simplified F1 score calculation
        correct = sum(1 for y_t, y_p in zip(y_true, y_pred) if y_t == y_p)
        precision = correct / len(y_pred) if len(y_pred) > 0 else 0
        recall = correct / len(y_true) if len(y_true) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        return f1
    
    def _enhance_date_extraction(self, text, entities):
        """
        Enhance date extraction with rule-based patterns
        """
        # Only try to enhance if we don't already have DATE entities
        if 'DATE' not in entities or not entities['DATE']:
            # Common date patterns to look for
            date_patterns = [
                # Match "19th of March", "19 March", etc.
                r'(\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)',
                # Match "March 19th", "March 19", etc.
                r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?',
                # Match MM/DD or MM/DD/YYYY
                r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?',
                # Match YYYY-MM-DD
                r'(\d{4})-(\d{1,2})-(\d{1,2})'
            ]
            
            text_lower = text.lower()
            
            # Try each pattern
            for pattern in date_patterns:
                matches = re.findall(pattern, text_lower)
                if matches:
                    # Extract the full matched text
                    match_obj = re.search(pattern, text_lower)
                    if match_obj:
                        date_text = match_obj.group(0)
                        
                        # Try to parse this with a date parser to validate it
                        # For this simple enhancement, we'll just assume it's valid
                        if 'DATE' not in entities:
                            entities['DATE'] = []
                        
                        # Add this date text to our entities
                        entities['DATE'].append(date_text)
                        print(f"Enhanced date extraction: Found '{date_text}'")
                        break  # Stop after finding one date
        
        return entities
    
    def predict(self, text):
        if self.model is None:
            raise ValueError("Model not initialized. Please train or load a model first.")
            
        self.model.eval()
        
        # Dictionary to store all extracted entities
        entities = {}
        
        # ====== DIRECT PATTERN MATCHING - Do this first to ensure key patterns aren't missed ======
        
        # Direct pattern matching for times
        time_patterns = [
            # More explicit patterns with better matching for edge cases
            (r'at\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)', lambda m: f"{m.group(1)}{':' + m.group(2) if m.group(2) else ''} {m.group(3)}"),
            (r'(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)', lambda m: f"{m.group(1)}{':' + m.group(2) if m.group(2) else ''} {m.group(3)}"),
            (r'at\s+(\d{1,2})\s*([ap]\.?m\.?)', lambda m: f"{m.group(1)} {m.group(2)}"),
            (r'at\s+(\d{1,2})(?::(\d{2}))?', lambda m: f"{m.group(1)}{':' + m.group(2) if m.group(2) else ''}"),
            (r'(\d{1,2})\s*o\'?clock', lambda m: f"{m.group(1)} o'clock"),
        ]
        
        time_entities = []
        for pattern, formatter in time_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                time_entities.append(formatter(match))
        
        # Direct pattern matching for durations
        duration_patterns = [
            (r'for\s+(\d+)\s*(?:hour|hr)s?', lambda m: f"{m.group(1)} hour"),
            (r'for\s+(\d+)\s*(?:minute|min)s?', lambda m: f"{m.group(1)} minute"),
            (r'(\d+)\s*(?:hour|hr)s?', lambda m: f"{m.group(1)} hour"),
            (r'(\d+)\s*(?:minute|min)s?', lambda m: f"{m.group(1)} minute"),
            (r'half\s*an?\s*hour', lambda m: "30 minute"),
            (r'an?\s*hour\s*and\s*(?:a\s*)?half', lambda m: "90 minute"),
        ]
        
        duration_entities = []
        for pattern, formatter in duration_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                duration_entities.append(formatter(match))
        
        # Attendee extraction - improved approach
        attendee_entities = []
        
        # Process patterns like "Add X, Y and Z" more comprehensively
        add_pattern = r'[Aa]dd\s+(.*?)(?:$|to the meeting)'
        add_matches = re.search(add_pattern, text)
        if add_matches:
            names_text = add_matches.group(1).strip()
            
            # Split by commas, "and", or just spaces
            if ',' in names_text or ' and ' in names_text:
                # Split by explicit separators first
                name_parts = re.split(r',|\s+and\s+', names_text)
                for part in name_parts:
                    part = part.strip()
                    if part and len(part) > 1:
                        attendee_entities.append(part.capitalize())
            else:
                # Space-separated names
                words = names_text.split()
                for word in words:
                    word = word.strip()
                    if word and len(word) > 1 and word.lower() not in ['to', 'the', 'a', 'for']:
                        attendee_entities.append(word.capitalize())

        # Also check for the "with X, Y, Z" pattern
        with_pattern = r'with\s+(.*?)(?:$|to the meeting)'
        with_matches = re.search(with_pattern, text)
        if with_matches:
            names_text = with_matches.group(1).strip()
            
            # Split by commas, "and", or just spaces
            if ',' in names_text or ' and ' in names_text:
                # Split by explicit separators first
                name_parts = re.split(r',|\s+and\s+', names_text)
                for part in name_parts:
                    part = part.strip()
                    if part and len(part) > 1:
                        attendee_entities.append(part.capitalize())
            else:
                # Space-separated names
                words = names_text.split()
                for word in words:
                    word = word.strip()
                    if word and len(word) > 1 and word.lower() not in ['to', 'the', 'a', 'for']:
                        attendee_entities.append(word.capitalize())
        
        # Check for date expressions like "tomorrow", "today", "next week"
        date_keywords = {
            "tomorrow": "tomorrow",
            "today": "today",
            "next week": "next week",
            "next monday": "next monday",
            "next tuesday": "next tuesday",
            "next wednesday": "next wednesday",
            "next thursday": "next thursday",
            "next friday": "next friday",
            "next saturday": "next saturday",
            "next sunday": "next sunday"
        }
        
        date_entities = []
        for keyword, value in date_keywords.items():
            if keyword in text.lower():
                date_entities.append(value)
        
        # Direct pattern matching for specific date formats
        date_patterns = [
            # Match "14th March", "14 Mar", "March 14th" style dates
            (r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)', lambda m: m.group(0)),
            (r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?', lambda m: m.group(0)),
            # Match MM/DD or MM/DD/YYYY
            (r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?', lambda m: m.group(0)),
            # Match YYYY-MM-DD
            (r'\d{4}-\d{1,2}-\d{1,2}', lambda m: m.group(0))
        ]
        
        for pattern, formatter in date_patterns:
            matches = re.finditer(pattern, text.lower())
            for match in matches:
                date_text = formatter(match)
                if date_text and date_text not in date_entities:
                    date_entities.append(date_text)
        
        # Add pattern-matched entities to our master dictionary
        if time_entities:
            entities['TIME'] = time_entities
        
        if duration_entities:
            entities['DURATION'] = duration_entities
            
        if attendee_entities:
            entities['ATTENDEE'] = attendee_entities
        
        if date_entities:
            entities['DATE'] = date_entities
        
        # ====== BERT MODEL PREDICTION ======
        
        # Tokenize for BERT
        encoding = self.tokenizer.encode_plus(
            text,
            add_special_tokens=True,
            return_token_type_ids=True,
            padding='max_length',
            max_length=128,
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )
        
        # Get predictions from BERT
        with torch.no_grad():
            input_ids = encoding['input_ids'].to(self.device)
            attention_mask = encoding['attention_mask'].to(self.device)
            token_type_ids = encoding['token_type_ids'].to(self.device)
            
            outputs = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids
            )
            
            logits = outputs.logits
            predictions = torch.argmax(logits, dim=2).squeeze().cpu().numpy()
        
        # Convert predictions to labels
        predicted_labels = []
        for i, pred in enumerate(predictions):
            if i == 0 or i == len(predictions) - 1:
                # Skip CLS and SEP tokens
                continue
                
            if attention_mask[0][i] == 1:  # Only consider non-padding tokens
                if pred >= 0 and pred < len(self.label_encoder.classes_):
                    predicted_labels.append(self.label_encoder.inverse_transform([pred])[0])
                else:
                    predicted_labels.append('O')
        
        # Convert token-level predictions to word-level
        tokens = self.tokenizer.convert_ids_to_tokens(input_ids[0])
        tokens = tokens[1:-1]  # Remove [CLS] and [SEP]
        tokens = [token for token, mask in zip(tokens, attention_mask[0][1:-1]) if mask == 1]
        
        # Combine tokens and labels
        token_labels = list(zip(tokens, predicted_labels[:len(tokens)]))
        
        # Extract entities from BERT predictions
        current_entity = None
        current_type = None
        
        for token, label in token_labels:
            # Skip subword tokens
            if token.startswith('##'):
                if current_entity:
                    current_entity += token[2:]  # Add without ##
                continue
                
            if label.startswith('B-'):
                # Beginning of a new entity
                if current_entity:
                    entity_type = current_type[2:]  # Remove 'B-' or 'I-'
                    if entity_type not in entities:
                        entities[entity_type] = []
                    entities[entity_type].append(current_entity)
                    
                current_entity = token
                current_type = label
            elif label.startswith('I-') and current_entity and label[2:] == current_type[2:]:
                # Continuation of the current entity
                current_entity += ' ' + token
            elif label == 'O':
                # Outside any entity
                if current_entity:
                    entity_type = current_type[2:]
                    if entity_type not in entities:
                        entities[entity_type] = []
                    entities[entity_type].append(current_entity)
                    current_entity = None
                    current_type = None
        
        # Add the last entity if there is one
        if current_entity:
            entity_type = current_type[2:]
            if entity_type not in entities:
                entities[entity_type] = []
            entities[entity_type].append(current_entity)
        
        # ====== ENHANCED DATE EXTRACTION - FINAL PASS ======
        # Do this last to ensure we have dates even if previous methods miss them
        entities = self._enhance_date_extraction(text, entities)
        
        # Try to extract compound time expressions
        if 'TIME' not in entities and 'at' in text.lower():
            time_in_compound = self.extract_time_from_compound(text)
            if time_in_compound:
                formatted_time = time_in_compound.strftime("%-I %p").lower() if time_in_compound.minute == 0 else time_in_compound.strftime("%-I:%M %p").lower()
                if 'TIME' not in entities:
                    entities['TIME'] = []
                entities['TIME'].append(formatted_time)
                print(f"Extracted compound time: {formatted_time}")
        
        # Print summary for debugging
        print(f"Initial extracted entities: {entities}")
        
        # Apply the improved attendee extraction as the final step
        entities = self._improve_attendee_extraction(text, entities)
        
        # Final print and return
        print(f"Final extracted entities after improvements: {entities}")
        return entities

    def extract_time_from_compound(self, text):
        """Extract time from compound statements that might include other entities"""
        time_in_compound = None
        
        print(f"DEBUG: Extracting time from: '{text}'")
        
        # Look for "at X" patterns in combined phrases with more specific patterns first
        at_time_patterns = [
            # These patterns look for specific "at TIME" references
            r'at\s+(\d{1,2}):(\d{2})\s*([ap]\.?m\.?)',  # "at 1:30pm"
            r'at\s+(\d{1,2}):(\d{2})',                  # "at 1:30"
            r'at\s+(\d{1,2})\s*([ap]\.?m\.?)',          # "at 1pm"
            r'at\s+(\d{1,2})',                          # "at 1"
        ]
        
        for pattern in at_time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                hour = int(match.group(1))
                
                # Get minutes if available, otherwise default to 0
                minute = 0
                if len(match.groups()) > 1 and match.group(2) and match.group(2).isdigit():
                    minute = int(match.group(2))
                
                # Get AM/PM if available
                ampm = None
                if len(match.groups()) > 2 and match.group(3):
                    ampm = match.group(3)
                elif len(match.groups()) > 1 and match.group(2) and not match.group(2).isdigit():
                    ampm = match.group(2)
                
                # If no explicit AM/PM, check nearby in text
                if not ampm:
                    # Look for AM/PM markers nearby (within 10 characters)
                    context = text[max(0, match.start()-10):min(len(text), match.end()+10)]
                    am_match = re.search(r'\b[aA]\.?[mM]\.?\b', context)
                    pm_match = re.search(r'\b[pP]\.?[mM]\.?\b', context)
                    
                    if pm_match and not am_match:
                        ampm = 'pm'
                        print(f"DEBUG: Found nearby PM marker in: '{context}'")
                    elif am_match and not pm_match:
                        ampm = 'am'
                        print(f"DEBUG: Found nearby AM marker in: '{context}'")
                    
                    # For business hours logic
                    if not ampm:
                        # For daytime meetings, assume 1-6 is PM (business hours)
                        if 1 <= hour <= 6:
                            ampm = 'pm'
                            print(f"DEBUG: Using business hours logic, assuming {hour} is PM")
                        elif 7 <= hour <= 11:
                            ampm = 'am'
                            print(f"DEBUG: Using business hours logic, assuming {hour} is AM")
                
                # Adjust hour based on AM/PM if specified
                if ampm and ('p' in ampm.lower()) and hour < 12:
                    hour += 12
                    print(f"DEBUG: Adjusting hour to {hour} for PM")
                elif ampm and ('a' in ampm.lower()) and hour == 12:
                    hour = 0
                    print(f"DEBUG: Adjusting 12 AM to {hour}")
                
                print(f"DEBUG: Extracted time {hour}:{minute:02d} from '{match.group(0)}'")
                return datetime.time(hour, minute)
        
        # Also check for standalone time expressions like "1:30pm"
        standalone_patterns = [
            r'(\d{1,2}):(\d{2})\s*([ap]\.?m\.?)',  # "1:30pm" 
            r'(\d{1,2})\.(\d{2})\s*([ap]\.?m\.?)',  # "1.30pm"
            r'(\d{1,2})\s*([ap]\.?m\.?)'            # "1pm"
        ]
        
        for pattern in standalone_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                hour = int(match.group(1))
                
                # Handle minutes
                minute = 0
                if len(match.groups()) > 1 and match.group(2) and match.group(2).isdigit():
                    minute = int(match.group(2))
                
                # Handle AM/PM
                ampm = None
                if len(match.groups()) > 2 and match.group(3):
                    ampm = match.group(3)
                elif len(match.groups()) > 1 and match.group(2) and not match.group(2).isdigit():
                    ampm = match.group(2)
                
                # Adjust hour based on AM/PM
                if ampm and ('p' in ampm.lower()) and hour < 12:
                    hour += 12
                    print(f"DEBUG: Adjusting hour to {hour} for PM")
                elif ampm and ('a' in ampm.lower()) and hour == 12:
                    hour = 0
                    print(f"DEBUG: Adjusting 12 AM to {hour}")
                
                print(f"DEBUG: Extracted time {hour}:{minute:02d} from '{match.group(0)}'")
                return datetime.time(hour, minute)
        
        print(f"DEBUG: Could not extract time from: '{text}'")
        return time_in_compound

    def load(self, model_path):
        # Load label encoder
        import joblib
        encoder_path = model_path.replace('.pt', '_encoder.pkl')
        try:
            self.label_encoder = joblib.load(encoder_path)
            self.n_classes = len(self.label_encoder.classes_)
            print(f"Label encoder loaded with {self.n_classes} classes")
        except:
            print("Label encoder not found. Please provide classes manually.")
            
        # Initialize and load model
        self.model = BertForTokenClassification.from_pretrained(
            self.model_name, 
            num_labels=self.n_classes
        )
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.to(self.device)
        print(f"Model loaded from {model_path}")
        
    def save(self, model_path='models/entity_model.pt'):
        torch.save(self.model.state_dict(), model_path)
        
        # Save label encoder
        import joblib
        encoder_path = model_path.replace('.pt', '_encoder.pkl')
        joblib.dump(self.label_encoder, encoder_path)
        
        print(f"Model saved to {model_path}")
        print(f"Label encoder saved to {encoder_path}")
    
    def _improve_attendee_extraction(self, text, entities):
        """
        Enhanced attendee extraction to better handle various ways users might request adding attendees
        """
        if 'ATTENDEE' not in entities:
            entities['ATTENDEE'] = []
        
        # Store original attendees for debugging
        original_attendees = entities['ATTENDEE'].copy()
        print(f"DEBUG: Original attendee extraction: {original_attendees}")
        
        # CRITICAL FIX: First filter out obviously wrong attendee names
        filtered_attendees = []
        invalid_attendees = []
        
        # Action words that should never be part of an attendee name
        action_words = [
            'add', 'invite', 'include', 'with', 'and', 'get', 'bring', 'ask', 
            'call', 'schedule', 'book', 'arrange', 'set', 'up', 'for', 'to'
        ]
        
        # Time-related patterns that should never be attendees
        time_patterns = [
            r'\d+\s*:\s*\d+',  # Matches patterns like "1:30"
            r'\d+\s*(?:am|pm|a\.m\.|p\.m\.)',  # Matches patterns like "1pm", "2 a.m."
            r'(?:min|minute|hour|sec|second)s?',  # Time units
            r'duration',
            r'tomorrow',
            r'today',
            r'monday|tuesday|wednesday|thursday|friday|saturday|sunday'
        ]
        
        # Build a combined pattern
        combined_time_pattern = '|'.join(time_patterns)
        
        # CRITICAL FIX: First identify full names (with spaces)
        full_names = []
        partial_names = []
        
        for attendee in entities['ATTENDEE']:
            # Skip empty or very short names
            if not attendee or len(attendee) <= 2:
                invalid_attendees.append(attendee)
                continue
                
            # Clean up the name - strip and remove special tokens
            clean_name = re.sub(r'\[.*?\]', '', attendee).strip()
            
            # Skip if it looks like a time expression
            if re.search(combined_time_pattern, clean_name.lower()):
                invalid_attendees.append(attendee)
                continue
                
            # Skip names that are just numbers or contain obvious time components
            if clean_name.isdigit() or ':' in clean_name or re.search(r'\d+\s*(?:am|pm)', clean_name.lower()):
                invalid_attendees.append(attendee)
                continue
                
            # CRITICAL FIX: Check for action words at the beginning
            lower_name = clean_name.lower()
            words = lower_name.split()
            
            # Skip if the entire name starts with an action word
            if words and words[0] in action_words:
                invalid_attendees.append(attendee)
                continue
                
            # CRITICAL: Skip phrases that begin with an action word followed by potential names
            if len(words) >= 3 and words[0] in action_words:
                # This might be something like "add john smith" or "invite mary jones"
                invalid_attendees.append(attendee)
                
                # Try to extract just the name part
                potential_name = ' '.join(words[1:])
                if len(potential_name) > 2 and not re.search(combined_time_pattern, potential_name):
                    # Capitalize properly
                    extracted_name = ' '.join(word.capitalize() for word in potential_name.split())
                    filtered_attendees.append(extracted_name)
                continue
                
            # Skip common non-name words
            non_name_words = ['min', 'at', 'for', 'the', 'a', 'an', 'this', 'that', 'make', 'sure', 
                            'also', 'please', 'with', 'call', 'meeting', 'schedule', 'duration',
                            'tomorrow', 'today', 'monday', 'tuesday', 'wednesday', 'thursday', 
                            'friday', 'saturday', 'sunday']
            
            if clean_name.lower() in non_name_words or clean_name.lower() in action_words:
                invalid_attendees.append(attendee)
                continue
            
            # Properly capitalize the name
            if ' ' in clean_name:
                capitalized_name = ' '.join(word.capitalize() for word in clean_name.split())
                full_names.append(capitalized_name)
            else:
                capitalized_name = clean_name.capitalize()
                partial_names.append(capitalized_name)
        
        # CRITICAL FIX: Process full names first, then partial names that aren't part of full names
        for full_name in full_names:
            filtered_attendees.append(full_name)
            
            # Get the parts of this full name to filter out later
            name_parts = full_name.split()
            for part in name_parts:
                # Check if this part is in our partial names list
                for i, partial in enumerate(partial_names):
                    if partial.lower() == part.lower():
                        # This partial name is part of a full name, mark it to skip
                        partial_names[i] = None
        
        # Add any remaining partial names
        for partial_name in partial_names:
            if partial_name is not None:
                filtered_attendees.append(partial_name)
        
        if invalid_attendees:
            print(f"DEBUG: Filtered out invalid attendees: {invalid_attendees}")
        
        # Replace the original list with our filtered list
        entities['ATTENDEE'] = filtered_attendees
        
        print(f"Final attendee extraction: {entities['ATTENDEE']}")
        return entities