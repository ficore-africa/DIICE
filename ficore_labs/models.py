

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
        
        Returns:
            bool: True if user is admin or trial/subscription is active, False otherwise
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
    
    Args:
        db: MongoDB database instance
        user_data: Dictionary containing user information
    
    Returns:
        User: Created user object
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
        
        logger.info(f"Created user with ID: {user_id} with 30-day trial", 
                   extra={'session_id': 'no-session-id'})
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
        logger.error(f"Error creating user: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise ValueError("User with this email or username already exists")

@lru_cache(maxsize=128)
def get_user_by_email(db, email):
    """
    Retrieve a user by email from the users collection.
    
    Args:
        db: MongoDB database instance
        email: Email address of the user
    
    Returns:
        User: User object or None if not found
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
        logger.error(f"{trans('general_user_fetch_error', default='Error getting user by email')} {email}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

@lru_cache(maxsize=128)
def get_user(db, user_id):
    """
    Retrieve a user by ID from the users collection.
    
    Args:
        db: MongoDB database instance
        user_id: ID of the user
    
    Returns:
        User: User object or None if not found
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
        logger.error(f"{trans('general_user_fetch_error', default='Error getting user by ID')} {user_id}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def update_user(db, user_id, update_data):
    """
    Update a user in the users collection.
    
    Args:
        db: MongoDB database instance
        user_id: The ID of the user to update
        update_data: Dictionary containing fields to update
    
    Returns:
        bool: True if updated, False if not found or no changes made
    """
    try:
        if 'password' in update_data:
            update_data['password_hash'] = generate_password_hash(update_data.pop('password'))
        result = db.users.update_one(
            {'_id': user_id},
            {'$set': update_data}
        )
        if result.modified_count > 0:
            logger.info(f"{trans('general_user_updated', default='Updated user with ID')}: {user_id}", 
                       extra={'session_id': 'no-session-id'})
            get_user.cache_clear()
            get_user_by_email.cache_clear()
            return True
        logger.info(f"{trans('general_user_no_change', default='No changes made to user with ID')}: {user_id}", 
                   extra={'session_id': 'no-session-id'})
        return False
    except Exception as e:
        logger.error(f"{trans('general_user_update_error', default='Error updating user with ID')} {user_id}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_records(db, filter_kwargs):
    """
    Retrieve records (debtors, creditors, inventory, etc.) based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of records
    """
    try:
        return list(db.records.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_records_fetch_error', default='Error getting records')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def create_record(db, record_data):
    """
    Create a new record in the records collection.
    
    Args:
        db: MongoDB database instance
        record_data: Dictionary containing record information
    
    Returns:
        str: ID of the created record
    """
    try:
        required_fields = ['user_id', 'type', 'created_at']
        if not all(field in record_data for field in required_fields):
            raise ValueError(trans('general_missing_record_fields', default='Missing required record fields'))
        result = db.records.insert_one(record_data)
        logger.info(f"{trans('general_record_created', default='Created record with ID')}: {result.inserted_id}", 
                   extra={'session_id': record_data.get('session_id', 'no-session-id')})
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_record_creation_error', default='Error creating record')}: {str(e)}", 
                    exc_info=True, extra={'session_id': record_data.get('session_id', 'no-session-id')})
        raise

def update_record(db, record_id, update_data):
    """
    Update a record in the records collection.
    
    Args:
        db: MongoDB database instance
        record_id: The ID of the record to update
        update_data: Dictionary containing fields to update
    
    Returns:
        bool: True if updated, False if not found or no changes made
    """
    try:
        update_data['updated_at'] = datetime.now(timezone.utc)
        result = db.records.update_one(
            {'_id': ObjectId(record_id)},
            {'$set': update_data}
        )
        if result.modified_count > 0:
            logger.info(f"{trans('general_record_updated', default='Updated record with ID')}: {record_id}", 
                       extra={'session_id': 'no-session-id'})
            return True
        logger.info(f"{trans('general_record_no_change', default='No changes made to record with ID')}: {record_id}", 
                   extra={'session_id': 'no-session-id'})
        return False
    except Exception as e:
        logger.error(f"{trans('general_record_update_error', default='Error updating record with ID')} {record_id}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_cashflows(db, filter_kwargs):
    """
    Retrieve cashflow records (receipts, payments) based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of cashflow records
    """
    try:
        return list(db.cashflows.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_cashflows_fetch_error', default='Error getting cashflows')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def create_cashflow(db, cashflow_data):
    """
    Create a new cashflow record in the cashflows collection.
    
    Args:
        db: MongoDB database instance
        cashflow_data: Dictionary containing cashflow information
    
    Returns:
        str: ID of the created cashflow record
    """
    try:
        required_fields = ['user_id', 'type', 'party_name', 'amount', 'created_at']
        if not all(field in cashflow_data for field in required_fields):
            raise ValueError(trans('general_missing_cashflow_fields', default='Missing required cashflow fields'))
        result = db.cashflows.insert_one(cashflow_data)
        logger.info(f"{trans('general_cashflow_created', default='Created cashflow record with ID')}: {result.inserted_id}", 
                   extra={'session_id': cashflow_data.get('session_id', 'no-session-id')})
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_cashflow_creation_error', default='Error creating cashflow record')}: {str(e)}", 
                    exc_info=True, extra={'session_id': cashflow_data.get('session_id', 'no-session-id')})
        raise

def update_cashflow(db, cashflow_id, update_data):
    """
    Update a cashflow record in the cashflows collection.
    
    Args:
        db: MongoDB database instance
        cashflow_id: The ID of the cashflow record to update
        update_data: Dictionary containing fields to update
    
    Returns:
        bool: True if updated, False if not found or no changes made
    """
    try:
        update_data['updated_at'] = datetime.now(timezone.utc)
        result = db.cashflows.update_one(
            {'_id': ObjectId(cashflow_id)},
            {'$set': update_data}
        )
        if result.modified_count > 0:
            logger.info(f"{trans('general_cashflow_updated', default='Updated cashflow record with ID')}: {cashflow_id}", 
                       extra={'session_id': 'no-session-id'})
            return True
        logger.info(f"{trans('general_cashflow_no_change', default='No changes made to cashflow record with ID')}: {cashflow_id}", 
                   extra={'session_id': 'no-session-id'})
        return False
    except Exception as e:
        logger.error(f"{trans('general_cashflow_update_error', default='Error updating cashflow record with ID')} {cashflow_id}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_audit_logs(db, filter_kwargs):
    """
    Retrieve audit log records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of audit log records
    """
    try:
        return list(db.audit_logs.find(filter_kwargs).sort('timestamp', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_audit_logs_fetch_error', default='Error getting audit logs')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def create_audit_log(db, audit_data):
    """
    Create a new audit log in the audit_logs collection.
    
    Args:
        db: MongoDB database instance
        audit_data: Dictionary containing audit log information
    
    Returns:
        str: ID of the created audit log
    """
    try:
        required_fields = ['admin_id', 'action', 'timestamp']
        if not all(field in audit_data for field in required_fields):
            raise ValueError(trans('general_missing_audit_fields', default='Missing required audit log fields'))
        result = db.audit_logs.insert_one(audit_data)
        logger.info(f"{trans('general_audit_log_created', default='Created audit log with ID')}: {result.inserted_id}", 
                   extra={'session_id': audit_data.get('session_id', 'no-session-id')})
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_audit_log_creation_error', default='Error creating audit log')}: {str(e)}", 
                    exc_info=True, extra={'session_id': audit_data.get('session_id', 'no-session-id')})
        raise

def create_feedback(db, feedback_data):
    """
    Create a new feedback entry in the feedback collection.
    
    Args:
        db: MongoDB database instance
        feedback_data: Dictionary containing feedback information
    
    Returns:
        str: ID of the created feedback entry
    """
    try:
        required_fields = ['tool_name', 'rating', 'timestamp']
        if not all(field in feedback_data for field in required_fields):
            raise ValueError(trans('general_missing_feedback_fields', default='Missing required feedback fields'))
        result = db.feedback.insert_one(feedback_data)
        logger.info(f"{trans('general_feedback_created', default='Created feedback with ID')}: {result.inserted_id}", 
                   extra={'session_id': feedback_data.get('session_id', 'no-session-id')})
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_feedback_creation_error', default='Error creating feedback')}: {str(e)}", 
                    exc_info=True, extra={'session_id': feedback_data.get('session_id', 'no-session-id')})
        raise

def get_feedback(db, filter_kwargs):
    """
    Retrieve feedback entries based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria (e.g., {'user_id': 'user123', 'tool_name': 'inventory'})
    
    Returns:
        list: List of feedback entries
    """
    try:
        return list(db.feedback.find(filter_kwargs).sort('timestamp', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_feedback_fetch_error', default='Error getting feedback')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def to_dict_feedback(record):
    """
    Convert feedback record to dictionary.
    
    Args:
        record: Feedback document
    
    Returns:
        dict: Feedback dictionary
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
    
    Args:
        user: User object
    
    Returns:
        dict: User dictionary
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

def to_dict_record(record):
    """
    Convert record to dictionary.
    
    Args:
        record: Record document
    
    Returns:
        dict: Record dictionary
    """
    if not record:
        return {'type': None}
    result = {
        'id': str(record.get('_id', '')),
        'user_id': record.get('user_id', ''),
        'type': record.get('type', ''),
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at')
    }
    if record['type'] in ['debtor', 'creditor']:
        result.update({
            'name': record.get('name', ''),
            'contact': record.get('contact', ''),
            'amount_owed': record.get('amount_owed', 0),
            'description': record.get('description', ''),
            'reminder_count': record.get('reminder_count', 0)
        })
    elif record['type'] == 'forecast':
        result.update({
            'title': record.get('title', ''),
            'projected_revenue': record.get('projected_revenue', 0),
            'projected_expenses': record.get('projected_expenses', 0),
            'forecast_date': record.get('forecast_date'),
            'description': record.get('description', '')
        })
    elif record['type'] == 'fund':
        result.update({
            'source': record.get('source', ''),
            'amount': record.get('amount', 0),
            'category': record.get('category', ''),
            'description': record.get('description', '')
        })
    elif record['type'] == 'investor_report':
        result.update({
            'title': record.get('title', ''),
            'report_date': record.get('report_date'),
            'summary': record.get('summary', ''),
            'financial_highlights': record.get('financial_highlights', '')
        })
    elif record['type'] == 'inventory':
        result.update({
            'name': record.get('name', ''),
            'cost': record.get('cost', 0),
            'expected_margin': record.get('expected_margin', 0)
        })
    return result

def to_dict_cashflow(record):
    """
    Convert cashflow record to dictionary.
    
    Args:
        record: Cashflow document
    
    Returns:
        dict: Cashflow dictionary
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
        'category': record.get('category', ''),
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at')
    }

def to_dict_audit_log(record):
    """
    Convert audit log record to dictionary.
    
    Args:
        record: Audit log document
    
    Returns:
        dict: Audit log dictionary
    """
    if not record:
        return {'action': None, 'timestamp': None}
    return {
        'id': str(record.get('_id', '')),
        'admin_id': record.get('admin_id', ''),
        'action': record.get('action', ''),
        'details': record.get('details', {}),
        'timestamp': record.get('timestamp')
    }

def create_kyc_record(db, kyc_data):
    """
    Create a new KYC record in the kyc_records collection.
    
    Args:
        db: MongoDB database instance
        kyc_data: Dictionary containing KYC information
    
    Returns:
        str: ID of the created KYC record
    """
    try:
        required_fields = ['user_id', 'full_name', 'id_type', 'id_number', 'uploaded_id_photo_url', 'status', 'created_at', 'updated_at']
        if not all(field in kyc_data for field in required_fields):
            raise ValueError(trans('general_missing_kyc_fields', default='Missing required KYC fields'))
        result = db.kyc_records.insert_one(kyc_data)
        logger.info(f"{trans('general_kyc_created', default='Created KYC record with ID')}: {result.inserted_id}", 
                   extra={'session_id': kyc_data.get('session_id', 'no-session-id')})
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_kyc_creation_error', default='Error creating KYC record')}: {str(e)}", 
                    exc_info=True, extra={'session_id': kyc_data.get('session_id', 'no-session-id')})
        raise

def update_kyc_record(db, kyc_id, update_data):
    """
    Update a KYC record in the kyc_records collection.
    
    Args:
        db: MongoDB database instance
        kyc_id: The ID of the KYC record to update
        update_data: Dictionary containing fields to update
    
    Returns:
        bool: True if updated, False if not found or no changes made
    """
    try:
        update_data['updated_at'] = datetime.now(timezone.utc)
        result = db.kyc_records.update_one(
            {'_id': ObjectId(kyc_id)},
            {'$set': update_data}
        )
        if result.modified_count > 0:
            logger.info(f"{trans('general_kyc_updated', default='Updated KYC record with ID')}: {kyc_id}", 
                       extra={'session_id': 'no-session-id'})
            return True
        logger.info(f"{trans('general_kyc_no_change', default='No changes made to KYC record with ID')}: {kyc_id}", 
                   extra={'session_id': 'no-session-id'})
        return False
    except Exception as e:
        logger.error(f"{trans('general_kyc_update_error', default='Error updating KYC record with ID')} {kyc_id}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_kyc_record(db, filter_kwargs):
    """
    Retrieve KYC records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria (e.g., {'user_id': 'user123'})
    
    Returns:
        list: List of KYC records
    """
    try:
        return list(db.kyc_records.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_kyc_fetch_error', default='Error getting KYC records')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def to_dict_kyc_record(record):
    """
    Convert KYC record to dictionary.
    
    Args:
        record: KYC document
    
    Returns:
        dict: KYC dictionary
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
    
    Args:
        db: MongoDB database instance
        waitlist_data: Dictionary containing waitlist information
    
    Returns:
        str: ID of the created waitlist entry
    """
    try:
        required_fields = ['full_name', 'whatsapp_number', 'email', 'created_at', 'updated_at']
        if not all(field in waitlist_data for field in required_fields):
            raise ValueError(trans('general_missing_waitlist_fields', default='Missing required waitlist fields'))
        result = db.waitlist.insert_one(waitlist_data)
        logger.info(f"{trans('general_waitlist_created', default='Created waitlist entry with ID')}: {result.inserted_id}", 
                   extra={'session_id': waitlist_data.get('session_id', 'no-session-id')})
        return str(result.inserted_id)
    except DuplicateKeyError:
        logger.error(f"Duplicate email or WhatsApp number in waitlist: {waitlist_data.get('email')}", 
                    exc_info=True, extra={'session_id': waitlist_data.get('session_id', 'no-session-id')})
        raise ValueError(trans('general_waitlist_duplicate_error', default='Email or WhatsApp number already exists in waitlist'))
    except Exception as e:
        logger.error(f"{trans('general_waitlist_creation_error', default='Error creating waitlist entry')}: {str(e)}", 
                    exc_info=True, extra={'session_id': waitlist_data.get('session_id', 'no-session-id')})
        raise

def get_waitlist_entries(db, filter_kwargs):
    """
    Retrieve waitlist entries based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria (e.g., {'email': 'user@example.com'})
    
    Returns:
        list: List of waitlist entries
    """
    try:
        return list(db.waitlist.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_waitlist_fetch_error', default='Error getting waitlist entries')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def to_dict_waitlist(record):
    """
    Convert waitlist record to dictionary.
    
    Args:
        record: Waitlist document
    
    Returns:
        dict: Waitlist dictionary
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
