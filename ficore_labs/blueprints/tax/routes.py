from flask import Blueprint, request, session, redirect, url_for, render_template, flash, current_app, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import FloatField, SubmitField, StringField, FieldList, FormField, SelectField
from wtforms.validators import DataRequired, NumberRange, Optional, Length
from flask_login import current_user, login_required
from utils import get_all_recent_activities, clean_currency, get_mongo_db, is_admin, requires_role, limiter, get_optimized_tax_calculation_data
from datetime import datetime
from translations import trans
import uuid
import bleach
from bson import ObjectId
from .tax_calculation_engine import calculate_tax_liability, DataValidationError, TaxCalculationError, safe_float_conversion, validate_tax_year, update_user_entity_type

tax_bp = Blueprint(
    'tax',
    __name__,
    template_folder='templates/',
    url_prefix='/tax'
)

# Define valid deduction categories
DEDUCTION_CATEGORIES = [
    ('office_admin', 'Office Administration'),
    ('staff_wages', 'Staff Wages'),
    ('business_travel', 'Business Travel'),
    ('rent_utilities', 'Rent and Utilities'),
    ('marketing_sales', 'Marketing and Sales'),
    ('cogs', 'Cost of Goods Sold'),
    ('statutory_legal', 'Statutory and Legal Contributions')
]

def strip_commas(value):
    """Filter to remove commas and return a float."""
    return clean_currency(value)

def format_currency(value):
    """Format a numeric value with comma separation, no currency symbol."""
    try:
        numeric_value = float(value)
        formatted = f"{numeric_value:,.2f}"
        return formatted
    except (ValueError, TypeError):
        return "0.00"

def custom_login_required(f):
    """Custom login decorator that requires authentication."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            return f(*args, **kwargs)
        flash(trans('general_login_required', default='Please log in to access this page.'), 'warning')
        return redirect(url_for('users.login', next=request.url))
    return decorated_function

def sync_form_deductions_to_cashflows(user_id, tax_year, deductions, db):
    """Sync form deductions to the cashflows collection with proper categories."""
    try:
        for item in deductions:
            db.cashflows.insert_one({
                'user_id': user_id,
                'type': 'payment',
                'tax_year': tax_year,
                'expense_category': item['category'],
                'amount': float(item['amount']),
                'description': bleach.clean(item['name']),
                'note': bleach.clean(item['note']) if item['note'] else None,
                'created_at': datetime.utcnow()
            })
        current_app.logger.info(f"Synced {len(deductions)} deductions to cashflows for user {user_id} in tax year {tax_year}")
    except Exception as e:
        current_app.logger.error(f"Failed to sync deductions to cashflows for user {user_id}: {str(e)}")
        raise TaxCalculationError(f"Failed to sync deductions: {str(e)}")

class TaxItemForm(FlaskForm):
    name = StringField(
        trans('tax_item_name', default='Item Name'),
        validators=[
            DataRequired(message=trans('tax_item_name_required', default='Item name is required')),
            Length(min=2, max=50, message=trans('tax_item_name_length', default='Item name must be between 2 and 50 characters'))
        ]
    )
    amount = FloatField(
        trans('tax_item_amount', default='Amount'),
        filters=[strip_commas],
        validators=[
            DataRequired(message=trans('tax_item_amount_required', default='Amount is required')),
            NumberRange(min=0.01, max=10000000000, message=trans('tax_amount_max', default='Amount must be between 0.01 and 10 billion'))
        ]
    )
    category = SelectField(
        trans('tax_item_category', default='Category'),
        choices=DEDUCTION_CATEGORIES,
        validators=[
            DataRequired(message=trans('tax_item_category_required', default='Category is required'))
        ]
    )
    note = StringField(
        trans('tax_item_note', default='Note (Optional)'),
        validators=[
            Optional(),
            Length(max=200, message=trans('tax_item_note_length', default='Note must be less than 200 characters'))
        ]
    )
    
    class Meta:
        csrf = False  # Disable CSRF for subform, as it's handled by the parent TaxForm

class TaxForm(FlaskForm):
    income = FloatField(
        trans('tax_income', default='Annual Income'),
        filters=[strip_commas],
        validators=[
            DataRequired(message=trans('tax_income_required', default='Annual income is required')),
            NumberRange(min=0, max=10000000000, message=trans('tax_income_max', default='Income must be between 0 and 10 billion'))
        ]
    )
    rent_expenses = FloatField(
        trans('rent_expenses', default='Annual Rent Expenses'),
        filters=[strip_commas],
        validators=[
            Optional(),
            NumberRange(min=0, max=10000000000, message=trans('rent_expenses_max', default='Rent expenses must be between 0 and 10 billion'))
        ]
    )
    deductions = FieldList(
        FormField(TaxItemForm),
        min_entries=0,
        max_entries=20,
        validators=[Optional()]
    )
    tax_year = StringField(
        trans('tax_year', default='Tax Year'),
        validators=[
            DataRequired(message=trans('tax_year_required', default='Tax year is required')),
            Length(min=4, max=4, message=trans('tax_year_length', default='Tax year must be a 4-digit year'))
        ]
    )
    entity_type = StringField(
        trans('entity_type', default='Entity Type'),
        validators=[
            DataRequired(message=trans('entity_type_required', default='Entity type is required')),
            Length(max=50, message=trans('entity_type_length', default='Entity type must be less than 50 characters'))
        ]
    )
    submit = SubmitField(trans('tax_calculate', default='Calculate Tax'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.income.label.text = trans('tax_income', lang) or 'Annual Income'
        self.rent_expenses.label.text = trans('rent_expenses', lang) or 'Annual Rent Expenses'
        self.tax_year.label.text = trans('tax_year', lang) or 'Tax Year'
        self.entity_type.label.text = trans('entity_type', lang) or 'Entity Type'
        self.submit.label.text = trans('tax_calculate', lang) or 'Calculate Tax'

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            current_app.logger.debug(f"Form validation failed: {self.errors}", extra={'session_id': session.get('sid', 'unknown')})
            return False
        try:
            item_names = []
            for item in self.deductions.entries:
                if not isinstance(item.form, TaxItemForm):
                    current_app.logger.warning(f"Invalid entry in deductions: {item.__dict__}",
                                  extra={'session_id': session.get('sid', 'unknown')})
                    self.deductions.errors.append(
                        trans('tax_invalid_item', default='Invalid deduction item format')
                    )
                    return False
                if item.form.name.data and item.form.amount.data:
                    item_names.append(item.form.name.data.lower())
                if item.form.category.data not in [cat[0] for cat in DEDUCTION_CATEGORIES]:
                    self.deductions.errors.append(
                        trans('tax_invalid_category', default='Invalid deduction category')
                    )
                    return False
                
                if len(item_names) != len(set(item_names)):
                    self.deductions.errors.append(
                        trans('tax_duplicate_item_names', default='Deduction item names must be unique')
                    )
                    return False
            try:
                validate_tax_year(self.tax_year.data)
            except DataValidationError as e:
                self.tax_year.errors.append(str(e))
                return False
            if self.entity_type.data not in ['sole_proprietor', 'limited_liability']:
                self.entity_type.errors.append(
                    trans('tax_invalid_entity_type', default='Entity type must be Sole Proprietor or Limited Liability')
                )
                return False
            return True
        except Exception as e:
            current_app.logger.error(f"Error in TaxForm.validate: {str(e)}",
                        exc_info=True, extra={'session_id': session.get('sid', 'unknown')})
            self.deductions.errors.append(
                trans('tax_validation_error', default='Error validating tax data.')
            )
            return False

@tax_bp.route('/', methods=['GET'])
@custom_login_required
@requires_role(['trader', 'admin'])
def index():
    """Tax calculator landing page with navigation cards."""
    return render_template('tax/index.html')

@tax_bp.route('/new', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['trader', 'admin'])
@limiter.limit("10 per minute")
def new():
    session.permanent = False
    session_id = session.get('sid', str(uuid.uuid4()))
    session['sid'] = session_id
    current_app.logger.debug(f"Session data: {session}", extra={'session_id': session_id})
    
    form = TaxForm(formdata=request.form if request.method == 'POST' else None)
    db = get_mongo_db()
    current_year = datetime.now().year

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    try:
        activities = get_all_recent_activities(
            db=db,
            user_id=current_user.id,
            session_id=None,
        )
        current_app.logger.debug(f"Fetched {len(activities)} recent activities for user {current_user.id}", extra={'session_id': session_id})
    except Exception as e:
        current_app.logger.error(f"Failed to fetch recent activities: {str(e)}", extra={'session_id': session_id})
        flash(trans('tax_activities_load_error', default='Error loading recent activities.'), 'warning')
        activities = []

    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        if request.method == 'POST':
            current_app.logger.debug(f"POST request.form: {dict(request.form)}", extra={'session_id': session_id})
            if not form.validate_on_submit():
                current_app.logger.debug(f"Form errors: {form.errors}", extra={'session_id': session_id})
                error_message = trans('tax_form_invalid', default='Invalid form data. Please check your inputs.')
                if is_ajax:
                    return jsonify({'success': False, 'message': error_message, 'errors': form.errors}), 400
                flash(error_message, 'danger')
                return render_template(
                    'tax/new.html',
                    form=form,
                    calculations={},
                    latest_calculation={
                        'id': None,
                        'user_id': None,
                        'session_id': session_id,
                        'user_email': current_user.email,
                        'income': format_currency(0.0),
                        'income_raw': 0.0,
                        'deductions': [],
                        'taxable_income': format_currency(0.0),
                        'taxable_income_raw': 0.0,
                        'total_tax': format_currency(0.0),
                        'total_tax_raw': 0.0,
                        'created_at': 'N/A',
                        'tax_year': current_year,
                        'entity_type': 'sole_proprietor'
                    },
                    tips=[],
                    insights=[],
                    activities=activities,
                    tool_title=trans('tax_calculator_title', default='Tax Calculator'),
                    active_tab='calculate-tax',
                    current_year=current_year
                ), 400

            try:
                income = float(form.income.data)
                rent_expenses = float(form.rent_expenses.data or 0.0)
                deductions = []
                total_deductions = 0.0
                for item in form.deductions.entries:
                    if item.form.name.data and item.form.amount.data and item.form.category.data:
                        deduction_item = {
                            'name': bleach.clean(item.form.name.data),
                            'amount': float(item.form.amount.data),
                            'category': item.form.category.data,
                            'note': bleach.clean(item.form.note.data) if item.form.note.data else None
                        }
                        deductions.append(deduction_item)
                        total_deductions += deduction_item['amount']

                # Add rent expenses as a deduction if provided
                if rent_expenses > 0:
                    deductions.append({
                        'name': 'Rent Expenses',
                        'amount': rent_expenses,
                        'category': 'rent_utilities',
                        'note': 'Annual rent expenses from form'
                    })
                    total_deductions += rent_expenses

                tax_year = int(form.tax_year.data)
                entity_type = form.entity_type.data

                # Sync deductions to cashflows
                sync_form_deductions_to_cashflows(current_user.id, tax_year, deductions, db)

                if not update_user_entity_type(current_user.id, entity_type, db):
                    current_app.logger.error(f"Failed to update entity type for user {current_user.id}", extra={'session_id': session_id})
                    error_message = trans('tax_entity_update_error', default='Error updating entity type.')
                    if is_ajax:
                        return jsonify({'success': False, 'message': error_message}), 500
                    flash(error_message, 'danger')
                    return redirect(url_for('tax.new'))

                # Log deductions for debugging
                current_app.logger.info(f"Deductions for user {current_user.id}: {deductions}", extra={'session_id': session_id})

                tax_result = calculate_tax_liability(current_user.id, tax_year, db)
                if 'error' in tax_result:
                    raise TaxCalculationError(tax_result['error'])
                
                taxable_income = tax_result.get('summary', {}).get('taxable_income', 0.0)
                total_tax = tax_result.get('final_tax_liability', 0.0)

                # Validate taxable income
                if taxable_income < 0:
                    current_app.logger.warning(f"Negative taxable income ({taxable_income}) for user {current_user.id} in tax year {tax_year}", 
                                             extra={'session_id': session_id})
                    error_message = trans('tax_negative_taxable', default='Taxable income is negative. Please review your deductions.')
                    if is_ajax:
                        return jsonify({'success': False, 'message': error_message, 'details': {'taxable_income': taxable_income}}), 400
                    flash(error_message, 'warning')

                tax_id = ObjectId()
                tax_data = {
                    '_id': tax_id,
                    'user_id': current_user.id,
                    'session_id': session_id,
                    'income': income,
                    'deductions': deductions,
                    'taxable_income': taxable_income,
                    'total_tax': total_tax,
                    'tax_year': tax_year,
                    'entity_type': entity_type,
                    'calculation_type': tax_result.get('calculation_type', 'Unknown'),
                    'calculation_details': tax_result,
                    'created_at': datetime.utcnow()
                }
                current_app.logger.debug(f"Saving tax calculation: {tax_data}", extra={'session_id': session_id})
                try:
                    with db.client.start_session() as mongo_session:
                        with mongo_session.start_transaction():
                            db.tax_calculations.insert_one(tax_data, session=mongo_session)
                            mongo_session.commit_transaction()
                    current_app.logger.info(f"Tax calculation {tax_id} saved successfully to MongoDB for session {session_id}", extra={'session_id': session_id})
                    try:
                        caching_ext = current_app.extensions.get('caching')
                        if caching_ext:
                            cache = list(caching_ext.values())[0]
                            cache.delete_memoized(get_optimized_tax_calculation_data)
                            current_app.logger.debug(f"Cleared cache for get_optimized_tax_calculation_data", extra={'session_id': session_id})
                        else:
                            current_app.logger.warning(f"Caching extension not found; skipping cache clear", extra={'session_id': session_id})
                    except Exception as e:
                        current_app.logger.warning(f"Failed to clear cache for get_optimized_tax_calculation_data: {str(e)}", extra={'session_id': session_id})
                    success_message = trans("tax_calculated_success", default='Tax calculated successfully!')
                    if is_ajax:
                        return jsonify({'success': True, 'tax_id': str(tax_id), 'message': success_message}), 200
                    flash(success_message, "success")
                    return redirect(url_for('tax.dashboard'))
                except Exception as e:
                    current_app.logger.error(f"Failed to save tax calculation {tax_id} to MongoDB for session {session_id}: {str(e)}", extra={'session_id': session_id})
                    error_message = trans("tax_storage_error", default='Error saving tax calculation.')
                    if is_ajax:
                        return jsonify({'success': False, 'message': error_message}), 500
                    flash(error_message, "danger")
                    return render_template(
                        'tax/new.html',
                        form=form,
                        calculations={},
                        latest_calculation={
                            'id': None,
                            'user_id': None,
                            'session_id': session_id,
                            'user_email': current_user.email,
                            'income': format_currency(0.0),
                            'income_raw': 0.0,
                            'deductions': [],
                            'taxable_income': format_currency(0.0),
                            'taxable_income_raw': 0.0,
                            'total_tax': format_currency(0.0),
                            'total_tax_raw': 0.0,
                            'created_at': 'N/A',
                            'tax_year': current_year,
                            'entity_type': 'sole_proprietor'
                        },
                        tips=[],
                        insights=[],
                        activities=activities,
                        tool_title=trans('tax_calculator_title', default='Tax Calculator'),
                        active_tab='calculate-tax',
                        current_year=current_year
                    )
            except TaxCalculationError as e:
                current_app.logger.error(f"Tax calculation error for user {current_user.id}: {str(e)}", extra={'session_id': session_id})
                error_message = trans('tax_calculation_error', default=e.message)
                if is_ajax:
                    return jsonify({'success': False, 'message': error_message, 'details': e.details}), 400
                flash(error_message, 'danger')
                return render_template(
                    'tax/new.html',
                    form=form,
                    calculations={},
                    latest_calculation={
                        'id': None,
                        'user_id': None,
                        'session_id': session_id,
                        'user_email': current_user.email,
                        'income': format_currency(0.0),
                        'income_raw': 0.0,
                        'deductions': [],
                        'taxable_income': format_currency(0.0),
                        'taxable_income_raw': 0.0,
                        'total_tax': format_currency(0.0),
                        'total_tax_raw': 0.0,
                        'created_at': 'N/A',
                        'tax_year': current_year,
                        'entity_type': 'sole_proprietor'
                    },
                    tips=[],
                    insights=[],
                    activities=activities,
                    tool_title=trans('tax_calculator_title', default='Tax Calculator'),
                    active_tab='calculate-tax',
                    current_year=current_year
                ), 400

        calculations = list(db.tax_calculations.find(filter_criteria).sort('created_at', -1).limit(10))
        calculations_dict = {}
        latest_calculation = None
        for calc in calculations:
            calc_data = {
                'id': str(calc['_id']),
                'user_id': calc.get('user_id'),
                'session_id': calc.get('session_id'),
                'user_email': calc.get('user_email', current_user.email),
                'income': format_currency(calc.get('income', 0.0)),
                'income_raw': float(calc.get('income', 0.0)),
                'deductions': calc.get('deductions', []),
                'taxable_income': format_currency(calc.get('taxable_income', 0.0)),
                'taxable_income_raw': float(calc.get('taxable_income', 0.0)),
                'total_tax': format_currency(calc.get('total_tax', 0.0)),
                'total_tax_raw': float(calc.get('total_tax', 0.0)),
                'tax_year': calc.get('tax_year', current_year),
                'entity_type': calc.get('entity_type', 'sole_proprietor'),
                'created_at': calc.get('created_at').strftime('%Y-%m-%d') if calc.get('created_at') else 'N/A'
            }
            calculations_dict[calc_data['id']] = calc_data
            if not latest_calculation or (calc.get('created_at') and (latest_calculation['created_at'] == 'N/A' or calc.get('created_at') > datetime.strptime(latest_calculation['created_at'], '%Y-%m-%d'))):
                latest_calculation = calc_data

        if not latest_calculation:
            latest_calculation = {
                'id': None,
                'user_id': None,
                'session_id': session_id,
                'user_email': current_user.email,
                'income': format_currency(0.0),
                'income_raw': 0.0,
                'deductions': [],
                'taxable_income': format_currency(0.0),
                'taxable_income_raw': 0.0,
                'total_tax': format_currency(0.0),
                'total_tax_raw': 0.0,
                'tax_year': current_year,
                'entity_type': 'sole_proprietor',
                'created_at': 'N/A'
            }

        tips = [
            trans("tax_tip_review_deductions", default='Review all possible deductions to reduce taxable income.'),
            trans("tax_tip_file_early", default='File your taxes early to avoid penalties.'),
            trans("tax_tip_keep_records", default='Keep detailed records of all deductible expenses.'),
            trans("tax_tip_consult_expert", default='Consult a tax professional for complex situations.')
        ]

        insights = []
        try:
            income_float = float(latest_calculation.get('income_raw', 0.0))
            taxable_income_float = float(latest_calculation.get('taxable_income_raw', 0.0))
            if income_float > 0:
                if taxable_income_float / income_float > 0.8:
                    insights.append(trans("tax_insight_high_taxable", default='Your taxable income is high. Consider additional deductions.'))
                if len(latest_calculation.get('deductions', [])) == 0:
                    insights.append(trans("tax_insight_no_deductions", default='No deductions claimed. Explore eligible deductions to lower your tax.'))
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"Error parsing tax amounts for insights: {str(e)}", extra={'session_id': session_id})

        return render_template(
            'tax/new.html',
            form=form,
            calculations=calculations_dict,
            latest_calculation=latest_calculation,
            tips=tips,
            insights=insights,
            activities=activities,
            tool_title=trans('tax_calculator_title', default='Tax Calculator'),
            active_tab='calculate-tax',
            current_year=current_year
        )
    except Exception as e:
        current_app.logger.exception(f"Unexpected error in tax.new: {str(e)}", extra={'session_id': session_id})
        error_message = trans('tax_dashboard_load_error', default='Error loading tax calculator.')
        if is_ajax:
            return jsonify({'success': False, 'message': error_message}), 500
        flash(error_message, 'danger')
        return render_template(
            'tax/new.html',
            form=form,
            calculations={},
            latest_calculation={
                'id': None,
                'user_id': None,
                'session_id': session_id,
                'user_email': current_user.email,
                'income': format_currency(0.0),
                'income_raw': 0.0,
                'deductions': [],
                'taxable_income': format_currency(0.0),
                'taxable_income_raw': 0.0,
                'total_tax': format_currency(0.0),
                'total_tax_raw': 0.0,
                'tax_year': current_year,
                'entity_type': 'sole_proprietor',
                'created_at': 'N/A'
            },
            tips=[],
            insights=[],
            activities=activities,
            tool_title=trans('tax_calculator_title', default='Tax Calculator'),
            active_tab='calculate-tax',
            current_year=current_year
        ), 500

@tax_bp.route('/dashboard', methods=['GET'])
@custom_login_required
@requires_role(['trader', 'admin'])
@limiter.limit("10 per minute")
def dashboard():
    """Tax calculator dashboard page."""
    if 'sid' not in session:
        session['sid'] = str(uuid.uuid4())
        current_app.logger.debug(f"New session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = False
    session.modified = True
    db = get_mongo_db()

    try:
        activities = get_all_recent_activities(
            db=db,
            user_id=current_user.id,
            session_id=None,
        )
    except Exception as e:
        current_app.logger.error(f"Failed to fetch recent activities: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('tax_activities_load_error', default='Error loading recent activities.'), 'warning')
        activities = []

    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        calculations = list(db.tax_calculations.find(filter_criteria).sort('created_at', -1).limit(10))
        
        calculations_dict = {}
        latest_calculation = None
        for calc in calculations:
            calc_data = {
                'id': str(calc['_id']),
                'user_id': calc.get('user_id'),
                'session_id': calc.get('session_id'),
                'user_email': calc.get('user_email', current_user.email),
                'income': format_currency(calc.get('income', 0.0)),
                'income_raw': float(calc.get('income', 0.0)),
                'deductions': calc.get('deductions', []),
                'taxable_income': format_currency(calc.get('taxable_income', 0.0)),
                'taxable_income_raw': float(calc.get('taxable_income', 0.0)),
                'total_tax': format_currency(calc.get('total_tax', 0.0)),
                'total_tax_raw': float(calc.get('total_tax', 0.0)),
                'tax_year': calc.get('tax_year', datetime.now().year),
                'entity_type': calc.get('entity_type', 'sole_proprietor'),
                'created_at': calc.get('created_at').strftime('%Y-%m-%d') if calc.get('created_at') else 'N/A'
            }
            calculations_dict[calc_data['id']] = calc_data
            if not latest_calculation or (calc.get('created_at') and (latest_calculation['created_at'] == 'N/A' or calc.get('created_at') > datetime.strptime(latest_calculation['created_at'], '%Y-%m-%d'))):
                latest_calculation = calc_data

        if not latest_calculation:
            latest_calculation = {
                'id': None,
                'user_id': None,
                'session_id': session.get('sid', 'unknown'),
                'user_email': current_user.email,
                'income': format_currency(0.0),
                'income_raw': 0.0,
                'deductions': [],
                'taxable_income': format_currency(0.0),
                'taxable_income_raw': 0.0,
                'total_tax': format_currency(0.0),
                'total_tax_raw': 0.0,
                'tax_year': datetime.now().year,
                'entity_type': 'sole_proprietor',
                'created_at': 'N/A'
            }

        tips = [
            trans("tax_tip_review_deductions", default='Review all possible deductions to reduce taxable income.'),
            trans("tax_tip_file_early", default='File your taxes early to avoid penalties.'),
            trans("tax_tip_keep_records", default='Keep detailed records of all deductible expenses.'),
            trans("tax_tip_consult_expert", default='Consult a tax professional for complex situations.')
        ]

        insights = []
        try:
            income_float = float(latest_calculation.get('income_raw', 0.0))
            taxable_income_float = float(latest_calculation.get('taxable_income_raw', 0.0))
            if income_float > 0:
                if taxable_income_float / income_float > 0.8:
                    insights.append(trans("tax_insight_high_taxable", default='Your taxable income is high. Consider additional deductions.'))
                if len(latest_calculation.get('deductions', [])) == 0:
                    insights.append(trans("tax_insight_no_deductions", default='No deductions claimed. Explore eligible deductions to lower your tax.'))
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"Error parsing tax amounts for insights: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})

        return render_template(
            'tax/dashboard.html',
            calculations=calculations_dict,
            latest_calculation=latest_calculation,
            tips=tips,
            insights=insights,
            activities=activities,
            tool_title=trans('tax_dashboard', default='Tax Dashboard')
        )
    except Exception as e:
        current_app.logger.error(f"Error in tax.dashboard: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('tax_dashboard_load_error', default='Error loading tax dashboard.'), 'danger')
        return render_template(
            'tax/dashboard.html',
            calculations={},
            latest_calculation={},
            tips=[],
            insights=[],
            activities=[],
            tool_title=trans('tax_dashboard', default='Tax Dashboard')
        )

@tax_bp.route('/history', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['trader', 'admin'])
@limiter.limit("10 per minute")
def history():
    """Manage tax calculations page."""
    if 'sid' not in session:
        session['sid'] = str(uuid.uuid4())
        current_app.logger.debug(f"New session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = False
    session.modified = True
    db = get_mongo_db()

    filter_criteria = {} if is_admin() else {'user_id': current_user.id}

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'delete':
            tax_id = request.form.get('tax_id')
            tax_calc = db.tax_calculations.find_one({'_id': ObjectId(tax_id), **filter_criteria})
            if not tax_calc:
                current_app.logger.warning(f"Tax calculation {tax_id} not found for deletion", extra={'session_id': session.get('sid', 'unknown')})
                flash(trans("tax_not_found", default='Tax calculation not found.'), "danger")
                return redirect(url_for('tax.history'))
            
            try:
                with db.client.start_session() as mongo_session:
                    with mongo_session.start_transaction():
                        result = db.tax_calculations.delete_one({'_id': ObjectId(tax_id), **filter_criteria}, session=mongo_session)
                        if result.deleted_count > 0:
                            mongo_session.commit_transaction()
                        else:
                            current_app.logger.warning(f"Tax calculation ID {tax_id} not found for session {session['sid']}", extra={'session_id': session['sid']})
                            flash(trans("tax_not_found", default='Tax calculation not found.'), "danger")
                            return redirect(url_for('tax.history'))
                try:
                    caching_ext = current_app.extensions.get('caching')
                    if caching_ext:
                        cache = list(caching_ext.values())[0]
                        cache.delete_memoized(get_optimized_tax_calculation_data)
                        current_app.logger.debug(f"Cleared cache for get_optimized_tax_calculation_data", extra={'session_id': session.get('sid', 'unknown')})
                    else:
                        current_app.logger.warning(f"Caching extension not found; skipping cache clear", extra={'session_id': session.get('sid', 'unknown')})
                except Exception as e:
                    current_app.logger.warning(f"Failed to clear cache for get_optimized_tax_calculation_data: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                current_app.logger.info(f"Deleted tax calculation ID {tax_id} for session {session['sid']}", extra={'session_id': session['sid']})
                flash(trans("tax_deleted_success", default='Tax calculation deleted successfully!'), "success")
            except Exception as e:
                current_app.logger.error(f"Failed to delete tax calculation ID {tax_id} for session {session['sid']}: {str(e)}", extra={'session_id': session['sid']})
                flash(trans("tax_delete_failed", default='Error deleting tax calculation.'), "danger")
            return redirect(url_for('tax.history'))

    try:
        calculations = list(db.tax_calculations.find(filter_criteria).sort('created_at', -1).limit(20))
        calculations_dict = {}
        
        for calc in calculations:
            calc_data = {
                'id': str(calc['_id']),
                'user_id': calc.get('user_id'),
                'session_id': calc.get('session_id'),
                'user_email': calc.get('user_email', current_user.email),
                'income': format_currency(calc.get('income', 0.0)),
                'income_raw': float(calc.get('income', 0.0)),
                'deductions': calc.get('deductions', []),
                'taxable_income': format_currency(calc.get('taxable_income', 0.0)),
                'taxable_income_raw': float(calc.get('taxable_income', 0.0)),
                'total_tax': format_currency(calc.get('total_tax', 0.0)),
                'total_tax_raw': float(calc.get('total_tax', 0.0)),
                'tax_year': calc.get('tax_year', datetime.now().year),
                'entity_type': calc.get('entity_type', 'sole_proprietor'),
                'created_at': calc.get('created_at').strftime('%Y-%m-%d %H:%M') if calc.get('created_at') else 'N/A'
            }
            calculations_dict[calc_data['id']] = calc_data

        return render_template(
            'tax/history.html',
            calculations=calculations_dict,
            tool_title=trans('tax_history', default='Tax History')
        )
    except Exception as e:
        current_app.logger.error(f"Error in tax.history: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('tax_history_load_error', default='Error loading tax calculations for management.'), 'danger')
        return render_template(
            'tax/history.html',
            calculations={},
            tool_title=trans('tax_history', default='Tax History')
        )
