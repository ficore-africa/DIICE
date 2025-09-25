from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, jsonify, session
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFError
from translations import trans
import utils
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

logger = logging.getLogger(__name__)

class PaymentForm(FlaskForm):
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
        # Populate expense category choices from utils
        self.expense_category.choices = utils.get_category_choices_for_forms()

payments_bp = Blueprint('payments', __name__, url_prefix='/payments')

@payments_bp.route('/')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def index():
    """List all payment cashflows for the current user."""
    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id), 'type': 'payment'}
        payments = utils.safe_find_cashflows(db, query, 'created_at', -1)
        
        # Calculate category-based summary statistics
        category_stats = utils.calculate_payment_category_stats(payments)
        
        return render_template(
            'payments/index.html',
            payments=payments,
            category_stats=category_stats,
            format_currency=utils.format_currency,
            format_date=utils.format_date,
            title=trans('payments_title', default='Money Out', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        )
    except Exception as e:
        logger.error(
            f"Error fetching payments for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_fetch_error', default='An error occurred'), 'danger')
        return redirect(url_for('dashboard.index'))

@payments_bp.route('/manage')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def manage():
    """Manage all payment cashflows for the current user (edit/delete)."""
    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id), 'type': 'payment'}
        payments = utils.safe_find_cashflows(db, query, 'created_at', -1)
        
        # Calculate category-based summary statistics
        category_stats = utils.calculate_payment_category_stats(payments)
        
        return render_template(
            'payments/manage.html',
            payments=payments,
            category_stats=category_stats,
            format_currency=utils.format_currency,
            format_date=utils.format_date,
            title=trans('payments_manage', default='Manage Payments', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        )
    except Exception as e:
        logger.error(
            f"Error fetching payments for manage page for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_fetch_error', default='An error occurred'), 'danger')
        return redirect(url_for('payments.index'))

@payments_bp.route('/view/<id>')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def view(id):
    """View detailed information about a specific payment."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query)
        if not payment:
            return jsonify({'error': trans('payments_record_not_found', default='Record not found')}), 404
        
        # Convert naive datetimes to timezone-aware
        if payment.get('created_at') and payment['created_at'].tzinfo is None:
            payment['created_at'] = payment['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        
        payment['_id'] = str(payment['_id'])
        payment['created_at'] = payment['created_at'].isoformat() if payment.get('created_at') else None
        return jsonify(payment)
    except ValueError:
        logger.error(
            f"Invalid payment ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({'error': trans('payments_invalid_id', default='Invalid payment ID')}), 404
    except Exception as e:
        logger.error(
            f"Error fetching payment {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({'error': trans('payments_fetch_error', default='An error occurred')}), 500

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
        payment = db.cashflows.find_one(query)
        if not payment:
            flash(trans('payments_record_not_found', default='Record not found'), 'danger')
            return redirect(url_for('payments.index'))
        
        # Convert naive datetimes to timezone-aware
        if payment.get('created_at') and payment['created_at'].tzinfo is None:
            payment['created_at'] = payment['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        
        # Sanitize inputs for PDF generation
        payment['party_name'] = utils.sanitize_input(payment['party_name'], max_length=100)
        # Use category_metadata display name if available, otherwise fallback to expense_category
        category_display = payment.get('category_metadata', {}).get('category_display_name', 
                                     payment.get('expense_category', 'No category provided'))
        payment['category_display'] = utils.sanitize_input(category_display, max_length=50)
        payment['contact'] = utils.sanitize_input(payment.get('contact', ''), max_length=100) if payment.get('contact') else ''
        payment['description'] = utils.sanitize_input(payment.get('description', ''), max_length=1000) if payment.get('description') else ''
        
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        p.setFont("Helvetica-Bold", 24)
        p.drawString(inch, height - inch, trans('payments_pdf_title', default='FiCore Records - Money Out Receipt'))
        p.setFont("Helvetica", 12)
        y_position = height - inch - 0.5 * inch
        p.drawString(inch, y_position, f"{trans('payments_recipient_name', default='Recipient')}: {payment['party_name']}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('payments_amount', default='Amount Paid')}: {utils.format_currency(payment['amount'])}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('general_payment_method', default='Payment Method')}: {payment.get('method', 'N/A')}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('general_category', default='Category')}: {payment['category_display']}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('general_date', default='Date')}: {utils.format_date(payment['created_at'])}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('payments_id', default='Payment ID')}: {str(payment['_id'])}")
        y_position -= 0.3 * inch
        if payment['contact']:
            p.drawString(inch, y_position, f"{trans('general_contact', default='Contact')}: {payment['contact']}")
            y_position -= 0.3 * inch
        if payment['description']:
            p.drawString(inch, y_position, f"{trans('general_description', default='Description')}: {payment['description']}")
        p.setFont("Helvetica-Oblique", 10)
        p.drawString(inch, inch, trans('payments_pdf_footer', default='This document serves as an official payment receipt generated by FiCore Records.'))
        p.showPage()
        p.save()
        buffer.seek(0)
        return Response(
            buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=payment_{utils.sanitize_input(payment["party_name"], max_length=50)}_{str(payment["_id"])}.pdf'
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
                # Additional server-side validation
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
                        can_interact=utils.can_user_interact(current_user)
                    )
                
                db = utils.get_mongo_db()
                # Convert date to datetime with UTC timezone
                payment_date = datetime.combine(form.date.data, datetime.min.time(), tzinfo=ZoneInfo("UTC"))
                # Get category metadata for the selected expense category
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
                    'updated_at': datetime.now(timezone.utc)
                }
                db.cashflows.insert_one(cashflow)
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
            can_interact=utils.can_user_interact(current_user)
        )
    except CSRFError as e:
        logger.error(
            f"CSRF error in adding payment for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('payments_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return render_template(
            'payments/add.html',
            form=form,
            title=trans('payments_add_title', default='Add Money Out', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        ), 400

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
        payment = db.cashflows.find_one(query)
        if not payment:
            logger.warning(
                f"Payment {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('payments_record_not_found', default='Cashflow not found'), 'danger')
            return redirect(url_for('payments.index'))
        
        # Convert naive datetimes to timezone-aware
        if payment.get('created_at') and payment['created_at'].tzinfo is None:
            payment['created_at'] = payment['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        
        form = PaymentForm(data={
            'party_name': payment['party_name'],
            'date': payment['created_at'].date(),  # Extract date part for form
            'amount': payment['amount'],
            'method': payment.get('method'),
            'expense_category': payment.get('expense_category', 'office_admin'),  # Default fallback
            'contact': payment.get('contact'),
            'description': payment.get('description')
        })
        if form.validate_on_submit():
            try:
                # Additional server-side validation
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
                        can_interact=utils.can_user_interact(current_user)
                    )
                
                # Convert date to datetime with UTC timezone
                payment_date = datetime.combine(form.date.data, datetime.min.time(), tzinfo=ZoneInfo("UTC"))
                
                # Get category metadata for the selected expense category
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
                    'updated_at': datetime.now(timezone.utc)
                }
                db.cashflows.update_one({'_id': ObjectId(id)}, {'$set': updated_cashflow})
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
            can_interact=utils.can_user_interact(current_user)
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
        return render_template(
            'payments/edit.html',
            form=form,
            payment=payment,
            title=trans('payments_edit_title', default='Edit Payment', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        ), 400
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
        result = db.cashflows.delete_one(query)
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
        return redirect(url_for('payments.index'))
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
            return jsonify({
                'success': False,
                'message': trans('payments_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to share payments.')
            }), 403
        
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
            return jsonify({
                'success': False,
                'message': trans('payments_missing_fields', default='Missing required fields')
            }), 400
        
        valid_share_types = ['sms', 'whatsapp']
        if share_type not in valid_share_types:
            logger.error(
                f"Invalid share type {share_type} in share payment request for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({
                'success': False,
                'message': trans('payments_invalid_share_type', default='Invalid share type')
            }), 400
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(payment_id), 'user_id': str(current_user.id), 'type': 'payment'}
        payment = db.cashflows.find_one(query)
        if not payment:
            logger.warning(
                f"Payment {payment_id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({
                'success': False,
                'message': trans('payments_record_not_found', default='Payment not found')
            }), 404
        
        success = utils.send_message(recipient=recipient, message=message, type=share_type)
        if success:
            logger.info(
                f"Payment {payment_id} shared via {share_type} for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({'success': True})
        else:
            logger.error(
                f"Failed to share payment {payment_id} via {share_type} for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({
                'success': False,
                'message': trans('payments_share_failed', default='Failed to share payment')
            }), 500
    except ValueError:
        logger.error(
            f"Invalid payment ID {payment_id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({
            'success': False,
            'message': trans('payments_invalid_id', default='Invalid payment ID')
        }), 404
    except CSRFError as e:
        logger.error(
            f"CSRF error in sharing payment {payment_id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({
            'success': False,
            'message': trans('payments_csrf_error', default='Invalid CSRF token. Please try again.')
        }), 400
    except Exception as e:
        logger.error(
            f"Error sharing payment {payment_id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({
            'success': False,
            'message': trans('payments_share_error', default='Error sharing payment')
        }), 500
