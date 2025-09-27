from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFError
from translations import trans
import utils
from bson import ObjectId
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from wtforms import StringField, DateField, FloatField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, NumberRange
import logging
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

logger = logging.getLogger(__name__)

# Simplified expense categories without redundant sanitization
expense_categories = {
    'office_admin': {
        'name': trans('category_office_admin', default='Office and Admin'),
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'staff_wages': {
        'name': trans('category_staff_wages', default='Staff and Wages'),
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'business_travel': {
        'name': trans('category_business_travel', default='Business Travel and Transport'),
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'rent_utilities': {
        'name': trans('category_rent_utilities', default='Rent and Utilities'),
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'marketing_sales': {
        'name': trans('category_marketing_sales', default='Marketing and Sales'),
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'cogs': {
        'name': trans('category_cogs', default='Cost of Goods Sold'),
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False
    },
    'personal_expenses': {
        'name': trans('category_personal_expenses', default='Personal Expenses'),
        'tax_deductible': False,
        'is_personal': True,
        'is_statutory': False
    },
    'statutory_contributions': {
        'name': trans('category_statutory_contributions', default='Statutory and Legal Contributions'),
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
                                 choices=[(key, value['name']) for key, value in expense_categories.items()],
                                 validators=[DataRequired()])
    contact = StringField(trans('general_contact', default='Contact'), validators=[Optional(), Length(max=100)])
    description = StringField(trans('general_description', default='Description'), validators=[Optional(), Length(max=1000)])
    submit = SubmitField(trans('payments_add_payment', default='Add Payment'))

payments_bp = Blueprint('payments', __name__, url_prefix='/payments')

def normalize_datetime(doc):
    """Convert created_at to timezone-aware datetime if naive."""
    if 'created_at' in doc and doc['created_at'].tzinfo is None:
        doc['created_at'] = doc['created_at'].replace(tzinfo=ZoneInfo("UTC"))
    if 'updated_at' in doc and doc['updated_at'] and doc['updated_at'].tzinfo is None:
        doc['updated_at'] = doc['updated_at'].replace(tzinfo=ZoneInfo("UTC"))
    return doc

def process_payment_data(payment):
    """Process payment data for display, adding formatted fields."""
    payment = normalize_datetime(payment.copy())
    payment['formatted_amount'] = utils.format_currency(payment.get('amount', 0), currency='₦')
    payment['formatted_date'] = utils.format_date(payment.get('created_at'), format_type='short') if payment.get('created_at') else 'N/A'
    return payment

@payments_bp.route('/')
@login_required
@utils.requires_role(['trader', 'admin'])
def index():
    """List all payment cashflows for the current user."""
    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id), 'type': 'payment'}
        payments = list(db.cashflows.find(query).sort('created_at', -1))
        
        cleaned_payments = [process_payment_data(payment) for payment in payments]
        
        return render_template(
            'payments/index.html',
            payments=cleaned_payments,
            category_stats=utils.calculate_payment_category_stats(cleaned_payments),
            title=trans('payments_title', default='Money Out'),
            can_interact=utils.can_user_interact(current_user),
            expense_categories=expense_categories
        )
    except Exception as e:
        logger.error(f"Error fetching payments for user {current_user.id}: {str(e).replace('\\', '\\\\')}")
        flash(trans('payments_fetch_error', default='An error occurred while loading your payments. Please try again.'), 'danger')
        return redirect(url_for('dashboard.index'))

@payments_bp.route('/manage')
@login_required
@utils.requires_role(['trader', 'admin'])
def manage():
    """Manage all payment cashflows for the current user (edit/delete)."""
    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id), 'type': 'payment'}
        payments = list(db.cashflows.find(query).sort('created_at', -1))
        
        cleaned_payments = [process_payment_data(payment) for payment in payments]
        
        return render_template(
            'payments/manage.html',
            payments=cleaned_payments,
            category_stats=utils.calculate_payment_category_stats(cleaned_payments),
            title=trans('payments_manage', default='Manage Payments'),
            can_interact=utils.can_user_interact(current_user),
            expense_categories=expense_categories,
            form=PaymentForm()
        )
    except Exception as e:
        logger.error(f"Error fetching payments for manage page for user {current_user.id}: {str(e).replace('\\', '\\\\')}")
        flash(trans('payments_fetch_error', default='An error occurred while loading your payments. Please try again.'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/view/<id>')
@login_required
@utils.requires_role(['trader', 'admin'])
@utils.limiter.limit('20 per minute')
def view(id):
    """View detailed information about a specific payment."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query, hint=[('_id', 1)])
        if not payment:
            logger.warning(f"Payment {id} not found for user {current_user.id}")
            return utils.safe_json_response({'error': trans('payments_record_not_found', default='Record not found')}, 404)
        
        payment = process_payment_data(payment)
        from models import to_dict_cashflow
        payment = to_dict_cashflow(payment)
        
        return utils.safe_json_response(payment)
    except ValueError:
        logger.error(f"Invalid payment ID {id} for user {current_user.id}")
        return utils.safe_json_response({'error': trans('payments_invalid_id', default='Invalid payment ID')}, 404)
    except Exception as e:
        logger.error(f"Error fetching payment {id} for user {current_user.id}: {str(e).replace('\\', '\\\\')}")
        return utils.safe_json_response({'error': trans('payments_fetch_error', default='An error occurred')}, 500)

@payments_bp.route('/generate_pdf/<id>')
@login_required
@utils.requires_role(['trader', 'admin'])
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
            logger.warning(f"Payment {id} not found for user {current_user.id}")
            flash(trans('payments_record_not_found', default='Record not found'), 'danger')
            return redirect(url_for('payments.index'))
        
        payment = process_payment_data(payment)
        from models import to_dict_cashflow
        payment = to_dict_cashflow(payment)
        payment['category_display'] = expense_categories.get(payment.get('expense_category', 'office_admin'), {}).get('name', 'No category')
        
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
            (trans('payments_amount', default='Amount Paid'), payment['formatted_amount']),
            (trans('general_payment_method', default='Payment Method'), payment.get('method', 'N/A')),
            (trans('general_category', default='Category'), payment['category_display']),
            (trans('general_date', default='Date'), payment['formatted_date']),
            (trans('payments_id', default='Payment ID'), payment['id'])
        ]
        for label, value in fields:
            p.drawString(inch, y_position, f"{label}:")
            text = Paragraph(str(value), styles['Normal'])
            text.wrapOn(p, max_width - inch, 100)
            text.drawOn(p, inch + 100, y_position - 10)
            y_position -= 0.3 * inch

        if payment.get('contact'):
            p.drawString(inch, y_position, f"{trans('general_contact', default='Contact')}:")
            text = Paragraph(payment['contact'], styles['Normal'])
            text.wrapOn(p, max_width - inch, 100)
            text.drawOn(p, inch + 100, y_position - 10)
            y_position -= 0.3 * inch

        if payment.get('description'):
            p.drawString(inch, y_position, f"{trans('general_description', default='Description')}:")
            text = Paragraph(payment['description'], styles['Normal'])
            text.wrapOn(p, max_width - inch, 200)
            text.drawOn(p, inch + 100, y_position - 10)

        p.setFont("Helvetica-Oblique", 10)
        p.drawString(inch, inch, trans('payments_pdf_footer', default='This document serves as an official payment receipt generated by FiCore Records.'))
        p.showPage()
        p.save()
        buffer.seek(0)
        return Response(
            buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=payment_{payment["party_name"]}_{payment["id"]}.pdf'
            }
        )
    except ValueError:
        logger.error(f"Invalid payment ID {id} for user {current_user.id}")
        flash(trans('payments_invalid_id', default='Invalid payment ID'), 'danger')
        return redirect(url_for('payments.index'))
    except Exception as e:
        logger.error(f"Error generating PDF for payment {id} for user {current_user.id}: {str(e).replace('\\', '\\\\')}")
        flash(trans('payments_pdf_generation_error', default='An error occurred'), 'danger')
        return redirect(url_for('payments.index'))

def process_payment_form(form, payment_id=None):
    """Helper function to process payment form data for add/edit."""
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
        return None, validation_errors
    
    payment_date = datetime.combine(form.date.data, datetime.min.time(), tzinfo=ZoneInfo('UTC'))
    category_metadata = expense_categories.get(form.expense_category.data, {})
    
    cashflow = {
        'user_id': str(current_user.id),
        'type': 'payment',
        'party_name': form.party_name.data,
        'amount': form.amount.data,
        'method': form.method.data or None,
        'expense_category': form.expense_category.data,
        'is_tax_deductible': category_metadata.get('tax_deductible', False),
        'tax_year': utils.extract_tax_year_from_date(payment_date),
        'category_metadata': {
            'category_display_name': category_metadata.get('name', ''),
            'is_personal': category_metadata.get('is_personal', False),
            'is_statutory': category_metadata.get('is_statutory', False)
        },
        'contact': form.contact.data or None,
        'description': form.description.data or None,
        'created_at': payment_date,
        'updated_at': datetime.now(tz=ZoneInfo('UTC'))
    }
    
    db = utils.get_mongo_db()
    if payment_id:
        from models import update_cashflow
        update_cashflow(db, payment_id, cashflow)
    else:
        from models import create_cashflow
        create_cashflow(db, cashflow)
    
    return cashflow, None

@payments_bp.route('/add', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'admin'])
@utils.limiter.limit('10 per minute')
def add():
    """Add a new payment cashflow."""
    try:
        if not utils.can_user_interact(current_user):
            flash(trans('payments_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to add a payment.'), 'warning')
            return redirect(url_for('subscribe_bp.subscribe'))
        
        form = PaymentForm()
        if form.validate_on_submit():
            cashflow, errors = process_payment_form(form)
            if errors:
                for field, error in errors.items():
                    if hasattr(form, field):
                        getattr(form, field).errors.append(error)
                    else:
                        flash(error, 'danger')
                return render_template(
                    'payments/add.html',
                    form=form,
                    title=trans('payments_add_title', default='Add Money Out'),
                    can_interact=utils.can_user_interact(current_user),
                    expense_categories=expense_categories
                )
            logger.info(f"Payment added for user {current_user.id}")
            flash(trans('payments_add_success', default='Payment added successfully'), 'success')
            return redirect(url_for('payments.index'))
        
        return render_template(
            'payments/add.html',
            form=form,
            title=trans('payments_add_title', default='Add Money Out'),
            can_interact=utils.can_user_interact(current_user),
            expense_categories=expense_categories
        )
    except CSRFError:
        logger.error(f"CSRF error in adding payment for user {current_user.id}")
        flash(trans('payments_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return redirect(url_for('payments.index')), 400
    except Exception as e:
        logger.error(f"Error adding payment for user {current_user.id}: {str(e).replace('\\', '\\\\')}")
        flash(trans('payments_add_error', default='An error occurred'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/edit/<id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'admin'])
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
            logger.warning(f"Payment {id} not found for user {current_user.id}")
            flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
            return redirect(url_for('payments.index'))
        
        payment = process_payment_data(payment)
        from models import to_dict_cashflow
        payment = to_dict_cashflow(payment)
        
        form = PaymentForm(data={
            'party_name': payment['party_name'],
            'date': payment['created_at'].date(),
            'amount': payment['amount'],
            'method': payment.get('method'),
            'expense_category': payment.get('expense_category', 'office_admin'),
            'contact': payment.get('contact'),
            'description': payment.get('description')
        })
        
        if form.validate_on_submit():
            cashflow, errors = process_payment_form(form, payment_id=id)
            if errors:
                for field, error in errors.items():
                    if hasattr(form, field):
                        getattr(form, field).errors.append(error)
                    else:
                        flash(error, 'danger')
                return render_template(
                    'payments/edit.html',
                    form=form,
                    payment=payment,
                    title=trans('payments_edit_title', default='Edit Payment'),
                    can_interact=utils.can_user_interact(current_user),
                    expense_categories=expense_categories
                )
            logger.info(f"Payment {id} updated for user {current_user.id}")
            flash(trans('payments_edit_success', default='Payment updated successfully'), 'success')
            return redirect(url_for('payments.index'))
        
        return render_template(
            'payments/edit.html',
            form=form,
            payment=payment,
            title=trans('payments_edit_title', default='Edit Payment'),
            can_interact=utils.can_user_interact(current_user),
            expense_categories=expense_categories
        )
    except ValueError:
        logger.error(f"Invalid payment ID {id} for user {current_user.id}")
        flash(trans('payments_invalid_id', default='Invalid payment ID'), 'danger')
        return redirect(url_for('payments.index'))
    except CSRFError:
        logger.error(f"CSRF error in editing payment {id} for user {current_user.id}")
        flash(trans('payments_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return redirect(url_for('payments.index')), 400
    except Exception as e:
        logger.error(f"Error fetching payment {id} for user {current_user.id}: {str(e).replace('\\', '\\\\')}")
        flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/delete/<id>', methods=['POST'])
@login_required
@utils.requires_role(['trader', 'admin'])
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
            logger.info(f"Payment {id} deleted for user {current_user.id}")
            flash(trans('payments_delete_success', default='Payment deleted successfully'), 'success')
        else:
            logger.warning(f"Payment {id} not found for user {current_user.id}")
            flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
        return redirect(url_for('payments.index'))
    except ValueError:
        logger.error(f"Invalid payment ID {id} for user {current_user.id}")
        flash(trans('payments_invalid_id', default='Invalid payment ID'), 'danger')
        return redirect(url_for('payments.index'))
    except CSRFError:
        logger.error(f"CSRF error in deleting payment {id} for user {current_user.id}")
        flash(trans('payments_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return redirect(url_for('payments.index')), 400
    except Exception as e:
        logger.error(f"Error deleting payment {id} for user {current_user.id}: {str(e).replace('\\', '\\\\')}")
        flash(trans('payments_delete_error', default='An error occurred'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/share', methods=['POST'])
@login_required
@utils.requires_role(['trader', 'admin'])
@utils.limiter.limit('10 per minute')
def share():
    """Share a payment receipt via SMS or WhatsApp."""
    try:
        if not utils.can_user_interact(current_user):
            return utils.safe_json_response({
                'success': False,
                'message': trans('payments_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to share payments.')
            }, 403)
        
        data = request.get_json()
        payment_id = data.get('paymentId')
        recipient = data.get('recipient')
        message = data.get('message')
        share_type = data.get('type')
        
        if not all([payment_id, recipient, message, share_type]):
            logger.error(f"Missing fields in share payment request for user {current_user.id}")
            return utils.safe_json_response({
                'success': False,
                'message': trans('payments_missing_fields', default='Missing required fields')
            }, 400)
        
        if share_type not in ['sms', 'whatsapp']:
            logger.error(f"Invalid share type {share_type} for user {current_user.id}")
            return utils.safe_json_response({
                'success': False,
                'message': trans('payments_invalid_share_type', default='Invalid share type')
            }, 400)
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(payment_id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query, hint=[('_id', 1)])
        if not payment:
            logger.warning(f"Payment {payment_id} not found for user {current_user.id}")
            return utils.safe_json_response({
                'success': False,
                'message': trans('payments_record_not_found', default='Payment not found')
            }, 404)
        
        success = utils.send_message(recipient=recipient, message=message, type=share_type)
        if success:
            logger.info(f"Payment {payment_id} shared via {share_type} for user {current_user.id}")
            return utils.safe_json_response({'success': True})
        else:
            logger.error(f"Failed to share payment {payment_id} via {share_type} for user {current_user.id}")
            return utils.safe_json_response({
                'success': False,
                'message': trans('payments_share_failed', default='Failed to share payment')
            }, 500)
    except ValueError:
        logger.error(f"Invalid payment ID {payment_id} for user {current_user.id}")
        return utils.safe_json_response({
            'success': False,
            'message': trans('payments_invalid_id', default='Invalid payment ID')
        }, 404)
    except CSRFError:
        logger.error(f"CSRF error in sharing payment {payment_id} for user {current_user.id}")
        return utils.safe_json_response({
            'success': False,
            'message': trans('payments_csrf_error', default='Invalid CSRF token. Please try again.')
        }, 400)
    except Exception as e:
        logger.error(f"Error sharing payment {payment_id} for user {current_user.id}: {str(e).replace('\\', '\\\\')}")
        return utils.safe_json_response({
            'success': False,
            'message': trans('payments_share_error', default='Error sharing payment')
        }, 500)
