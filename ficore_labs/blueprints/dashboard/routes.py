from flask import Blueprint, render_template, flash, session, jsonify, request
from datetime import timedelta, datetime, timezone
from flask_login import login_required, current_user
from zoneinfo import ZoneInfo
from bson import ObjectId
import logging
from translations import trans
import utils
from utils import format_date
from helpers import reminders

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/test-notifications')
@login_required
def test_notifications():
    """Test route to verify notifications work - remove in production"""
    return render_template('dashboard/index.html', 
                         inventory_loss=True,
                         unpaid_debtors=[{'name': 'Test Debtor', 'amount': 1000}],
                         unpaid_creditors=[{'name': 'Test Creditor', 'amount': 500}],
                         stats={}, 
                         recent_creditors=[], 
                         recent_debtors=[], 
                         recent_payments=[], 
                         recent_receipts=[], 
                         recent_funds=[], 
                         recent_inventory=[],
                         can_interact=True,
                         show_daily_log_reminder=False,
                         streak=0,
                         tax_prep_mode=False)

# API endpoint for weekly profit data (for dashboard chart)
@dashboard_bp.route('/weekly_profit_data')
@login_required
def weekly_profit_data():
    try:
        db = utils.get_mongo_db()
        user_id = str(current_user.id)
        today = datetime.now(timezone.utc)
        # Get last 7 days
        days = [(today - timedelta(days=i)).date() for i in range(6, -1, -1)]
        profit_per_day = []
        
        for day in days:
            start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            end = start + timedelta(days=1)
            
            try:
                # Sum receipts (income) for the day
                receipts = db.cashflows.aggregate([
                    {'$match': {'user_id': user_id, 'type': 'receipt', 'created_at': {'$gte': start, '$lt': end}}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                ])
                receipts_total = next(receipts, {}).get('total', 0) or 0
                
                # Sum payments (expenses) for the day
                payments = db.cashflows.aggregate([
                    {'$match': {'user_id': user_id, 'type': 'payment', 'created_at': {'$gte': start, '$lt': end}}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                ])
                payments_total = next(payments, {}).get('total', 0) or 0
                
                profit = receipts_total - payments_total
                profit_per_day.append({
                    'date': day.strftime('%a'),
                    'profit': profit,
                    'receipts': receipts_total,
                    'payments': payments_total
                })
            except Exception as day_error:
                logger.warning(f"Error calculating profit for {day}: {str(day_error)}")
                profit_per_day.append({
                    'date': day.strftime('%a'),
                    'profit': 0,
                    'receipts': 0,
                    'payments': 0
                })
        
        return jsonify({'data': profit_per_day, 'success': True})
    except Exception as e:
        logger.error(f"Error generating weekly profit data: {str(e)}")
        return jsonify({'error': 'Failed to generate profit data', 'success': False}), 500

# API endpoint for real-time dashboard data refresh
@dashboard_bp.route('/api/refresh_data')
@login_required
def refresh_dashboard_data():
    """API endpoint to refresh dashboard data without full page reload."""
    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id)}
        
        # Get fresh statistics
        stats = {}
        try:
            # Use aggregation for better performance
            receipts_result = db.cashflows.aggregate([
                {'$match': {**query, 'type': 'receipt'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
            ])
            receipts_data = next(receipts_result, {})
            stats['total_receipts'] = receipts_data.get('count', 0)
            stats['total_receipts_amount'] = receipts_data.get('total_amount', 0)
            
            payments_result = db.cashflows.aggregate([
                {'$match': {**query, 'type': 'payment'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
            ])
            payments_data = next(payments_result, {})
            stats['total_payments'] = payments_data.get('count', 0)
            stats['total_payments_amount'] = payments_data.get('total_amount', 0)
            
            debtors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'debtor'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount_owed'}, 'count': {'$sum': 1}}}
            ])
            debtors_data = next(debtors_result, {})
            stats['total_debtors'] = debtors_data.get('count', 0)
            stats['total_debtors_amount'] = debtors_data.get('total_amount', 0)
            
            creditors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'creditor'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount_owed'}, 'count': {'$sum': 1}}}
            ])
            creditors_data = next(creditors_result, {})
            stats['total_creditors'] = creditors_data.get('count', 0)
            stats['total_creditors_amount'] = creditors_data.get('total_amount', 0)
            
            inventory_result = db.records.aggregate([
                {'$match': {**query, 'type': 'inventory'}},
                {'$group': {'_id': None, 'total_cost': {'$sum': '$cost'}, 'count': {'$sum': 1}}}
            ])
            inventory_data = next(inventory_result, {})
            stats['total_inventory'] = inventory_data.get('count', 0)
            stats['total_inventory_cost'] = inventory_data.get('total_cost', 0)
            
            # Calculate profit
            stats['gross_profit'] = stats['total_receipts_amount'] - stats['total_payments_amount']
            stats['true_profit'] = stats['gross_profit'] - stats['total_inventory_cost']
            
        except Exception as stats_error:
            logger.error(f"Error calculating refresh stats: {str(stats_error)}")
            return jsonify({'error': 'Failed to calculate statistics', 'success': False}), 500
        
        # Format currency values for display
        formatted_stats = {}
        for key, value in stats.items():
            if 'amount' in key or 'cost' in key or 'profit' in key:
                formatted_stats[key] = utils.format_currency(value)
                formatted_stats[f"{key}_raw"] = value
            else:
                formatted_stats[key] = value
        
        return jsonify({
            'stats': formatted_stats,
            'success': True,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error refreshing dashboard data: {str(e)}")
        return jsonify({'error': 'Failed to refresh data', 'success': False}), 500

@dashboard_bp.route('/')
@login_required
def index():
    """Display the user's dashboard with recent activity and role-specific content."""
    # Initialize data containers with defaults
    recent_creditors = []
    recent_debtors = []
    recent_payments = []
    recent_receipts = []
    recent_funds = []
    recent_inventory = []
    stats = {
        'total_debtors': 0,
        'total_creditors': 0,
        'total_payments': 0,
        'total_receipts': 0,
        'total_funds': 0,
        'total_debtors_amount': 0,
        'total_creditors_amount': 0,
        'total_payments_amount': 0,
        'total_receipts_amount': 0,
        'total_funds_amount': 0,
        'total_forecasts': 0,
        'total_forecasts_amount': 0,
        'total_inventory': 0,
        'total_inventory_cost': 0
    }
    can_interact = False
    show_daily_log_reminder = False
    streak = 0
    unpaid_debtors = []
    unpaid_creditors = []
    inventory_loss = False

    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id)}
        tax_prep_mode = request.args.get('tax_prep') == '1'

        # Fetch reminders and streak data
        try:
            show_daily_log_reminder = reminders.needs_daily_log_reminder(db, current_user.id)
            rewards_data = db.rewards.find_one({'user_id': str(current_user.id)})
            streak = rewards_data.get('streak', 0) if rewards_data else 0
            unpaid_debtors, unpaid_creditors = reminders.get_unpaid_debts_credits(db, current_user.id)
            inventory_loss = reminders.detect_inventory_loss(db, current_user.id)
            logger.debug(f"Calculated streak: {streak} for user_id: {current_user.id}")
        except Exception as e:
            logger.warning(f"Failed to calculate reminders or streak: {str(e)}", 
                          extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            streak = 0
            flash(trans('reminder_load_error', default='Unable to load reminders or streak data.'), 'warning')

        # Fetch recent data with enhanced error handling and fallbacks
        try:
            # Handle tax prep mode calculations with proper error handling
            if tax_prep_mode:
                try:
                    # Calculate true profit: Total Income - (Expenses + Inventory Cost)
                    # Get total income from receipts (cashflows)
                    income_result = db.cashflows.aggregate([
                        {'$match': {**query, 'type': 'receipt'}},
                        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                    ])
                    total_income = next(income_result, {}).get('total', 0) or 0
                    
                    # Get total expenses from payments (cashflows)
                    expenses_result = db.cashflows.aggregate([
                        {'$match': {**query, 'type': 'payment'}},
                        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                    ])
                    total_expenses = next(expenses_result, {}).get('total', 0) or 0
                    
                    # Get total inventory cost
                    inventory_result = db.records.aggregate([
                        {'$match': {**query, 'type': 'inventory'}},
                        {'$group': {'_id': None, 'total': {'$sum': '$cost'}}}
                    ])
                    total_inventory_cost = next(inventory_result, {}).get('total', 0) or 0
                    
                    # Calculate true profit
                    stats['profit_only'] = total_income - (total_expenses + total_inventory_cost)
                    stats['total_receipts'] = stats['total_payments'] = stats['total_funds'] = 0
                    stats['total_receipts_amount'] = stats['total_payments_amount'] = stats['total_funds_amount'] = 0
                except Exception as tax_error:
                    logger.error(f"Error calculating tax prep mode data: {str(tax_error)}", 
                               extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                    stats['profit_only'] = 0
            
            # Fetch recent data with individual error handling for each data type
            try:
                recent_creditors = list(db.records.find({**query, 'type': 'creditor'}).sort('created_at', -1).limit(5))
            except Exception as e:
                logger.warning(f"Error fetching recent creditors: {str(e)}", 
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                recent_creditors = []
            
            try:
                recent_debtors = list(db.records.find({**query, 'type': 'debtor'}).sort('created_at', -1).limit(5))
            except Exception as e:
                logger.warning(f"Error fetching recent debtors: {str(e)}", 
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                recent_debtors = []
            
            try:
                recent_payments = utils.safe_find_cashflows(db, {**query, 'type': 'payment'}, 'created_at', -1)[:5]
                if not recent_payments:
                    # Fallback: try direct query if safe_find returns empty
                    fallback_payments = list(db.cashflows.find({**query, 'type': 'payment'}).sort('created_at', -1).limit(5))
                    recent_payments = []
                    for payment in fallback_payments:
                        try:
                            cleaned_payment = utils.clean_cashflow_record(payment)
                            if cleaned_payment:
                                recent_payments.append(cleaned_payment)
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"Error fetching recent payments: {str(e)}", 
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                recent_payments = []
            
            try:
                recent_receipts = utils.safe_find_cashflows(db, {**query, 'type': 'receipt'}, 'created_at', -1)[:5]
                if not recent_receipts:
                    # Fallback: try direct query if safe_find returns empty
                    fallback_receipts = list(db.cashflows.find({**query, 'type': 'receipt'}).sort('created_at', -1).limit(5))
                    recent_receipts = []
                    for receipt in fallback_receipts:
                        try:
                            cleaned_receipt = utils.clean_cashflow_record(receipt)
                            if cleaned_receipt:
                                recent_receipts.append(cleaned_receipt)
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"Error fetching recent receipts: {str(e)}", 
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                recent_receipts = []
            
            try:
                recent_funds = list(db.records.find({**query, 'type': 'fund'}).sort('created_at', -1).limit(5))
            except Exception as e:
                logger.warning(f"Error fetching recent funds: {str(e)}", 
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                recent_funds = []
            
            try:
                recent_inventory = list(db.records.find({**query, 'type': 'inventory'}).sort('created_at', -1).limit(5))
            except Exception as e:
                logger.warning(f"Error fetching recent inventory: {str(e)}", 
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                recent_inventory = []
                
        except Exception as e:
            logger.error(f"Critical error querying MongoDB for dashboard data: {str(e)}", 
                        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            flash(trans('dashboard_load_error', default='Failed to load some dashboard data. Displaying available information.'), 'warning')
            # Ensure all variables are initialized even on error
            recent_creditors = recent_debtors = recent_payments = recent_receipts = recent_funds = recent_inventory = []

        # Sanitize and convert datetimes
        for item in recent_creditors + recent_debtors:
            try:
                if item.get('created_at') and item['created_at'].tzinfo is None:
                    item['created_at'] = item['created_at'].replace(tzinfo=ZoneInfo("UTC"))
                if item.get('reminder_date') and item['reminder_date'].tzinfo is None:
                    item['reminder_date'] = item['reminder_date'].replace(tzinfo=ZoneInfo("UTC"))
                item['name'] = utils.sanitize_input(item.get('name', ''), max_length=100)
                item['description'] = utils.sanitize_input(item.get('description', 'No description provided'), max_length=500)
                item['contact'] = utils.sanitize_input(item.get('contact', 'N/A'), max_length=50)
                # Ensure ObjectId is converted to string to prevent JSON serialization errors
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Convert datetime objects to ISO strings for JSON serialization
                if 'created_at' in item and item['created_at']:
                    item['created_at'] = item['created_at'].isoformat() if hasattr(item['created_at'], 'isoformat') else str(item['created_at'])
                if 'updated_at' in item and item['updated_at']:
                    item['updated_at'] = item['updated_at'].isoformat() if hasattr(item['updated_at'], 'isoformat') else str(item['updated_at'])
                if 'reminder_date' in item and item['reminder_date']:
                    item['reminder_date'] = item['reminder_date'].isoformat() if hasattr(item['reminder_date'], 'isoformat') else str(item['reminder_date'])
            except Exception as e:
                logger.warning(f"Error processing creditor/debtor item {item.get('_id', 'unknown')}: {str(e)}")
                # Ensure _id is string even on error
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Ensure datetime fields are strings even on error
                for date_field in ['created_at', 'updated_at', 'reminder_date']:
                    if date_field in item and item[date_field]:
                        item[date_field] = str(item[date_field])
                continue

        # Process payments with enhanced field mapping
        for item in recent_payments:
            try:
                if item.get('created_at') and item['created_at'].tzinfo is None:
                    item['created_at'] = item['created_at'].replace(tzinfo=ZoneInfo("UTC"))
                item['description'] = utils.sanitize_input(item.get('description', 'No description provided'), max_length=500)
                # Ensure ObjectId is converted to string to prevent JSON serialization errors
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Convert datetime objects to ISO strings for JSON serialization
                if 'created_at' in item and item['created_at']:
                    item['created_at'] = item['created_at'].isoformat() if hasattr(item['created_at'], 'isoformat') else str(item['created_at'])
                if 'updated_at' in item and item['updated_at']:
                    item['updated_at'] = item['updated_at'].isoformat() if hasattr(item['updated_at'], 'isoformat') else str(item['updated_at'])
                # Map party_name to recipient for payments
                item['recipient'] = utils.sanitize_input(item.get('party_name', 'N/A'), max_length=100)
                # Ensure amount is properly formatted
                item['amount'] = float(item.get('amount', 0))
                # Add category information for display
                if item.get('expense_category'):
                    category_metadata = utils.get_category_metadata(item['expense_category'])
                    item['category_display'] = category_metadata.get('name', item['expense_category'])
                else:
                    item['category_display'] = 'No category'
            except Exception as e:
                logger.warning(f"Error processing payment item {item.get('_id', 'unknown')}: {str(e)}")
                # Ensure _id is string even on error
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Ensure datetime fields are strings even on error
                for date_field in ['created_at', 'updated_at']:
                    if date_field in item and item[date_field]:
                        item[date_field] = str(item[date_field])
                continue
        
        # Process receipts with enhanced field mapping
        for item in recent_receipts:
            try:
                if item.get('created_at') and item['created_at'].tzinfo is None:
                    item['created_at'] = item['created_at'].replace(tzinfo=ZoneInfo("UTC"))
                item['description'] = utils.sanitize_input(item.get('description', 'No description provided'), max_length=500)
                # Ensure ObjectId is converted to string to prevent JSON serialization errors
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Convert datetime objects to ISO strings for JSON serialization
                if 'created_at' in item and item['created_at']:
                    item['created_at'] = item['created_at'].isoformat() if hasattr(item['created_at'], 'isoformat') else str(item['created_at'])
                if 'updated_at' in item and item['updated_at']:
                    item['updated_at'] = item['updated_at'].isoformat() if hasattr(item['updated_at'], 'isoformat') else str(item['updated_at'])
                # Map party_name to payer for receipts
                item['payer'] = utils.sanitize_input(item.get('party_name', 'N/A'), max_length=100)
                # Ensure amount is properly formatted
                item['amount'] = float(item.get('amount', 0))
                # Add category information for display
                item['category_display'] = utils.sanitize_input(item.get('category', 'No category'), max_length=50)
            except Exception as e:
                logger.warning(f"Error processing receipt item {item.get('_id', 'unknown')}: {str(e)}")
                # Ensure _id is string even on error
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Ensure datetime fields are strings even on error
                for date_field in ['created_at', 'updated_at']:
                    if date_field in item and item[date_field]:
                        item[date_field] = str(item[date_field])
                continue

        for item in recent_funds:
            try:
                if item.get('created_at') and item['created_at'].tzinfo is None:
                    item['created_at'] = item['created_at'].replace(tzinfo=ZoneInfo("UTC"))
                item['name'] = utils.sanitize_input(item.get('source', ''), max_length=100)
                item['description'] = utils.sanitize_input(item.get('description', 'No description provided'), max_length=500)
                # Ensure ObjectId is converted to string to prevent JSON serialization errors
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Convert datetime objects to ISO strings for JSON serialization
                if 'created_at' in item and item['created_at']:
                    item['created_at'] = item['created_at'].isoformat() if hasattr(item['created_at'], 'isoformat') else str(item['created_at'])
                if 'updated_at' in item and item['updated_at']:
                    item['updated_at'] = item['updated_at'].isoformat() if hasattr(item['updated_at'], 'isoformat') else str(item['updated_at'])
            except Exception as e:
                logger.warning(f"Error processing fund item {item.get('_id', 'unknown')}: {str(e)}")
                # Ensure _id is string even on error
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Ensure datetime fields are strings even on error
                for date_field in ['created_at', 'updated_at']:
                    if date_field in item and item[date_field]:
                        item[date_field] = str(item[date_field])
                continue

        for item in recent_inventory:
            try:
                if item.get('created_at') and item['created_at'].tzinfo is None:
                    item['created_at'] = item['created_at'].replace(tzinfo=ZoneInfo("UTC"))
                item['name'] = utils.sanitize_input(item.get('name', ''), max_length=100)
                item['cost'] = float(item.get('cost', 0))
                item['expected_margin'] = float(item.get('expected_margin', 0))
                # Ensure ObjectId is converted to string to prevent JSON serialization errors
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Convert datetime objects to ISO strings for JSON serialization
                if 'created_at' in item and item['created_at']:
                    item['created_at'] = item['created_at'].isoformat() if hasattr(item['created_at'], 'isoformat') else str(item['created_at'])
                if 'updated_at' in item and item['updated_at']:
                    item['updated_at'] = item['updated_at'].isoformat() if hasattr(item['updated_at'], 'isoformat') else str(item['updated_at'])
            except Exception as e:
                logger.warning(f"Error processing inventory item {item.get('_id', 'unknown')}: {str(e)}")
                # Ensure _id is string even on error
                if '_id' in item:
                    item['_id'] = str(item['_id'])
                # Ensure datetime fields are strings even on error
                for date_field in ['created_at', 'updated_at']:
                    if date_field in item and item[date_field]:
                        item[date_field] = str(item[date_field])
                continue

        # Calculate stats with enhanced error handling and fallbacks
        try:
            # Calculate counts with individual error handling
            try:
                total_debtors = db.records.count_documents({**query, 'type': 'debtor'})
            except Exception:
                total_debtors = len(recent_debtors)
                
            try:
                total_creditors = db.records.count_documents({**query, 'type': 'creditor'})
            except Exception:
                total_creditors = len(recent_creditors)
                
            try:
                total_payments = db.cashflows.count_documents({**query, 'type': 'payment'})
            except Exception:
                total_payments = len(recent_payments)
                
            try:
                total_receipts = db.cashflows.count_documents({**query, 'type': 'receipt'})
            except Exception:
                total_receipts = len(recent_receipts)
                
            try:
                total_funds = db.records.count_documents({**query, 'type': 'fund'})
            except Exception:
                total_funds = len(recent_funds)
                
            try:
                total_inventory = db.records.count_documents({**query, 'type': 'inventory'})
            except Exception:
                total_inventory = len(recent_inventory)
                
            try:
                total_forecasts = db.records.count_documents({**query, 'type': 'forecast'})
            except Exception:
                total_forecasts = 0
            
            # Calculate amounts with enhanced error handling
            try:
                total_debtors_amount = sum(doc.get('amount_owed', 0) for doc in db.records.find({**query, 'type': 'debtor'}))
            except Exception:
                total_debtors_amount = sum(item.get('amount_owed', 0) for item in recent_debtors)
                
            try:
                total_creditors_amount = sum(doc.get('amount_owed', 0) for doc in db.records.find({**query, 'type': 'creditor'}))
            except Exception:
                total_creditors_amount = sum(item.get('amount_owed', 0) for item in recent_creditors)
                
            try:
                # Use safe_find_cashflows with fallback
                all_payments = utils.safe_find_cashflows(db, {**query, 'type': 'payment'})
                if not all_payments:
                    # Fallback to aggregation
                    payment_result = db.cashflows.aggregate([
                        {'$match': {**query, 'type': 'payment'}},
                        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                    ])
                    total_payments_amount = next(payment_result, {}).get('total', 0) or 0
                else:
                    total_payments_amount = sum(doc.get('amount', 0) for doc in all_payments)
            except Exception:
                total_payments_amount = sum(item.get('amount', 0) for item in recent_payments)
                
            try:
                # Use safe_find_cashflows with fallback
                all_receipts = utils.safe_find_cashflows(db, {**query, 'type': 'receipt'})
                if not all_receipts:
                    # Fallback to aggregation
                    receipt_result = db.cashflows.aggregate([
                        {'$match': {**query, 'type': 'receipt'}},
                        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                    ])
                    total_receipts_amount = next(receipt_result, {}).get('total', 0) or 0
                else:
                    total_receipts_amount = sum(doc.get('amount', 0) for doc in all_receipts)
            except Exception:
                total_receipts_amount = sum(item.get('amount', 0) for item in recent_receipts)
                
            try:
                total_funds_amount = sum(doc.get('amount', 0) for doc in db.records.find({**query, 'type': 'fund'}))
            except Exception:
                total_funds_amount = sum(item.get('amount', 0) for item in recent_funds)
                
            try:
                total_forecasts_amount = sum(doc.get('projected_revenue', 0) for doc in db.records.find({**query, 'type': 'forecast'}))
            except Exception:
                total_forecasts_amount = 0
                
            try:
                total_inventory_cost = sum(doc.get('cost', 0) for doc in db.records.find({**query, 'type': 'inventory'}))
            except Exception:
                total_inventory_cost = sum(item.get('cost', 0) for item in recent_inventory)
            
            # Update stats dictionary
            stats.update({
                'total_debtors': total_debtors,
                'total_creditors': total_creditors,
                'total_payments': total_payments,
                'total_receipts': total_receipts,
                'total_funds': total_funds,
                'total_debtors_amount': total_debtors_amount,
                'total_creditors_amount': total_creditors_amount,
                'total_payments_amount': total_payments_amount,
                'total_receipts_amount': total_receipts_amount,
                'total_funds_amount': total_funds_amount,
                'total_forecasts': total_forecasts,
                'total_forecasts_amount': total_forecasts_amount,
                'total_inventory': total_inventory,
                'total_inventory_cost': total_inventory_cost
            })
            
        except Exception as e:
            logger.error(f"Error calculating stats for dashboard: {str(e)}", 
                        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            flash(trans('dashboard_stats_error', default='Unable to calculate dashboard statistics. Displaying defaults.'), 'warning')
            # Ensure stats has safe defaults
            stats.update({
                'total_debtors': len(recent_debtors),
                'total_creditors': len(recent_creditors),
                'total_payments': len(recent_payments),
                'total_receipts': len(recent_receipts),
                'total_funds': len(recent_funds),
                'total_debtors_amount': 0,
                'total_creditors_amount': 0,
                'total_payments_amount': 0,
                'total_receipts_amount': 0,
                'total_funds_amount': 0,
                'total_forecasts': 0,
                'total_forecasts_amount': 0,
                'total_inventory': len(recent_inventory),
                'total_inventory_cost': 0
            })

        # Check subscription status
        try:
            can_interact = utils.can_user_interact(current_user)
        except Exception as e:
            logger.error(f"Error checking user interaction status: {str(e)}", 
                        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            flash(trans('interaction_check_error', default='Unable to verify interaction status.'), 'warning')

        # Render dashboard with all required variables
        return render_template(
            'dashboard/index.html',
            recent_creditors=recent_creditors,
            recent_debtors=recent_debtors,
            recent_payments=recent_payments,
            recent_receipts=recent_receipts,
            recent_funds=recent_funds,
            recent_inventory=recent_inventory,
            stats=stats,
            can_interact=can_interact,
            show_daily_log_reminder=show_daily_log_reminder,
            streak=streak,
            unpaid_debtors=unpaid_debtors,
            unpaid_creditors=unpaid_creditors,
            tax_prep_mode=tax_prep_mode,
            inventory_loss=inventory_loss
        )

    except Exception as e:
        logger.critical(f"Critical error in dashboard route: {str(e)}", 
                       extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('dashboard_critical_error', default='An error occurred while loading the dashboard. Please try again later.'), 'danger')
        return render_template(
            'dashboard/index.html',
            recent_creditors=[],
            recent_debtors=[],
            recent_payments=[],
            recent_receipts=[],
            recent_funds=[],
            recent_inventory=[],
            stats=stats,
            can_interact=False,
            show_daily_log_reminder=False,
            streak=0,
            unpaid_debtors=[],
            unpaid_creditors=[],
            tax_prep_mode=False,
            inventory_loss=False
        )
