from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId
from datetime import datetime, timedelta, timezone
import logging
from werkzeug.security import generate_password_hash
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure
from translations import trans
from utils import get_mongo_db, logger, normalize_datetime
from zoneinfo import ZoneInfo
from dateutil.parser import parse as parse_datetime
import os
import time
import uuid

# Configure logger for the application
logger = logging.getLogger('business_finance_app')
logger.setLevel(logging.INFO)

def parse_and_normalize_datetime(value):
    """
    Parse and normalize datetime values, handling strings and naive datetimes.
    
    Args:
        value: Datetime, string, or other input
        
    Returns:
        datetime: UTC-aware datetime object compatible with MongoDB BSON date
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            dt = parse_datetime(value)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"Invalid datetime string: {value}")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raise ValueError(f"Unsupported datetime type: {type(value)}")

def convert_naive_to_aware_datetimes(db):
    """
    Convert naive datetimes to UTC-aware datetimes in all collections.
    
    Args:
        db: MongoDB database instance
    """
    try:
        # Check if migration has already been applied
        if db.system_config.find_one({'_id': 'datetime_migration_applied'}):
            logger.info("Naive datetime migration already applied, skipping.")
            return
        
        datetime_fields = ['created_at', 'updated_at', 'timestamp', 'trial_start', 'trial_end', 
                          'subscription_start', 'subscription_end', 'expires_at', 'redeemed_at', 
                          'last_viewed', 'completed_at', 'payment_date', 'approved_at', 'rejected_at']
        
        for collection_name in db.list_collection_names():
            collection = db[collection_name]
            # Get a sample document to check for relevant fields
            sample_doc = collection.find_one() or {}
            # Filter fields that exist in the sample document
            relevant_fields = [field for field in datetime_fields if field in sample_doc]
            
            if not relevant_fields:
                continue
                
            # Find documents with naive datetimes or string datetimes
            query = {
                '$or': [
                    {field: {'$type': ['date', 'string'], '$not': {'$type': 'timestamp'}}}
                    for field in relevant_fields
                ]
            }
            
            updated_count = 0
            for doc in collection.find(query):
                updates = {}
                for field in relevant_fields:
                    if field in doc:
                        value = doc[field]
                        try:
                            if isinstance(value, str) or (isinstance(value, datetime) and value.tzinfo is None):
                                updates[field] = parse_and_normalize_datetime(value)
                        except ValueError as ve:
                            logger.warning(f"Skipping invalid datetime in {collection_name}.{field}: {value}")
                            continue
                
                if updates:
                    collection.update_one(
                        {'_id': doc['_id']},
                        {'$set': updates}
                    )
                    updated_count += 1
            
            if updated_count > 0:
                logger.info(f"Converted {updated_count} naive or string datetimes to UTC-aware in {collection_name}")
        
        # Mark migration as complete
        db.system_config.update_one(
            {'_id': 'datetime_migration_applied'},
            {'$set': {'value': True, 'migrated_at': datetime.now(timezone.utc)}},
            upsert=True
        )
        logger.info("Naive datetime migration completed and marked in system_config")
        
    except Exception as e:
        logger.error(f"Failed to convert naive datetimes: {str(e)}", exc_info=True)
        raise

def manage_index(collection, keys, options=None, name=None):
    """
    Manage MongoDB index creation with simplified conflict resolution.
    
    Args:
        collection: MongoDB collection object
        keys: List of tuples for index keys [(field, direction), ...]
        options: Dictionary of index options (unique, sparse, etc.)
        name: Custom index name (optional)
    
    Returns:
        bool: True if index was created/updated, False if already exists
    """
    if options is None:
        options = {}
    
    try:
        # Generate index name if not provided
        if not name:
            name = '_'.join(f"{k}_{v if isinstance(v, int) else str(v).replace(' ', '_')}" for k, v in keys)
        
        # Get existing indexes
        existing_indexes = collection.index_information()
        index_key_tuple = tuple(keys)
        
        # Check if index with same key pattern already exists
        for existing_name, existing_info in existing_indexes.items():
            if tuple(existing_info['key']) == index_key_tuple:
                if existing_name == '_id_':
                    logger.info(f"Skipping _id index on {collection.name}")
                    return False
                existing_options = {k: v for k, v in existing_info.items() if k not in ['key', 'v', 'ns']}
                if existing_options == options and existing_name == name:
                    logger.info(f"Index already exists on {collection.name}: {keys} with options {options}")
                    return False
                logger.info(f"Dropping conflicting index {existing_name} on {collection.name}")
                collection.drop_index(existing_name)
                break
        
        # Create the index
        collection.create_index(keys, name=name, **options)
        logger.info(f"Created index on {collection.name}: {keys} with name '{name}' and options {options}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create index on {collection.name}: {str(e)}", exc_info=True)
        raise

def to_dict_record(record):
    """
    Convert a record document to a standardized dictionary with normalized datetime fields.
    
    Args:
        record: MongoDB record document
    
    Returns:
        dict: Standardized record dictionary
    """
    if not record:
        return {'type': None}
    
    result = {
        'id': str(record.get('_id', '')),
        'user_id': record.get('user_id', ''),
        'type': record.get('type', ''),
        'name': record.get('name', ''),
        'contact': record.get('contact', ''),
        'amount_owed': record.get('amount_owed', 0),
        'description': record.get('description', ''),
        'reminder_count': record.get('reminder_count', 0),
        'cost': record.get('cost', 0),
        'selling_price': record.get('selling_price', 0),
        'stock_qty': record.get('stock_qty', 0),
        'quantity_in_stock': record.get('quantity_in_stock', 0),
        'reorder_level': record.get('reorder_level', 0),
        'restock_date': record.get('restock_date', ''),
        'status': record.get('status', ''),
        'vendor_id': record.get('vendor_id', ''),
        'category': record.get('category', ''),
        'unit': record.get('unit', ''),
        'created_at': normalize_datetime(record.get('created_at')),
        'updated_at': normalize_datetime(record.get('updated_at')) if record.get('updated_at') else None
    }
    
    return result

def to_dict_cashflow(record):
    """
    Convert a cashflow document to a standardized dictionary with normalized datetime fields.
    
    Args:
        record: MongoDB cashflow document
    
    Returns:
        dict: Standardized cashflow dictionary
    """
    if not record:
        return {'party_name': None, 'amount': None}
    
    return {
        'id': str(record.get('_id', '')),
        'user_id': record.get('user_id', ''),
        'type': record.get('type', ''),
        'party_name': record.get('party_name', ''),
        'amount': record.get('amount', 0),
        'method': record.get('method', ''),
        'expense_category': record.get('expense_category', ''),
        'contact': record.get('contact', '') if record.get('contact') else '',
        'description': record.get('description', '') if record.get('description') else '',
        'is_tax_deductible': record.get('is_tax_deductible'),
        'tax_year': record.get('tax_year'),
        'category_metadata': record.get('category_metadata'),
        'created_at': normalize_datetime(record.get('created_at')),
        'updated_at': normalize_datetime(record.get('updated_at')) if record.get('updated_at') else None
    }

def get_db():
    """
    Get MongoDB database connection using the global client from utils.py.
    
    Returns:
        Database object
    """
    try:
        db = get_mongo_db()
        logger.info(f"Successfully connected to MongoDB database: {db.name}")
        return db
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}", exc_info=True)
        raise

def verify_no_naive_datetimes(db):
    """
    Verify no naive datetimes remain in any collection.
    
    Args:
        db: MongoDB database instance
    """
    for collection_name in db.list_collection_names():
        collection = db[collection_name]
        datetime_fields = ['created_at', 'updated_at', 'timestamp']
        # Get a sample document to check for relevant fields
        sample_doc = collection.find_one() or {}
        # Filter fields that exist in the sample document
        relevant_fields = [field for field in datetime_fields if field in sample_doc]
        # Only query if there are relevant fields to avoid empty $or
        if relevant_fields:
            naive_count = collection.count_documents({
                '$or': [
                    {field: {'$type': 'date', '$not': {'$type': 'timestamp'}}}
                    for field in relevant_fields
                ]
            })
            if naive_count > 0:
                logger.warning(f"Found {naive_count} naive datetimes in {collection_name}")

def initialize_app_data(app):
    """
    Initialize MongoDB collections, indexes, and perform one-off migrations.
    """
    max_retries = 3
    retry_delay = 1
    
    with app.app_context():
        for attempt in range(max_retries):
            try:
                db = get_db()
                db.command('ping')
                logger.info(f"Attempt {attempt + 1}/{max_retries} - {trans('general_database_connection_established', default='MongoDB connection established')}")
                break
            except Exception as e:
                logger.error(f"Failed to initialize database (attempt {attempt + 1}/{max_retries}): {str(e)}", exc_info=True)
                if attempt == max_retries - 1:
                    raise RuntimeError(trans('general_database_connection_failed', default='MongoDB connection failed after max retries'))
                time.sleep(retry_delay)
        
        try:
            db_instance = get_db()
            collections = db_instance.list_collection_names()
            
            admin_user = db_instance.users.find_one({'_id': 'admin', 'role': 'admin'})
            if not admin_user or 'password_hash' not in admin_user:
                ficore_user = db_instance.users.find_one({'_id': 'ficorerecords'})
                if not ficore_user:
                    admin_data = {
                        '_id': 'admin',
                        'email': 'ficorerecords@gmail.com',
                        'password_hash': generate_password_hash('Admin123!'),
                        'role': 'admin',
                        'is_admin': True,
                        'display_name': 'Admin',
                        'setup_complete': True,
                        'language': 'en',
                        'is_trial': False,
                        'is_subscribed': True,
                        'subscription_plan': 'admin',
                        'subscription_start': datetime.now(timezone.utc),
                        'subscription_end': None,
                        'created_at': datetime.now(timezone.utc)
                    }
                    try:
                        if admin_user:
                            db_instance.users.update_one(
                                {'_id': 'admin'},
                                {'$set': admin_data, '$unset': {'password': ''}},
                                upsert=True
                            )
                            logger.info(f"Updated default admin user: {admin_data['_id']}")
                        else:
                            created_user = create_user(db_instance, admin_data)
                            logger.info(f"Created default admin user: {created_user.id}")
                    except DuplicateKeyError:
                        logger.info(f"Admin user creation/update skipped due to existing user with same email or ID")
                    except Exception as e:
                        logger.error(f"Failed to create/update default admin user: {str(e)}", exc_info=True)
                        raise
                else:
                    logger.info(f"User with ID 'ficorerecords' already exists, skipping admin creation")
            else:
                logger.info(f"Admin user with ID 'admin' already exists with valid password_hash, skipping creation")
            
            collection_schemas = {
                'users': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['_id', 'email', 'password_hash', 'role', 'is_trial', 'trial_start', 'trial_end', 'is_subscribed'],
                            'properties': {
                                '_id': {'bsonType': 'string'},
                                'email': {'bsonType': 'string', 'pattern': r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'},
                                'password_hash': {'bsonType': 'string'},
                                'role': {'enum': ['trader', 'admin']},
                                'is_trial': {'bsonType': 'bool'},
                                'trial_start': {'bsonType': ['date', 'null']},
                                'trial_end': {'bsonType': ['date', 'null']},
                                'is_subscribed': {'bsonType': 'bool'},
                                'subscription_plan': {'bsonType': ['string', 'null'], 'enum': [None, 'monthly', 'yearly', 'admin']},
                                'subscription_start': {'bsonType': ['date', 'null']},
                                'subscription_end': {'bsonType': ['date', 'null']},
                                'language': {'bsonType': ['string', 'null'], 'enum': [None, 'en', 'ha']},
                                'created_at': {'bsonType': 'date'},
                                'display_name': {'bsonType': ['string', 'null']},
                                'is_admin': {'bsonType': 'bool'},
                                'setup_complete': {'bsonType': 'bool'},
                                'reset_token': {'bsonType': ['string', 'null']},
                                'reset_token_expiry': {'bsonType': ['date', 'null']},
                                'otp': {'bsonType': ['string', 'null']},
                                'otp_expiry': {'bsonType': ['date', 'null']},
                                'business_details': {
                                    'bsonType': ['object', 'null'],
                                    'properties': {
                                        'name': {'bsonType': 'string'},
                                        'address': {'bsonType': 'string'},
                                        'industry': {'bsonType': 'string'},
                                        'products_services': {'bsonType': 'string'},
                                        'phone_number': {'bsonType': 'string'}
                                    }
                                },
                                'profile_picture': {'bsonType': ['string', 'null']},
                                'phone': {'bsonType': ['string', 'null']},
                                'coin_balance': {'bsonType': ['double', 'null']},
                                'dark_mode': {'bsonType': ['bool', 'null']},
                                'settings': {
                                    'bsonType': ['object', 'null'],
                                    'properties': {
                                        'show_kobo': {'bsonType': 'bool'},
                                        'incognito_mode': {'bsonType': 'bool'},
                                        'app_sounds': {'bsonType': 'bool'}
                                    }
                                },
                                'security_settings': {
                                    'bsonType': ['object', 'null'],
                                    'properties': {
                                        'fingerprint_password': {'bsonType': 'bool'},
                                        'fingerprint_pin': {'bsonType': 'bool'},
                                        'hide_sensitive_data': {'bsonType': 'bool'}
                                    }
                                },
                                'annual_rent': {'bsonType': ['double', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('email', ASCENDING)], 'unique': True},
                        {'key': [('reset_token', ASCENDING)], 'sparse': True},
                        {'key': [('role', ASCENDING)]}
                    ]
                },
                'records': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'type', 'created_at'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'type': {'enum': ['debtor', 'creditor', 'inventory']},
                                'name': {'bsonType': ['string', 'null']},
                                'contact': {'bsonType': ['string', 'null']},
                                'amount_owed': {'bsonType': ['number', 'null'], 'minimum': 0},
                                'description': {'bsonType': ['string', 'null']},
                                'reminder_count': {'bsonType': ['int', 'null'], 'minimum': 0},
                                'cost': {'bsonType': ['number', 'null'], 'minimum': 0},
                                'selling_price': {'bsonType': ['number', 'null'], 'minimum': 0},
                                'stock_qty': {'bsonType': ['number', 'null'], 'minimum': 0},
                                'quantity_in_stock': {'bsonType': ['number', 'null'], 'minimum': 0},
                                'reorder_level': {'bsonType': ['number', 'null'], 'minimum': 0},
                                'restock_date': {'bsonType': ['string', 'null']},
                                'status': {'bsonType': ['string', 'null'], 'enum': [None, 'Active', 'Out of Stock', 'Discontinued']},
                                'vendor_id': {'bsonType': ['string', 'null']},
                                'category': {'bsonType': ['string', 'null']},
                                'unit': {'bsonType': ['string', 'null']},
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': ['date', 'null']}
                            },
                            'anyOf': [
                                {
                                    'properties': {
                                        'type': {'const': 'inventory'},
                                        'name': {'bsonType': 'string'},
                                        'cost': {'bsonType': 'number', 'minimum': 0},
                                        'selling_price': {'bsonType': 'number', 'minimum': 0}
                                    },
                                    'required': ['name', 'cost', 'selling_price']
                                },
                                {
                                    'properties': {
                                        'type': {'enum': ['debtor', 'creditor']}
                                    }
                                }
                            ]
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('type', ASCENDING)]},
                        {'key': [('created_at', DESCENDING)]},
                        {'key': [('user_id', ASCENDING), ('category', ASCENDING)], 'sparse': True},
                        {'key': [('user_id', ASCENDING), ('status', ASCENDING)], 'sparse': True}
                    ]
                },
                'cashflows': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'type', 'party_name', 'amount', 'created_at'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'type': {'enum': ['receipt', 'payment']},
                                'party_name': {'bsonType': 'string'},
                                'amount': {'bsonType': 'number', 'minimum': 0},
                                'method': {'bsonType': ['string', 'null']},
                                'expense_category': {
                                    'bsonType': ['string', 'null'],
                                    'enum': [None, 'office_admin', 'staff_wages', 'business_travel', 'rent_utilities', 
                                             'marketing_sales', 'cogs', 'personal_expenses', 'statutory_contributions']
                                },
                                'contact': {'bsonType': ['string', 'null']},
                                'description': {'bsonType': ['string', 'null']},
                                'is_tax_deductible': {'bsonType': ['bool', 'null']},
                                'tax_year': {'bsonType': ['int', 'null']},
                                'category_metadata': {
                                    'bsonType': ['object', 'null'],
                                    'properties': {
                                        'category_display_name': {'bsonType': ['string', 'null']},
                                        'is_personal': {'bsonType': ['bool', 'null']},
                                        'is_statutory': {'bsonType': ['bool', 'null']}
                                    }
                                },
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('type', ASCENDING)]},
                        {'key': [('created_at', DESCENDING)]},
                        {'key': [('user_id', ASCENDING), ('expense_category', ASCENDING)]},
                        {'key': [('user_id', ASCENDING), ('tax_year', ASCENDING)]},
                        {'key': [('user_id', ASCENDING), ('is_tax_deductible', ASCENDING)]}
                    ]
                },
                'inventory_movements': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['inventory_item_id', 'change_type', 'quantity', 'date', 'notes'],
                            'properties': {
                                'inventory_item_id': {'bsonType': 'string'},
                                'change_type': {'enum': ['add', 'adjust', 'remove']},
                                'quantity': {'bsonType': 'number'},
                                'date': {'bsonType': 'date'},
                                'notes': {'bsonType': 'string'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('inventory_item_id', ASCENDING)]},
                        {'key': [('date', DESCENDING)]}
                    ]
                },
                'audit_logs': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['action', 'timestamp'],
                            'properties': {
                                'admin_id': {'bsonType': ['string', 'null']},
                                'action': {'bsonType': 'string'},
                                'details': {'bsonType': ['object', 'null']},
                                'timestamp': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('admin_id', ASCENDING)], 'sparse': True},
                        {'key': [('timestamp', DESCENDING)]}
                    ]
                },
                'temp_passwords': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'temp_password', 'created_at'],
                            'properties': {
                                '_id': {'bsonType': 'objectId'},
                                'user_id': {'bsonType': 'string'},
                                'temp_password': {'bsonType': 'string'},
                                'created_at': {'bsonType': 'date'},
                                'expires_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING)], 'unique': True},
                        {'key': [('expires_at', ASCENDING)], 'expireAfterSeconds': 604800}
                    ]
                },
                'feedback': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['tool_name', 'rating', 'timestamp'],
                            'properties': {
                                '_id': {'bsonType': 'objectId'},
                                'user_id': {'bsonType': ['string', 'null']},
                                'session_id': {'bsonType': 'string'},
                                'tool_name': {'enum': ['profile', 'debtors', 'creditors', 'receipts', 'payment', 'report', 'inventory']},
                                'rating': {'bsonType': 'int', 'minimum': 1, 'maximum': 5},
                                'comment': {'bsonType': ['string', 'null']},
                                'timestamp': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING)], 'sparse': True},
                        {'key': [('tool_name', ASCENDING)]},
                        {'key': [('timestamp', DESCENDING)]}
                    ]
                },
                'notifications': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'message', 'type', 'read', 'timestamp'],
                            'properties': {
                                '_id': {'bsonType': 'objectId'},
                                'user_id': {'bsonType': 'string'},
                                'message': {'bsonType': 'string'},
                                'type': {'enum': ['info', 'warning', 'error', 'success', 'email', 'sms', 'whatsapp']},
                                'read': {'bsonType': 'bool'},
                                'timestamp': {'bsonType': 'date'},
                                'details': {'bsonType': ['object', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('read', ASCENDING)]},
                        {'key': [('timestamp', DESCENDING)]}
                    ]
                },
                'kyc_records': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'full_name', 'id_type', 'id_number', 'uploaded_id_photo_url', 'status', 'created_at', 'updated_at'],
                            'properties': {
                                '_id': {'bsonType': 'objectId'},
                                'user_id': {'bsonType': 'string'},
                                'full_name': {'bsonType': 'string'},
                                'id_type': {'enum': ['NIN', 'Voters Card', 'Passport']},
                                'id_number': {'bsonType': 'string'},
                                'uploaded_id_photo_url': {'bsonType': 'string'},
                                'status': {'enum': ['pending', 'approved', 'rejected']},
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING)], 'unique': True},
                        {'key': [('status', ASCENDING)]},
                        {'key': [('created_at', DESCENDING)]}
                    ]
                },
                'waitlist': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['full_name', 'whatsapp_number', 'email', 'created_at', 'updated_at'],
                            'properties': {
                                '_id': {'bsonType': 'objectId'},
                                'full_name': {'bsonType': 'string'},
                                'whatsapp_number': {'bsonType': 'string'},
                                'email': {'bsonType': 'string', 'pattern': r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'},
                                'business_type': {'bsonType': ['string', 'null']},
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('email', ASCENDING)], 'unique': True},
                        {'key': [('whatsapp_number', ASCENDING)], 'unique': True},
                        {'key': [('created_at', DESCENDING)]}
                    ]
                },
                'payment_receipts': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'filename', 'file_path', 'plan_type', 'amount_paid', 'payment_date', 'status', 'uploaded_at'],
                            'properties': {
                                '_id': {'bsonType': 'objectId'},
                                'user_id': {'bsonType': 'string'},
                                'filename': {'bsonType': 'string'},
                                'file_path': {'bsonType': 'string'},
                                'plan_type': {'enum': ['monthly', 'yearly']},
                                'amount_paid': {'bsonType': 'number', 'minimum': 0},
                                'payment_date': {'bsonType': 'date'},
                                'status': {'enum': ['pending', 'approved', 'rejected']},
                                'uploaded_at': {'bsonType': 'date'},
                                'approved_by': {'bsonType': ['string', 'null']},
                                'approved_at': {'bsonType': ['date', 'null']},
                                'rejected_by': {'bsonType': ['string', 'null']},
                                'rejected_at': {'bsonType': ['date', 'null']},
                                'rejection_reason': {'bsonType': ['string', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING)]},
                        {'key': [('status', ASCENDING)]},
                        {'key': [('uploaded_at', DESCENDING)]}
                    ]
                },
                'rewards': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'type', 'points', 'status', 'created_at'],
                            'properties': {
                                '_id': {'bsonType': 'objectId'},
                                'user_id': {'bsonType': 'string'},
                                'type': {'enum': ['referral', 'milestone', 'promotion', 'loyalty']},
                                'points': {'bsonType': 'int', 'minimum': 0},
                                'status': {'enum': ['pending', 'awarded', 'redeemed', 'expired']},
                                'description': {'bsonType': ['string', 'null']},
                                'created_at': {'bsonType': 'date'},
                                'expires_at': {'bsonType': ['date', 'null']},
                                'redeemed_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('type', ASCENDING)]},
                        {'key': [('status', ASCENDING)]},
                        {'key': [('created_at', DESCENDING)]},
                        {'key': [('expires_at', ASCENDING)], 'expireAfterSeconds': 31536000}
                    ]
                },
                'education_progress': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'module_id'],
                            'properties': {
                                '_id': {'bsonType': 'objectId'},
                                'user_id': {'bsonType': 'string'},
                                'module_id': {'bsonType': 'string'},
                                'last_viewed': {'bsonType': ['date', 'null']},
                                'view_count': {'bsonType': ['int', 'null'], 'minimum': 0},
                                'total_views': {'bsonType': ['int', 'null'], 'minimum': 0},
                                'completed': {'bsonType': ['bool', 'null']},
                                'completed_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
378
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('module_id', ASCENDING)], 'unique': True},
                        {'key': [('user_id', ASCENDING)]},
                        {'key': [('completed', ASCENDING)]},
                        {'key': [('last_viewed', DESCENDING)]}
                    ]
                },
                'user_entities': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'business_entity_type'],
                            'properties': {
                                '_id': {'bsonType': 'objectId'},
                                'user_id': {'bsonType': 'string'},
                                'business_entity_type': {
                                    'enum': ['sole_proprietor', 'limited_liability']
                                },
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING)], 'unique': True},
                        {'key': [('business_entity_type', ASCENDING)]},
                        {'key': [('created_at', DESCENDING)]}
                    ]
                }
            }
                
            for collection_name, config in collection_schemas.items():
                if collection_name not in collections:
                    try:
                        db_instance.create_collection(collection_name, validator=config.get('validator', {}))
                        logger.info(f"{trans('general_collection_created', default='Created collection')}: {collection_name}")
                    except Exception as e:
                        logger.error(f"Failed to create collection {collection_name}: {str(e)}", exc_info=True)
                        raise
                else:
                    try:
                        db_instance.command('collMod', collection_name, validator=config.get('validator', {}))
                        logger.info(f"Updated validator for collection: {collection_name}")
                    except Exception as e:
                        logger.error(f"Failed to update validator for collection {collection_name}: {str(e)}", exc_info=True)
                        raise
                
                collection_obj = db_instance[collection_name]
                for index in config.get('indexes', []):
                    keys = index['key']
                    options = {k: v for k, v in index.items() if k != 'key'}
                    index_name = '_'.join(f"{k}_{v if isinstance(v, int) else str(v).replace(' ', '_')}" for k, v in keys)
                    try:
                        manage_index(collection_obj, keys, options, index_name)
                    except Exception as e:
                        logger.error(f"Failed to manage index on {collection_name}: {str(e)}", exc_info=True)
                        raise
            
            if 'rewards' in collections:
                reward_exists = db_instance.rewards.find_one({'type': 'referral'})
                if not reward_exists:
                    sample_reward = {
                        'user_id': 'admin',
                        'type': 'referral',
                        'points': 100,
                        'status': 'pending',
                        'description': 'Sample referral reward for testing purposes.',
                        'created_at': datetime.now(timezone.utc),
                        'expires_at': datetime.now(timezone.utc) + timedelta(days=365)
                    }
                    try:
                        result = db_instance.rewards.insert_one(sample_reward)
                        logger.info(f"Created sample reward with ID: {result.inserted_id}")
                    except Exception as e:
                        logger.error(f"Failed to create sample reward: {str(e)}", exc_info=True)
                        raise
            
            if 'records' in collections:
                inventory_exists = db_instance.records.find_one({'type': 'inventory'})
                if not inventory_exists:
                    sample_inventory = {
                        'user_id': 'admin',
                        'type': 'inventory',
                        'name': 'Sample Inventory Item',
                        'cost': 100.0,
                        'selling_price': 125.0,
                        'created_at': datetime.now(timezone.utc)
                    }
                    try:
                        result = db_instance.records.insert_one(sample_inventory)
                        logger.info(f"Created sample inventory record with ID: {result.inserted_id}")
                    except Exception as e:
                        logger.error(f"Failed to create sample inventory record: {str(e)}", exc_info=True)
                        raise
            
            if 'users' in collections:
                try:
                    fix_flag = db_instance.system_config.find_one({'_id': 'user_fixes_applied'})
                    if fix_flag and fix_flag.get('value') is True:
                        logger.info("User fixes already applied, skipping.")
                    else:
                        users_to_fix = db_instance.users.find({
                            '$or': [
                                {'password_hash': {'$exists': False}},
                                {'is_trial': {'$exists': False}},
                                {'trial_start': {'$exists': False}},
                                {'trial_end': {'$exists': False}},
                                {'is_subscribed': {'$exists': False}},
                                {'subscription_plan': {'$exists': False}},
                                {'subscription_start': {'$exists': False}},
                                {'subscription_end': {'$exists': False}},
                                {'settings': {'$exists': False}},
                                {'security_settings': {'$exists': False}}
                            ]
                        })
                        for user in users_to_fix:
                            updates = {}
                            if 'password_hash' not in user:
                                temp_password = str(uuid.uuid4())
                                updates['password_hash'] = generate_password_hash(temp_password)
                                logger.info(f"Added password_hash for user {user['_id']}. Temporary password: {temp_password} (for admin use only)")
                                try:
                                    db_instance.temp_passwords.update_one(
                                        {'user_id': str(user['_id'])},
                                        {
                                            '$set': {
                                                'temp_password': temp_password,
                                                'created_at': datetime.now(timezone.utc),
                                                'expires_at': datetime.now(timezone.utc) + timedelta(days=7)
                                            },
                                            '$setOnInsert': {
                                                '_id': ObjectId(),
                                                'user_id': str(user['_id'])
                                            }
                                        },
                                        upsert=True
                                    )
                                    logger.info(f"Stored temporary password for user {user['_id']} in temp_passwords collection")
                                except Exception as e:
                                    logger.error(f"Failed to store temporary password for user {user['_id']}: {str(e)}", exc_info=True)
                                    raise
                            if 'is_trial' not in user:
                                updates['is_trial'] = True
                                updates['trial_start'] = datetime.now(timezone.utc)
                                updates['trial_end'] = datetime.now(timezone.utc) + timedelta(days=30)
                                updates['is_subscribed'] = False
                                updates['subscription_plan'] = None
                                updates['subscription_start'] = None
                                updates['subscription_end'] = None
                                logger.info(f"Initialized trial and subscription fields for user {user['_id']}")
                            if 'settings' not in user:
                                updates['settings'] = {
                                    'show_kobo': False,
                                    'incognito_mode': False,
                                    'app_sounds': True
                                }
                            if 'security_settings' not in user:
                                updates['security_settings'] = {
                                    'fingerprint_password': False,
                                    'fingerprint_pin': False,
                                    'hide_sensitive_data': False
                                }
                            if updates:
                                db_instance.users.update_one(
                                    {'_id': user['_id']},
                                    {'$set': updates}
                                )
                        
                        db_instance.system_config.update_one(
                            {'_id': 'user_fixes_applied'},
                            {'$set': {'value': True}},
                            upsert=True
                        )
                        logger.info("Marked user fixes as applied in system_config")
                except Exception as e:
                    logger.error(f"Failed to fix user documents: {str(e)}", exc_info=True)
                    raise
            
            try:
                convert_naive_to_aware_datetimes(db_instance)
            except Exception as e:
                logger.error(f"Failed to convert naive datetimes during initialization: {str(e)}", exc_info=True)
                raise
                
            try:
                verify_no_naive_datetimes(db_instance)
            except Exception as e:
                logger.error(f"Failed to verify naive datetimes: {str(e)}", exc_info=True)
                raise
                
        except Exception as e:
            logger.error(f"{trans('general_database_initialization_failed', default='Failed to initialize database')}: {str(e)}", exc_info=True)
            raise

class User:
    def __init__(self, id, email, display_name=None, role='trader', is_admin=False, setup_complete=False, language='en', 
                 is_trial=True, trial_start=None, trial_end=None, is_subscribed=False, 
                 subscription_plan=None, subscription_start=None, subscription_end=None,
                 profile_picture=None, phone=None, coin_balance=0, dark_mode=False, 
                 settings=None, security_settings=None, annual_rent=None):
        self.id = id
        self.email = email
        self.username = display_name or email.split('@')[0]
        self.role = role
        self.display_name = display_name or self.username
        self.is_admin = is_admin
        self.setup_complete = setup_complete
        self.language = language
        self.is_trial = is_trial
        self.trial_start = trial_start or datetime.now(timezone.utc)
        self.trial_end = trial_end or (datetime.now(timezone.utc) + timedelta(days=30))
        self.is_subscribed = is_subscribed
        self.subscription_plan = subscription_plan
        self.subscription_start = subscription_start
        self.subscription_end = subscription_end
        self.profile_picture = profile_picture
        self.phone = phone
        self.coin_balance = coin_balance
        self.dark_mode = dark_mode
        self.settings = settings or {}
        self.security_settings = security_settings or {}
        self.annual_rent = annual_rent or 0

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def is_trial_active(self):
        """
        Check if the user's trial or subscription is active.
        """
        if self.role == 'admin' or self.is_admin:
            return True
        if self.is_subscribed and self.subscription_end:
            subscription_end_aware = (
                self.subscription_end.replace(tzinfo=timezone.utc)
                if self.subscription_end.tzinfo is None
                else self.subscription_end
            )
            return datetime.now(timezone.utc) <= subscription_end_aware
        if self.is_trial and self.trial_end:
            trial_end_aware = (
                self.trial_end.replace(tzinfo=timezone.utc)
                if self.trial_end.tzinfo is None
                else self.trial_end
            )
            return datetime.now(timezone.utc) <= trial_end_aware
        return False

def create_user(db, user_data):
    """
    Create a new user in the users collection with trial and subscription settings.
    """
    try:
        user_id = user_data.get('username', user_data['email'].split('@')[0]).lower()
        if 'password' not in user_data:
            user_data['password'] = str(uuid.uuid4())
        user_data['password_hash'] = generate_password_hash(user_data['password'])
        
        user_doc = {
            '_id': user_id,
            'email': user_data['email'].lower(),
            'password_hash': user_data['password_hash'],
            'role': user_data.get('role', 'trader'),
            'display_name': user_data.get('display_name', user_id),
            'is_admin': user_data.get('is_admin', False),
            'setup_complete': user_data.get('setup_complete', False),
            'language': user_data.get('language', 'en'),
            'is_trial': True,
            'trial_start': datetime.now(timezone.utc),
            'trial_end': datetime.now(timezone.utc) + timedelta(days=30),
            'is_subscribed': False,
            'subscription_plan': None,
            'subscription_start': None,
            'subscription_end': None,
            'created_at': datetime.now(timezone.utc),
            'business_details': user_data.get('business_details'),
            'profile_picture': user_data.get('profile_picture', None),
            'phone': user_data.get('phone', None),
            'coin_balance': user_data.get('coin_balance', 0),
            'dark_mode': user_data.get('dark_mode', False),
            'settings': user_data.get('settings', {
                'show_kobo': False,
                'incognito_mode': False,
                'app_sounds': True
            }),
            'security_settings': user_data.get('security_settings', {
                'fingerprint_password': False,
                'fingerprint_pin': False,
                'hide_sensitive_data': False
            })
        }
        
        with db.client.start_session() as session:
            with session.start_transaction():
                db.users.insert_one(user_doc, session=session)
        
        logger.info(f"Created user with ID: {user_id} with 30-day trial")
        get_user.cache_clear()
        get_user_by_email.cache_clear()
        return User(
            id=user_doc['_id'],
            email=user_doc['email'],
            role=user_doc['role'],
            display_name=user_doc['display_name'],
            is_admin=user_doc['is_admin'],
            setup_complete=user_doc['setup_complete'],
            language=user_doc['language'],
            is_trial=user_doc['is_trial'],
            trial_start=user_doc['trial_start'],
            trial_end=user_doc['trial_end'],
            is_subscribed=user_doc['is_subscribed'],
            subscription_plan=user_doc['subscription_plan'],
            subscription_start=user_doc['subscription_start'],
            subscription_end=user_doc['subscription_end'],
            profile_picture=user_doc['profile_picture'],
            phone=user_doc['phone'],
            coin_balance=user_doc['coin_balance'],
            dark_mode=user_doc['dark_mode'],
            settings=user_doc['settings'],
            security_settings=user_doc['security_settings']
        )
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}", exc_info=True)
        raise ValueError("User with this email or username already exists")

from functools import lru_cache

@lru_cache(maxsize=128)
def get_user_by_email(db, email):
    """
    Retrieve a user by email from the users collection.
    """
    try:
        user_doc = db.users.find_one({'email': email.lower()})
        if user_doc:
            return User(
                id=user_doc['_id'],
                email=user_doc['email'],
                role=user_doc.get('role', 'trader'),
                display_name=user_doc.get('display_name'),
                is_admin=user_doc.get('is_admin', False),
                setup_complete=user_doc.get('setup_complete', False),
                language=user_doc.get('language', 'en'),
                is_trial=user_doc.get('is_trial', True),
                trial_start=user_doc.get('trial_start'),
                trial_end=user_doc.get('trial_end'),
                is_subscribed=user_doc.get('is_subscribed', False),
                subscription_plan=user_doc.get('subscription_plan'),
                subscription_start=user_doc.get('subscription_start'),
                subscription_end=user_doc.get('subscription_end'),
                profile_picture=user_doc.get('profile_picture'),
                phone=user_doc.get('phone'),
                coin_balance=user_doc.get('coin_balance', 0),
                dark_mode=user_doc.get('dark_mode', False),
                settings=user_doc.get('settings', {}),
                security_settings=user_doc.get('security_settings', {})
            )
        return None
    except Exception as e:
        logger.error(f"{trans('general_user_fetch_error', default='Error getting user by email')} {email}: {str(e)}", exc_info=True)
        raise

@lru_cache(maxsize=128)
def get_user(db, user_id):
    """
    Retrieve a user by ID from the users collection.
    """
    try:
        user_doc = db.users.find_one({'_id': user_id})
        if user_doc:
            return User(
                id=user_doc['_id'],
                email=user_doc['email'],
                role=user_doc.get('role', 'trader'),
                display_name=user_doc.get('display_name'),
                is_admin=user_doc.get('is_admin', False),
                setup_complete=user_doc.get('setup_complete', False),
                language=user_doc.get('language', 'en'),
                is_trial=user_doc.get('is_trial', True),
                trial_start=user_doc.get('trial_start'),
                trial_end=user_doc.get('trial_end'),
                is_subscribed=user_doc.get('is_subscribed', False),
                subscription_plan=user_doc.get('subscription_plan'),
                subscription_start=user_doc.get('subscription_start'),
                subscription_end=user_doc.get('subscription_end'),
                profile_picture=user_doc.get('profile_picture'),
                phone=user_doc.get('phone'),
                coin_balance=user_doc.get('coin_balance', 0),
                dark_mode=user_doc.get('dark_mode', False),
                settings=user_doc.get('settings', {}),
                security_settings=user_doc.get('security_settings', {})
            )
        return None
    except Exception as e:
        logger.error(f"{trans('general_user_fetch_error', default='Error getting user by ID')} {user_id}: {str(e)}", exc_info=True)
        raise

def update_user(db, user_id, update_data):
    """
    Update a user in the users collection.
    """
    try:
        if 'password' in update_data:
            update_data['password_hash'] = generate_password_hash(update_data.pop('password'))
        result = db.users.update_one(
            {'_id': user_id},
            {'$set': update_data}
        )
        if result.modified_count > 0:
            logger.info(f"{trans('general_user_updated', default='Updated user with ID')}: {user_id}")
            get_user.cache_clear()
            get_user_by_email.cache_clear()
            return True
        logger.info(f"{trans('general_user_no_change', default='No changes made to user with ID')}: {user_id}")
        return False
    except Exception as e:
        logger.error(f"{trans('general_user_update_error', default='Error updating user with ID')} {user_id}: {str(e)}", exc_info=True)
        raise

def get_records(db, filter_kwargs):
    """
    Retrieve records based on filter criteria.
    """
    try:
        from utils import safe_find_records
        records = safe_find_records(db, filter_kwargs, 'created_at', -1)
        return [to_dict_record(record) for record in records]
    except Exception as e:
        logger.error(f"{trans('general_records_fetch_error', default='Error getting records')}: {str(e)}", exc_info=True)
        raise

def create_record(db, record_data):
    """
    Create a new record in the records collection.
    """
    try:
        required_fields = ['user_id', 'type', 'created_at']
        if not all(field in record_data for field in required_fields):
            raise ValueError(trans('general_missing_record_fields', default='Missing required record fields'))
        
        record_data['created_at'] = parse_and_normalize_datetime(record_data['created_at'])
        if 'updated_at' in record_data:
            record_data['updated_at'] = parse_and_normalize_datetime(record_data['updated_at'])
        
        result = db.records.insert_one(record_data)
        logger.info(f"{trans('general_record_created', default='Created record with ID')}: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_record_creation_error', default='Error creating record')}: {str(e)}", exc_info=True)
        raise

def update_record(db, record_id, update_data):
    """
    Update a record in the records collection.
    """
    try:
        update_data['updated_at'] = datetime.now(timezone.utc)
        result = db.records.update_one(
            {'_id': ObjectId(record_id)},
            {'$set': update_data}
        )
        if result.modified_count > 0:
            logger.info(f"{trans('general_record_updated', default='Updated record with ID')}: {record_id}")
            return True
        logger.info(f"{trans('general_record_no_change', default='No changes made to record with ID')}: {record_id}")
        return False
    except Exception as e:
        logger.error(f"{trans('general_record_update_error', default='Error updating record with ID')} {record_id}: {str(e)}", exc_info=True)
        raise

def get_cashflows(db, filter_kwargs):
    """
    Retrieve cashflow records based on filter criteria.
    """
    try:
        from utils import safe_find_cashflows
        cashflows = safe_find_cashflows(db, filter_kwargs, 'created_at', -1)
        return [to_dict_cashflow(cashflow) for cashflow in cashflows]
    except Exception as e:
        logger.error(f"{trans('general_cashflows_fetch_error', default='Error getting cashflows')}: {str(e)}", exc_info=True)
        raise

def create_cashflow(db, cashflow_data):
    """
    Create a new cashflow record in the cashflows collection.
    """
    try:
        required_fields = ['user_id', 'type', 'party_name', 'amount', 'created_at']
        if not all(field in cashflow_data for field in required_fields):
            raise ValueError(trans('general_missing_cashflow_fields', default='Missing required cashflow fields'))
        
        cashflow_data['created_at'] = parse_and_normalize_datetime(cashflow_data['created_at'])
        if 'updated_at' in cashflow_data:
            cashflow_data['updated_at'] = parse_and_normalize_datetime(cashflow_data['updated_at'])
        
        result = db.cashflows.insert_one(cashflow_data)
        logger.info(f"{trans('general_cashflow_created', default='Created cashflow record with ID')}: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_cashflow_creation_error', default='Error creating cashflow record')}: {str(e)}", exc_info=True)
        raise

def update_cashflow(db, cashflow_id, update_data):
    """
    Update a cashflow record in the cashflows collection.
    """
    try:
        update_data['updated_at'] = datetime.now(timezone.utc)
        result = db.cashflows.update_one(
            {'_id': ObjectId(cashflow_id)},
            {'$set': update_data}
        )
        if result.modified_count > 0:
            logger.info(f"{trans('general_cashflow_updated', default='Updated cashflow record with ID')}: {cashflow_id}")
            return True
        logger.info(f"{trans('general_cashflow_no_change', default='No changes made to cashflow record with ID')}: {cashflow_id}")
        return False
    except Exception as e:
        logger.error(f"{trans('general_cashflow_update_error', default='Error updating cashflow record with ID')} {cashflow_id}: {str(e)}", exc_info=True)
        raise

def get_audit_logs(db, filter_kwargs):
    """
    Retrieve audit log records based on filter criteria.
    """
    try:
        return list(db.audit_logs.find(filter_kwargs).sort('timestamp', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_audit_logs_fetch_error', default='Error getting audit logs')}: {str(e)}", exc_info=True)
        raise

def create_audit_log(db, audit_data):
    """
    Create a new audit log in the audit_logs collection.
    """
    try:
        required_fields = ['admin_id', 'action', 'timestamp']
        if not all(field in audit_data for field in required_fields):
            raise ValueError(trans('general_missing_audit_fields', default='Missing required audit log fields'))
        result = db.audit_logs.insert_one(audit_data)
        logger.info(f"{trans('general_audit_log_created', default='Created audit log with ID')}: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_audit_log_creation_error', default='Error creating audit log')}: {str(e)}", exc_info=True)
        raise

def create_feedback(db, feedback_data):
    """
    Create a new feedback entry in the feedback collection.
    """
    try:
        required_fields = ['tool_name', 'rating', 'timestamp']
        if not all(field in feedback_data for field in required_fields):
            raise ValueError(trans('general_missing_feedback_fields', default='Missing required feedback fields'))
        result = db.feedback.insert_one(feedback_data)
        logger.info(f"{trans('general_feedback_created', default='Created feedback with ID')}: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_feedback_creation_error', default='Error creating feedback')}: {str(e)}", exc_info=True)
        raise

def get_feedback(db, filter_kwargs):
    """
    Retrieve feedback entries based on filter criteria.
    """
    try:
        return list(db.feedback.find(filter_kwargs).sort('timestamp', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_feedback_fetch_error', default='Error getting feedback')}: {str(e)}", exc_info=True)
        raise

def to_dict_feedback(record):
    """
    Convert feedback record to dictionary.
    """
    if not record:
        return {'tool_name': None, 'rating': None}
    return {
        'id': str(record.get('_id', '')),
        'user_id': record.get('user_id', None),
        'session_id': record.get('session_id', ''),
        'tool_name': record.get('tool_name', ''),
        'rating': record.get('rating', 0),
        'comment': record.get('comment', None),
        'timestamp': record.get('timestamp')
    }

def to_dict_user(user):
    """
    Convert user object to dictionary.
    """
    if not user:
        return {'id': None, 'email': None}
    return {
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'role': user.role,
        'display_name': user.display_name,
        'is_admin': user.is_admin,
        'setup_complete': user.setup_complete,
        'language': user.language,
        'is_trial': user.is_trial,
        'trial_start': user.trial_start,
        'trial_end': user.trial_end,
        'is_subscribed': user.is_subscribed,
        'subscription_plan': user.subscription_plan,
        'subscription_start': user.subscription_start,
        'subscription_end': user.subscription_end,
        'profile_picture': user.profile_picture,
        'phone': user.phone,
        'dark_mode': user.dark_mode,
        'settings': user.settings,
        'security_settings': user.security_settings
    }

def create_kyc_record(db, kyc_data):
    """
    Create a new KYC record in the kyc_records collection.
    """
    try:
        required_fields = ['user_id', 'full_name', 'id_type', 'id_number', 'uploaded_id_photo_url', 'status', 'created_at', 'updated_at']
        if not all(field in kyc_data for field in required_fields):
            raise ValueError(trans('general_missing_kyc_fields', default='Missing required KYC fields'))
        kyc_data['created_at'] = parse_and_normalize_datetime(kyc_data['created_at'])
        kyc_data['updated_at'] = parse_and_normalize_datetime(kyc_data['updated_at'])
        result = db.kyc_records.insert_one(kyc_data)
        logger.info(f"{trans('general_kyc_created', default='Created KYC record with ID')}: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_kyc_creation_error', default='Error creating KYC record')}: {str(e)}", exc_info=True)
        raise

def get_kyc_record(db, filter_kwargs):
    """
    Retrieve KYC records based on filter criteria.
    """
    try:
        return list(db.kyc_records.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_kyc_fetch_error', default='Error getting KYC records')}: {str(e)}", exc_info=True)
        raise

def update_kyc_record(db, filter_kwargs, update_data):
    """
    Updates a KYC record in the database.
    """
    try:
        update_data['updated_at'] = datetime.now(timezone.utc)
        result = db.kyc_records.update_one(filter_kwargs, {'$set': update_data})
        if result.matched_count == 0:
            raise Exception("No KYC record found matching the criteria for update.")
        return result
    except Exception as e:
        logger.error(f"Error updating KYC record: {str(e)}", exc_info=True, extra={'filter': filter_kwargs, 'data': update_data})
        raise

def to_dict_kyc_record(record):
    """
    Convert KYC record to dictionary.
    """
    if not record:
        return {'user_id': None, 'status': None}
    return {
        'id': str(record.get('_id', '')),
        'user_id': record.get('user_id', ''),
        'full_name': record.get('full_name', ''),
        'id_type': record.get('id_type', ''),
        'id_number': record.get('id_number', ''),
        'uploaded_id_photo_url': record.get('uploaded_id_photo_url', ''),
        'status': record.get('status', ''),
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at')
    }

def create_waitlist_entry(db, waitlist_data):
    """
    Create a new waitlist entry in the waitlist collection.
    """
    try:
        required_fields = ['full_name', 'whatsapp_number', 'email', 'created_at', 'updated_at']
        if not all(field in waitlist_data for field in required_fields):
            raise ValueError(trans('general_missing_waitlist_fields', default='Missing required waitlist fields'))
        result = db.waitlist.insert_one(waitlist_data)
        logger.info(f"{trans('general_waitlist_created', default='Created waitlist entry with ID')}: {result.inserted_id}")
        return str(result.inserted_id)
    except DuplicateKeyError:
        logger.error(f"Duplicate email or WhatsApp number in waitlist: {waitlist_data.get('email')}: {str(e)}", exc_info=True)
        raise ValueError(trans('general_waitlist_duplicate_error', default='Email or WhatsApp number already exists in waitlist'))
    except Exception as e:
        logger.error(f"{trans('general_waitlist_creation_error', default='Error creating waitlist entry')}: {str(e)}", exc_info=True)
        raise

def get_waitlist_entries(db, filter_kwargs):
    """
    Retrieve waitlist entries based on filter criteria.
    """
    try:
        return list(db.waitlist.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_waitlist_fetch_error', default='Error getting waitlist entries')}: {str(e)}", exc_info=True)
        raise

def to_dict_waitlist(record):
    """
    Convert waitlist record to dictionary.
    """
    if not record:
        return {'full_name': None, 'email': None}
    return {
        'id': str(record.get('_id', '')),
        'full_name': record.get('full_name', ''),
        'whatsapp_number': record.get('whatsapp_number', ''),
        'email': record.get('email', ''),
        'business_type': record.get('business_type', None),
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at')
    }
