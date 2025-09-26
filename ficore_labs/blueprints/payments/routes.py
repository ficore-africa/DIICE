from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, jsonify, session
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFError
from translations import trans
import utils
from utils import serialize_for_json, safe_json_response, clean_document_for_json, bulk_clean_documents_for_json, safe_parse_datetime
from bson import ObjectId
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from wtforms import StringField, DateField, FloatField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, NumberRange
import logging
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

logger = logging.getLogger(__name__)

# Define expense categories (consistent with templates)
expense_categories = {
    'office_admin': {
        'name': trans('category_office_admin', default='Office & Admin'),
        'description': trans('category_office_admin_desc', default='Office supplies, stationery, internet/data, utility bills'),
        'examples': [
            trans('example_office_supplies', default='Office supplies'),
            trans('example_stationery', default='Stationery'),
            trans('example_internet', default='Internet/Data'),
            trans('example_electricity', default='Electricity')
        ],
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'staff_wages': {
        'name': trans('category_staff_wages', default='Staff & Wages'),
        'description': trans('category_staff_wages_desc', default='Employee salaries, wages, and related costs'),
        'examples': [
            trans('example_salaries', default='Salaries'),
            trans('example_wages', default='Wages'),
            trans('example_staff_benefits', default='Staff benefits'),
            trans('example_payroll', default='Payroll costs')
        ],
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'business_travel': {
        'name': trans('category_business_travel', default='Business Travel & Transport'),
        'description': trans('category_business_travel_desc', default='Fuel, vehicle maintenance, and travel expenses for business'),
        'examples': [
            trans('example_fuel', default='Fuel'),
            trans('example_vehicle_maintenance', default='Vehicle maintenance'),
            trans('example_business_travel', default='Business travel'),
            trans('example_transport', default='Transport costs')
        ],
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'rent_utilities': {
        'name': trans('category_rent_utilities', default='Rent & Utilities'),
        'description': trans('category_rent_utilities_desc', default='Rent for shop or business office'),
        'examples': [
            trans('example_shop_rent', default='Shop rent'),
            trans('example_office_rent', default='Office rent'),
            trans('example_business_premises', default='Business premises rent')
        ],
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'marketing_sales': {
        'name': trans('category_marketing_sales', default='Marketing & Sales'),
        'description': trans('category_marketing_sales_desc', default='Advertising, social media promotion, business cards'),
        'examples': [
            trans('example_advertising', default='Advertising'),
            trans('example_social_media', default='Social media promotion'),
            trans('example_business_cards', default='Business cards')
        ],
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'cogs': {
        'name': trans('category_cogs', default='Cost of Goods Sold (COGS)'),
        'description': trans('category_cogs_desc', default='Direct costs of producing goods or services'),
        'examples': [
            trans('example_raw_materials', default='Raw materials'),
            trans('example_manufacturing', default='Manufacturing costs'),
            trans('example_direct_labor', default='Direct labor')
        ],
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'personal_expenses': {
        'name': trans('category_personal_expenses', default='Personal Expenses'),
        'description': trans('category_personal_expenses_desc', default='Personal expenses not related to business'),
        'examples': [
            trans('example_personal_meals', default='Personal meals'),
            trans('example_personal_shopping', default='Personal shopping'),
            trans('example_family_expenses', default='Family expenses')
        ],
        'tax_deductible': False,
        'is_personal': True,
        'is_statutory': False
    },
    'statutory_legal': {
        'name': trans('category_statutory_legal', default='Statutory & Legal Contributions'),
        'description': trans('category_statutory_legal_desc', default='Accounting, legal, and consulting fees directly related to business'),
        'examples': [
            trans('example_accounting_fees', default='Accounting fees'),
            trans('example_legal_fees', default='Legal fees'),
            trans('example_consulting_fees', default='Consulting fees')
        ],
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': True
    }
}

class PaymentForm(FlaskForm):
    """Form for adding or editing a payment cashflow."""
    party_name = StringField(trans('payments_recipient_name', default='Recipient Name'), validators=[DataRequired(), Length(max=100)])
    date = DateField(trans('general_date', default='Date'), validators=[DataRequired()])
    amount = FloatField(trans('payments_amount', default='Amount'), validators=[DataRequired(), NumberRange(min=0.01)])
    method = SelectField(trans('general_payment_method', default='Payment Method'), choices=[
        ('cash', trans('general_cash', default='Cash')),
        ('card', trans('general_card', default='Card')),
        ('bank', trans('general_bank_transfer', default='Bank Transfer'))
    ], validators=[Optional()])
    expense_category = SelectField(trans('general_expense_category', default='Expense Category'), 
                                 choices=[], validators=[DataRequired()])
    contact = StringField(trans('general_contact', default='Contact'), validators=[Optional(), Length(max=100)])
    description = StringField(trans('general_description', default='Description'), validators=[Optional(), Length(max=1000)])
    submit = SubmitField(trans('payments_add_payment', default='Add Payment'))
    
    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)
        try:
            # Populate expense category choices from expense_categories
            self.expense_category.choices = [
                (key, value['name']) for key, value in expense_categories.items()
            ]
        except Exception as e:
            logger.warning(f"Failed to load expense category choices: {str(e)}")
            # Fallback to minimal categories
            self.expense_category.choices = [
                ('office_admin', trans('category_office_admin', default='Office & Admin')),
                ('staff_wages', trans('category_staff_wages', default='Staff & Wages')),
                ('personal_expenses', trans('category_personal_expenses', default='Personal Expenses'))
            ]

payments_bp = Blueprint('payments', __name__, url_prefix='/payments')

def fetch_payments_with_fallback(db, query, sort_field='created_at', sort_direction=-1, limit=50):
    """Fetch payments with fallback logic for robustness."""
    payments = utils.safe_find_cashflows(db, query, sort_field=sort_field, sort_direction=sort_direction)
    if not payments:
        try:
            test_count = db.cashflows.count_documents(query, hint=[('user_id', 1), ('type', 1)])
            if test_count > 0:
                logger.warning(
                    f"Found {test_count} payments for user {current_user.id} but safe_find returned empty",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                raw_payments = list(db.cashflows.find(query, hint=[('user_id', 1), ('type', 1)]).sort(sort_field, sort_direction).limit(limit))
                payments = []
                for payment in raw_payments:
                    try:
                        from models import to_dict_cashflow
                        cleaned_payment = to_dict_cashflow(payment)
                        if cleaned_payment:
                            payments.append(cleaned_payment)
                    except Exception as clean_error:
                        logger.debug(f"Failed to clean payment record {payment.get('_id', 'unknown')}: {str(clean_error)}")
                        continue
                logger.info(f"Fallback cleaning recovered {len(payments)} payments for user {current_user.id}")
        except Exception as fallback_error:
            logger.error(
                f"Fallback query failed for user {current_user.id}: {str(fallback_error)}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
    return payments

def normalize_datetime(doc):
    """Convert created_at to timezone-aware datetime if it's a string or naive datetime."""
    if 'created_at' in doc:
        doc['created_at'] = safe_parse_datetime(doc['created_at'])
    return doc

@payments_bp.route('/')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def index():
    """List all payment cashflows for the current user."""
    try:
        db = utils.get_mongo_db()
        utils.audit_datetime_fields(db, 'cashflows')  # Run audit
        query = {'user_id': str(current_user.id), 'type': 'payment'}
        
        payments = [normalize_datetime(doc) for doc in fetch_payments_with_fallback(db, query)]
        category_stats = utils.calculate_payment_category_stats(payments)
        
        return render_template(
            'payments/index.html',
            payments=payments,
            category_stats=category_stats,
            format_currency=utils.format_currency,
            format_date=utils.format_date,
            title=trans('payments_title', default='Money Out', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user),
            expense_categories=expense_categories
        )
    except Exception as e:
        logger.error(
            f"Error fetching payments for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_fetch_error', default='An error occurred while loading your payments. Please try again.'), 'danger')
        return redirect(url_for('dashboard.index'))

@payments_bp.route('/manage')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def manage():
    """Manage all payment cashflows for the current user (edit/delete)."""
    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id), 'type': 'payment'}
        
        payments = [normalize_datetime(doc) for doc in fetch_payments_with_fallback(db, query)]
        category_stats = utils.calculate_payment_category_stats(payments)
        
        return render_template(
            'payments/manage.html',
            payments=payments,
            category_stats=category_stats,
            format_currency=utils.format_currency,
            format_date=utils.format_date,
            title=trans('payments_manage', default='Manage Payments', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user),
            expense_categories=expense_categories,
            form=PaymentForm()  # For delete form CSRF token
        )
    except Exception as e:
        logger.error(
            f"Error fetching payments for manage page for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_fetch_error', default='An error occurred while loading your payments. Please try again.'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/view/<id>')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('20 per minute')
def view(id):
    """View detailed information about a specific payment."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query, hint=[('_id', 1)])
        if not payment:
            logger.warning(
                f"Payment {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return safe_json_response({'error': trans('payments_record_not_found', default='Record not found')}, 404)
        
        payment = normalize_datetime(payment)
        required_fields = ['party_name', 'amount', 'created_at']
        for field in required_fields:
            if field not in payment:
                logger.warning(
                    f"Payment {id} missing required field {field} for user {current_user.id}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                return safe_json_response({'error': trans('payments_invalid_data', default='Invalid payment data')}, 500)
        
        payment.setdefault('method', 'N/A')
        payment.setdefault('expense_category', 'office_admin')
        payment.setdefault('contact', '')
        payment.setdefault('description', '')
        
        from models import to_dict_cashflow
        payment = to_dict_cashflow(payment)
        return safe_json_response(payment)
    except ValueError:
        logger.error(
            f"Invalid payment ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return safe_json_response({'error': trans('payments_invalid_id', default='Invalid payment ID')}, 404)
    except Exception as e:
        logger.error(
            f"Error fetching payment {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return safe_json_response({'error': trans('payments_fetch_error', default='An error occurred')}, 500)

@payments_bp.route('/generate_pdf/<id>')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def generate_pdf(id):
    """Generate PDF receipt for a payment transaction."""
    try:
        if not utils.can_user_interact(current_user):
            flash(trans('payments_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to generate a PDF receipt.'), 'warning')
            return redirect(url_for('subscribe_bp.subscribe'))
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query, hint=[('_id', 1)])
        if not payment:
            logger.warning(
                f"Payment {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('payments_record_not_found', default='Record not found'), 'danger')
            return redirect(url_for('payments.index'))
        
        payment = normalize_datetime(payment)
        from models import to_dict_cashflow
        payment = to_dict_cashflow(payment)
        
        payment['party_name'] = utils.sanitize_input(payment['party_name'], max_length=100)
        category_display = payment.get('category_metadata', {}).get('category_display_name', 
                                     payment.get('expense_category', 'No category provided'))
        payment['category_display'] = utils.sanitize_input(category_display, max_length=50)
        payment['contact'] = utils.sanitize_input(payment.get('contact', ''), max_length=100) if payment.get('contact') else ''
        payment['description'] = utils.sanitize_input(payment.get('description', ''), max_length=1000) if payment.get('description') else ''
        
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        styles = getSampleStyleSheet()
        max_width = width - 2 * inch

        p.setFont("Helvetica-Bold", 24)
        p.drawString(inch, height - inch, trans('payments_pdf_title', default='FiCore Records - Money Out Receipt'))

        p.setFont("Helvetica", 12)
        y_position = height - inch - 0.5 * inch
        fields = [
            (trans('payments_recipient_name', default='Recipient'), payment['party_name']),
            (trans('payments_amount', default='Amount Paid'), utils.format_currency(payment['amount'])),
            (trans('general_payment_method', default='Payment Method'), payment.get('method', 'N/A')),
            (trans('general_category', default='Category'), payment['category_display']),
            (trans('general_date', default='Date'), utils.format_date(payment['created_at'])),
            (trans('payments_id', default='Payment ID'), payment['id'])
        ]
        for label, value in fields:
            p.drawString(inch, y_position, f"{label}:")
            text = Paragraph(str(value), styles['Normal'])
            text.wrapOn(p, max_width - inch, 100)
            text.drawOn(p, inch + 100, y_position - 10)
            y_position -= 0.3 * inch

        if payment['contact']:
            p.drawString(inch, y_position, f"{trans('general_contact', default='Contact')}:")
            text = Paragraph(payment['contact'], styles['Normal'])
            text.wrapOn(p, max_width - inch, 100)
            text.drawOn(p, inch + 100, y_position - 10)
            y_position -= 0.3 * inch

        if payment['description']:
            p.drawString(inch, y_position, f"{trans('general_description', default='Description')}:")
            text = Paragraph(payment['description'], styles['Normal'])
            text.wrapOn(p, max_width - inch, 200)
            text.drawOn(p, inch + 100, y_position - 10)
            y_position -= text.height + 0.3 * inch

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(inch, inch, trans('payments_pdf_footer', default='This document serves as an official payment receipt generated by FiCore Records.'))
        p.showPage()
        p.save()
        buffer.seek(0)
        return Response(
            buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=payment_{utils.sanitize_input(payment["party_name"], max_length=50)}_{payment["id"]}.pdf'
            }
        )
    except ValueError:
        logger.error(
            f"Invalid payment ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_invalid_id', default='Invalid payment ID'), 'danger')
        return redirect(url_for('payments.index'))
    except Exception as e:
        logger.error(
            f"Error generating PDF for payment {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_pdf_generation_error', default='An error occurred'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/add', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('10 per minute')
def add():
    """Add a new payment cashflow."""
    try:
        if not utils.can_user_interact(current_user):
            flash(trans('payments_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to add a payment.'), 'warning')
            return redirect(url_for('subscribe_bp.subscribe'))
        
        form = PaymentForm()
        if form.validate_on_submit():
            try:
                from models import create_cashflow
                form_data = {
                    'party_name': form.party_name.data,
                    'date': form.date.data,
                    'amount': form.amount.data,
                    'expense_category': form.expense_category.data,
                    'method': form.method.data,
                    'contact': form.contact.data,
                    'description': form.description.data
                }
                
                is_valid, validation_errors = utils.validate_payment_form_data(form_data)
                if not is_valid:
                    for field, error in validation_errors.items():
                        if hasattr(form, field):
                            getattr(form, field).errors.append(error)
                        else:
                            flash(error, 'danger')
                    return render_template(
                        'payments/add.html',
                        form=form,
                        title=trans('payments_add_title', default='Add Money Out', lang=session.get('lang', 'en')),
                        can_interact=utils.can_user_interact(current_user),
                        expense_categories=expense_categories
                    )
                
                db = utils.get_mongo_db()
                payment_date = safe_parse_datetime(datetime.combine(form.date.data, datetime.min.time(), tzinfo=ZoneInfo('UTC')))
                category_metadata = utils.get_category_metadata(form.expense_category.data)
                
                cashflow = {
                    'user_id': str(current_user.id),
                    'type': 'payment',
                    'party_name': utils.sanitize_input(form.party_name.data, max_length=100),
                    'amount': form.amount.data,
                    'method': form.method.data,
                    'expense_category': form.expense_category.data,
                    'is_tax_deductible': utils.is_category_tax_deductible(form.expense_category.data),
                    'tax_year': utils.extract_tax_year_from_date(payment_date),
                    'category_metadata': {
                        'category_display_name': category_metadata.get('name', ''),
                        'is_personal': category_metadata.get('is_personal', False),
                        'is_statutory': category_metadata.get('is_statutory', False)
                    },
                    'contact': utils.sanitize_input(form.contact.data, max_length=100) if form.contact.data else None,
                    'description': utils.sanitize_input(form.description.data, max_length=1000) if form.description.data else None,
                    'created_at': payment_date,
                    'updated_at': safe_parse_datetime(datetime.now(tz=ZoneInfo('UTC')))
                }
                create_cashflow(db, cashflow)
                logger.info(
                    f"Payment added for user {current_user.id}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('payments_add_success', default='Payment added successfully'), 'success')
                return redirect(url_for('payments.index'))
            except Exception as e:
                logger.error(
                    f"Error adding payment for user {current_user.id}: {str(e)}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('payments_add_error', default='An error occurred'), 'danger')
        return render_template(
            'payments/add.html',
            form=form,
            title=trans('payments_add_title', default='Add Money Out', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user),
            expense_categories=expense_categories
        )
    except CSRFError as e:
        logger.error(
            f"CSRF error in adding payment for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return redirect(url_for('payments.index')), 400

@payments_bp.route('/edit/<id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('10 per minute')
def edit(id):
    """Edit an existing payment cashflow."""
    try:
        if not utils.can_user_interact(current_user):
            flash(trans('payments_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to edit payments.'), 'warning')
            return redirect(url_for('subscribe_bp.subscribe'))
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query, hint=[('_id', 1)])
        if not payment:
            logger.warning(
                f"Payment {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
            return redirect(url_for('payments.index'))
        
        payment = normalize_datetime(payment)
        from models import to_dict_cashflow
        payment = to_dict_cashflow(payment)
        
        form = PaymentForm(data={
            'party_name': payment['party_name'],
            'date': safe_parse_datetime(payment['created_at']).date(),
            'amount': payment['amount'],
            'method': payment.get('method'),
            'expense_category': payment.get('expense_category', 'office_admin'),
            'contact': payment.get('contact'),
            'description': payment.get('description')
        })
        if form.validate_on_submit():
            try:
                from models import update_cashflow
                form_data = {
                    'party_name': form.party_name.data,
                    'date': form.date.data,
                    'amount': form.amount.data,
                    'expense_category': form.expense_category.data,
                    'method': form.method.data,
                    'contact': form.contact.data,
                    'description': form.description.data
                }
                
                is_valid, validation_errors = utils.validate_payment_form_data(form_data)
                if not is_valid:
                    for field, error in validation_errors.items():
                        if hasattr(form, field):
                            getattr(form, field).errors.append(error)
                        else:
                            flash(error, 'danger')
                    return render_template(
                        'payments/edit.html',
                        form=form,
                        payment=payment,
                        title=trans('payments_edit_title', default='Edit Payment', lang=session.get('lang', 'en')),
                        can_interact=utils.can_user_interact(current_user),
                        expense_categories=expense_categories
                    )
                
                payment_date = safe_parse_datetime(datetime.combine(form.date.data, datetime.min.time(), tzinfo=ZoneInfo('UTC')))
                category_metadata = utils.get_category_metadata(form.expense_category.data)
                
                updated_cashflow = {
                    'party_name': utils.sanitize_input(form.party_name.data, max_length=100),
                    'amount': form.amount.data,
                    'method': form.method.data,
                    'expense_category': form.expense_category.data,
                    'is_tax_deductible': utils.is_category_tax_deductible(form.expense_category.data),
                    'tax_year': utils.extract_tax_year_from_date(payment_date),
                    'category_metadata': {
                        'category_display_name': category_metadata.get('name', ''),
                        'is_personal': category_metadata.get('is_personal', False),
                        'is_statutory': category_metadata.get('is_statutory', False)
                    },
                    'contact': utils.sanitize_input(form.contact.data, max_length=100) if form.contact.data else None,
                    'description': utils.sanitize_input(form.description.data, max_length=1000) if form.description.data else None,
                    'created_at': payment_date,
                    'updated_at': safe_parse_datetime(datetime.now(tz=ZoneInfo('UTC')))
                }
                update_cashflow(db, id, updated_cashflow)
                logger.info(
                    f"Payment {id} updated for user {current_user.id}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('payments_edit_success', default='Payment updated successfully'), 'success')
                return redirect(url_for('payments.index'))
            except Exception as e:
                logger.error(
                    f"Error updating payment {id} for user {current_user.id}: {str(e)}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('payments_edit_error', default='An error occurred'), 'danger')
        return render_template(
            'payments/edit.html',
            form=form,
            payment=payment,
            title=trans('payments_edit_title', default='Edit Payment', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user),
            expense_categories=expense_categories
        )
    except ValueError:
        logger.error(
            f"Invalid payment ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_invalid_id', default='Invalid payment ID'), 'danger')
        return redirect(url_for('payments.index'))
    except CSRFError as e:
        logger.error(
            f"CSRF error in editing payment {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return redirect(url_for('payments.index')), 400
    except Exception as e:
        logger.error(
            f"Error fetching payment {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/delete/<id>', methods=['POST'])
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('10 per minute')
def delete(id):
    """Delete a payment cashflow."""
    try:
        if not utils.can_user_interact(current_user):
            flash(trans('payments_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to delete payments.'), 'warning')
            return redirect(url_for('subscribe_bp.subscribe'))
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        result = db.cashflows.delete_one(query, hint=[('_id', 1)])
        if result.deleted_count:
            logger.info(
                f"Payment {id} deleted for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('payments_delete_success', default='Payment deleted successfully'), 'success')
        else:
            logger.warning(
                f"Payment {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
        return redirect(url_for('payments.index'))
    except ValueError:
        logger.error(
            f"Invalid payment ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_invalid_id', default='Invalid payment ID'), 'danger')
        return redirect(url_for('payments.index'))
    except CSRFError as e:
        logger.error(
            f"CSRF error in deleting payment {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return redirect(url_for('payments.index')), 400
    except Exception as e:
        logger.error(
            f"Error deleting payment {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_delete_error', default='An error occurred'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/share', methods=['POST'])
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('10 per minute')
def share():
    """Share a payment receipt via SMS or WhatsApp."""
    try:
        if not utils.can_user_interact(current_user):
            return safe_json_response({
                'success': False,
                'message': trans('payments_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to share payments.')
            }, 403)
        
        data = request.get_json()
        payment_id = data.get('paymentId')
        recipient = utils.sanitize_input(data.get('recipient'), max_length=100)
        message = utils.sanitize_input(data.get('message'), max_length=1000)
        share_type = data.get('type')
        
        if not all([payment_id, recipient, message, share_type]):
            logger.error(
                f"Missing fields in share payment request for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return safe_json_response({
                'success': False,
                'message': trans('payments_missing_fields', default='Missing required fields')
            }, 400)
        
        valid_share_types = ['sms', 'whatsapp']
        if share_type not in valid_share_types:
            logger.error(
                f"Invalid share type {share_type} in share payment request for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return safe_json_response({
                'success': False,
                'message': trans('payments_invalid_share_type', default='Invalid share type')
            }, 400)
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(payment_id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query, hint=[('_id', 1)])
        if not payment:
            logger.warning(
                f"Payment {payment_id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return safe_json_response({
                'success': False,
                'message': trans('payments_record_not_found', default='Payment not found')
            }, 404)
        
        payment = normalize_datetime(payment)
        success = utils.send_message(recipient=recipient, message=message, type=share_type)
        if success:
            logger.info(
                f"Payment {payment_id} shared via {share_type} for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return safe_json_response({'success': True})
        else:
            logger.error(
                f"Failed to share payment {payment_id} via {share_type} for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return safe_json_response({
                'success': False,
                'message': trans('payments_share_failed', default='Failed to share payment')
            }, 500)
    except ValueError:
        logger.error(
            f"Invalid payment ID {payment_id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return safe_json_response({
            'success': False,
            'message': trans('payments_invalid_id', default='Invalid payment ID')
        }, 404)
    except CSRFError as e:
        logger.error(
            f"CSRF error in sharing payment {payment_id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return safe_json_response({
            'success': False,
            'message': trans('payments_csrf_error', default='Invalid CSRF token. Please try again.')
        }, 400)
    except Exception as e:
        logger.error(
            f"Error sharing payment {payment_id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return safe_json_response({
            'success': False,
            'message': trans('payments_share_error', default='Error sharing payment')
        }, 500)
