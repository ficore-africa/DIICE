#!/usr/bin/env python3
"""
Data cleanup script to fix problematic characters in cashflow records.
This script addresses the "unexpected char '\\' at 17127" error by cleaning existing data.
"""

import os
import sys
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

# Add the current directory to Python path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import get_mongo_db, sanitize_input, logger

def clean_cashflow_data():
    """
    Clean all cashflow records to remove problematic characters.
    """
    try:
        db = get_mongo_db()
        
        # Get all cashflow records
        total_records = db.cashflows.count_documents({})
        logger.info(f"Starting cleanup of {total_records} cashflow records")
        
        # Process records in batches to avoid memory issues
        batch_size = 100
        processed = 0
        cleaned = 0
        
        # Fields that need cleaning
        string_fields = ['party_name', 'description', 'contact', 'method', 'expense_category']
        
        cursor = db.cashflows.find({})
        
        for record in cursor:
            try:
                updates = {}
                record_cleaned = False
                
                # Clean string fields
                for field in string_fields:
                    if field in record and record[field] is not None:
                        original_value = record[field]
                        if isinstance(original_value, str):
                            cleaned_value = sanitize_input(original_value, max_length=1000 if field == 'description' else 100)
                            
                            # Check if cleaning changed the value
                            if original_value != cleaned_value:
                                updates[field] = cleaned_value
                                record_cleaned = True
                                logger.info(f"Cleaning field '{field}' in record {record['_id']}: '{original_value}' -> '{cleaned_value}'")
                
                # Ensure datetime fields are properly handled
                if 'created_at' in record and record['created_at']:
                    if hasattr(record['created_at'], 'tzinfo') and record['created_at'].tzinfo is None:
                        updates['created_at'] = record['created_at'].replace(tzinfo=ZoneInfo("UTC"))
                        record_cleaned = True
                
                # Apply updates if any
                if updates:
                    db.cashflows.update_one(
                        {'_id': record['_id']},
                        {'$set': updates}
                    )
                    cleaned += 1
                
                processed += 1
                
                # Log progress every 100 records
                if processed % 100 == 0:
                    logger.info(f"Processed {processed}/{total_records} records, cleaned {cleaned} records")
                    
            except Exception as record_error:
                logger.error(f"Error processing record {record.get('_id', 'unknown')}: {str(record_error)}")
                continue
        
        logger.info(f"Cleanup completed: processed {processed} records, cleaned {cleaned} records")
        
        # Mark cleanup as completed
        db.system_config.update_one(
            {'_id': 'cashflow_data_cleanup_completed'},
            {'$set': {'value': True, 'completed_at': datetime.now(ZoneInfo("UTC"))}},
            upsert=True
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error during cashflow data cleanup: {str(e)}")
        return False

def check_for_problematic_characters():
    """
    Check for records that might contain problematic characters.
    """
    try:
        db = get_mongo_db()
        
        # Search for records with backslashes or other problematic characters
        problematic_patterns = [
            {'party_name': {'$regex': r'[\\<>"\']+'}},
            {'description': {'$regex': r'[\\<>"\']+'}},
            {'contact': {'$regex': r'[\\<>"\']+'}},
            {'method': {'$regex': r'[\\<>"\']+'}},
        ]
        
        total_problematic = 0
        for pattern in problematic_patterns:
            count = db.cashflows.count_documents(pattern)
            if count > 0:
                logger.info(f"Found {count} records matching pattern: {pattern}")
                total_problematic += count
        
        logger.info(f"Total records with potentially problematic characters: {total_problematic}")
        return total_problematic
        
    except Exception as e:
        logger.error(f"Error checking for problematic characters: {str(e)}")
        return -1

if __name__ == "__main__":
    print("Cashflow Data Cleanup Script")
    print("=" * 40)
    
    # Check if cleanup was already completed
    try:
        db = get_mongo_db()
        cleanup_flag = db.system_config.find_one({'_id': 'cashflow_data_cleanup_completed'})
        if cleanup_flag and cleanup_flag.get('value'):
            print(f"Cleanup already completed at: {cleanup_flag.get('completed_at', 'unknown time')}")
            
            # Still check for problematic characters
            problematic_count = check_for_problematic_characters()
            if problematic_count > 0:
                print(f"Warning: Still found {problematic_count} records with problematic characters")
                response = input("Do you want to run cleanup again? (y/N): ")
                if response.lower() != 'y':
                    sys.exit(0)
            else:
                print("No problematic characters found. Cleanup not needed.")
                sys.exit(0)
    except Exception as e:
        print(f"Error checking cleanup status: {str(e)}")
    
    # Check for problematic characters first
    print("Checking for problematic characters...")
    problematic_count = check_for_problematic_characters()
    
    if problematic_count == 0:
        print("No problematic characters found. Cleanup not needed.")
        sys.exit(0)
    elif problematic_count < 0:
        print("Error checking for problematic characters. Proceeding with cleanup anyway.")
    else:
        print(f"Found {problematic_count} records that may need cleaning.")
    
    # Confirm before proceeding
    response = input("Do you want to proceed with the cleanup? (y/N): ")
    if response.lower() != 'y':
        print("Cleanup cancelled.")
        sys.exit(0)
    
    # Run the cleanup
    print("Starting cashflow data cleanup...")
    success = clean_cashflow_data()
    
    if success:
        print("Cleanup completed successfully!")
    else:
        print("Cleanup failed. Check the logs for details.")
        sys.exit(1)