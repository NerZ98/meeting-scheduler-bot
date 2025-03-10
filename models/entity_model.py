import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import BertTokenizer, BertModel, BertForTokenClassification
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from tqdm import tqdm
import re

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
        
        # Basic pattern matching for common formats in case BERT misses them
        import re
        
        # Direct pattern matching for times
        time_patterns = [
            (r'(\d{1,2})\s*(?::|\.)\s*(\d{2})\s*([ap]\.?m\.?)', lambda m: f"{m.group(1)}:{m.group(2)} {m.group(3)}"),
            (r'(\d{1,2})\s*([ap]\.?m\.?)', lambda m: f"{m.group(1)} {m.group(2)}"),
            (r'(\d{1,2})\s*o\'?clock', lambda m: f"{m.group(1)} o'clock"),
        ]
        
        time_entities = []
        for pattern, formatter in time_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                time_entities.append(formatter(match))
        
        # Direct pattern matching for durations
        duration_patterns = [
            (r'(\d+)\s*(?:hour|hr)s?', lambda m: f"{m.group(1)} hour"),
            (r'(\d+)\s*(?:minute|min)s?', lambda m: f"{m.group(1)} minute"),
            (r'half\s*an?\s*hour', lambda m: "30 minutes"),
            (r'an?\s*hour\s*and\s*(?:a\s*)?half', lambda m: "1.5 hours"),
        ]
        
        duration_entities = []
        for pattern, formatter in duration_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                duration_entities.append(formatter(match))
        
        # Attendee extraction - look for common patterns for adding people
        attendee_entities = []
        
        # Clean any previous text to avoid common pitfalls
        text_for_attendees = re.sub(r'\[.*?\]', ' ', text.lower())  # Remove [sep] and similar tags
        
        # Check for "add X and Y" pattern
        add_pattern = r'add\s+([\w\s,]+)(?:to|for|into|in)?\s*(?:the|this|our)?\s*(?:meeting|call)'
        add_match = re.search(add_pattern, text_for_attendees)
        if add_match:
            attendee_text = add_match.group(1).strip()
            if attendee_text and attendee_text not in attendee_entities:
                attendee_entities.append(attendee_text)
            
        # Check for "with X and Y" pattern
        with_pattern = r'(?:with|include|invite)\s+([\w\s,]+)(?:to|for|into|in)?\s*(?:the|this|our)?\s*(?:meeting|call)?'
        with_match = re.search(with_pattern, text_for_attendees)
        if with_match:
            attendee_text = with_match.group(1).strip()
            if attendee_text and attendee_text not in attendee_entities:
                attendee_entities.append(attendee_text)
            
        # Check for names separated by "and" or commas not part of above patterns
        if "and" in text:
            # Look for capitalized names (more likely to be proper names)
            potential_name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+and\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'
            name_matches = re.finditer(potential_name_pattern, text)
            for match in name_matches:
                # Extract full names with first and last names
                name1 = match.group(1).strip()
                name2 = match.group(2).strip()
                
                # Add each name separately for better processing
                if name1 and name1 not in attendee_entities:
                    attendee_entities.append(name1)
                if name2 and name2 not in attendee_entities:
                    attendee_entities.append(name2)
        
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
        entities = {}
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
        
        # Merge pattern-matched entities with BERT entities
        if time_entities:
            if 'TIME' not in entities:
                entities['TIME'] = []
            entities['TIME'].extend(time_entities)
        
        if duration_entities:
            if 'DURATION' not in entities:
                entities['DURATION'] = []
            entities['DURATION'].extend(duration_entities)
            
        if attendee_entities:
            if 'ATTENDEE' not in entities:
                entities['ATTENDEE'] = []
            entities['ATTENDEE'].extend(attendee_entities)
        
        # Special case for "tomorrow" and similar date expressions
        date_keywords = ["tomorrow", "today", "next week", "next month"]
        for keyword in date_keywords:
            if keyword in text.lower() and 'DATE' not in entities:
                entities['DATE'] = [keyword]
                break
        
        # Enhanced date extraction with more patterns
        entities = self._enhance_date_extraction(text, entities)
        
        # Apply additional date pattern matching for specific formats
        if 'DATE' not in entities or not entities['DATE']:
            # Match "19th of March", "19 March", "March 19th" type formats
            date_patterns = [
                # DD Month [YYYY]
                r'(\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+\d{4})?',
                # Month DD [YYYY]
                r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+\d{4})?',
                # MM/DD[/YYYY]
                r'(\d{1,2})/(\d{1,2})(?:/\d{2,4})?',
                # YYYY-MM-DD
                r'\d{4}-\d{1,2}-\d{1,2}'
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, text.lower())
                if match:
                    date_text = match.group(0)
                    if 'DATE' not in entities:
                        entities['DATE'] = []
                    entities['DATE'].append(date_text)
                    print(f"Pattern match: Found date '{date_text}'")
                    break
        
        # Print summary for debugging
        print(f"Extracted entities: {entities}")
        
        return entities
    
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