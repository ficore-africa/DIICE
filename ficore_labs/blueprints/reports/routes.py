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

('/')

@utils.requires_role(['admin'])
def index():
    try:
        can_ser)
        er.info(
            f"Rendering reports index for user {current_user,
            extra={'}
        )
        return render_template(
         ',
            title=trans('report),
            can_interact=can_interact
        )
    except Exception as e:
        lr(
            f"Error loadin
            extra={'sd}
        )
        flash(trans('reports_load_error', default='An error occurred'), 'danger')
        r)

@reports_bp.route('/profit_loss', methods=['GET', 'T'])
red
@utils.requires_role(['trader', 'admin'])
@utils.limiter. minute')
def profit_loss():
    form = ReportForm()
    can_interact =
    if not can_interact:
        logger.warning(
            f"Subscriptirt",
            extra={'ses
        )
        flash(trans('subscription_required', default='Subscription required to generate reports. 
        r)
    cashflows = []
    query = {'user_id': str(current_user.id)}
    if form.valida
        try:
            if form.format.data n]:
            rror(
                    f"Invalid format {form.format.data} for pr",
                    extra={'s
                )
                flash(trans('reports_invalid_format', default='Invalid report format'), 'danger')
                rloss'))
            db = utils.get_mongo_db()
            if form.start_date.data:
                start_datetime = dateC"))
                query['created_at'] me}
            if form.end_date.data:
                end_datetime = datetime.combine(form.end_date.))
                query['created_at'
            cashflows = [to_dict_cashflow(cf) for cf in utils.safe_find_cashflows(db, query, 'created_at', -1)]
            output_format = form.format.data
            logger.info(
                f"Generating profit/loss rep
                extra={'}
            )
            if output_format == 'pdf':
             
            elif output_format == 'csv':
                return generate_profit_loss_csv(cashflows)
        except pymongo.errors.PyMongoErre:
            logger.error(
                f"MongoDB error generating profi",
                extra={'s
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
        exceps e:
            logger.error(
                f"Error genera
                extra={'s
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    else:
        try:
         b()
            -1)]
        except pymongo.errors.PyMongo e:
            logger.error(
                f"MongoDB error fetching cashflo}",
                extra={'sd}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
        excep
            logger.error(
                f"Error fetchir(e)}",
                extra={'sr.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    logger.in
        f"Rendering profit/loss report page for user {current_user.id}",
        extra={'
    )
    return render_template(
     
        form=form,
        cashflows=cashflows,
        title=trann')),
        can_interact=can_int
    )

@repo'])
@login_ruired
@utils.requi])
@utils.limiter.limit('10 pte')
def debtors_creditors
    form = ReportForm()
    can_interact = utils.can_user_interact(current_user)
    if nonteract:
        logger.warning(
            f"Subscription requt",
            extra={'session_id': sessio
        )
        flash(trans('subscriptio'warning')
        return redirect(url_for('subscribe_bp.subscribe'))
    records = []
    query = {'

        try:
            if v']:
                logger.error(
                    f"Invalid format id}",
                    extr
                )
                flash(trans('reports_invalid_format', deer')
                return r)
            db = utils.b()
            if form.start_date.data:
                start_datetime = datetime.combine(form.start_date.data, datetime.min.time(), tzin))
         
            if form.end_date.data:
                end_datetime = datetime.combine(form.end_d"))
                
            records = [to_dict_record(r) for , -1)]
            output_format = form..data
            ger.info(
                f"Generating debtors/creditors report for user}",
                extra={'sessi}
            )
            if output_format == 'pdf':
                rds)
            elif output_format == 'csv':
                return generate_debtors_creditors_csv(records)
        except pymongo.errors.PyMongos e:
            logger.error(
                f"MongoDB error generating debtors/creditors report for user {current_user.id}: {str(e)}",
                extra={'session_id': session.get('sid', 'no-sed}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
        except Exception as e:
            logger.error(
                f"Error generating debtors/c
                extra={'.id}
            )
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    else:
        try:
            db = utils.get_mongo_db()
            records = [to_dict_record(r)
        except pymongo.errors.PyMongoError as e:
            logger.error(
                f"MongoDBr(e)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            fger')
        except Exception as e:
            logger.error(
                f"Error f,
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            f')
    logger.info(
        f",
        extrser.id}
    )
    return render_template(
        'reports/debtors_creditors.html',
        form=form,
        records=records,
        title=trans('reports_debtors_creditors', default='Debtors/Creditors Report', lang=session.get
        can_ieract
    )

@reports_bp.route('/adminT'])
@login_required
@utils.requires_role('admin')
@utils.limitete')
def customer_reports():
    form = Custorm()
    can_interact = utils.can_user_interact(current_user)  # Should always be T admins
    if form.validate_on_submit():
     :
            role = utils.salse None
            report_format = form.format.d
            if rep']:
                logger.er(
                    f"Invalid format {report_format} for customer reports by user {current_user.id}",
                    extra={'sessid}
         )
        
            '))
            if role and ro'admin']:
                logge(
                    f"Invalid role {role} for customer reports by user {current_user.id}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_r.id}
            )
                flash(trans('reports_invalid_role', default='Invalid role selected'), 'danger')
                return redirect
            db = utils.get_mongo_db()
            pipeline =
                {'$match': {
                {'$lookup': {
                    'from': 'records'
              
': [
                        {'$match': {'$expr': {'$eq':
               
                            '_id': '$type'
                            'total_amowed'}
            }}
                    ],
                    'as': 'record_totals'
                }},
                {'$look
                    'from': 'cashflows',
                    'let': {'user_id': '$_id'},
         
                        {'$match': {'$expr': {'$eq': ['$user_id', '$user_id']}}},
                        {'$group': {
              type',
                            'total_amount': {unt'}
                        }}
            ],
                    'as': 'cashflow_totals'
                }}
            ]
            users = list(db.users.aggregate(pipeline))
            reporta = []
            for user in users:
                record_totals = {r['_id']: r['total_amounor': 0}
                cashflow_totals = {c[}
                data = {
                    'username': utils.sanitize_input(str(user['_id']), max_length=100),
                    'email': utils.sanitize_input(user.get('em
                    'role': utils.,
                    'is_trial': user.get('is_trial', False),
                    'trial_end': utils.format_date(user.get('trial_end')) if user.get('tri'-',
                    'is_subscribed': user.get('is_subscribed', False),
                    'total_debtors': record_0),
                    'tottor', 0),
                    'total_receipts': cashflow_totals.get('receipt', 0),
                    'total_payments': cashflow_totals.get('payment', 0)
             
                report_data.append(data)
            logger.info(
                f"Generating customer re",
                extra={'session_id': session.get.id}
            )
            if report_fortml':
                return render_template('reports/customer_reports.html', report_data=report_datt)
            elif report_format == 'pdf':
             ata)
            elif report_format == 'csv':
                return generatata)
        except pymongo.er
            logger.error(
                f"MongoDB error generating customer report for user {current_user.id}: {str(e)}",
             r.id}
            )
         
        exce e:
            logger.error(
                f"Error generating customer report for user {current_user.id}: {str(e)}",
                extra={'session_id': session.get
            )
            flash(trans('reports_generation_error', default='An error occurred while )
    logger.info(
        f"Ren,
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.i
    )
    return render_templat

def generate_profit_loss_pdf(cashflows):
    buffer = 
    p = canvas.Canvas(buffer, pagesize=A4)
    header_heigh 0.7
    extra_space = 0.2
    row_height = 0.3
    b.5
    max_y = 10.5
    title_y = max_y - header_
    page_height = nch
    rows_per_page = )

    def draw_table_headers(y):
     lack)
        'Date'))
        p.dr)
        p.drawString(4 * i
        p.drawString(ount'))
        return y - row_height

    draw_ax_y)
    p.setFont("Helvetica", 12)
    p.drawString(1 * inch, titlrt'))
    p.drawString(1 * inch, (title}")
    y = title_y - 0.6
    y = draw_table_heade)

    total_income = 0
    total_expee = 0


    for t in ca
        if row_count >= rows_per_page:
            p.showPage()
            draw
            y = title_y - 0.6
            y = draw_table_headers(y)
            row_count = 0

        p.drawString(1 * inch, y * inch, utils.format_date(t['created_at']))
        p.drawString(2.5 * inch, y * inch, utils.sanitize_input(t['party_name'], max_length=100))
        p))
        p.drawString(5 * inch, y * inch, utils.format_currency(t['amount']))
        if t['type'] == 'receipt':
            total_]
        else:
            total_expense += t['a
        y -=t
        row_count += 1

    if row_count + 3 <= rows_per_page:
        y -= row_height
        p.drawStr
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_to")
        y -= row_height
        p.drawString(1 * inch, y * i")
    else:
        p.showPage()
        draw_ficore_pdf_header(p, 
        y = title_y - 0.6
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_income', default='Total I}")
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{)
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_net_profit', default='Net Profit')}: {ut)

    p.save()
    buffer.seek(0)
    logger.info(
        f"Generated profit/loss PDF for ",
        extra={'session_id': session.get('sid', 'no-sess
    )
    return Response(buffedf'})

def generate_profit_loss_csv(cashflows):
    output = []
    output.extend(ficore_csv_header(current_user))
    output.append([trans('gene')])
    total_income = 0
    total_expense = 0
    for t in cashflows:
        outpuunt'])])
        if t['type'] == 'receipt':
         unt']
        else
            total_expense += t['amoun]
    output.append(['', '', '', f"{trans('reports_total_income', default='Total Income')}: {utils.forma
    output.append(['', '', '', f"{trans('reports)}"])
    output.append(['', ''
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.wr)
    buffer.seek(0)
    logger.info(
        f"Generated profi",
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': curruser.id}
    )
    return Recsv'})

def generate_deb):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    h 0.7
    extra_space = 0.2
    row_height = 0.3
    bottom_margin  0.5
    max_y = 10.5
    title_y = max_y - header_height - extra_space
    page_height = (max_y - bottom * inch
    r

    def draw
        p.setFillColor(colblack)
        p.drawString(
        p.drawString(2.5 * inch, y * inch, trans('general_name', default='Name'))
        p.drawString(4 * inch, y * inch, trans('general_type', default='Type'))
        ped'))
        p.drawString(6.5 * inch, y * inch, trans('general_description', default='Description'))
        return y - row_height

    draw_ficore_pdf_hert=max_y)
    p.setFont("Helvetica", 12)
    p.drawString(1 * inch, title_y * inch, trans('reports_debtors_creditors_report', default='Debtors/Cre
    p.drawString(1 * inch, (title_y -")
    y = title_6


    total_debto
    total_creditors = 0
    row_count = 0

    for r in records:
        if row_count >= rows_per_page:
            p.showPage()
            draw_ficorey)
            y = title_y - 0.6
            y = draw_table_headers(y)
          0

        p.drawString(1 * inch, y * inch, utils.format_date))
        p.drawSt100))
        p.drawString(4 * inch, y * inch, tran']))
        p.drawString(5 * inch, y ]))
        p.dr20))
        if r['type'] == 'debtor':
            total_debtors += 
        else:
            total_creditors += r['amount_owed']
        y -= row_
        row_count += 1

    if row_count + 2 <= rows_per_page
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_debtors', default='Total Debtors')}: {utils.format_}")
        y -= row_height
        p.drawString(1 * inch, y *
    else:
        p.showPage()
        draw_ficore_pdf_header(p, current_user, y_start=max_y)
        y = title_y - 0.6
        p.drawString(1 *)}")
        y -= row_height
        p.drawString(1 * inch, y * inch, f"{trans('reports_total_creditors', default='Total Creditorsitors)}")

    p.save()
    buffer.seek(0)
    logger.info(
        f"Generated debtors/creditors PDF for user {current_uid}",
        extra={'session_id': session.get('sid', d}
    )
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachmendf'})

def generate_
    output = []
    output.extend(ficore_csv_hr))
    output.append([trans()
    total_debtors = 0
    total_creditors = 0
    for r in rds:
        output.append([utils.format_date(r['created_at']), utils.sanitize_input(r['name'], 000)])
        i 'debtor':
            
        else:
            total_creditors += r['amount_owed']
    output.append(['', '', '', f"{trans('reports}", ''])
    output.append(['', ''''])
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.wrput)
    buffer.seek(0)
    logger.info(
        f"Generated debto
        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
    )
    return Rev'})

def generate_cust_data):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    hght = 0.7
    extra_space = 0.2
    row_height = 0.2
    bottom_margin 0.5
    max_y = 10.5
    title_y = max_y - header_height - extra_space
    page_height = (max_y - bottom inch
    r* inch))

    def draw(y):
        p.setFillColor(col)
        headers = [
            'Username', 'Email', 'Role', 'Trial', 'Trial End', 'Subscribed',
            'Debtors', 'Creditors', 'Receipts', 'Payments'
        ]
        x_positions = [0.5 * inch + i * 0.7 * inch for i in range(len(headers))]
        for header, x in zip(heions):
            p.drawString(x, y * inch, header)
        return y - rows

    draw_ficore_pdf_header(p, current_user, y_start=max_y)
    p.setFont("Helvetica", 8)
    p.drawStri
")
    y = title_y - 0.6
    y, x_positi

    row_count = 0
    for data in report_
        if row_count >= rows_pee:
            p.showPage()
            draw_ficore_pdf_heade_y)
            
            y, x_positions = draw_table_headers(y)
            row_count = 0

        values = [
            data['username'][:15],
            data['email'][:15],
            data[ole'],
            str(data['is_trial']),
            data['trial_end'],
            str(data['is_subscribed']),
            utils.format_curr']),
            utils.format_currency(data['total_creditors']),
            utils.format_currency(data['total_receipts']),
            utils])
        ]
        for value, x in zip(values, x_positions):
            p.drawString(x, y * inch,)
        y -= row_height
        row_count += 1

    p.save()
    buffer.seek(0)
    return Response(buffer, mimet.pdf'})

def generate_customer_report_csv(repa):
    output = []
    output.extend(ficore_csv_header(current_user))
    headers = [
        'Username', 'Ebscribed',
        'Total Debtors', 'Total Creditorsments'
    ]
    output.append(headers)
    for data in report_data:
        row = [
            data['username'], dat
            utils.format_currency(data['total_debtors']), utils.format_currency(da']),
            utils.format_currency(da
        ]
        output.append(row)
    buffer = StringIO()
    writer = csv.write\n')
    writer.writerows(output)
    buffer.seek(0)
    return Response(buffer.geeport.csv'})r_re=customefilenamnt; 'attachme':ispositionontent-D'C headers={t/csv',metype='tex), mitvalue(