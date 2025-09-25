#!/usr/bin/env python3
"""
Diagnostic script to find and analyze backslash character errors in cashflows.
"""

import os
import re
import logging
import json
from datetime import datetime, timezone
from pymongo import MongoClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection."""
    try:
        uri = 'mongodb+srv://ficoreaiafrica:kA1ba9Ote6SsHV3w@records.9xeqmnn.mongodb.net/ficore_accounting?retryWrites=true&w=majority&tlsAllowInvalidCertificates=true'
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        client.admin.command('ping')
        db = client['ficore_accounting']
        logger.info("Connected to MongoDB: ficore_accounting")
        return db
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        return None

def find_problematic_records(db):
    """Find records with backslash characters."""
    try:
        # Search for records containing backslashes in various fields
        problematic_records = []
        
        # Fields to check for backslashes
        fields_to_check = [
            'party_name', 'description', 'contact', 'method', 
            'expense_category', 'business_name', 'customer_name',
            'supplier_name', 'notes', 'reference'
        ]
        
        for field in fields_to_check:
            query = {field: {'$regex': r'\\'}}
            records = list(db.cashflows.find(query))
            
            if records:
                logger.info(f"Found {len(records)} records with backslashes in field '{field}'")
                for record in records:
                    problematic_records.append({
                        'record_id': str(record['_id']),
                        'user_id': record.get('user_id'),
                        'field': field,
                        'value': record.get(field),
                        'type': record.get('type')
                    })
        
        return problematic_records
        
    except Exception as e:
        logger.error(f"Error finding problematic records: {str(e)}")
        return []

def analyze_all_users(db):
    """Analyze all users and their cashflow data."""
    try:
        # Get all users
        all_users = db.cashflows.distinct('user_id')
        logger.info(f"Found {len(all_users)} unique users in cashflows")
        
        for user_id in all_users:
            user_cashflows = db.cashflows.count_documents({'user_id': user_id})
            payment_count = db.cashflows.count_documents({'user_id': user_id, 'type': 'payment'})
            receipt_count = db.cashflows.count_documents({'user_id': user_id, 'type': 'receipt'})
            
            logger.info(f"User '{user_id}': {user_cashflows} total cashflows ({payment_count} payments, {receipt_count} receipts)")
            
            # Try to query this user's payments to see if it causes the error
            try:
                query = {'user_id': user_id, 'type': 'payment'}
                cursor = db.cashflows.find(query).sort('created_at', -1)
                payments = list(cursor)
                logger.info(f"Successfully retrieved {len(payments)} payments for user '{user_id}'")
            except Exception as e:
                logger.error(f"ERROR retrieving payments for user '{user_id}': {str(e)}")
                
                # Try to find the specific problematic record
                try:
                    cursor = db.cashflows.find(query)
                    for i, record in enumerate(cursor):
                        try:
                            # Try to convert to JSON to see if it causes parsing issues
                            json.dumps(record, default=str)
                        except Exception as json_error:
                            logger.error(f"Problematic record found for user '{user_id}' at position {i}: {str(json_error)}")
                            logger.error(f"Record ID: {record.get('_id')}")
                            logger.error(f"Record data: {record}")
                            break
                except Exception as inner_e:
                    logger.error(f"Error analyzing individual records for user '{user_id}': {str(inner_e)}")
        
    except Exception as e:
        logger.error(f"Error analyzing users: {str(e)}")

def test_character_at_position(db, position=17127):
    """Try to find what's at character position 17127 in the data."""
    try:
        # Get all cashflows and try to find the character at position 17127
        all_cashflows = list(db.cashflows.find())
        
        # Convert all data to a string and check position 17127
        all_data_str = json.dumps(all_cashflows, default=str)
        
        if len(all_data_str) > position:
            char_at_position = all_data_str[position]
            context_start = max(0, position - 50)
            context_end = min(len(all_data_str), position + 50)
            context = all_data_str[context_start:context_end]
            
            logger.info(f"Character at position {position}: '{char_at_position}' (ASCII: {ord(char_at_position)})")
            logger.info(f"Context around position {position}: {context}")
        else:
            logger.info(f"Data string length ({len(all_data_str)}) is shorter than position {position}")
            
    except Exception as e:
        logger.error(f"Error testing character at position {position}: {str(e)}")

def main():
    """Main diagnostic function."""
    logger.info("Starting backslash error diagnosis")
    
    db = get_db_connection()
    if db is None:
        logger.error("Could not connect to database")
        return
    
    # 1. Find records with backslashes
    logger.info("=== Searching for records with backslashes ===")
    problematic_records = find_problematic_records(db)
    
    if problematic_records:
        logger.info(f"Found {len(problematic_records)} problematic records:")
        for record in problematic_records:
            logger.info(f"  Record {record['record_id']} (User: {record['user_id']}, Field: {record['field']}, Value: '{record['value']}')")
    else:
        logger.info("No records with backslashes found")
    
    # 2. Analyze all users
    logger.info("=== Analyzing all users ===")
    analyze_all_users(db)
    
    # 3. Test character at position 17127
    logger.info("=== Testing character at position 17127 ===")
    test_character_at_position(db, 17127)
    
    logger.info("Diagnosis completed")

if __name__ == "__main__":
    main()