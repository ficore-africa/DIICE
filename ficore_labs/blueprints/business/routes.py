from flask import Blueprint, jsonify, render_template, session, request, redirect, url_for
from flask_login import current_user, login_required
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import utils
from utils import logger, get_mongo_db, safe_parse_datetime, safe_json_response, serialize_for_json
from translations import trans

business = Blueprint('business', __name__, url_prefix='/business')

@business.route('/home')
@login_required
@utils.requires_role(['trader', 'admin'])
def home():
    """Render the Business Finance homepage with debt and cashflow summaries."""
    try:
        db = utils.get_mongo_db()
        user_id = current_user.id
        lang = session.get('lang', 'en')

        # Subscription/trial check REMOVED
        # if not current_user.is_trial_active() and not current_user.is_subscribed:
        #     return redirect(url_for('subscribe_bp.subscription_required'))

        # is_read_only is now set to False as the subscription check is removed.
        # If read-only mode should still be enforced for non-subscribed users, 
        # the check below can be re-enabled without the redirect.
        # is_read_only = not current_user.is_subscribed and not current_user.is_trial_active()
        is_read_only = False 

        # Fetch debt summary
        creditors_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'creditor'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount_owed'}}}
        ]
        creditors_result = list(db.records.aggregate(creditors_pipeline))
        total_i_owe = utils.clean_currency(creditors_result[0]['total'] if creditors_result else 0)

        debtors_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'debtor'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount_owed'}}}
        ]
        debtors_result = list(db.records.aggregate(debtors_pipeline))
        total_i_am_owed = utils.clean_currency(debtors_result[0]['total'] if debtors_result else 0)

        # Fetch cashflow summary
        today = datetime.now(timezone.utc)
        start_of_month = datetime(today.year, today.month, 1, tzinfo=timezone.utc)
        receipts_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'receipt', 'created_at': {'$gte': start_of_month}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]
        receipts_result = list(db.cashflows.aggregate(receipts_pipeline))
        total_receipts = utils.clean_currency(receipts_result[0]['total'] if receipts_result else 0)

        payments_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'payment', 'created_at': {'$gte': start_of_month}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]
        payments_result = list(db.cashflows.aggregate(payments_pipeline))
        total_payments = utils.clean_currency(payments_result[0]['total'] if payments_result else 0)
        net_cashflow = total_receipts - total_payments

        logger.info(
            f"Rendered business homepage for user {user_id}, read_only={is_read_only}, "
            f"total_i_owe={total_i_owe}, total_i_am_owed={total_i_am_owed}, net_cashflow={net_cashflow}, "
            f"total_receipts={total_receipts}, total_payments={total_payments}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr}
        )

        return render_template(
            'general/home.html',
            total_i_owe=total_i_owe,
            total_i_am_owed=total_i_am_owed,
            net_cashflow=net_cashflow,
            total_receipts=total_receipts,
            total_payments=total_payments,
            title=trans('business_home', lang=lang, default='Business Home'),
            format_currency=utils.format_currency,
            is_read_only=is_read_only,
            tools_for_template=utils.TRADER_NAV if current_user.role == 'trader' else utils.ADMIN_NAV,
            explore_features_for_template=utils.get_explore_features()
        )
    except Exception as e:
        logger.error(
            f"Error rendering business homepage for user {user_id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr}
        )
        return render_template(
            'general/error.html',
            error=trans('dashboard_error', lang=lang, default='An error occurred while loading the dashboard'),
            title=trans('error', lang=lang, default='Error')
        ), 500

@business.route('/view_data')
@login_required
@utils.requires_role(['trader', 'admin'])
def view_data():
    """Render read-only view of user's financial data."""
    try:
        db = utils.get_mongo_db()
        user_id = current_user.id
        lang = session.get('lang', 'en')

        # Fetch debt records
        debt_records = list(db.records.find({'user_id': user_id}).sort('created_at', -1).limit(50))
        for record in debt_records:
            if 'created_at' in record and record['created_at'].tzinfo is None:
                record['created_at'] = record['created_at'].replace(tzinfo=ZoneInfo("UTC"))

        # Fetch cashflow records
        cashflows = utils.safe_find_cashflows(db, {'user_id': user_id}, 'created_at', -1)[:50]

        logger.info(
            f"Rendered view_data for user {user_id}, debt_records={len(debt_records)}, cashflows={len(cashflows)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr}
        )

        return render_template(
            'general/view_data.html',
            debt_records=debt_records,
            cashflows=cashflows,
            title=trans('view_data_title', lang=lang, default='View Financial Data'),
            format_currency=utils.format_currency,
            is_read_only=True
        )
    except Exception as e:
        logger.error(
            f"Error rendering view_data for user {user_id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr}
        )
        return render_template(
            'general/error.html',
            error=trans('dashboard_error', lang=lang, default='An error occurred while loading financial data'),
            title=trans('error', lang=lang, default='Error')
        ), 500

@business.route('/debt/summary')
@login_required
@utils.requires_role(['trader', 'admin'])
def debt_summary():
    """Fetch debt summary (I Owe, I Am Owed) for the authenticated user."""
    try:
        db = utils.get_mongo_db()
        user_id = current_user.id
        creditors_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'creditor'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount_owed'}}}
        ]
        creditors_result = list(db.records.aggregate(creditors_pipeline))
        total_i_owe = utils.clean_currency(creditors_result[0]['total'] if creditors_result else 0)

        debtors_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'debtor'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount_owed'}}}
        ]
        debtors_result = list(db.records.aggregate(debtors_pipeline))
        total_i_am_owed = utils.clean_currency(debtors_result[0]['total'] if debtors_result else 0)

        logger.info(
            f"Fetched debt summary for user {user_id}: total_i_owe={total_i_owe}, total_i_am_owed={total_i_am_owed}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr}
        )
        return jsonify({
            'totalIOwe': total_i_owe,
            'totalIAmOwed': total_i_am_owed
        })
    except Exception as e:
        logger.error(
            f"Error fetching debt summary for user {user_id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr}
        )
        return jsonify({
            'error': trans('debt_summary_error', default='An error occurred while fetching debt summary')
        }), 500

@business.route('/cashflow/summary')
@login_required
@utils.requires_role(['trader', 'admin'])
def cashflow_summary():
    """Fetch the net cashflow (month-to-date) for the authenticated user."""
    try:
        db = utils.get_mongo_db()
        user_id = current_user.id
        today = datetime.now(timezone.utc)
        start_of_month = datetime(today.year, today.month, 1, tzinfo=timezone.utc)
        receipts_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'receipt', 'created_at': {'$gte': start_of_month}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]
        receipts_result = list(db.cashflows.aggregate(receipts_pipeline))
        total_receipts = utils.clean_currency(receipts_result[0]['total'] if receipts_result else 0)

        payments_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'payment', 'created_at': {'$gte': start_of_month}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]
        payments_count = db.cashflows.count_documents({'user_id': user_id, 'type': 'payment', 'created_at': {'$gte': start_of_month}})
        logger.info(f"Found {payments_count} payment records for user {user_id} in MTD")
        payments_result = list(db.cashflows.aggregate(payments_pipeline))
        total_payments = utils.clean_currency(payments_result[0]['total'] if payments_result else 0)
        net_cashflow = total_receipts - total_payments

        logger.info(
            f"Fetched cashflow summary for user {user_id}: net_cashflow={net_cashflow}, total_receipts={total_receipts}, total_payments={total_payments}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr}
        )
        return jsonify({
            'netCashflow': net_cashflow,
            'totalReceipts': total_receipts,
            'totalPayments': total_payments
        })
    except Exception as e:
        logger.error(
            f"Error fetching cashflow summary for user {user_id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr}
        )
        return jsonify({
            'error': trans('cashflow_error', default='An error occurred while fetching cashflow summary')
        }), 500

@business.route('/recent_activity')
@login_required
@utils.requires_role(['trader', 'admin'])
def recent_activity():
    """Fetch and display recent activity for the current user."""
    try:
        db = utils.get_mongo_db()
        user_id = str(current_user.id)
        lang = session.get('lang', 'en')

        # Fetch recent cashflows, limit to 10 for performance
        cashflows = list(db.cashflows.find({'user_id': user_id}).sort('created_at', -1).limit(10))
        
        # Normalize datetime fields
        cashflows = [normalize_datetime(doc) for doc in cashflows]
        
        # Clean and serialize data for JSON response
        cleaned_cashflows = []
        for cashflow in cashflows:
            try:
                cleaned_cashflow = serialize_for_json(cashflow)
                cleaned_cashflows.append(cleaned_cashflow)
            except Exception as e:
                logger.warning(f"Failed to clean cashflow record {cashflow.get('_id', 'unknown')}: {str(e)}")
                continue
        
        return safe_json_response(cleaned_cashflows)
    except Exception as e:
        logger.error(
            f"Error fetching recent activity for user {user_id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': user_id}
        )
        return safe_json_response({
            'error': trans('activity_error', default='An error occurred while loading recent activity. Please try again.')
        }, 500)

def normalize_datetime(doc):
    """Convert created_at and updated_at to timezone-aware datetime if they are strings or naive datetimes."""
    for field in ['created_at', 'updated_at']:
        if field in doc:
            doc[field] = safe_parse_datetime(doc[field])
    return doc
