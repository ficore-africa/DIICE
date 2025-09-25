"""
API Routes for Offline Functionality
Handles data synchronization, conflict resolution, and offline data management
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timezone
import hashlib
import json
from utils import get_mongo_db, logger
from bson import ObjectId

api_bp = Blueprint('api', __name__)

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for connectivity monitoring"""
    try:
        db = get_mongo_db()
        # Test database connection
        db.command('ping')
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'version': '2.0.0'
        }), 200
    except Exception as e:
        logger.error(f'Health check failed: {str(e)}')
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 503

@api_bp.route('/debtors/sync', methods=['POST', 'PUT'])
@login_required
def sync_debtors():
    """Sync debtors data with conflict resolution"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        db = get_mongo_db()
        collection = db.debtors
        
        # Validate data
        validation_result = validate_debtor_data(data)
        if not validation_result['valid']:
            return jsonify({
                'error': 'Validation failed',
                'details': validation_result['errors']
            }), 400
        
        # Check for conflicts
        existing_record = None
        if 'id' in data and data['id']:
            existing_record = collection.find_one({
                '_id': ObjectId(data['id']),
                'user_id': current_user.id
            })
        
        # Handle conflict detection
        if existing_record and request.method == 'PUT':
            client_timestamp = datetime.fromisoformat(data.get('clientTimestamp', '1970-01-01T00:00:00+00:00'))
            server_timestamp = existing_record.get('last_modified', datetime.min.replace(tzinfo=timezone.utc))
            
            if server_timestamp > client_timestamp:
                # Conflict detected
                return jsonify({
                    'conflict': True,
                    'serverData': serialize_document(existing_record),
                    'message': 'Data has been modified on server since last sync'
                }), 409
        
        # Prepare document for storage
        doc = {
            'user_id': current_user.id,
            'name': data['name'],
            'amount': float(data.get('amount', 0)),
            'phone': data.get('phone', ''),
            'email': data.get('email', ''),
            'address': data.get('address', ''),
            'notes': data.get('notes', ''),
            'last_modified': datetime.now(timezone.utc),
            'synced': True
        }
        
        if request.method == 'POST':
            # Create new record
            result = collection.insert_one(doc)
            doc['_id'] = result.inserted_id
            
            logger.info(f'Created new debtor: {doc["name"]}', 
                       extra={'user_id': current_user.id})
        else:
            # Update existing record
            doc['_id'] = ObjectId(data['id'])
            collection.replace_one(
                {'_id': ObjectId(data['id']), 'user_id': current_user.id},
                doc
            )
            
            logger.info(f'Updated debtor: {doc["name"]}', 
                       extra={'user_id': current_user.id})
        
        return jsonify({
            'success': True,
            'data': serialize_document(doc),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f'Debtor sync failed: {str(e)}', 
                    extra={'user_id': current_user.id if current_user.is_authenticated else None})
        return jsonify({'error': 'Sync failed', 'details': str(e)}), 500

@api_bp.route('/creditors/sync', methods=['POST', 'PUT'])
@login_required
def sync_creditors():
    """Sync creditors data with conflict resolution"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        db = get_mongo_db()
        collection = db.creditors
        
        # Validate data
        validation_result = validate_creditor_data(data)
        if not validation_result['valid']:
            return jsonify({
                'error': 'Validation failed',
                'details': validation_result['errors']
            }), 400
        
        # Check for conflicts
        existing_record = None
        if 'id' in data and data['id']:
            existing_record = collection.find_one({
                '_id': ObjectId(data['id']),
                'user_id': current_user.id
            })
        
        # Handle conflict detection
        if existing_record and request.method == 'PUT':
            client_timestamp = datetime.fromisoformat(data.get('clientTimestamp', '1970-01-01T00:00:00+00:00'))
            server_timestamp = existing_record.get('last_modified', datetime.min.replace(tzinfo=timezone.utc))
            
            if server_timestamp > client_timestamp:
                # Conflict detected
                return jsonify({
                    'conflict': True,
                    'serverData': serialize_document(existing_record),
                    'message': 'Data has been modified on server since last sync'
                }), 409
        
        # Prepare document for storage
        doc = {
            'user_id': current_user.id,
            'name': data['name'],
            'amount': float(data.get('amount', 0)),
            'phone': data.get('phone', ''),
            'email': data.get('email', ''),
            'address': data.get('address', ''),
            'notes': data.get('notes', ''),
            'last_modified': datetime.now(timezone.utc),
            'synced': True
        }
        
        if request.method == 'POST':
            # Create new record
            result = collection.insert_one(doc)
            doc['_id'] = result.inserted_id
            
            logger.info(f'Created new creditor: {doc["name"]}', 
                       extra={'user_id': current_user.id})
        else:
            # Update existing record
            doc['_id'] = ObjectId(data['id'])
            collection.replace_one(
                {'_id': ObjectId(data['id']), 'user_id': current_user.id},
                doc
            )
            
            logger.info(f'Updated creditor: {doc["name"]}', 
                       extra={'user_id': current_user.id})
        
        return jsonify({
            'success': True,
            'data': serialize_document(doc),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f'Creditor sync failed: {str(e)}', 
                    extra={'user_id': current_user.id if current_user.is_authenticated else None})
        return jsonify({'error': 'Sync failed', 'details': str(e)}), 500

@api_bp.route('/inventory/sync', methods=['POST', 'PUT'])
@login_required
def sync_inventory():
    """Sync inventory data with conflict resolution"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        db = get_mongo_db()
        collection = db.inventory
        
        # Validate data
        validation_result = validate_inventory_data(data)
        if not validation_result['valid']:
            return jsonify({
                'error': 'Validation failed',
                'details': validation_result['errors']
            }), 400
        
        # Check for conflicts
        existing_record = None
        if 'id' in data and data['id']:
            existing_record = collection.find_one({
                '_id': ObjectId(data['id']),
                'user_id': current_user.id
            })
        
        # Handle conflict detection
        if existing_record and request.method == 'PUT':
            client_timestamp = datetime.fromisoformat(data.get('clientTimestamp', '1970-01-01T00:00:00+00:00'))
            server_timestamp = existing_record.get('last_modified', datetime.min.replace(tzinfo=timezone.utc))
            
            if server_timestamp > client_timestamp:
                # Conflict detected
                return jsonify({
                    'conflict': True,
                    'serverData': serialize_document(existing_record),
                    'message': 'Data has been modified on server since last sync'
                }), 409
        
        # Prepare document for storage
        doc = {
            'user_id': current_user.id,
            'name': data['name'],
            'quantity': int(data.get('quantity', 0)),
            'price': float(data.get('price', 0)),
            'category': data.get('category', ''),
            'description': data.get('description', ''),
            'sku': data.get('sku', ''),
            'last_modified': datetime.now(timezone.utc),
            'synced': True
        }
        
        if request.method == 'POST':
            # Create new record
            result = collection.insert_one(doc)
            doc['_id'] = result.inserted_id
            
            logger.info(f'Created new inventory item: {doc["name"]}', 
                       extra={'user_id': current_user.id})
        else:
            # Update existing record
            doc['_id'] = ObjectId(data['id'])
            collection.replace_one(
                {'_id': ObjectId(data['id']), 'user_id': current_user.id},
                doc
            )
            
            logger.info(f'Updated inventory item: {doc["name"]}', 
                       extra={'user_id': current_user.id})
        
        return jsonify({
            'success': True,
            'data': serialize_document(doc),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f'Inventory sync failed: {str(e)}', 
                    extra={'user_id': current_user.id if current_user.is_authenticated else None})
        return jsonify({'error': 'Sync failed', 'details': str(e)}), 500

@api_bp.route('/transactions/sync', methods=['POST', 'PUT'])
@login_required
def sync_transactions():
    """Sync transaction data with conflict resolution"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        db = get_mongo_db()
        collection = db.transactions
        
        # Validate data
        validation_result = validate_transaction_data(data)
        if not validation_result['valid']:
            return jsonify({
                'error': 'Validation failed',
                'details': validation_result['errors']
            }), 400
        
        # Check for conflicts
        existing_record = None
        if 'id' in data and data['id']:
            existing_record = collection.find_one({
                '_id': ObjectId(data['id']),
                'user_id': current_user.id
            })
        
        # Handle conflict detection
        if existing_record and request.method == 'PUT':
            client_timestamp = datetime.fromisoformat(data.get('clientTimestamp', '1970-01-01T00:00:00+00:00'))
            server_timestamp = existing_record.get('last_modified', datetime.min.replace(tzinfo=timezone.utc))
            
            if server_timestamp > client_timestamp:
                # Conflict detected
                return jsonify({
                    'conflict': True,
                    'serverData': serialize_document(existing_record),
                    'message': 'Data has been modified on server since last sync'
                }), 409
        
        # Prepare document for storage
        doc = {
            'user_id': current_user.id,
            'type': data['type'],
            'amount': float(data['amount']),
            'description': data['description'],
            'category': data.get('category', ''),
            'date': datetime.fromisoformat(data.get('date', datetime.now(timezone.utc).isoformat())),
            'last_modified': datetime.now(timezone.utc),
            'synced': True
        }
        
        if request.method == 'POST':
            # Create new record
            result = collection.insert_one(doc)
            doc['_id'] = result.inserted_id
            
            logger.info(f'Created new transaction: {doc["type"]} - {doc["amount"]}', 
                       extra={'user_id': current_user.id})
        else:
            # Update existing record
            doc['_id'] = ObjectId(data['id'])
            collection.replace_one(
                {'_id': ObjectId(data['id']), 'user_id': current_user.id},
                doc
            )
            
            logger.info(f'Updated transaction: {doc["type"]} - {doc["amount"]}', 
                       extra={'user_id': current_user.id})
        
        return jsonify({
            'success': True,
            'data': serialize_document(doc),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f'Transaction sync failed: {str(e)}', 
                    extra={'user_id': current_user.id if current_user.is_authenticated else None})
        return jsonify({'error': 'Sync failed', 'details': str(e)}), 500

@api_bp.route('/<collection_name>/checksum', methods=['POST'])
@login_required
def verify_data_integrity(collection_name):
    """Verify data integrity between client and server"""
    try:
        data = request.get_json()
        local_checksum = data.get('localChecksum')
        
        if not local_checksum:
            return jsonify({'error': 'Local checksum required'}), 400
        
        # Get server data
        db = get_mongo_db()
        collection = getattr(db, collection_name)
        server_data = list(collection.find({'user_id': current_user.id}))
        
        # Calculate server checksum
        server_checksum = calculate_checksum(server_data)
        
        return jsonify({
            'match': local_checksum == server_checksum,
            'serverChecksum': server_checksum,
            'localChecksum': local_checksum,
            'recordCount': len(server_data)
        }), 200
        
    except Exception as e:
        logger.error(f'Data integrity check failed: {str(e)}', 
                    extra={'user_id': current_user.id if current_user.is_authenticated else None})
        return jsonify({'error': 'Integrity check failed', 'details': str(e)}), 500

# Validation functions
def validate_debtor_data(data):
    """Validate debtor data"""
    errors = []
    
    if not data.get('name') or not data['name'].strip():
        errors.append('Name is required')
    
    if 'amount' in data:
        try:
            amount = float(data['amount'])
            if amount < 0:
                errors.append('Amount must be positive')
        except (ValueError, TypeError):
            errors.append('Amount must be a valid number')
    
    if 'phone' in data and data['phone']:
        import re
        if not re.match(r'^\+?[\d\s\-\(\)]+$', data['phone']):
            errors.append('Invalid phone number format')
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }

def validate_creditor_data(data):
    """Validate creditor data (same as debtor)"""
    return validate_debtor_data(data)

def validate_inventory_data(data):
    """Validate inventory data"""
    errors = []
    
    if not data.get('name') or not data['name'].strip():
        errors.append('Item name is required')
    
    if 'quantity' in data:
        try:
            quantity = int(data['quantity'])
            if quantity < 0:
                errors.append('Quantity must be positive')
        except (ValueError, TypeError):
            errors.append('Quantity must be a valid number')
    
    if 'price' in data:
        try:
            price = float(data['price'])
            if price < 0:
                errors.append('Price must be positive')
        except (ValueError, TypeError):
            errors.append('Price must be a valid number')
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }

def validate_transaction_data(data):
    """Validate transaction data"""
    errors = []
    
    if not data.get('type') or data['type'] not in ['income', 'expense']:
        errors.append('Transaction type must be income or expense')
    
    if not data.get('amount'):
        errors.append('Amount is required')
    else:
        try:
            amount = float(data['amount'])
            if amount <= 0:
                errors.append('Amount must be positive')
        except (ValueError, TypeError):
            errors.append('Amount must be a valid number')
    
    if not data.get('description') or not data['description'].strip():
        errors.append('Description is required')
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }

# Utility functions
def serialize_document(doc):
    """Convert MongoDB document to JSON-serializable format"""
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == '_id':
                result['id'] = str(value)
            elif isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result
    return doc

def calculate_checksum(data):
    """Calculate checksum for data integrity verification"""
    # Sort data by ID for consistent checksum
    sorted_data = sorted(data, key=lambda x: str(x.get('_id', '')))
    
    # Create string representation
    data_str = json.dumps(sorted_data, default=str, sort_keys=True)
    
    # Calculate hash
    return hashlib.md5(data_str.encode()).hexdigest()