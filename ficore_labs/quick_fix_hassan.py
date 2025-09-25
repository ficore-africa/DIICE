#!/usr/bin/env python3
"""
Quick fix for hassan's cashflow data to resolve backslash character errors.
"""

import re
import logging
from datetime import datetime, timezone
from flask import Flask
from utils import get_mongo_db, sanitize_input

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_string_aggressively(value):
    """Remove all problematic characters from a string."""
    if not value or not isinstance(value, str):
        return value
    
    # Remove ALL backslashes
    cleaned = value.replace('\\', '')
    # Remove control characters
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)
    # Remove newlines and tabs
    cleaned = cleaned.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    # Clean up multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned

def fix_hassan_cashflows():
    """Fix cashflows specifically for user hassan."""
    try:
        # Create a minimal Flask app context to use utils
        app = Flask(__name__)
        with app.app_context():
            db = get_mongo_db()
            if not db:
                logger.error("Could not connect to database")
                return
            
            # Find all cashflows for user hassan
            query = {'user_id': 'hassan'}
            cashflows = list(db.cashflows.find(query))
            
            logger.info(f"Found {len(cashflows)} cashflows for user hassan")
            
            fixed_count = 0
            for cashflow in cashflows:
                try:
                    changes_made = False
                    
                    # Clean string fields
                    string_fields = ['party_name', 'description', 'contact', 'method', 'expense_category']
                    
                    for field in string_fields:
                        if field in cashflow and cashflow[field] is not None:
                            original = cashflow[field]
                            if isinstance(original, str) and ('\\' in original or len(original) > 200):
                                cleaned = clean_string_aggressively(original)
                                if cleaned != original:
                                    cashflow[field] = cleaned
                                    changes_made = True
                                    logger.info(f"Cleaned {field} in record {cashflow['_id']}")
                    
                    if changes_made:
                        cashflow['updated_at'] = datetime.now(timezone.utc)
                        db.cashflows.replace_one({'_id': cashflow['_id']}, cashflow)
                        fixed_count += 1
                        
                except Exception as e:
                    logger.error(f"Error processing record {cashflow.get('_id')}: {str(e)}")
                    continue
            
            logger.info(f"Fixed {fixed_count} records for user hassan")
            
    except Exception as e:
        logger.error(f"Error in fix_hassan_cashflows: {str(e)}")

if __name__ == "__main__":
    fix_hassan_cashflows()