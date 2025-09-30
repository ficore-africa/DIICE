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
from models import get_records, get_cashflows, parse_and_normalize_datetime, to_dict_record, to_dict_cashflow

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

def safe_to_float(value, default=0.0):
    """Convert a value to float, return default if conversion fails."""
    if value is None or value == "":
        logger.warning(f"Received None or empty value for conversion to float")
        return default
    try:
        result = float(value)
        if result == float('inf') or result == float('-inf') or result != result:  # Check for NaN/inf
            logger.warning(f"Invalid float value: {value}")
            return default
        return result
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert value to float: {value} (type: {type(value)}), error: {str(e)}")
        return default

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
        today = parse_and_normalize_datetime(datetime.now(timezone.utc))
        days = [(today - timedelta(days=i)).date() for i in range(6, -1, -1)]
        profit_per_day = []

        for day in days:
            start = parse_and_normalize_datetime(datetime(day.year, day.month, day.day, tzinfo=timezone.utc))
            end = start + timedelta(days=1)
            try:
                # Sum receipts (income) for the day
                receipts = db.cashflows.aggregate([
                    {'$match': {'user_id': user_id, 'type': 'receipt', 'created_at': {'$gte': start, '$lt': end}}},
                    {'$group': {
                        '_id': None,
                        'total': {
                            '$sum': {
                                '$cond': {
                                    'if': {'$isNumber': '$amount'},
                                    'then': {'$toDouble': '$amount'},
                                    'else': 0.0
                                }
                            }
                        }
                    }}
                ])
                receipts_total = safe_to_float(next(receipts, {}).get('total', 0))
                logger.debug(f"Day {day}: receipts_total = {receipts_total} (type: {type(receipts_total)})")

                # Sum payments (expenses) for the day
                payments = db.cashflows.aggregate([
                    {'$match': {'user_id': user_id, 'type': 'payment', 'created_at': {'$gte': start, '$lt': end}}},
                    {'$group': {
                        '_id': None,
                        'total': {
                            '$sum': {
                                '$cond': {
                                    'if': {'$isNumber': '$amount'},
                                    'then': {'$toDouble': '$amount'},
                                    'else': 0.0
                                }
                            }
                        }
                    }}
                ])
                payments_total = safe_to_float(next(payments, {}).get('total', 0))
                logger.debug(f"Day {day}: payments_total = {payments_total} (type: {type(payments_total)})")

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
                    'profit': 0.0,
                    'receipts': 0.0,
                    'payments': 0.0
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
                {'$group': {
                    '_id': None,
                    'total_amount': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$amount'},
                                'then': {'$toDouble': '$amount'},
                                'else': 0.0
                            }
                        }
                    },
                    'count': {'$sum': 1}
                }}
            ])
            receipts_data = next(receipts_result, {})
            stats['total_receipts'] = receipts_data.get('count', 0)
            stats['total_receipts_amount'] = safe_to_float(receipts_data.get('total_amount', 0))
            logger.debug(f"Receipts: total_receipts_amount = {stats['total_receipts_amount']} (type: {type(stats['total_receipts_amount'])})")

            # Calculate payments
            payments_result = db.cashflows.aggregate([
                {'$match': {**query, 'type': 'payment'}},
                {'$group': {
                    '_id': None,
                    'total_amount': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$amount'},
                                'then': {'$toDouble': '$amount'},
                                'else': 0.0
                            }
                        }
                    },
                    'count': {'$sum': 1}
                }}
            ])
            payments_data = next(payments_result, {})
            stats['total_payments'] = payments_data.get('count', 0)
            stats['total_payments_amount'] = safe_to_float(payments_data.get('total_amount', 0))
            logger.debug(f"Payments: total_payments_amount = {stats['total_payments_amount']} (type: {type(stats['total_payments_amount'])})")

            # Calculate debtors
            debtors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'debtor'}},
                {'$group': {
                    '_id': None,
                    'total_amount': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$amount_owed'},
                                'then': {'$toDouble': '$amount_owed'},
                                'else': 0.0
                            }
                        }
                    },
                    'count': {'$sum': 1}
                }}
            ])
            debtors_data = next(debtors_result, {})
            stats['total_debtors'] = debtors_data.get('count', 0)
            stats['total_debtors_amount'] = safe_to_float(debtors_data.get('total_amount', 0))
            logger.debug(f"Debtors: total_debtors_amount = {stats['total_debtors_amount']} (type: {type(stats['total_debtors_amount'])})")

            # Calculate creditors
            creditors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'creditor'}},
                {'$group': {
                    '_id': None,
                    'total_amount': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$amount_owed'},
                                'then': {'$toDouble': '$amount_owed'},
                                'else': 0.0
                            }
                        }
                    },
                    'count': {'$sum': 1}
                }}
            ])
            creditors_data = next(creditors_result, {})
            stats['total_creditors'] = creditors_data.get('count', 0)
            stats['total_creditors_amount'] = safe_to_float(creditors_data.get('total_amount', 0))
            logger.debug(f"Creditors: total_creditors_amount = {stats['total_creditors_amount']} (type: {type(stats['total_creditors_amount'])})")

            # Calculate inventory
            inventory_result = db.records.aggregate([
                {'$match': {**query, 'type': 'inventory'}},
                {'$group': {
                    '_id': None,
                    'total_cost': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$cost'},
                                'then': {'$toDouble': '$cost'},
                                'else': 0.0
                            }
                        }
                    },
                    'count': {'$sum': 1}
                }}
            ])
            inventory_data = next(inventory_result, {})
            stats['total_inventory'] = inventory_data.get('count', 0)
            stats['total_inventory_cost'] = safe_to_float(inventory_data.get('total_cost', 0))
            logger.debug(f"Inventory: total_inventory_cost = {stats['total_inventory_cost']} (type: {type(stats['total_inventory_cost'])})")

            # Calculate profits
            stats['gross_profit'] = stats['total_receipts_amount'] - stats['total_payments_amount']
            stats['true_profit'] = stats['gross_profit'] - stats['total_inventory_cost']
            stats['profit_only'] = stats['true_profit']
            logger.debug(f"Profits: gross_profit = {stats['gross_profit']} (type: {type(stats['gross_profit'])}), true_profit = {stats['true_profit']} (type: {type(stats['true_profit'])})")

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
            'timestamp': parse_and_normalize_datetime(datetime.now(timezone.utc)).isoformat(),
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
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id)}
        stats = utils.standardize_stats_dictionary()
        recent_debtors = []
        recent_creditors = []
        recent_receipts = []
        recent_payments = []
        recent_inventory = []
        unpaid_debtors = []
        unpaid_creditors = []
        inventory_loss = False
        show_daily_log_reminder = False
        streak = 0
        tax_prep_mode = request.args.get('tax_prep') == '1'

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

        # Fetch reminders and streak data
        try:
            show_daily_log_reminder = reminders.needs_daily_log_reminder(db, current_user.id)
            rewards_data = db.rewards.find_one({'user_id': str(current_user.id)})
            streak = rewards_data.get('streak', 0) if rewards_data else 0
            unpaid_debtors, unpaid_creditors = reminders.get_unpaid_debts_credits(db, current_user.id)
            unpaid_debtors = [to_dict_record(doc) for doc in unpaid_debtors]
            unpaid_creditors = [to_dict_record(doc) for doc in unpaid_creditors]
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

        # Fetch recent records
        try:
            recent_debtors = [to_dict_record(doc) for doc in db.records.find({**query, 'type': 'debtor'}).sort('created_at', -1).limit(5)]
            recent_creditors = [to_dict_record(doc) for doc in db.records.find({**query, 'type': 'creditor'}).sort('created_at', -1).limit(5)]
            recent_receipts = [to_dict_cashflow(doc) for doc in db.cashflows.find({**query, 'type': 'receipt'}).sort('created_at', -1).limit(5)]
            recent_payments = [to_dict_cashflow(doc) for doc in db.cashflows.find({**query, 'type': 'payment'}).sort('created_at', -1).limit(5)]
            recent_inventory = [to_dict_record(doc) for doc in db.records.find({**query, 'type': 'inventory'}).sort('created_at', -1).limit(5)]
        except Exception as e:
            logger.warning(
                f"Failed to fetch recent records: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('recent_records_error', default='Unable to load recent records.'), 'warning')

        # Calculate stats
        try:
            # Counts
            stats['total_debtors'] = db.records.count_documents({**query, 'type': 'debtor'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_debtors)
            stats['total_creditors'] = db.records.count_documents({**query, 'type': 'creditor'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_creditors)
            stats['total_payments'] = db.cashflows.count_documents({**query, 'type': 'payment'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_payments)
            stats['total_receipts'] = db.cashflows.count_documents({**query, 'type': 'receipt'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_receipts)
            stats['total_inventory'] = db.records.count_documents({**query, 'type': 'inventory'}, hint=[('user_id', 1), ('type', 1)]) or len(recent_inventory)

            # Amounts
            receipts_result = db.cashflows.aggregate([
                {'$match': {**query, 'type': 'receipt'}},
                {'$group': {
                    '_id': None,
                    'total_amount': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$amount'},
                                'then': {'$toDouble': '$amount'},
                                'else': 0.0
                            }
                        }
                    }
                }}
            ])
            stats['total_receipts_amount'] = safe_to_float(next(receipts_result, {}).get('total_amount', 0))

            payments_result = db.cashflows.aggregate([
                {'$match': {**query, 'type': 'payment'}},
                {'$group': {
                    '_id': None,
                    'total_amount': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$amount'},
                                'then': {'$toDouble': '$amount'},
                                'else': 0.0
                            }
                        }
                    }
                }}
            ])
            stats['total_payments_amount'] = safe_to_float(next(payments_result, {}).get('total_amount', 0))

            debtors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'debtor'}},
                {'$group': {
                    '_id': None,
                    'total_amount': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$amount_owed'},
                                'then': {'$toDouble': '$amount_owed'},
                                'else': 0.0
                            }
                        }
                    }
                }}
            ])
            stats['total_debtors_amount'] = safe_to_float(next(debtors_result, {}).get('total_amount', 0))

            creditors_result = db.records.aggregate([
                {'$match': {**query, 'type': 'creditor'}},
                {'$group': {
                    '_id': None,
                    'total_amount': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$amount_owed'},
                                'then': {'$toDouble': '$amount_owed'},
                                'else': 0.0
                            }
                        }
                    }
                }}
            ])
            stats['total_creditors_amount'] = safe_to_float(next(creditors_result, {}).get('total_amount', 0))

            inventory_result = db.records.aggregate([
                {'$match': {**query, 'type': 'inventory'}},
                {'$group': {
                    '_id': None,
                    'total_cost': {
                        '$sum': {
                            '$cond': {
                                'if': {'$isNumber': '$cost'},
                                'then': {'$toDouble': '$cost'},
                                'else': 0.0
                            }
                        }
                    }
                }}
            ])
            stats['total_inventory_cost'] = safe_to_float(next(inventory_result, {}).get('total_cost', 0))

            # Handle tax prep mode calculations
            if tax_prep_mode:
                stats['profit_only'] = stats['total_receipts_amount'] - (stats['total_payments_amount'] + stats['total_inventory_cost'])
                stats['total_receipts'] = stats['total_payments'] = 0
                stats['total_receipts_amount'] = stats['total_payments_amount'] = 0
            else:
                stats['gross_profit'] = stats['total_receipts_amount'] - stats['total_payments_amount']
                stats['true_profit'] = stats['gross_profit'] - stats['total_inventory_cost']
                stats['profit_only'] = stats['true_profit']

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
                'total_debtors_amount': sum(safe_to_float(item.get('amount_owed', 0)) for item in recent_debtors),
                'total_creditors_amount': sum(safe_to_float(item.get('amount_owed', 0)) for item in recent_creditors),
                'total_payments_amount': sum(safe_to_float(item.get('amount', 0)) for item in recent_payments),
                'total_receipts_amount': sum(safe_to_float(item.get('amount', 0)) for item in recent_receipts),
                'total_inventory_cost': sum(safe_to_float(item.get('cost', 0)) for item in recent_inventory),
                'total_sales_amount': sum(safe_to_float(item.get('amount', 0)) for item in recent_receipts),
                'total_expenses_amount': sum(safe_to_float(item.get('amount', 0)) for item in recent_payments),
                'gross_profit': sum(safe_to_float(item.get('amount', 0)) for item in recent_receipts) - sum(safe_to_float(item.get('amount', 0)) for item in recent_payments),
                'true_profit': (sum(safe_to_float(item.get('amount', 0)) for item in recent_receipts) - sum(safe_to_float(item.get('amount', 0)) for item in recent_payments)) - sum(safe_to_float(item.get('cost', 0)) for item in recent_inventory),
                'profit_only': (sum(safe_to_float(item.get('amount', 0)) for item in recent_receipts) - sum(safe_to_float(item.get('amount', 0)) for item in recent_payments)) - sum(safe_to_float(item.get('cost', 0)) for item in recent_inventory)
            })

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
        safe_stats = utils.standardize_stats_dictionary({}, log_defaults=True)
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
        ), 500
