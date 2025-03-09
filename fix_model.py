"""
Script to fix model mismatch issues or regenerate training data
"""
import os
import torch
import joblib
import argparse
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from models.intent_model import IntentClassifier

def check_model_consistency():
    """Check if the model and label encoder are consistent"""
    model_path = 'models/saved/intent_model.pt'
    encoder_path = 'models/saved/intent_model_encoder.pkl'
    
    if not os.path.exists(model_path):
        print(f"Model file {model_path} not found. Please run training first.")
        return False
    
    if not os.path.exists(encoder_path):
        print(f"Encoder file {encoder_path} not found.")
        # Try to create from training data
        try:
            print("Attempting to recreate encoder from training data...")
            train_df = pd.read_csv('data/processed/intent_train.csv')
            val_df = pd.read_csv('data/processed/intent_val.csv')
            all_labels = pd.concat([train_df['intent'], val_df['intent']]).unique()
            encoder = LabelEncoder()
            encoder.fit(all_labels)
            
            # Save the encoder
            os.makedirs(os.path.dirname(encoder_path), exist_ok=True)
            joblib.dump(encoder, encoder_path)
            print(f"Created and saved label encoder with {len(all_labels)} classes")
            
            # Now check if it's consistent with the model
            checkpoint = torch.load(model_path, map_location='cpu')
            output_size = checkpoint['fc.bias'].size(0)
            
            if output_size != len(all_labels):
                print(f"Model has {output_size} output classes but encoder has {len(all_labels)} classes.")
                return False
            
            return True
        except Exception as e:
            print(f"Failed to recreate encoder: {e}")
            return False
    
    # Both files exist, check consistency
    try:
        encoder = joblib.load(encoder_path)
        checkpoint = torch.load(model_path, map_location='cpu')
        output_size = checkpoint['fc.bias'].size(0)
        
        if output_size != len(encoder.classes_):
            print(f"Model has {output_size} output classes but encoder has {len(encoder.classes_)} classes.")
            return False
        
        print(f"Model and encoder are consistent. Number of classes: {output_size}")
        return True
    except Exception as e:
        print(f"Error checking consistency: {e}")
        return False

def regenerate_training_data():
    """Regenerate the training data from scratch"""
    from data.training_data import generate_intent_data, generate_entity_data
    
    print("Regenerating training data...")
    try:
        train_df, val_df = generate_intent_data()
        train_entity_df, val_entity_df = generate_entity_data()
        print("Successfully regenerated training data")
        return True
    except Exception as e:
        print(f"Failed to regenerate training data: {e}")
        return False

def retrain_intent_model():
    """Retrain the intent model"""
    import sys
    import importlib
    
    print("Retraining intent model...")
    try:
        # Make sure we have the latest version of the module
        if 'models.intent_model' in sys.modules:
            importlib.reload(sys.modules['models.intent_model'])
        
        from train import train_intent_model
        
        class Args:
            batch_size = 16
            epochs = 5
            learning_rate = 2e-5
        
        train_intent_model(Args())
        print("Successfully retrained intent model")
        return True
    except Exception as e:
        print(f"Failed to retrain intent model: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Fix model and data issues')
    parser.add_argument('--check', action='store_true', help='Check model consistency')
    parser.add_argument('--regenerate-data', action='store_true', help='Regenerate training data')
    parser.add_argument('--retrain', action='store_true', help='Retrain the intent model')
    parser.add_argument('--all', action='store_true', help='Run all fixes')
    
    args = parser.parse_args()
    
    if args.check or args.all:
        is_consistent = check_model_consistency()
        if not is_consistent and args.all:
            print("Model is inconsistent. Proceeding with fixes...")
        elif not is_consistent:
            print("Model is inconsistent. Use --regenerate-data and --retrain to fix.")
            return
    
    if args.regenerate_data or args.all:
        success = regenerate_training_data()
        if not success:
            print("Failed to regenerate training data. Aborting.")
            return
    
    if args.retrain or args.all:
        success = retrain_intent_model()
        if not success:
            print("Failed to retrain model. Please check the errors and try again.")
            return
    
    if not (args.check or args.regenerate_data or args.retrain or args.all):
        print("No action specified. Use --check, --regenerate-data, --retrain, or --all")

if __name__ == "__main__":
    main()