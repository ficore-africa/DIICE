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
    if not current_user.is_trial_active():
        # Directly render the subscription required page, no redirect
        return render_template(
            'subscribe/subscription_required.html',
            title=trans('subscribe_required_title', default='Subscription Required'),
            can_interact=False
        )
    # ...existing code...
