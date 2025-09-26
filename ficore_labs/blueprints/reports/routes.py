from flask import Blueprint, session, request, render_template, redirect, url_for, flash, jsonify, current_app, Response
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFError
from translations import trans
import utils
from bson import ObjectId
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from io import BytesIO, StringIO
from wtforms import DateField, StringField, SubmitField, SelectField
from wtforms.validators import Optional, Length
import csv
import logging
from helpers.branding_helpers import draw_ficore_pdf_header, ficore_csv_header
import pymongo.errors

logger = logging.getLogger(__name__)

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

class ReportForm(FlaskForm):
    start_date = DateField(trans('reports_start_date', default='Start Date'), validators=[Optional()])
    end_date = DateField(trans('reports_end_date', default='End Date'), validators=[Optional()])
    format = SelectField('Format', choices=[('html', 'HTML'), ('pdf', 'PDF'), ('csv', 'CSV')], default='html', validators=[Optional()])
    submit = SubmitField(trans('reports_generate_report', default='Generate Report'))

class CustomerReportForm(FlaskForm):
    role = SelectField('User Role', choices=[('', 'All'), ('trader', 'Trader'), ('admin', 'Admin')], validators=[Optional(), Length(max=20)])
    format = SelectField('Format', choices=[('html', 'HTML'), ('pdf', 'PDF'), ('csv', 'CSV')], default='html', validators=[Optional()])
    submit = SubmitField('Generate Report')

def to_dict_record(record):
    if not record:
        return {'name': None, 'amount_owed': None}
    try:
        if record.get('created_at') and record['created_at'].tzinfo is None:
            record['created_at'] = record['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        if record.get('updated_at') and record['updated_at'].tzinfo is None:
            record['updated_at'] = record['updated_at'].replace(tzinfo=ZoneInfo("UTC"))
        created_at = utils.format_date(record.get('created_at'), format_type='iso') if record.get('created_at') else None
        updated_at = utils.format_date(record.get('updated_at'), format_type='iso') if record.get('updated_at') else None
    except Exception as e:
        logger.error(
            f"Error formatting dates in to_dict_record: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id if current_user.is_authenticated else 'anonymous'}
        )
        created_at = None
        updated_at = None
    return {
        'id': str(record.get('_id', '')),
        'user_id': str(record.get('user_id', '')),
        'type': utils.sanitize_input(record.get('type', ''), max_length=20),
        'name': utils.sanitize_input(record.get('name', ''), max_length=100),
        'contact': utils.sanitize_input(record.get('contact', ''), max_length=100),
        'amount_owed': record.get('amount_owed', 0),
        'description': utils.sanitize_input(record.get('description', ''), max_length=1000),
        'created_at': created_at,
        'updated_at': updated_at
    }

def to_dict_cashflow(record):
    if not record:
        return {'party_name': None, 'amount': None}
    try:
        if record.get('created_at') and record['created_at'].tzinfo is None:
            record['created_at'] = record['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        if record.get('updated_at') and record['updated_at'].tzinfo is None:
            record['updated_at'] = record['updated_at'].replace(tzinfo=ZoneInfo("UTC"))
        created_at = utils.format_date(record.get('created_at'), format_type='iso')
        updated_at = utils.format_date(record.get('updated_at'), format_type='iso') if record.get('updated_at') else None
    except Exception as e:
        logger.error(
            f"Error formatting dates in to_dict_cashflow: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id if current_user.is_authenticated else 'anonymous'}
        )
        created_at = None
        updated_at = None
    return {
        'id': str(record.get('_id', '')),
        'user_id': str(record.get('user_id', '')),
        'type': utils.sanitize_input(record.get('type', ''), max_length=20),
        'party_name': utils.sanitize_input(record.get('party_name', ''), max_length=100),
        'amount': record.get('amount', 0),
        'method': utils.sanitize_input(record.get('method', ''), max_length=50),
        'created_at': created_at,
        'updated_at': updated_at
    }

@reports_bp.route('/')
@login_required
@utils.requires_role(['trader', 'admin'])
def index():
    try:
        can_interact = utils.can_user_interact(current_user)
        logger.info(
            f"Rendering reports index for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return render_template(
            'reports/index.html',
            title=trans('reports_title', default='Reports'),
            can_interact=can_interact
        )
    except Exception as e:
        logger.error(
            f"Error loading reports index: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('reports_load_error', default='An error occurred'), 'danger')
        return redirect(url_for('main.index'))

@reports_bp.route('/profit_loss', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'admin'])
@utils.limiter.limit('10 per minute')
def profit_loss():
    form = ReportForm()
    can_interact = utils.can_user_interact(current_user)
    if not can_interact:
        logger.warning(
            f"Subscription required to generate reports for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('subscription_required', default='Subscription required to generate reports.'), 'warning')
        return redirect(url_for('subscribe_bp.subscribe'))
    cashflows = []
    query = {'user_id': str(current_user.id)}
    if form.validate_on_submit():
        try:
            if form.format.data not in ['html', 'pdf', 'csv']:
                logger.error(
                    f"Invalid format {form.format.data} for profit/loss report",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('reports_invalid_format', default='Invalid report format'), 'danger')
                return redirect(url_for('reports.profit_loss'))
            db = utils.get_mongo_db()
            if form.start_date.data:
                start_datetime = datetime.combine(form.start_date.data, datetime.min.time(), tzinfo=ZoneInfo("UTC"))
                query['created_at'] = {'$gte': start_datetime}
            if form.end_date.data:
                end_datetime = datetime.combine(form.end_date.data, datetime.max.time(), tzinfo=ZoneInfo("UTC"))
                query['created_at'] = {**query.get('created_at', {}), '$lte': end_datetime}
            cashflows = [to_dict_cashflow(cf) for cf in utils.safe_find_cashflows(db, query, 'created_at', -1)]
            output_format = form.format.data
            logger.info(
                f"Generating profit/loss report for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            if output_format == 'pdf':
                return generate_profit_loss_pdf(cashflows)
            elif output_format == 'csv':
                return generate_profit_loss_csv(cashflows)
        except pymongo.errors.PyMongoError as e:
            logger.error(
                f"MongoDB error generating profit/loss report: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
        except Exception as e:
            logger.error(
                f"Error generating profit/loss report: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    else:
        try:
            db = utils.get_mongo_db()
            cashflows = [to_dict_cashflow(cf) for cf in utils.safe_find_cashflows(db, query, 'created_at', -1)]
        except pymongo.errors.PyMongoError as e:
            logger.error(
                f"MongoDB error fetching cashflows: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
        except Exception as e:
            logger.error(
                f"Error fetching cashflows: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    logger.info(
        f"Rendering profit/loss report page for user {current_user.id}",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return render_template(
        'reports/profit_loss.html',
        form=form,
        cashflows=cashflows,
        title=trans('reports_profit_loss', default='Profit/Loss Report'),
        can_interact=can_interact
    )

@reports_bp.route('/debtors_creditors', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'admin'])
@utils.limiter.limit('10 per minute')
def debtors_creditors():
    form = ReportForm()
    can_interact = utils.can_user_interact(current_user)
    if not can_interact:
        logger.warning(
            f"Subscription required to generate reports for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('subscription_required', default='Subscription required to generate reports.'), 'warning')
        return redirect(url_for('subscribe_bp.subscribe'))
    records = []
    query = {'user_id': str(current_user.id)}
    if form.validate_on_submit():
        try:
            if form.format.data not in ['html', 'pdf', 'csv']:
                logger.error(
                    f"Invalid format {form.format.data} for debtors/creditors report",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('reports_invalid_format', default='Invalid report format'), 'danger')
                return redirect(url_for('reports.debtors_creditors'))
            db = utils.get_mongo_db()
            if form.start_date.data:
                start_datetime = datetime.combine(form.start_date.data, datetime.min.time(), tzinfo=ZoneInfo("UTC"))
                query['created_at'] = {'$gte': start_datetime}
            if form.end_date.data:
                end_datetime = datetime.combine(form.end_date.data, datetime.max.time(), tzinfo=ZoneInfo("UTC"))
                query['created_at'] = {**query.get('created_at', {}), '$lte': end_datetime}
            records = [to_dict_record(r) for r in utils.safe_find_records(db, query, 'created_at', -1)]
            output_format = form.format.data
            logger.info(
                f"Generating debtors/creditors report for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            if output_format == 'pdf':
                return generate_debtors_creditors_pdf(records)
            elif output_format == 'csv':
                return generate_debtors_creditors_csv(records)
        except pymongo.errors.PyMongoError as e:
            logger.error(
                f"MongoDB error generating debtors/creditors report for user {current_user.id}: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
        except Exception as e:
            logger.error(
                f"Error generating debtors/creditors report: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    else:
        try:
            db = utils.get_mongo_db()
            records = [to_dict_record(r) for r in utils.safe_find_records(db, query, 'created_at', -1)]
        except pymongo.errors.PyMongoError as e:
            logger.error(
                f"MongoDB error fetching records: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
        except Exception as e:
            logger.error(
                f"Error fetching records: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    logger.info(
        f"Rendering debtors/creditors report page for user {current_user.id}",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return render_template(
        'reports/debtors_creditors.html',
        form=form,
        records=records,
        title=trans('reports_debtors_creditors', default='Debtors/Creditors Report'),
        can_interact=can_interact
    )

@reports_bp.route('/admin/customer_reports', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit('10 per minute')
def customer_reports():
    form = CustomerReportForm()
    can_interact = utils.can_user_interact(current_user)  # Should always be True for admins
    if form.validate_on_submit():
        try:
            role = utils.sanitize_input(form.role.data, max_length=20) if form.role.data else None
            report_format = form.format.data
            if report_format not in ['html', 'pdf', 'csv']:
                logger.error(
                    f"Invalid format {report_format} for customer reports by user {current_user.id}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('reports_invalid_format', default='Invalid report format'), 'danger')
                return redirect(url_for('reports.customer_reports'))
            if role and role not in ['trader', 'admin']:
                logger.error(
                    f"Invalid role {role} for customer reports by user {current_user.id}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('reports_invalid_role', default='Invalid role selected'), 'danger')
                return redirect(url_for('reports.customer_reports'))
            db = utils.get_mongo_db()
            pipeline = [
                {'$match': {'role': role} if role else {}},
                {'$lookup': {
                    'from': 'records',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}}},
                        {'$group': {
                            '_id': '$type',
                            'total_amount_owed': {'$sum': '$amount_owed'}
                        }}
                    ],
                    'as': 'record_totals'
                }},
                {'$lookup': {
                    'from': 'cashflows',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}}},
                        {'$group': {
                            '_id': '$type',
                            'total_amount': {'$sum': '$amount'}
                        }}
                    ],
                    'as': 'cashflow_totals'
                }}
            ]
            users = list(db.users.aggregate(pipeline))
            report_data = []
            for user in users:
                record_totals = {r['_id']: r['total_amount_owed'] for r in user.get('record_totals', [])}
                cashflow_totals = {c['_id']: c['total_amount'] for c in user.get('cashflow_totals', [])}
                data = {
                    'username': utils.sanitize_input(str(user['_id']), max_length=100),
                    'email': utils.sanitize_input(user.get('email', ''), max_length=100),
                    'role': utils.sanitize_input(user.get('role', ''), max_length=20),
                    'is_trial': user.get('is_trial', False),
                    'trial_end': utils.format_date(user.get('trial_end')) if user.get('trial_end') else '-',
                    'is_subscribed': user.get('is_subscribed', False),
                    'total_debtors': record_totals.get('debtor', 0),
                    'total_creditors': record_totals.get('creditor', 0),
                    'total_receipts': cashflow_totals.get('receipt', 0),
                    'total_payments': cashflow_totals.get('payment', 0)
                }
                report_data.append(data)
            logger.info(
                f"Generating customer report for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            if report_format == 'html':
                return render_template('reports/customer_reports.html', report_data=report_data, form=form, title=trans('reports_customer_reports', default='Customer Reports'))
            elif report_format == 'pdf':
                return generate_customer_report_pdf(report_data)
            elif report_format == 'csv':
                return generate_customer_report_csv(report_data)
        except pymongo.errors.PyMongoError as e:
            logger.error(
                f"MongoDB error generating customer report for user {current_user.id}: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
        except Exception as e:
            logger.error(
                f"Error generating customer report for user {current_user.id}: {str(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    logger.info(
        f"Rendering customer reports page for user {current_user.id}",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return render_template(
        'reports/customer_reports.html',
        form=form,
        title=trans('reports_customer_reports', default='Customer Reports'),
        can_interact=can_interact
    )

def generate_profit_loss_pdf(cashflows):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    header_height = 0.7 * inch
    extra_space = 0.2 * inch
    row_height = 0.3 * inch
    bottom_margin = 0.5 * inch
    max_y = 10.5
    title_y = max_y - header_height - extra_space
    rows_per_page = int((max_y - bottom_margin - header_height - extra_space) // row_height)

    def draw_table_headers(y):
        p.setFillColor(colors.black)
        p.drawString(1 * inch, y * inch, trans('general_date', default='Date'))
        p.drawString(2.5 * inch, y * inch, trans('general_party_name', default='Party Name'))
        p.drawString(4 * inch, y * inch, trans('general_type', default='Type'))
        p.drawString(5 * inch, y * inch, trans('general_amount', default='Amount'))
        return y - row_height

    draw_ficore_pdf_header(p, current_user, y_start=max_y)
    p.setFont("Helvetica", 12)
    p.drawString(1 * inch, title_y * inch, trans('reports_profit_loss_report', default='Profit/Loss Report'))
    p.drawString(1 * inch, (title_y - 0.3) * inch, f"{trans('general_generated', default='Generated')}: {utils.format_date(datetime.now(timezone.utc))}")
    y = title_y - 0.6
    y = draw_table_headers(y)

    total_income = 0
    total_expense = 0
    row_count = 0

    for t in cashflows:
        if row_count >= rows_per_page:
            p.showPage()
            draw_ficore_pdf_header(p, current_user, y_start=max_y)
            y = title_y - 0.6
            y = draw_table_headers(y)
            row_count = 0

        p.drawString(1 * inch, y * inch, utils.format_date(t['created_at']))
        p.drawString(2.5 * inch, y * inch, utils.sanitize_input(t['party_name'], max_length=100))
        p.drawString(4 * inch, y * inch, t['type'])
        p.drawString(5 * inch, y * inch, utils.format_currency(t['amount']))
        if t['type'] == 'receipt':
            total_income += t['amount']
        else:
            total_expense += t['amount']
        y -= row_height
        row_count += 1

    if row_count + 3 <= rows_per_page:
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_income', default='Total Income')}: {utils.format_currency(total_income)}")
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_expense', default='Total Expense')}: {utils.format_currency(total_expense)}")
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_net_profit', default='Net Profit')}: {utils.format_currency(total_income - total_expense)}")
    else:
        p.showPage()
        draw_ficore_pdf_header(p, current_user, y_start=max_y)
        y = title_y - 0.6
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_income', default='Total Income')}: {utils.format_currency(total_income)}")
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_expense', default='Total Expense')}: {utils.format_currency(total_expense)}")
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_net_profit', default='Net Profit')}: {utils.format_currency(total_income - total_expense)}")

    p.save()
    buffer.seek(0)
    logger.info(
        f"Generated profit/loss PDF for user {current_user.id}",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment; filename=profit_loss_report.pdf'})

def generate_profit_loss_csv(cashflows):
    output = []
    output.extend(ficore_csv_header(current_user))
    output.append([trans('reports_profit_loss_report', default='Profit/Loss Report'), '', '', ''])
    output.append(['Date', 'Party Name', 'Type', 'Amount'])
    total_income = 0
    total_expense = 0
    for t in cashflows:
        output.append([utils.format_date(t['created_at']), utils.sanitize_input(t['party_name'], max_length=100), t['type'], utils.format_currency(t['amount'])])
        if t['type'] == 'receipt':
            total_income += t['amount']
        else:
            total_expense += t['amount']
    output.append(['', '', '', f"{trans('reports_total_income', default='Total Income')}: {utils.format_currency(total_income)}"])
    output.append(['', '', '', f"{trans('reports_total_expense', default='Total Expense')}: {utils.format_currency(total_expense)}"])
    output.append(['', '', '', f"{trans('reports_net_profit', default='Net Profit')}: {utils.format_currency(total_income - total_expense)}"])
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerows(output)
    buffer.seek(0)
    logger.info(
        f"Generated profit/loss CSV for user {current_user.id}",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return Response(buffer.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=profit_loss_report.csv'})

def generate_debtors_creditors_pdf(records):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    header_height = 0.7 * inch
    extra_space = 0.2 * inch
    row_height = 0.3 * inch
    bottom_margin = 0.5 * inch
    max_y = 10.5
    title_y = max_y - header_height - extra_space
    rows_per_page = int((max_y - bottom_margin - header_height - extra_space) // row_height)

    def draw_table_headers(y):
        p.setFillColor(colors.black)
        p.drawString(1 * inch, y * inch, trans('general_date', default='Date'))
        p.drawString(2.5 * inch, y * inch, trans('general_name', default='Name'))
        p.drawString(4 * inch, y * inch, trans('general_type', default='Type'))
        p.drawString(5 * inch, y * inch, trans('general_amount_owed', default='Amount Owed'))
        p.drawString(6.5 * inch, y * inch, trans('general_description', default='Description'))
        return y - row_height

    draw_ficore_pdf_header(p, current_user, y_start=max_y)
    p.setFont("Helvetica", 12)
    p.drawString(1 * inch, title_y * inch, trans('reports_debtors_creditors_report', default='Debtors/Creditors Report'))
    p.drawString(1 * inch, (title_y - 0.3) * inch, f"{trans('general_generated', default='Generated')}: {utils.format_date(datetime.now(timezone.utc))}")
    y = title_y - 0.6
    y = draw_table_headers(y)

    total_debtors = 0
    total_creditors = 0
    row_count = 0

    for r in records:
        if row_count >= rows_per_page:
            p.showPage()
            draw_ficore_pdf_header(p, current_user, y_start=max_y)
            y = title_y - 0.6
            y = draw_table_headers(y)
            row_count = 0

        p.drawString(1 * inch, y * inch, utils.format_date(r['created_at']))
        p.drawString(2.5 * inch, y * inch, utils.sanitize_input(r['name'], max_length=100))
        p.drawString(4 * inch, y * inch, trans(f"general_{r['type']}", default=r['type']))
        p.drawString(5 * inch, y * inch, utils.format_currency(r['amount_owed']))
        p.drawString(6.5 * inch, y * inch, utils.sanitize_input(r['description'], max_length=120))
        if r['type'] == 'debtor':
            total_debtors += r['amount_owed']
        else:
            total_creditors += r['amount_owed']
        y -= row_height
        row_count += 1

    if row_count + 2 <= rows_per_page:
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_debtors', default='Total Debtors')}: {utils.format_currency(total_debtors)}")
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_creditors', default='Total Creditors')}: {utils.format_currency(total_creditors)}")
    else:
        p.showPage()
        draw_ficore_pdf_header(p, current_user, y_start=max_y)
        y = title_y - 0.6
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_debtors', default='Total Debtors')}: {utils.format_currency(total_debtors)}")
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_creditors', default='Total Creditors')}: {utils.format_currency(total_creditors)}")

    p.save()
    buffer.seek(0)
    logger.info(
        f"Generated debtors/creditors PDF for user {current_user.id}",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment; filename=debtors_creditors_report.pdf'})

def generate_debtors_creditors_csv(records):
    output = []
    output.extend(ficore_csv_header(current_user))
    output.append([trans('reports_debtors_creditors_report', default='Debtors/Creditors Report'), '', '', '', ''])
    output.append(['Date', 'Name', 'Type', 'Amount Owed', 'Description'])
    total_debtors = 0
    total_creditors = 0
    for r in records:
        output.append([
            utils.format_date(r['created_at']),
            utils.sanitize_input(r['name'], max_length=100),
            trans(f"general_{r['type']}", default=r['type']),
            utils.format_currency(r['amount_owed']),
            utils.sanitize_input(r['description'], max_length=1000)
        ])
        if r['type'] == 'debtor':
            total_debtors += r['amount_owed']
        else:
            total_creditors += r['amount_owed']
    output.append(['', '', '', f"{trans('reports_total_debtors', default='Total Debtors')}: {utils.format_currency(total_debtors)}", ''])
    output.append(['', '', '', f"{trans('reports_total_creditors', default='Total Creditors')}: {utils.format_currency(total_creditors)}", ''])
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerows(output)
    buffer.seek(0)
    logger.info(
        f"Generated debtors/creditors CSV for user {current_user.id}",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return Response(buffer.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=debtors_creditors_report.csv'})

def generate_customer_report_pdf(report_data):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    header_height = 0.7 * inch
    extra_space = 0.2 * inch
    row_height = 0.2 * inch
    bottom_margin = 0.5 * inch
    max_y = 10.5
    title_y = max_y - header_height - extra_space
    rows_per_page = int((max_y - bottom_margin - header_height - extra_space) // row_height)

    def draw_table_headers(y):
        p.setFillColor(colors.black)
        headers = [
            'Username', 'Email', 'Role', 'Trial', 'Trial End', 'Subscribed',
            'Debtors', 'Creditors', 'Receipts', 'Payments'
        ]
        x_positions = [0.5 * inch + i * 0.7 * inch for i in range(len(headers))]
        for header, x in zip(headers, x_positions):
            p.drawString(x, y * inch, header)
        return y - row_height, x_positions

    draw_ficore_pdf_header(p, current_user, y_start=max_y)
    p.setFont("Helvetica", 8)
    p.drawString(1 * inch, title_y * inch, trans('reports_customer_reports', default='Customer Reports'))
    p.drawString(1 * inch, (title_y - 0.3) * inch, f"{trans('general_generated', default='Generated')}: {utils.format_date(datetime.now(timezone.utc))}")
    y = title_y - 0.6
    y, x_positions = draw_table_headers(y)

    row_count = 0
    for data in report_data:
        if row_count >= rows_per_page:
            p.showPage()
            draw_ficore_pdf_header(p, current_user, y_start=max_y)
            y = title_y - 0.6
            y, x_positions = draw_table_headers(y)
            row_count = 0

        values = [
            data['username'][:15],
            data['email'][:15],
            data['role'],
            str(data['is_trial']),
            data['trial_end'],
            str(data['is_subscribed']),
            utils.format_currency(data['total_debtors']),
            utils.format_currency(data['total_creditors']),
            utils.format_currency(data['total_receipts']),
            utils.format_currency(data['total_payments'])
        ]
        for value, x in zip(values, x_positions):
            p.drawString(x, y * inch, str(value))
        y -= row_height
        row_count += 1

    p.save()
    buffer.seek(0)
    logger.info(
        f"Generated customer report PDF for user {current_user.id}",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment; filename=customer_report.pdf'})
def generate_customer_report_csv(report_data):
    output = []
    output.extend(ficore_csv_header(current_user))
    output.append([trans('reports_customer_reports', default='Customer Reports'), '', '', '', '', '', '', '', '', ''])
    headers = [
        'Username', 'Email', 'Role', 'Trial', 'Trial End', 'Subscribed',
        'Total Debtors', 'Total Creditors', 'Total Receipts', 'Total Payments'
    ]
    output.append(headers)
    for data in report_data:
        row = [
            data['username'],
            data['email'],
            data['role'],
            str(data['is_trial']),
            data['trial_end'],
            str(data['is_subscribed']),
            utils.format_currency(data['total_debtors']),
            utils.format_currency(data['total_creditors']),
            utils.format_currency(data['total_receipts']),
            utils.format_currency(data['total_payments'])
        ]
        output.append(row)
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerows(output)
    buffer.seek(0)
    logger.info(
        f"Generated customer report CSV for user {current_user.id}",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return Response(buffer.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=customer_report.csv'})
