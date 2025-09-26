from flask import Blueprint, render_template, flash, session, jsonify, request
from datetime import timedelta, datetime, timezone
from flask_login import login_required, current_user
from zoneinfo import ZoneInfo
from bson import ObjectId
import logging
from translations import trans
import utils
from utils import format_date, serialize_for_json, safe_json_response, clean_document_for_json, bulk_clean_documents_for_json, create_dashboard_safe_response
from helpers import reminders
from models import get_records

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

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
            creditors_result = db.records.aggregate([  # Fixed to use db.records
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
            'timestamp': datetime.now(timezone.utc).isoformat(),
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
    # Initialize data containers with defaults
    recent_creditors = []
    recent_debtors = []
    recent_payments = []
    recent_receipts = []
    recent_inventory = []
    stats = utils.standardize_stats_dictionary()
    can_interact = False
    show_daily_log_reminder = False
    streak = 0
    unpaid_debtors = []
    unpaid_creditors = []
    inventory_loss = False
    tax_prep_mode = request.args.get('tax_prep') == '1'

    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id)}

        # Fetch reminders and streak data
        try:
            show_daily_log_reminder = reminders.needs_daily_log_reminder(db, current_user.id)
            rewards_data = db.rewards.find_one({'user_id': str(current_user.id)})
            streak = rewards_data.get('streak', 0) if rewards_data else 0
            unpaid_debtors, unpaid_creditors = reminders.get_unpaid_debts_credits(db, current_user.id)
            unpaid_debtors = bulk_clean_documents_for_json(unpaid_debtors)  # Ensure JSON-safe
            unpaid_creditors = bulk_clean_documents_for_json(unpaid_creditors)  # Ensure JSON-safe
            inventory_loss = reminders.detect_inventory_loss(db, current_user.id)
            logger.debug(
                f"Calculated streak: {streak} for user_id: {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
        except Exception as e:
            logger.warning(
                f"Failed to calculate reminders or streak: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reminder_load_error', default='Unable to load reminders or streak data.'), 'warning')

        # Fetch recent records (limit to 5 for performance)
        try:
            recent_debtors = list(get_records(db, {**query, 'type': 'debtor'}, sort=[('created_at', -1)], limit=5))
            recent_creditors = list(get_records(db, {**query, 'type': 'creditor'}, sort=[('created_at', -1)], limit=5))
            recent_payments = list(utils.safe_find_cashflows(db, {**query, 'type': 'payment'}, sort_key='created_at', sort_direction=-1, limit=5))
            recent_payments = bulk_clean_documents_for_json(recent_payments)
            recent_receipts = list(utils.safe_find_cashflows(db, {**query, 'type': 'receipt'}, sort_key='created_at', sort_direction=-1, limit=5))
            recent_receipts = bulk_clean_documents_for_json(recent_receipts)
            recent_inventory = list(get_records(db, {**query, 'type': 'inventory'}, sort=[('created_at', -1)], limit=5))
        except Exception as e:
            logger.warning(
                f"Failed to fetch recent records: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('recent_records_error', default='Unable to load recent records.'), 'warning')

        # Handle tax prep mode calculations
        if tax_prep_mode:
            try:
                # Calculate true profit: Total Income - (Expenses + Inventory Cost)
                income_result = db.cashflows.aggregate([
                    {'$match': {**query, 'type': 'receipt'}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                ])
                total_income = next(income_result, {}).get('total', 0) or 0

                expenses_result = db.cashflows.aggregate([
                    {'$match': {**query, 'type': 'payment'}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                ])
                total_expenses = next(expenses_result, {}).get('total', 0) or 0

                inventory_result = db.records.aggregate([
                    {'$match': {**query, 'type': 'inventory'}},
                    {'$group': {'_id': None, 'total': {'$sum': '$cost'}}}
                ])
                total_inventory_cost = next(inventory_result, {}).get('total', 0) or 0

                stats['profit_only'] = total_income - (total_expenses + total_inventory_cost)
                stats['total_receipts'] = stats['total_payments'] = 0
                stats['total_receipts_amount'] = stats['total_payments_amount'] = 0
            except Exception as tax_error:
                logger.error(
                    f"Error calculating tax prep mode data: {str(tax_error)}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                stats['profit_only'] = 0

        # Calculate stats
        try:
            # Counts
            stats['total_debtors'] = db.records.count_documents({**query, 'type': 'debtor'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_debtors)
            stats['total_creditors'] = db.records.count_documents({**query, 'type': 'creditor'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_creditors)
            stats['total_payments'] = db.cashflows.count_documents({**query, 'type': 'payment'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_payments)
            stats['total_receipts'] = db.cashflows.count_documents({**query, 'type': 'receipt'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_receipts)
            stats['total_inventory'] = db.records.count_documents({**query, 'type': 'inventory'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_inventory)  # Fixed to use db.records

            # Amounts
            total_debtors_amount = sum(doc.get('amount_owed', 0) for doc in get_records(db, {**query, 'type': 'debtor'})) or sum(item.get('amount_owed', 0) for item in recent_debtors)
            total_creditors_amount = sum(doc.get('amount_owed', 0) for doc in get_records(db, {**query, 'type': 'creditor'})) or sum(item.get('amount_owed', 0) for item in recent_creditors)
            total_payments_amount = sum(doc.get('amount', 0) for doc in utils.safe_find_cashflows(db, {**query, 'type': 'payment'})) or sum(item.get('amount', 0) for item in recent_payments)
            total_receipts_amount = sum(doc.get('amount', 0) for doc in utils.safe_find_cashflows(db, {**query, 'type': 'receipt'})) or sum(item.get('amount', 0) for item in recent_receipts)
            total_inventory_cost = sum(doc.get('cost', 0) for doc in get_records(db, {**query, 'type': 'inventory'})) or sum(item.get('cost', 0) for item in recent_inventory)

            # Update stats
            stats.update({
                'total_debtors_amount': total_debtors_amount,
                'total_creditors_amount': total_creditors_amount,
                'total_payments_amount': total_payments_amount,
                'total_receipts_amount': total_receipts_amount,
                'total_inventory_cost': total_inventory_cost,
                'total_sales_amount': total_receipts_amount,
                'total_expenses_amount': total_payments_amount,
                'gross_profit': total_receipts_amount - total_payments_amount,
                'true_profit': (total_receipts_amount - total_payments_amount) - total_inventory_cost
            })

        except Exception as e:
            logger.error(
                f"Error calculating stats for dashboard: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('dashboard_stats_error', default='Unable to calculate dashboard statistics. Displaying defaults.'), 'warning')
            stats.update({
                'total_debtors': len(recent_debtors),
                'total_creditors': len(recent_creditors),
                'total_payments': len(recent_payments),
                'total_receipts': len(recent_receipts),
                'total_inventory': len(recent_inventory),
                'total_debtors_amount': sum(item.get('amount_owed', 0) for item in recent_debtors),
                'total_creditors_amount': sum(item.get('amount_owed', 0) for item in recent_creditors),
                'total_payments_amount': sum(item.get('amount', 0) for item in recent_payments),
                'total_receipts_amount': sum(item.get('amount', 0) for item in recent_receipts),
                'total_inventory_cost': sum(item.get('cost', 0) for item in recent_inventory),
                'total_sales_amount': sum(item.get('amount', 0) for item in recent_receipts),
                'total_expenses_amount': sum(item.get('amount', 0) for item in recent_payments),
                'gross_profit': sum(item.get('amount', 0) for item in recent_receipts) - sum(item.get('amount', 0) for item in recent_payments),
                'true_profit': (sum(item.get('amount', 0) for item in recent_receipts) - sum(item.get('amount', 0) for item in recent_payments)) - sum(item.get('cost', 0) for item in recent_inventory)
            })

        # Check subscription status
        try:
            can_interact = utils.can_user_interact(current_user)
        except Exception as e:
            logger.error(
                f"Error checking user interaction status: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('interaction_check_error', default='Unable to verify interaction status.'), 'warning')
            can_interact = False

        # Standardize and validate stats
        standardized_stats = utils.standardize_stats_dictionary(stats, log_defaults=True)
        is_valid, missing_keys, warnings = utils.validate_stats_completeness(standardized_stats, 'dashboard_index')
        if not is_valid:
            logger.warning(
                f"Stats validation failed in dashboard index: missing {missing_keys}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
        if warnings:
            logger.info(
                f"Stats validation warnings in dashboard index: {warnings}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )

        # Render dashboard
        return render_template(
            'dashboard/index.html',
            stats=standardized_stats,
            can_interact=can_interact,
            show_daily_log_reminder=show_daily_log_reminder,
            streak=streak,
            unpaid_debtors=unpaid_debtors,
            unpaid_creditors=unpaid_creditors,
            tax_prep_mode=tax_prep_mode,
            inventory_loss=inventory_loss,
            recent_debtors=recent_debtors,
            recent_creditors=recent_creditors,
            recent_payments=recent_payments,
            recent_receipts=recent_receipts,
            recent_inventory=recent_inventory
        )

    except Exception as e:
        logger.critical(
            f"Critical error in dashboard route: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('dashboard_critical_error', default='An error occurred while loading the dashboard. Please try again later.'), 'danger')
        safe_stats = utils.standardize_stats_dictionary(stats, log_defaults=True)

        return render_template(
            'dashboard/index.html',
            stats=safe_stats,
            can_interact=False,
            show_daily_log_reminder=False,
            streak=0,
            unpaid_debtors=[],
            unpaid_creditors=[],
            tax_prep_mode=False,
            inventory_loss=False,
            recent_debtors=[],
            recent_creditors=[],
            recent_payments=[],
            recent_receipts=[],
            recent_inventory=[]
        )
