from flask import Blueprint, render_template, flash, session, jsonify, request
from datetime import timedelta, datetime, timezone
from flask_login import login_required, current_user
from zoneinfo import ZoneInfo
from bson import ObjectId
import logging
from translations import trans
import utils
from utils import format_date, serialize_for_json, safe_json_response, clean_document_for_json, bulk_clean_documents_for_json, create_dashboard_safe_response, safe_parse_datetime
from helpers import reminders
from models import get_records

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

def normalize_datetime(doc):
    """Convert created_at to timezone-aware datetime if it's a string or naive datetime."""
    if 'created_at' in doc:
        doc['created_at'] = safe_parse_datetime(doc['created_at'])
    return doc

@dashboard_bp.route('/test-notifications')
@login_required
def test_notifications():
    """Test route to verify notifications work - intended for development, remove in production."""
    return render_template(
        'dashboard/index.html',
        inventory_loss=True,
        unpaid_debtors=[{'name': 'Test Debtor', 'amount': 1000}],
        unpaid_creditors=[{'name': 'Test Creditor', 'amount': 500}],
        stats={},
        can_interact=True,
        show_daily_log_reminder=False,
        streak=0,
        tax_prep_mode=False
    )

@dashboard_bp.route('/weekly_profit_data')
@login_required
def weekly_profit_data():
    """API endpoint to fetch weekly profit data for dashboard chart."""
    try:
        db = utils.get_mongo_db()
        user_id = str(current_user.id)
        today = safe_parse_datetime(datetime.now(timezone.utc))
        # Get last 7 days
        days = [(today - timedelta(days=i)).date() for i in range(6, -1, -1)]
        profit_per_day = []

        for day in days:
            start = safe_parse_datetime(datetime(day.year, day.month, day.day, tzinfo=timezone.utc))
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
                logger.warning(
                    f"Error calculating profit for {day}: {str(day_error)}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': user_id}
                )
                profit_per_day.append({
                    'date': day.strftime('%a'),
                    'profit': 0,
                    'receipts': 0,
                    'payments': 0
                })

        return safe_json_response({'data': profit_per_day, 'success': True})
    except Exception as e:
        logger.error(
            f"Error generating weekly profit data: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return safe_json_response({'error': 'Failed to generate profit data', 'success': False}, 500)

@dashboard_bp.route('/api/refresh_data')
@login_required
def refresh_dashboard_data():
    """API endpoint to refresh dashboard data without full page reload."""
    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id)}
        stats = utils.standardize_stats_dictionary()

        try:
            # Calculate receipts
            receipts_result = db.cashflows.aggregate([
                {'$match': {**query, 'type': 'receipt'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
            ])
            receipts_data = next(receipts_result, {})
            stats['total_receipts'] = receipts_data.get('count', 0)
            stats['total_receipts_amount'] = receipts_data.get('total_amount', 0)

            # Calculate payments
            payments_result = db.cashflows.aggregate([
                {'$match': {**query, 'type': 'payment'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
            ])
            payments_data = next(payments_result, {})
            stats['total_payments'] = payments_data.get('count', 0)
            stats['total_payments_amount'] = payments_data.get('total_amount', 0)

            # Calculate debtors
            debtors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'debtor'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount_owed'}, 'count': {'$sum': 1}}}
            ])
            debtors_data = next(debtors_result, {})
            stats['total_debtors'] = debtors_data.get('count', 0)
            stats['total_debtors_amount'] = debtors_data.get('total_amount', 0)

            # Calculate creditors
            creditors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'creditor'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount_owed'}, 'count': {'$sum': 1}}}
            ])
            creditors_data = next(creditors_result, {})
            stats['total_creditors'] = creditors_data.get('count', 0)
            stats['total_creditors_amount'] = creditors_data.get('total_amount', 0)

            # Calculate inventory
            inventory_result = db.records.aggregate([
                {'$match': {**query, 'type': 'inventory'}},
                {'$group': {'_id': None, 'total_cost': {'$sum': '$cost'}, 'count': {'$sum': 1}}}
            ])
            inventory_data = next(inventory_result, {})
            stats['total_inventory'] = inventory_data.get('count', 0)
            stats['total_inventory_cost'] = inventory_data.get('total_cost', 0)

            # Calculate profits
            stats['gross_profit'] = stats['total_receipts_amount'] - stats['total_payments_amount']
            stats['true_profit'] = stats['gross_profit'] - stats['total_inventory_cost']
            stats['profit_only'] = stats['true_profit']  # Ensure profit_only is included for template

        except Exception as stats_error:
            logger.error(
                f"Error calculating refresh stats: {str(stats_error)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return safe_json_response({'error': 'Failed to calculate statistics', 'success': False}, 500)

        # Standardize and format stats
        standardized_stats = utils.standardize_stats_dictionary(stats, log_defaults=True)
        formatted_stats = utils.format_stats_for_template(standardized_stats)

        # Validate stats completeness
        is_valid, missing_keys, warnings = utils.validate_stats_completeness(standardized_stats, 'refresh_dashboard_data')
        if not is_valid:
            logger.warning(
                f"Stats validation failed in refresh_dashboard_data: missing {missing_keys}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )

        return safe_json_response({
            'stats': formatted_stats,
            'success': True,
            'timestamp': safe_parse_datetime(datetime.now(timezone.utc)).isoformat(),
            'validation': {'is_valid': is_valid, 'warnings': warnings}
        })

    except Exception as e:
        logger.error(
            f"Error refreshing dashboard data: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return safe_json_response({'error': 'Failed to refresh data', 'success': False}, 500)

@dashboard_bp.route('/')
@login_required
def index():
    """Display the user's dashboard with recent activity and role-specific content."""
    try:
        # Check if trial is active
        if not current_user.is_trial_active():
            return render_template(
                'subscribe/subscription_required.html',
                title=trans('subscribe_required_title', default='Subscription Required'),
                can_interact=False
            )

        # Initialize database and query parameters
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id)}
        stats = utils.standardize_stats_dictionary()

        # Calculate stats (similar to /api/refresh_data)
        try:
            # Receipts
            receipts_result = db.cashflows.aggregate([
                {'$match': {**query, 'type': 'receipt'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
            ])
            receipts_data = next(receipts_result, {})
            stats['total_receipts'] = receipts_data.get('count', 0)
            stats['total_receipts_amount'] = receipts_data.get('total_amount', 0)

            # Payments
            payments_result = db.cashflows.aggregate([
                {'$match': {**query, 'type': 'payment'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
            ])
            payments_data = next(payments_result, {})
            stats['total_payments'] = payments_data.get('count', 0)
            stats['total_payments_amount'] = payments_data.get('total_amount', 0)

            # Debtors
            debtors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'debtor'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount_owed'}, 'count': {'$sum': 1}}}
            ])
            debtors_data = next(debtors_result, {})
            stats['total_debtors'] = debtors_data.get('count', 0)
            stats['total_debtors_amount'] = debtors_data.get('total_amount', 0)

            # Creditors
            creditors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'creditor'}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount_owed'}, 'count': {'$sum': 1}}}
            ])
            creditors_data = next(creditors_result, {})
            stats['total_creditors'] = creditors_data.get('count', 0)
            stats['total_creditors_amount'] = creditors_data.get('total_amount', 0)

            # Inventory
            inventory_result = db.records.aggregate([
                {'$match': {**query, 'type': 'inventory'}},
                {'$group': {'_id': None, 'total_cost': {'$sum': '$cost'}, 'count': {'$sum': 1}}}
            ])
            inventory_data = next(inventory_result, {})
            stats['total_inventory'] = inventory_data.get('count', 0)
            stats['total_inventory_cost'] = inventory_data.get('total_cost', 0)

            # Profits
            stats['gross_profit'] = stats['total_receipts_amount'] - stats['total_payments_amount']
            stats['true_profit'] = stats['gross_profit'] - stats['total_inventory_cost']
            stats['profit_only'] = stats['true_profit']  # Required by template
        except Exception as stats_error:
            logger.error(
                f"Error calculating dashboard stats: {str(stats_error)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('general_error', default='Unable to load dashboard data'), 'danger')
            return render_template('error/500.html', error_message=str(stats_error), title="Error"), 500

        # Fetch recent activity (limit to 5 records each)
        try:
            recent_debtors = list(db.records.find({**query, 'type': 'debtor'}).sort('created_at', -1).limit(5))
            recent_debtors = [normalize_datetime(clean_document_for_json(doc)) for doc in recent_debtors]

            recent_creditors = list(db.records.find({**query, 'type': 'creditor'}).sort('created_at', -1).limit(5))
            recent_creditors = [normalize_datetime(clean_document_for_json(doc)) for doc in recent_creditors]

            recent_receipts = list(db.cashflows.find({**query, 'type': 'receipt'}).sort('created_at', -1).limit(5))
            recent_receipts = [normalize_datetime(clean_document_for_json(doc)) for doc in recent_receipts]

            recent_payments = list(db.cashflows.find({**query, 'type': 'payment'}).sort('created_at', -1).limit(5))
            recent_payments = [normalize_datetime(clean_document_for_json(doc)) for doc in recent_payments]

            recent_inventory = list(db.records.find({**query, 'type': 'inventory'}).sort('created_at', -1).limit(5))
            recent_inventory = [normalize_datetime(clean_document_for_json(doc)) for doc in recent_inventory]
        except Exception as activity_error:
            logger.error(
                f"Error fetching recent activity: {str(activity_error)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            recent_debtors = recent_creditors = recent_receipts = recent_payments = recent_inventory = []

        # Calculate streak (example logic, adjust based on your requirements)
        try:
            streak = 0  # Placeholder: Implement actual streak calculation
            # Example: Count consecutive days with at least one record
            records = db.cashflows.find({**query}).sort('created_at', -1).limit(100)
            last_date = None
            for record in records:
                record_date = safe_parse_datetime(record['created_at']).date()
                if last_date is None:
                    last_date = record_date
                    streak = 1
                elif (last_date - record_date).days == 1:
                    streak += 1
                    last_date = record_date
                else:
                    break
        except Exception as streak_error:
            logger.error(
                f"Error calculating streak: {str(streak_error)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            streak = 0

        # Check for inventory loss (example logic, adjust as needed)
        inventory_loss = stats['total_inventory_cost'] < 0  # Example condition

        # Fetch unpaid debtors and creditors for notifications
        try:
            unpaid_debtors = list(db.records.find({**query, 'type': 'debtor', 'status': 'unpaid'}).limit(5))
            unpaid_debtors = [clean_document_for_json(doc) for doc in unpaid_debtors]
            unpaid_creditors = list(db.records.find({**query, 'type': 'creditor', 'status': 'unpaid'}).limit(5))
            unpaid_creditors = [clean_document_for_json(doc) for doc in unpaid_creditors]
        except Exception as notify_error:
            logger.error(
                f"Error fetching notifications data: {str(notify_error)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            unpaid_debtors = unpaid_creditors = []

        # Determine tax prep mode
        tax_prep_mode = request.args.get('tax_prep') == '1'

        # Determine if daily log reminder should be shown
        show_daily_log_reminder = reminders.should_show_daily_reminder(db, str(current_user.id))

        # Format stats for template
        formatted_stats = utils.format_stats_for_template(stats)

        # Render the dashboard template
        return render_template(
            'dashboard/index.html',
            stats=formatted_stats,
            recent_debtors=recent_debtors,
            recent_creditors=recent_creditors,
            recent_receipts=recent_receipts,
            recent_payments=recent_payments,
            recent_inventory=recent_inventory,
            streak=streak,
            tax_prep_mode=tax_prep_mode,
            can_interact=True,
            show_daily_log_reminder=show_daily_log_reminder,
            inventory_loss=inventory_loss,
            unpaid_debtors=unpaid_debtors,
            unpaid_creditors=unpaid_creditors
        )

    except Exception as e:
        logger.error(
            f"Error rendering dashboard: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('general_error', default='An error occurred while loading the dashboard'), 'danger')
        return render_template('error/500.html', error_message=str(e), title="Error"), 500
