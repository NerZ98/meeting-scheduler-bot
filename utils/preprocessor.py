import re
import string
import torch
from transformers import BertTokenizer

class TextPreprocessor:
    """
    Utility class for preprocessing text for BERT models
    """
    
    def __init__(self, tokenizer_name='bert-base-uncased'):
        self.tokenizer = BertTokenizer.from_pretrained(tokenizer_name)
    
    def clean_text(self, text):
        """
        Clean the text by removing special characters, extra spaces, etc.
        """
        # Convert to lowercase
        text = text.lower()
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove URLs
        text = re.sub(r'https?://\S+|www\.\S+', '', text)
        
        # Remove HTML tags
        text = re.sub(r'<.*?>', '', text)
        
        # Remove punctuation (except those needed for dates/times)
        punct_to_keep = ['-', ':', '.', '/']
        text = ''.join([c if c not in string.punctuation or c in punct_to_keep else ' ' for c in text])
        
        # Remove extra whitespace again
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def tokenize(self, text, max_length=128, padding='max_length', truncation=True, return_tensors='pt'):
        """
        Tokenize text using the BERT tokenizer
        """
        cleaned_text = self.clean_text(text)
        
        encoding = self.tokenizer.encode_plus(
            cleaned_text,
            add_special_tokens=True,
            max_length=max_length,
            padding=padding,
            truncation=truncation,
            return_attention_mask=True,
            return_token_type_ids=True,
            return_tensors=return_tensors
        )
        
        return encoding
    
    def get_tokens(self, text):
        """
        Get the tokens from a text string
        """
        cleaned_text = self.clean_text(text)
        return self.tokenizer.tokenize(cleaned_text)
    
    def decode(self, token_ids):
        """
        Decode token IDs back to text
        """
        return self.tokenizer.decode(token_ids)
    
    def prepare_for_bert(self, texts, max_length=128):
        """
        Prepare a batch of texts for BERT
        """
        encodings = [self.tokenize(text, max_length=max_length) for text in texts]
        
        # Stack tensors
        input_ids = torch.cat([encoding['input_ids'] for encoding in encodings], dim=0)
        attention_mask = torch.cat([encoding['attention_mask'] for encoding in encodings], dim=0)
        token_type_ids = torch.cat([encoding['token_type_ids'] for encoding in encodings], dim=0)
        
        return {
            'input_ids': input_ids,
            'attention_mask': attention_mask,
            'token_type_ids': token_type_ids
        } 
