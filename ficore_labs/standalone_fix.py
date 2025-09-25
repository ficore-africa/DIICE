#!/usr/bin/env python3
"""
Standalone fix for cashflow backslash character errors.
"""

import os
import re
import logging
from datetime import datetime, timezone
from pymongo import MongoClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection."""
    try:
        # Try different MongoDB connection strings
        possible_uris = [
            os.environ.get('MONGODB_URI'),
            'mongodb://localhost:27017/ficore_labs',
            'mongodb://127.0.0.1:27017/ficore_labs'
        ]
        
        for uri in possible_uris:
            if uri:
                try:
                    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
                    client.admin.command('ping')
                    
                    # Extract database name
                    if 'ficore_accounting' in uri:
                        db_name = 'ficore_accounting'
                    elif '/' in uri and uri.split('/')[-1]:
                        db_name = uri.split('/')[-1].split('?')[0]
                    else:
                        db_name = 'ficore_labs'
                    
                    db = client[db_name]
                    logger.info(f"Connected to MongoDB: {db_name}")
                    return db
                except Exception as e:
                    logger.warning(f"Failed to connect with {uri}: {str(e)}")
                    continue
        
        logger.error("Could not connect to MongoDB with any URI")
        return None
        
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        return None

def clean_string_field(value):
    """Clean a string field of problematic characters."""
    if not value or not isinstance(value, str):
        return value
    
    # Remove ALL backslashes - this is the main issue
    cleaned = value.replace('\\', '')
    
    # Remove control characters that can cause parsing issues
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)
    
    # Replace newlines and tabs with spaces
    cleaned = cleaned.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    
    # Clean up multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Limit length to prevent issues
    if len(cleaned) > 500:
        cleaned = cleaned[:500]
    
    return cleaned

def fix_user_data(db, user_id):
    """Fix cashflow data for a specific user."""
    if db is None:
        return False
    
    try:
        # Find cashflows for the user
        query = {'user_id': user_id}
        cashflows = list(db.cashflows.find(query))
        
        logger.info(f"Found {len(cashflows)} cashflows for user {user_id}")
        
        if not cashflows:
            logger.info(f"No cashflows found for user {user_id}")
            return True
        
        fixed_count = 0
        
        for cashflow in cashflows:
            try:
                changes_made = False
                original_doc = cashflow.copy()
                
                # Fields that commonly contain problematic characters
                fields_to_clean = [
                    'party_name', 'description', 'contact', 'method', 
                    'expense_category', 'business_name', 'customer_name',
                    'supplier_name', 'notes', 'reference'
                ]
                
                for field in fields_to_clean:
                    if field in cashflow and cashflow[field] is not None:
                        original_value = cashflow[field]
                        
                        if isinstance(original_value, str):
                            cleaned_value = clean_string_field(original_value)
                            
                            if cleaned_value != original_value:
                                cashflow[field] = cleaned_value
                                changes_made = True
                                logger.info(f"Cleaned field '{field}' in record {cashflow['_id']}")
                
                # Update the record if changes were made
                if changes_made:
                    cashflow['updated_at'] = datetime.now(timezone.utc)
                    result = db.cashflows.replace_one({'_id': cashflow['_id']}, cashflow)
                    
                    if result.modified_count > 0:
                        fixed_count += 1
                        logger.info(f"Updated record {cashflow['_id']}")
                    else:
                        logger.warning(f"Failed to update record {cashflow['_id']}")
                
            except Exception as e:
                logger.error(f"Error processing record {cashflow.get('_id', 'unknown')}: {str(e)}")
                continue
        
        logger.info(f"Successfully fixed {fixed_count} out of {len(cashflows)} records for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error fixing data for user {user_id}: {str(e)}")
        return False

def fix_all_users():
    """Fix cashflow data for all users."""
    db = get_db_connection()
    if db is None:
        return False
    
    try:
        # Get all unique user IDs
        user_ids = db.cashflows.distinct('user_id')
        logger.info(f"Found {len(user_ids)} unique users")
        
        total_success = 0
        for user_id in user_ids:
            logger.info(f"Processing user: {user_id}")
            if fix_user_data(db, user_id):
                total_success += 1
            else:
                logger.error(f"Failed to fix data for user: {user_id}")
        
        logger.info(f"Successfully processed {total_success} out of {len(user_ids)} users")
        return total_success == len(user_ids)
        
    except Exception as e:
        logger.error(f"Error in fix_all_users: {str(e)}")
        return False

def main():
    """Main function."""
    logger.info("Starting cashflow data cleanup for all users")
    
    # Fix data for all users
    success = fix_all_users()
    
    if success:
        logger.info("Cleanup completed successfully for all users")
    else:
        logger.error("Cleanup failed for some users")

if __name__ == "__main__":

    main()
