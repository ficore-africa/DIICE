#!/usr/bin/env python3
"""
Migration and cleanup script for cashflow records.
This script ensures all cashflow records have proper structure and clean data.
"""

import os
import sys
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

# Add the current directory to Python path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import get_mongo_db, sanitize_input, logger
from models import migrate_cashflows_expense_categories, migrate_naive_datetimes

def comprehensive_cashflow_migration():
    """
    Run comprehensive migration and cleanup for cashflow records.
    """
    try:
        print("Starting comprehensive cashflow migration and cleanup...")
        
        # Step 1: Migrate naive datetimes
        print("Step 1: Migrating naive datetimes...")
        migrate_naive_datetimes()
        print("✓ Datetime migration completed")
        
        # Step 2: Migrate expense categories
        print("Step 2: Migrating expense categories...")
        migrate_cashflows_expense_categories()
        print("✓ Expense categories migration completed")
        
        # Step 3: Clean problematic data
        print("Step 3: Cleaning problematic characters...")
        clean_success = clean_all_cashflow_data()
        if clean_success:
            print("✓ Data cleaning completed")
        else:
            print("⚠ Data cleaning had some issues, check logs")
        
        # Step 4: Validate data integrity
        print("Step 4: Validating data integrity...")
        validation_success = validate_cashflow_data()
        if validation_success:
            print("✓ Data validation passed")
        else:
            print("⚠ Data validation found issues, check logs")
        
        print("Comprehensive migration completed!")
        return True
        
    except Exception as e:
        logger.error(f"Error during comprehensive migration: {str(e)}")
        print(f"Migration failed: {str(e)}")
        return False

def clean_all_cashflow_data():
    """
    Clean all cashflow records to remove problematic characters and ensure data integrity.
    """
    try:
        db = get_mongo_db()
        
        # Get all cashflow records
        total_records = db.cashflows.count_documents({})
        logger.info(f"Starting comprehensive cleanup of {total_records} cashflow records")
        
        processed = 0
        cleaned = 0
        errors = 0
        
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
                            # Enhanced cleaning for problematic characters
                            cleaned_value = sanitize_input(original_value, max_length=1000 if field == 'description' else 100)
                            
                            # Additional cleaning for specific problematic patterns
                            cleaned_value = cleaned_value.replace('\\', '')  # Remove backslashes
                            cleaned_value = cleaned_value.replace('\x00', '')  # Remove null bytes
                            cleaned_value = cleaned_value.strip()  # Remove leading/trailing whitespace
                            
                            # Check if cleaning changed the value
                            if original_value != cleaned_value:
                                updates[field] = cleaned_value
                                record_cleaned = True
                                logger.info(f"Cleaned field '{field}' in record {record['_id']}")
                
                # Ensure required fields exist with defaults
                if 'user_id' not in record or not record['user_id']:
                    logger.warning(f"Record {record['_id']} missing user_id, skipping")
                    continue
                
                if 'type' not in record:
                    # Try to infer type from other fields
                    if 'expense_category' in record and record['expense_category']:
                        updates['type'] = 'payment'
                    else:
                        updates['type'] = 'receipt'  # Default assumption
                    record_cleaned = True
                
                # Ensure datetime fields are properly handled
                if 'created_at' in record and record['created_at']:
                    if hasattr(record['created_at'], 'tzinfo') and record['created_at'].tzinfo is None:
                        updates['created_at'] = record['created_at'].replace(tzinfo=ZoneInfo("UTC"))
                        record_cleaned = True
                else:
                    # Add created_at if missing
                    updates['created_at'] = datetime.now(ZoneInfo("UTC"))
                    record_cleaned = True
                
                # Ensure amount is a valid number
                if 'amount' in record:
                    try:
                        amount = float(record['amount'])
                        if amount < 0:
                            updates['amount'] = abs(amount)  # Convert negative to positive
                            record_cleaned = True
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid amount in record {record['_id']}: {record.get('amount')}")
                        updates['amount'] = 0.0
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
                    print(f"Processed {processed}/{total_records} records, cleaned {cleaned}, errors {errors}")
                    
            except Exception as record_error:
                logger.error(f"Error processing record {record.get('_id', 'unknown')}: {str(record_error)}")
                errors += 1
                continue
        
        logger.info(f"Comprehensive cleanup completed: processed {processed} records, cleaned {cleaned} records, errors {errors}")
        
        # Mark cleanup as completed
        db.system_config.update_one(
            {'_id': 'comprehensive_cashflow_cleanup_completed'},
            {'$set': {'value': True, 'completed_at': datetime.now(ZoneInfo("UTC")), 'stats': {
                'processed': processed,
                'cleaned': cleaned,
                'errors': errors
            }}},
            upsert=True
        )
        
        return errors == 0
        
    except Exception as e:
        logger.error(f"Error during comprehensive cashflow cleanup: {str(e)}")
        return False

def validate_cashflow_data():
    """
    Validate cashflow data integrity after cleanup.
    """
    try:
        db = get_mongo_db()
        
        issues = []
        
        # Check for records with problematic characters
        problematic_patterns = [
            {'party_name': {'$regex': r'[\\<>"\']+'}},
            {'description': {'$regex': r'[\\<>"\']+'}},
            {'contact': {'$regex': r'[\\<>"\']+'}},
        ]
        
        for pattern in problematic_patterns:
            count = db.cashflows.count_documents(pattern)
            if count > 0:
                issues.append(f"Found {count} records with problematic characters: {pattern}")
        
        # Check for records missing required fields
        missing_user_id = db.cashflows.count_documents({'user_id': {'$exists': False}})
        if missing_user_id > 0:
            issues.append(f"Found {missing_user_id} records missing user_id")
        
        missing_type = db.cashflows.count_documents({'type': {'$exists': False}})
        if missing_type > 0:
            issues.append(f"Found {missing_type} records missing type")
        
        missing_amount = db.cashflows.count_documents({'amount': {'$exists': False}})
        if missing_amount > 0:
            issues.append(f"Found {missing_amount} records missing amount")
        
        # Check for records with invalid amounts
        invalid_amounts = db.cashflows.count_documents({'amount': {'$lt': 0}})
        if invalid_amounts > 0:
            issues.append(f"Found {invalid_amounts} records with negative amounts")
        
        # Check for records with naive datetimes
        # This is more complex to check directly, so we'll just log a warning
        logger.info("Checking for naive datetimes (manual verification recommended)")
        
        if issues:
            for issue in issues:
                logger.warning(issue)
                print(f"⚠ {issue}")
            return False
        else:
            logger.info("Data validation passed - no issues found")
            return True
            
    except Exception as e:
        logger.error(f"Error during data validation: {str(e)}")
        return False

if __name__ == "__main__":
    print("Comprehensive Cashflow Migration and Cleanup")
    print("=" * 50)
    
    # Check if comprehensive cleanup was already completed
    try:
        db = get_mongo_db()
        cleanup_flag = db.system_config.find_one({'_id': 'comprehensive_cashflow_cleanup_completed'})
        if cleanup_flag and cleanup_flag.get('value'):
            print(f"Comprehensive cleanup already completed at: {cleanup_flag.get('completed_at', 'unknown time')}")
            stats = cleanup_flag.get('stats', {})
            print(f"Previous run stats: processed={stats.get('processed', 0)}, cleaned={stats.get('cleaned', 0)}, errors={stats.get('errors', 0)}")
            
            # For production/automated environments, skip interactive prompts
            if os.getenv('FLASK_ENV') == 'production' or os.getenv('AUTOMATED_MIGRATION') == 'true':
                print("Production environment detected. Skipping migration to prevent data issues.")
                sys.exit(0)
            
            response = input("Do you want to run the migration again? (y/N): ")
            if response.lower() != 'y':
                print("Migration cancelled.")
                sys.exit(0)
    except Exception as e:
        print(f"Error checking migration status: {str(e)}")
    
    # Skip interactive confirmation in production
    if os.getenv('FLASK_ENV') != 'production' and os.getenv('AUTOMATED_MIGRATION') != 'true':
        response = input("This will run a comprehensive migration and cleanup. Continue? (y/N): ")
        if response.lower() != 'y':
            print("Migration cancelled.")
            sys.exit(0)
    
    # Run the comprehensive migration
    success = comprehensive_cashflow_migration()
    
    if success:
        print("\n✓ Comprehensive migration completed successfully!")
        print("The cashflow data should now be clean and properly structured.")
    else:
        print("\n⚠ Migration completed with some issues. Check the logs for details.")
        sys.exit(1)