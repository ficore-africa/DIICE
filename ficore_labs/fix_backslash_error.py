#!/usr/bin/env python3
"""
Comprehensive fix for the backslash character error in cashflows collection.
This script addresses the persistent "unexpected char '\\' at 17127" error.
"""

import os
import sys
import re
import logging
from datetime import datetime, timezone
from pymongo import MongoClient
from bson import ObjectId

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_mongo_connection():
    """Get MongoDB connection using environment variables."""
    try:
        mongodb_uri = os.environ.get('MONGODB_URI')
        if not mongodb_uri:
            # Try common local MongoDB URIs
            mongodb_uri = 'mongodb://localhost:27017/ficore_labs'
        
        client = MongoClient(mongodb_uri)
        # Test connection
        client.admin.command('ping')
        
        # Get database name from URI or use default
        if '/' in mongodb_uri and mongodb_uri.split('/')[-1]:
            db_name = mongodb_uri.split('/')[-1].split('?')[0]
        else:
            db_name = 'ficore_labs'
        
        db = client[db_name]
        logger.info(f"Connected to MongoDB database: {db_name}")
        return db
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        return None

def advanced_sanitize_string(value):
    """
    Advanced string sanitization to remove all problematic characters.
    """
    if not value or not isinstance(value, str):
        return value
    
    try:
        # Remove all backslashes and escape sequences
        sanitized = value.replace('\\', '')
        sanitized = sanitized.replace('\n', ' ')
        sanitized = sanitized.replace('\r', ' ')
        sanitized = sanitized.replace('\t', ' ')
        
        # Remove control characters and non-printable characters
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
        
        # Remove potentially dangerous characters
        sanitized = re.sub(r'[<>"\'`]', '', sanitized)
        
        # Clean up multiple spaces
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        return sanitized
    except Exception as e:
        logger.error(f"Error sanitizing string '{value}': {str(e)}")
        return ''

def clean_cashflow_document(doc):
    """
    Clean a single cashflow document by sanitizing all string fields.
    """
    if not doc or not isinstance(doc, dict):
        return doc
    
    cleaned_doc = doc.copy()
    changes_made = False
    
    # Fields that commonly contain user input and might have problematic characters
    string_fields = [
        'party_name', 'description', 'contact', 'method', 'expense_category',
        'business_name', 'customer_name', 'supplier_name', 'notes', 'reference'
    ]
    
    for field in string_fields:
        if field in cleaned_doc and cleaned_doc[field] is not None:
            original_value = cleaned_doc[field]
            if isinstance(original_value, str):
                cleaned_value = advanced_sanitize_string(original_value)
                if original_value != cleaned_value:
                    cleaned_doc[field] = cleaned_value
                    changes_made = True
                    logger.info(f"Cleaned field '{field}' in document {doc.get('_id', 'unknown')}")
    
    return cleaned_doc, changes_made

def fix_user_cashflows(db, user_id):
    """
    Fix cashflows for a specific user by cleaning problematic data.
    """
    try:
        query = {'user_id': user_id}
        total_count = db.cashflows.count_documents(query)
        logger.info(f"Processing {total_count} cashflow records for user {user_id}")
        
        if total_count == 0:
            logger.info(f"No cashflow records found for user {user_id}")
            return
        
        fixed_count = 0
        cursor = db.cashflows.find(query)
        
        for doc in cursor:
            try:
                cleaned_doc, changes_made = clean_cashflow_document(doc)
                
                if changes_made:
                    # Update the document in the database
                    cleaned_doc['updated_at'] = datetime.now(timezone.utc)
                    db.cashflows.replace_one({'_id': doc['_id']}, cleaned_doc)
                    fixed_count += 1
                    logger.info(f"Fixed document {doc['_id']} for user {user_id}")
                    
            except Exception as e:
                logger.error(f"Error processing document {doc.get('_id', 'unknown')} for user {user_id}: {str(e)}")
                continue
        
        logger.info(f"Fixed {fixed_count} out of {total_count} documents for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error fixing cashflows for user {user_id}: {str(e)}")

def fix_all_cashflows(db):
    """
    Fix all cashflows in the database by cleaning problematic data.
    """
    try:
        total_count = db.cashflows.count_documents({})
        logger.info(f"Processing {total_count} total cashflow records")
        
        if total_count == 0:
            logger.info("No cashflow records found in database")
            return
        
        fixed_count = 0
        cursor = db.cashflows.find({})
        
        for doc in cursor:
            try:
                cleaned_doc, changes_made = clean_cashflow_document(doc)
                
                if changes_made:
                    # Update the document in the database
                    cleaned_doc['updated_at'] = datetime.now(timezone.utc)
                    db.cashflows.replace_one({'_id': doc['_id']}, cleaned_doc)
                    fixed_count += 1
                    
                    if fixed_count % 100 == 0:
                        logger.info(f"Fixed {fixed_count} documents so far...")
                    
            except Exception as e:
                logger.error(f"Error processing document {doc.get('_id', 'unknown')}: {str(e)}")
                continue
        
        logger.info(f"Fixed {fixed_count} out of {total_count} total documents")
        
    except Exception as e:
        logger.error(f"Error fixing all cashflows: {str(e)}")

def main():
    """Main function to run the fix."""
    logger.info("Starting cashflow data cleanup to fix backslash character errors")
    
    # Get MongoDB connection
    db = get_mongo_connection()
    if not db:
        logger.error("Could not connect to MongoDB. Exiting.")
        sys.exit(1)
    
    # Check command line arguments
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        logger.info(f"Fixing cashflows for specific user: {user_id}")
        fix_user_cashflows(db, user_id)
    else:
        logger.info("Fixing all cashflows in database")
        fix_all_cashflows(db)
    
    logger.info("Cashflow data cleanup completed")

if __name__ == "__main__":
    main()