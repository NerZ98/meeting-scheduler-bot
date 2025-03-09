import os
import argparse
import pandas as pd
from tqdm import tqdm

from models.intent_model import IntentClassificationModel
from models.entity_model import EntityRecognitionModel
from data.training_data import generate_intent_data, generate_entity_data

def train_intent_model(args):
    """Train the intent classification model"""
    print("Training intent classification model...")
    
    # Check if processed data exists, if not generate it
    if not os.path.exists('data/processed/intent_train.csv'):
        print("Generating training data...")
        train_df, val_df = generate_intent_data()
    else:
        print("Loading existing training data...")
        train_df = pd.read_csv('data/processed/intent_train.csv')
        val_df = pd.read_csv('data/processed/intent_val.csv')
    
    # Create model
    model = IntentClassificationModel(
        n_classes=len(train_df['intent'].unique())
    )
    
    # Train model
    model.train(
        train_df=train_df,
        val_df=val_df,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate
    )
    
    # Make sure the directory exists
    os.makedirs('models/saved', exist_ok=True)
    
    # Save model explicitly after training
    model_path = 'models/saved/intent_model.pt'
    model.save(model_path)
    
    # Double-check that label encoder was saved
    encoder_path = model_path.replace('.pt', '_encoder.pkl')
    if not os.path.exists(encoder_path):
        print(f"Warning: Label encoder file not found at {encoder_path}")
        print("Saving label encoder explicitly...")
        import joblib
        joblib.dump(model.label_encoder, encoder_path)
        print(f"Label encoder saved to {encoder_path}")
    
    print("Intent model trained and saved!")

def train_entity_model(args):
    """Train the entity recognition model"""
    print("Training entity recognition model...")
    
    # Check if processed data exists, if not generate it
    if not os.path.exists('data/processed/entity_train.csv'):
        print("Generating training data...")
        train_df, val_df = generate_entity_data()
    else:
        print("Loading existing training data...")
        train_df = pd.read_csv('data/processed/entity_train.csv')
        val_df = pd.read_csv('data/processed/entity_val.csv')
    
    # Create model
    model = EntityRecognitionModel()
    
    # Train model
    model.train(
        train_df=train_df,
        val_df=val_df,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate
    )
    
    # Save model
    os.makedirs('models/saved', exist_ok=True)
    model.save('models/saved/entity_model.pt')
    print("Entity model trained and saved!")

def main():
    parser = argparse.ArgumentParser(description='Train the meeting scheduler bot models')
    parser.add_argument('--model', type=str, choices=['intent', 'entity', 'all'], default='all',
                        help='Which model to train (intent, entity, or all)')
    parser.add_argument('--batch_size', type=int, default=16, help='Batch size for training')
    parser.add_argument('--epochs', type=int, default=5, help='Number of epochs for training')
    parser.add_argument('--learning_rate', type=float, default=2e-5, help='Learning rate for training')
    
    args = parser.parse_args()
    
    # Create necessary directories
    os.makedirs('data/processed', exist_ok=True)
    os.makedirs('models/saved', exist_ok=True)
    
    if args.model in ['intent', 'all']:
        train_intent_model(args)
        
    if args.model in ['entity', 'all']:
        train_entity_model(args)

if __name__ == "__main__":
    main()