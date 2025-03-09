import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import BertTokenizer, BertModel
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
import os
import joblib

class IntentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len=128):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_len = max_len
        
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, index):
        text = str(self.texts[index])
        label = self.labels[index]
        
        encoding = self.tokenizer.encode_plus(
            text,
            add_special_tokens=True,
            max_length=self.max_len,
            return_token_type_ids=True,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )
        
        return {
            'text': text,
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'token_type_ids': encoding['token_type_ids'].flatten(),
            'label': torch.tensor(label, dtype=torch.long)
        }

class IntentClassifier(nn.Module):
    def __init__(self, n_classes, model_name='bert-base-uncased', dropout_p=0.3):
        super(IntentClassifier, self).__init__()
        self.bert = BertModel.from_pretrained(model_name)
        self.dropout = nn.Dropout(dropout_p)
        self.fc = nn.Linear(self.bert.config.hidden_size, n_classes)
        
    def forward(self, input_ids, attention_mask, token_type_ids):
        outputs = self.bert(
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids
        )
        
        # Use the [CLS] token representation
        pooled_output = outputs.pooler_output
        output = self.dropout(pooled_output)
        return self.fc(output)

class IntentClassificationModel:
    def __init__(self, n_classes=8, model_name='bert-base-uncased', device=None):
        self.model_name = model_name
        self.n_classes = n_classes
        self.tokenizer = BertTokenizer.from_pretrained(model_name)
        self.device = device if device else torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = IntentClassifier(n_classes=n_classes, model_name=model_name)
        self.model.to(self.device)
        self.label_encoder = LabelEncoder()
        
    def train(self, train_df, val_df, batch_size=16, epochs=5, learning_rate=2e-5):
        # Encode labels
        all_labels = pd.concat([train_df['intent'], val_df['intent']]).unique()
        self.label_encoder.fit(all_labels)
        
        train_labels = self.label_encoder.transform(train_df['intent'])
        val_labels = self.label_encoder.transform(val_df['intent'])
        
        # Create data loaders
        train_dataset = IntentDataset(
            texts=train_df['text'].values,
            labels=train_labels,
            tokenizer=self.tokenizer
        )
        
        val_dataset = IntentDataset(
            texts=val_df['text'].values,
            labels=val_labels,
            tokenizer=self.tokenizer
        )
        
        train_loader = DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True
        )
        
        val_loader = DataLoader(
            val_dataset,
            batch_size=batch_size
        )
        
        # Define optimizer and loss
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=learning_rate)
        loss_fn = nn.CrossEntropyLoss()
        
        # Training loop
        best_accuracy = 0
        
        for epoch in range(epochs):
            print(f"Epoch {epoch + 1}/{epochs}")
            
            # Training phase
            self.model.train()
            train_losses = []
            
            for batch in train_loader:
                optimizer.zero_grad()
                
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                token_type_ids = batch['token_type_ids'].to(self.device)
                labels = batch['label'].to(self.device)
                
                outputs = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids
                )
                
                loss = loss_fn(outputs, labels)
                train_losses.append(loss.item())
                
                loss.backward()
                optimizer.step()
            
            train_loss = np.mean(train_losses)
            
            # Validation phase
            self.model.eval()
            val_losses = []
            correct_predictions = 0
            total_predictions = 0
            
            with torch.no_grad():
                for batch in val_loader:
                    input_ids = batch['input_ids'].to(self.device)
                    attention_mask = batch['attention_mask'].to(self.device)
                    token_type_ids = batch['token_type_ids'].to(self.device)
                    labels = batch['label'].to(self.device)
                    
                    outputs = self.model(
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        token_type_ids=token_type_ids
                    )
                    
                    loss = loss_fn(outputs, labels)
                    val_losses.append(loss.item())
                    
                    _, preds = torch.max(outputs, dim=1)
                    correct_predictions += torch.sum(preds == labels)
                    total_predictions += labels.shape[0]
            
            val_loss = np.mean(val_losses)
            accuracy = correct_predictions.double() / total_predictions
            
            print(f"Train Loss: {train_loss:.4f}")
            print(f"Val Loss: {val_loss:.4f}, Accuracy: {accuracy:.4f}")
            
            if accuracy > best_accuracy:
                torch.save(self.model.state_dict(), 'models/intent_model.pt')
                best_accuracy = accuracy
                print("Model saved!")
        
    def predict(self, text):
        self.model.eval()
        
        encoding = self.tokenizer.encode_plus(
            text,
            add_special_tokens=True,
            max_length=128,
            return_token_type_ids=True,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )
        
        input_ids = encoding['input_ids'].to(self.device)
        attention_mask = encoding['attention_mask'].to(self.device)
        token_type_ids = encoding['token_type_ids'].to(self.device)
        
        with torch.no_grad():
            outputs = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids
            )
            _, preds = torch.max(outputs, dim=1)
        
        predicted_intent = self.label_encoder.inverse_transform([preds.item()])[0]
        
        # Get probabilities
        probs = torch.nn.functional.softmax(outputs, dim=1).squeeze().cpu().numpy()
        intent_probs = {intent: prob for intent, prob in zip(self.label_encoder.classes_, probs)}
        
        return {
            'intent': predicted_intent,
            'probabilities': intent_probs
        }
    
    def load(self, model_path):
        # Load label encoder
        encoder_path = model_path.replace('.pt', '_encoder.pkl')
        try:
            if os.path.exists(encoder_path):
                self.label_encoder = joblib.load(encoder_path)
                self.n_classes = len(self.label_encoder.classes_)
                print(f"Label encoder loaded with {self.n_classes} classes")
            else:
                # If we don't have a saved encoder, try to infer from training data
                print("Label encoder file not found, trying to recreate from training data...")
                try:
                    train_df = pd.read_csv('data/processed/intent_train.csv')
                    val_df = pd.read_csv('data/processed/intent_val.csv')
                    all_labels = pd.concat([train_df['intent'], val_df['intent']]).unique()
                    self.label_encoder.fit(all_labels)
                    self.n_classes = len(all_labels)
                    print(f"Recreated label encoder with {self.n_classes} classes")
                    
                    # Save it for future use
                    os.makedirs(os.path.dirname(encoder_path), exist_ok=True)
                    joblib.dump(self.label_encoder, encoder_path)
                    print(f"Saved recreated label encoder to {encoder_path}")
                except Exception as e:
                    print(f"Error recreating label encoder: {e}")
                    raise Exception("Label encoder not found and could not be recreated.")
        except Exception as e:
            print(f"Error loading label encoder: {e}")
            raise Exception("Label encoder could not be loaded. Please train the model again.")
        
        # Initialize the model with the correct number of classes
        self.model = IntentClassifier(n_classes=self.n_classes, model_name=self.model_name)
        self.model.to(self.device)
            
        # Load the model weights
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        print(f"Model loaded from {model_path}")
        
    def save(self, model_path='models/intent_model.pt'):
        torch.save(self.model.state_dict(), model_path)
        print(f"Model saved to {model_path}")