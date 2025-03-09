"""
Script to retrain the intent model from scratch
"""
import os
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import BertTokenizer, BertModel
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
import joblib

# Define the model classes
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

def train_intent_model():
    """Train the intent classification model from scratch"""
    print("Training intent classification model...")
    
    # Load training data
    train_df = pd.read_csv('data/processed/intent_train.csv')
    val_df = pd.read_csv('data/processed/intent_val.csv')
    
    # Set up device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    # Initialize tokenizer
    tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
    
    # Encode labels
    all_labels = pd.concat([train_df['intent'], val_df['intent']]).unique()
    label_encoder = LabelEncoder()
    label_encoder.fit(all_labels)
    n_classes = len(label_encoder.classes_)
    print(f"Number of classes: {n_classes}")
    print(f"Classes: {label_encoder.classes_}")
    
    train_labels = label_encoder.transform(train_df['intent'])
    val_labels = label_encoder.transform(val_df['intent'])
    
    # Initialize model
    model = IntentClassifier(n_classes=n_classes)
    model.to(device)
    
    # Create data loaders
    train_dataset = IntentDataset(
        texts=train_df['text'].values,
        labels=train_labels,
        tokenizer=tokenizer
    )
    
    val_dataset = IntentDataset(
        texts=val_df['text'].values,
        labels=val_labels,
        tokenizer=tokenizer
    )
    
    batch_size = 16
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
    learning_rate = 2e-5
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    loss_fn = nn.CrossEntropyLoss()
    
    # Training loop
    best_accuracy = 0
    epochs = 5
    
    for epoch in range(epochs):
        print(f"Epoch {epoch + 1}/{epochs}")
        
        # Training phase
        model.train()
        train_losses = []
        
        for batch in train_loader:
            optimizer.zero_grad()
            
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            token_type_ids = batch['token_type_ids'].to(device)
            labels = batch['label'].to(device)
            
            outputs = model(
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
        model.eval()
        val_losses = []
        correct_predictions = 0
        total_predictions = 0
        
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch['input_ids'].to(device)
                attention_mask = batch['attention_mask'].to(device)
                token_type_ids = batch['token_type_ids'].to(device)
                labels = batch['label'].to(device)
                
                outputs = model(
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
            # Save model
            os.makedirs('models/saved', exist_ok=True)
            torch.save(model.state_dict(), 'models/saved/intent_model.pt')
            
            # Save label encoder
            joblib.dump(label_encoder, 'models/saved/intent_model_encoder.pkl')
            
            best_accuracy = accuracy
            print("Model saved!")
    
    print("Training complete!")

if __name__ == "__main__":
    train_intent_model()