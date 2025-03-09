import os
import argparse
import pandas as pd
import numpy as np
import torch
from sklearn.metrics import classification_report, confusion_matrix
from torch.utils.data import DataLoader

from models.intent_model import IntentClassificationModel, IntentDataset
from models.entity_model import EntityRecognitionModel, NERDataset

def evaluate_intent_model(model_path):
    """Evaluate the intent classification model"""
    print("Evaluating intent classification model...")
    
    # Load validation data
    val_df = pd.read_csv('data/processed/intent_val.csv')
    
    # Load model
    model = IntentClassificationModel()
    model.load(model_path)
    
    # Evaluate on each example
    y_true = []
    y_pred = []
    
    for _, row in val_df.iterrows():
        text = row['text']
        true_intent = row['intent']
        
        # Predict
        result = model.predict(text)
        pred_intent = result['intent']
        
        y_true.append(true_intent)
        y_pred.append(pred_intent)
    
    # Print evaluation metrics
    print("\nIntent Classification Report:")
    print(classification_report(y_true, y_pred))
    
    # Print confusion matrix
    print("\nConfusion Matrix:")
    cm = confusion_matrix(y_true, y_pred, labels=sorted(set(y_true)))
    print(cm)
    
    # Print accuracy
    accuracy = np.mean(np.array(y_true) == np.array(y_pred))
    print(f"\nAccuracy: {accuracy:.4f}")

def evaluate_entity_model(model_path):
    """Evaluate the entity recognition model"""
    print("Evaluating entity recognition model...")
    
    # Load validation data
    val_df = pd.read_csv('data/processed/entity_val.csv')
    
    # Load model
    model = EntityRecognitionModel()
    model.load(model_path)
    
    # Group by sentence_id to get complete sentences
    sentences = val_df.groupby('sentence_id')['word'].apply(lambda x: ' '.join(x)).reset_index()
    
    # Set up metrics
    found_entities = 0
    correct_entities = 0
    total_entities = 0
    
    # Process each sentence
    for _, row in sentences.iterrows():
        sentence_id = row['sentence_id']
        text = row['word']
        
        # Get true entities for this sentence
        true_entities = {}
        
        # Extract entity labels for this sentence
        sentence_df = val_df[val_df['sentence_id'] == sentence_id]
        
        # Get sequential entity spans
        current_entity = None
        current_type = None
        
        for _, token_row in sentence_df.iterrows():
            label = token_row['label']
            word = token_row['word']
            
            if label.startswith('B-'):
                # Beginning of a new entity
                if current_entity:
                    entity_type = current_type[2:]  # Remove 'B-' or 'I-'
                    if entity_type not in true_entities:
                        true_entities[entity_type] = []
                    true_entities[entity_type].append(current_entity)
                    
                current_entity = word
                current_type = label
            elif label.startswith('I-') and current_entity and label[2:] == current_type[2:]:
                # Continuation of the current entity
                current_entity += ' ' + word
            elif label == 'O':
                # Outside any entity
                if current_entity:
                    entity_type = current_type[2:]
                    if entity_type not in true_entities:
                        true_entities[entity_type] = []
                    true_entities[entity_type].append(current_entity)
                    current_entity = None
                    current_type = None
        
        # Add the last entity if there is one
        if current_entity:
            entity_type = current_type[2:]
            if entity_type not in true_entities:
                true_entities[entity_type] = []
            true_entities[entity_type].append(current_entity)
        
        # Predict entities
        pred_entities = model.predict(text)
        
        # Update metrics
        for entity_type, entities in true_entities.items():
            total_entities += len(entities)
        
        for entity_type, entities in pred_entities.items():
            found_entities += len(entities)
            
            if entity_type in true_entities:
                # Count exact matches
                for entity in entities:
                    if entity in true_entities[entity_type]:
                        correct_entities += 1
    
    # Calculate metrics
    precision = correct_entities / found_entities if found_entities > 0 else 0
    recall = correct_entities / total_entities if total_entities > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"\nEntity Recognition Metrics:")
    print(f"Precision: {precision:.4f}")
    print(f"Recall: {recall:.4f}")
    print(f"F1 Score: {f1:.4f}")
    print(f"Found {found_entities} entities, {correct_entities} correct out of {total_entities} total")

def main():
    parser = argparse.ArgumentParser(description='Evaluate the meeting scheduler bot models')
    parser.add_argument('--model', type=str, choices=['intent', 'entity', 'all'], default='all',
                        help='Which model to evaluate (intent, entity, or all)')
    parser.add_argument('--intent_model', type=str, default='models/saved/intent_model.pt',
                        help='Path to the intent model')
    parser.add_argument('--entity_model', type=str, default='models/saved/entity_model.pt',
                        help='Path to the entity model')
    
    args = parser.parse_args()
    
    if args.model in ['intent', 'all']:
        evaluate_intent_model(args.intent_model)
        
    if args.model in ['entity', 'all']:
        evaluate_entity_model(args.entity_model)

if __name__ == "__main__":
    main() 
