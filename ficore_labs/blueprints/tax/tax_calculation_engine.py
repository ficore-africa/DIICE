from datetime import datetime
from zoneinfo import ZoneInfo
import logging
from translations import trans
from typing import Dict, Any, Tuple, Optional, Union

# Set up comprehensive logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaxCalculationError(Exception):
    """Custom exception for tax calculation errors"""
    def __init__(self, message: str, error_code: str = None, details: Dict = None):
        self.message = message
        self.error_code = error_code or 'CALCULATION_ERROR'
        self.details = details or {}
        super().__init__(self.message)

class DataValidationError(TaxCalculationError):
    """Exception for data validation errors"""
    def __init__(self, message: str, field: str = None, value: Any = None):
        self.field = field
        self.value = value
        super().__init__(message, 'VALIDATION_ERROR', {'field': field, 'value': value})

class InsufficientDataError(TaxCalculationError):
    """Exception for insufficient data scenarios"""
    def __init__(self, message: str, missing_data: list = None):
        self.missing_data = missing_data or []
        super().__init__(message, 'INSUFFICIENT_DATA', {'missing_data': missing_data})

def safe_float_conversion(value: Any, field_name: str = "value", allow_negative: bool = False) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, str) and value.strip() == '':
            return 0.0
        converted_value = float(value)
        if not allow_negative and converted_value < 0:
            raise DataValidationError(
                trans('tax_negative_value', default=f"{field_name} cannot be negative: {converted_value}"),
                field=field_name,
                value=value
            )
        if abs(converted_value) > 1e12:  # 1 trillion limit
            raise DataValidationError(
                trans('tax_value_too_large', default=f"{field_name} is unreasonably large: {converted_value}"),
                field=field_name,
                value=value
            )
        return converted_value
    except (ValueError, TypeError) as e:
        raise DataValidationError(
            trans('tax_invalid_number', default=f"Invalid {field_name}: cannot convert '{value}' to number"),
            field=field_name,
            value=value
        ) from e

def validate_tax_year(tax_year: Any) -> int:
    try:
        if tax_year is None:
            return datetime.now().year
        year = int(tax_year)
        current_year = datetime.now().year
        if year < 2020 or year > current_year + 1:
            raise DataValidationError(
                trans('tax_invalid_year_range', default=f"Invalid tax year: {year}. Must be between 2020 and {current_year + 1}"),
                field='tax_year',
                value=tax_year
            )
        return year
    except (ValueError, TypeError) as e:
        raise DataValidationError(
            trans('tax_invalid_year_format', default=f"Invalid tax year format: {tax_year}"),
            field='tax_year',
            value=tax_year
        ) from e

def handle_calculation_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TaxCalculationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise TaxCalculationError(
                trans('tax_unexpected_error', default=f"Unexpected error during tax calculation: {str(e)}"),
                error_code='UNEXPECTED_ERROR',
                details={'function': func.__name__, 'args': str(args)[:200]}
            ) from e
    return wrapper

def log_calculation_attempt(user_id: str, calculation_type: str, input_data: Dict):
    try:
        sanitized_data = {
            'total_income': input_data.get('total_income', 0),
            'expense_count': len(input_data.get('expenses', {})),
            'has_rent_data': bool(input_data.get('annual_rent')),
            'calculation_timestamp': datetime.now(ZoneInfo("UTC")).isoformat()
        }
        logger.info(
            f"Tax calculation attempt - User: {user_id}, Type: {calculation_type}, Data: {sanitized_data}"
        )
    except Exception as e:
        logger.warning(f"Failed to log calculation attempt: {str(e)}")

def create_error_response(error: TaxCalculationError, user_id: str = None) -> Dict:
    try:
        logger.error(
            f"Tax calculation error for user {user_id}: {error.message}",
            extra={
                'error_code': error.error_code,
                'error_details': error.details,
                'user_id': user_id
            }
        )
        return {
            'success': False,
            'error_code': error.error_code,
            'error_message': error.message,
            'user_message': get_user_friendly_error_message(error),
            'details': error.details,
            'timestamp': datetime.now(ZoneInfo("UTC")).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to create error response: {str(e)}")
        return {
            'success': False,
            'error_code': 'SYSTEM_ERROR',
            'error_message': trans('tax_system_error', default='A system error occurred during tax calculation'),
            'user_message': trans('tax_system_error_message', default='We encountered an error while calculating your tax. Please try again.'),
            'timestamp': datetime.now(ZoneInfo("UTC")).isoformat()
        }

def get_user_friendly_error_message(error: TaxCalculationError) -> str:
    error_messages = {
        'VALIDATION_ERROR': trans('tax_check_input', default='Please check your input data and try again.'),
        'INSUFFICIENT_DATA': trans('tax_missing_data', default='Some required information is missing. Please provide all necessary details.'),
        'CALCULATION_ERROR': trans('tax_calculation_failed', default='We encountered an error while calculating your tax. Please try again.'),
        'DATABASE_ERROR': trans('tax_technical_issue', default='We are experiencing technical difficulties. Please try again later.'),
        'UNEXPECTED_ERROR': trans('tax_unexpected_error_message', default='An unexpected error occurred. Please try again or contact support.')
    }
    if error.error_code == 'VALIDATION_ERROR' and error.details.get('field'):
        field_name = error.details['field'].replace('_', ' ').title()
        return trans('tax_check_field', default=f"Please check the {field_name} field and try again.")
    return error_messages.get(error.error_code, trans('tax_general_error', default='An error occurred during tax calculation. Please try again.'))

ENTITY_TYPES = {
    'sole_proprietor': {
        'name': trans('tax_entity_sole_proprietor', default='Individual/Sole Proprietor'),
        'description': trans('tax_entity_sole_description', default='Personal business, freelancer, or individual trader'),
        'tax_type': trans('tax_type_pit', default='Personal Income Tax (PIT)'),
        'tax_details': trans('tax_pit_details', default='Progressive tax bands with NGN 800,000 exemption')
    },
    'limited_liability': {
        'name': trans('tax_entity_limited_liability', default='Registered Limited Liability Company'),
        'description': trans('tax_entity_limited_description', default='Incorporated company with RC number'),
        'tax_type': trans('tax_type_cit', default='Companies Income Tax (CIT)'),
        'tax_details': trans('tax_cit_details', default='0% for revenue up to NGN 50M, 30% for revenue above NGN 50M')
    }
}

def get_user_entity_type(user_id, db):
    try:
        entity_record = db.user_entities.find_one({'user_id': user_id})
        if entity_record:
            entity_type = entity_record.get('business_entity_type', 'sole_proprietor')
            entity_type = str(entity_type).strip()
            if entity_type not in ENTITY_TYPES:
                entity_type = 'sole_proprietor'
            logger.info(f"Retrieved entity type for user {user_id}: {entity_type}")
            return entity_type
        logger.info(f"No entity type found for user {user_id}, defaulting to sole_proprietor")
        return 'sole_proprietor'
    except Exception as e:
        logger.error(f"Error retrieving entity type for user {user_id}: {str(e)}")
        return 'sole_proprietor'

def update_user_entity_type(user_id, entity_type, db):
    try:
        if entity_type not in ENTITY_TYPES:
            raise ValueError(trans('tax_invalid_entity_type_value', default=f"Invalid entity type: {entity_type}. Must be one of: {list(ENTITY_TYPES.keys())}"))
        result = db.user_entities.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'business_entity_type': entity_type,
                    'updated_at': datetime.now(ZoneInfo("UTC"))
                },
                '$setOnInsert': {
                    'created_at': datetime.now(ZoneInfo("UTC"))
                }
            },
            upsert=True
        )
        logger.info(f"Updated entity type for user {user_id} to {entity_type}")
        return True
    except Exception as e:
        logger.error(f"Error updating entity type for user {user_id}: {str(e)}")
        return False

def validate_entity_type(entity_type):
    return entity_type in ENTITY_TYPES

def get_entity_type_info(entity_type):
    import json
    entity_info = ENTITY_TYPES.get(entity_type)
    if entity_info:
        sanitized_info = {}
        for key, value in entity_info.items():
            if isinstance(value, str):
                sanitized_info[key] = json.dumps(value)[1:-1]
            else:
                sanitized_info[key] = value
        return sanitized_info
    return None

def get_total_income(user_id, tax_year, db):
    try:
        income_query = {
            'user_id': user_id,
            'type': 'receipt',
            'tax_year': tax_year
        }
        from utils import safe_find_cashflows
        income_records = safe_find_cashflows(db, income_query)
        total_income = sum(record.get('amount', 0) for record in income_records)
        logger.info(f"Retrieved total income for user {user_id} in {tax_year}: {total_income}")
        return float(total_income)
    except Exception as e:
        logger.error(f"Error retrieving total income for user {user_id} in {tax_year}: {str(e)}")
        return 0.0

def get_expenses_by_categories(user_id, tax_year, category_list, db):
    try:
        pipeline = [
            {
                '$match': {
                    'user_id': user_id,
                    'type': 'payment',
                    'tax_year': tax_year,
                    'expense_category': {'$in': category_list}
                }
            },
            {
                '$group': {
                    '_id': '$expense_category',
                    'total_amount': {'$sum': '$amount'},
                    'count': {'$sum': 1}
                }
            }
        ]
        results = list(db.cashflows.aggregate(pipeline))
        category_totals = {category: 0.0 for category in category_list}
        for result in results:
            category = result['_id']
            if category in category_totals:
                category_totals[category] = float(result['total_amount'])
        logger.info(f"Retrieved expenses by categories for user {user_id} in {tax_year}: {category_totals}")
        return category_totals
    except Exception as e:
        logger.error(f"Error retrieving expenses by categories for user {user_id} in {tax_year}: {str(e)}")
        try:
            expense_query = {
                'user_id': user_id,
                'type': 'payment',
                'tax_year': tax_year,
                'expense_category': {'$in': category_list}
            }
            expense_records = safe_find_cashflows(db, expense_query)
            category_totals = {category: 0.0 for category in category_list}
            for record in expense_records:
                category = record.get('expense_category')
                amount = record.get('amount', 0)
                if category in category_totals:
                    category_totals[category] += float(amount)
            return category_totals
        except Exception as fallback_error:
            logger.error(f"Fallback query also failed for user {user_id} in {tax_year}: {str(fallback_error)}")
            return {category: 0.0 for category in category_list}

def calculate_net_business_profit(user_id, tax_year, db):
    try:
        deductible_categories = [
            'office_admin', 'staff_wages', 'business_travel', 
            'rent_utilities', 'marketing_sales', 'cogs'
        ]
        total_income = get_total_income(user_id, tax_year, db)
        deductible_expenses = get_expenses_by_categories(user_id, tax_year, deductible_categories, db)
        total_deductible_expenses = sum(deductible_expenses.values())
        net_business_profit = total_income - total_deductible_expenses
        breakdown = {
            'step': 1,
            'step_name': trans('tax_step1_net_business_profit', default='Net Business Profit Calculation'),
            'total_income': total_income,
            'deductible_categories': deductible_categories,
            'expense_breakdown': deductible_expenses,
            'total_deductible_expenses': total_deductible_expenses,
            'net_business_profit': net_business_profit,
            'calculation_formula': trans('tax_step1_formula', default='Total Income - Sum of 6 Deductible Categories')
        }
        logger.info(f"Calculated net business profit for user {user_id} in {tax_year}: {net_business_profit}")
        return breakdown
    except Exception as e:
        logger.error(f"Error calculating net business profit for user {user_id} in {tax_year}: {str(e)}")
        return {
            'step': 1,
            'step_name': trans('tax_step1_net_business_profit', default='Net Business Profit Calculation'),
            'total_income': 0.0,
            'deductible_categories': [],
            'expense_breakdown': {},
            'total_deductible_expenses': 0.0,
            'net_business_profit': 0.0,
            'error': str(e)
        }

def apply_statutory_deductions(net_business_profit, user_id, tax_year, db):
    try:
        statutory_expenses = get_expenses_by_categories(user_id, tax_year, ['statutory_contributions'], db)
        statutory_amount = statutory_expenses.get('statutory_contributions', 0.0)
        adjusted_profit = net_business_profit - statutory_amount
        breakdown = {
            'step': 2,
            'step_name': trans('tax_step2_statutory_deductions', default='Statutory Deductions'),
            'net_business_profit_input': net_business_profit,
            'statutory_contributions_expenses': statutory_amount,
            'adjusted_profit_after_statutory': adjusted_profit,
            'calculation_formula': trans('tax_step2_formula', default='Net Business Profit - Statutory Contributions')
        }
        logger.info(f"Applied statutory deductions for user {user_id} in {tax_year}: {statutory_amount}, adjusted profit: {adjusted_profit}")
        return breakdown
    except Exception as e:
        logger.error(f"Error applying statutory deductions for user {user_id} in {tax_year}: {str(e)}")
        return {
            'step': 2,
            'step_name': trans('tax_step2_statutory_deductions', default='Statutory Deductions'),
            'net_business_profit_input': net_business_profit,
            'statutory_contributions_expenses': 0.0,
            'adjusted_profit_after_statutory': net_business_profit,
            'error': str(e)
        }

def apply_rent_relief(adjusted_profit_after_statutory, user_id, tax_year, db):
    try:
        rent_expenses = get_expenses_by_categories(user_id, tax_year, ['rent_utilities'], db)
        annual_rent_expenses = rent_expenses.get('rent_utilities', 0.0)
        if annual_rent_expenses <= 0:
            rent_relief = 0.0
            rent_relief_calculation = trans('tax_no_rent_expenses', default='No rent expenses found')
        else:
            twenty_percent_rent = annual_rent_expenses * 0.20
            max_rent_relief = 500000.0
            rent_relief = min(twenty_percent_rent, max_rent_relief)
            rent_relief_calculation = trans('tax_rent_relief_formula', default=f"min(20% of {annual_rent_expenses:,.2f}, NGN 500,000) = min({twenty_percent_rent:,.2f}, {max_rent_relief:,.2f}) = {rent_relief:,.2f}")
        taxable_income_after_rent_relief = adjusted_profit_after_statutory - rent_relief
        breakdown = {
            'step': 3,
            'step_name': trans('tax_step3_rent_relief', default='Rent Relief Calculation and Application'),
            'adjusted_profit_input': adjusted_profit_after_statutory,
            'annual_rent_utilities_expenses': annual_rent_expenses,
            'twenty_percent_of_rent': annual_rent_expenses * 0.20 if annual_rent_expenses > 0 else 0.0,
            'max_rent_relief_cap': 500000.0,
            'calculated_rent_relief': rent_relief,
            'rent_relief_calculation': rent_relief_calculation,
            'taxable_income_after_rent_relief': taxable_income_after_rent_relief,
            'calculation_formula': trans('tax_step3_formula', default='Adjusted Profit - min(20% of Rent Expenses, NGN 500,000)')
        }
        logger.info(f"Applied rent relief for user {user_id} in {tax_year}: {rent_relief}, taxable income: {taxable_income_after_rent_relief}")
        return breakdown
    except Exception as e:
        logger.error(f"Error applying rent relief for user {user_id} in {tax_year}: {str(e)}")
        return {
            'step': 3,
            'step_name': trans('tax_step3_rent_relief', default='Rent Relief Calculation and Application'),
            'adjusted_profit_input': adjusted_profit_after_statutory,
            'annual_rent_utilities_expenses': 0.0,
            'twenty_percent_of_rent': 0.0,
            'max_rent_relief_cap': 500000.0,
            'calculated_rent_relief': 0.0,
            'taxable_income_after_rent_relief': adjusted_profit_after_statutory,
            'error': str(e)
        }

def apply_progressive_tax_bands(taxable_income):
    try:
        tax_bands = [
            {'min': 0, 'max': 800000, 'rate': 0.0, 'description': trans('tax_band_1', default='First NGN 800,000 (Tax-free)')},
            {'min': 800001, 'max': 3000000, 'rate': 0.15, 'description': trans('tax_band_2', default='Next NGN 2,200,000 (15%)')},
            {'min': 3000001, 'max': 12000000, 'rate': 0.18, 'description': trans('tax_band_3', default='Next NGN 9,000,000 (18%)')},
            {'min': 12000001, 'max': 25000000, 'rate': 0.21, 'description': trans('tax_band_4', default='Next NGN 13,000,000 (21%)')},
            {'min': 25000001, 'max': 50000000, 'rate': 0.23, 'description': trans('tax_band_5', default='Next NGN 25,000,000 (23%)')},
            {'min': 50000001, 'max': float('inf'), 'rate': 0.25, 'description': trans('tax_band_6', default='Above NGN 50,000,000 (25%)')}
        ]
        if taxable_income <= 0:
            return {
                'step': 4,
                'step_name': trans('tax_step4_progressive_tax', default='Progressive Tax Band Application'),
                'taxable_income': taxable_income,
                'total_tax_liability': 0.0,
                'effective_tax_rate': 0.0,
                'tax_band_breakdown': [],
                'calculation_note': trans('tax_no_tax_due', default='No tax liability due to zero or negative taxable income')
            }
        total_tax = 0.0
        tax_band_breakdown = []
        for band in tax_bands:
            band_min = band['min']
            band_max = band['max']
            rate = band['rate']
            description = band['description']
            if taxable_income < band_min:
                continue
            if taxable_income <= band_max:
                taxable_in_band = taxable_income - band_min + 1
            else:
                taxable_in_band = band_max - band_min + 1
            tax_in_band = taxable_in_band * rate
            total_tax += tax_in_band
            tax_band_breakdown.append({
                'band_description': description,
                'band_min': band_min,
                'band_max': band_max if band_max != float('inf') else None,
                'tax_rate': rate,
                'taxable_amount_in_band': taxable_in_band,
                'tax_in_band': tax_in_band,
                'band_formula': trans('tax_band_formula', default=f"{taxable_in_band:,.2f} × {rate:.1%} = {tax_in_band:,.2f}")
            })
        effective_tax_rate = (total_tax / taxable_income * 100) if taxable_income > 0 else 0.0
        breakdown = {
            'step': 4,
            'step_name': trans('tax_step4_progressive_tax', default='Progressive Tax Band Application'),
            'taxable_income': taxable_income,
            'total_tax_liability': total_tax,
            'effective_tax_rate': effective_tax_rate,
            'tax_band_breakdown': tax_band_breakdown,
            'calculation_formula': trans('tax_step4_formula', default='Progressive tax bands applied to taxable income')
        }
        logger.info(f"Applied progressive tax bands to taxable income {taxable_income}: total tax {total_tax}")
        return breakdown
    except Exception as e:
        logger.error(f"Error applying progressive tax bands to taxable income {taxable_income}: {str(e)}")
        return {
            'step': 4,
            'step_name': trans('tax_step4_progressive_tax', default='Progressive Tax Band Application'),
            'taxable_income': taxable_income,
            'total_tax_liability': 0.0,
            'effective_tax_rate': 0.0,
            'tax_band_breakdown': [],
            'error': str(e)
        }

def calculate_cit_taxable_income(user_id, tax_year, db):
    try:
        total_income = get_total_income(user_id, tax_year, db)
        all_business_categories = [
            'office_admin', 'staff_wages', 'business_travel', 
            'rent_utilities', 'marketing_sales', 'cogs', 'statutory_contributions'
        ]
        business_expenses = get_expenses_by_categories(user_id, tax_year, all_business_categories, db)
        total_business_expenses = sum(business_expenses.values())
        taxable_income = total_income - total_business_expenses
        breakdown = {
            'calculation_type': 'CIT_taxable_income',
            'total_income': total_income,
            'business_expense_categories': all_business_categories,
            'expense_breakdown': business_expenses,
            'total_business_expenses': total_business_expenses,
            'taxable_income': taxable_income,
            'calculation_formula': trans('tax_cit_formula', default='Total Income - All Business Expenses')
        }
        logger.info(f"Calculated CIT taxable income for user {user_id} in {tax_year}: {taxable_income}")
        return breakdown
    except Exception as e:
        logger.error(f"Error calculating CIT taxable income for user {user_id} in {tax_year}: {str(e)}")
        return {
            'calculation_type': 'CIT_taxable_income',
            'total_income': 0.0,
            'business_expense_categories': [],
            'expense_breakdown': {},
            'total_business_expenses': 0.0,
            'taxable_income': 0.0,
            'error': str(e)
        }

@handle_calculation_errors
def calculate_cit_liability(user_id, tax_year, db):
    if not user_id:
        raise DataValidationError(trans('tax_user_id_required', default="User ID is required for CIT calculation"), field='user_id', value=user_id)
    validated_tax_year = validate_tax_year(tax_year)
    if db is None:
        raise InsufficientDataError(trans('tax_db_required', default="Database connection is required"), missing_data=['database'])
    log_calculation_attempt(user_id, 'CIT', {'tax_year': validated_tax_year})
    try:
        total_income = get_total_income(user_id, validated_tax_year, db)
        if total_income is None:
            raise InsufficientDataError(
                trans('tax_no_income_data', default="No income data found for CIT calculation"),
                missing_data=['income_data']
            )
        total_income = safe_float_conversion(total_income, 'total_income')
        cit_revenue_threshold = 50000000.0
        logger.info(f"CIT: Total revenue {total_income:,.2f}, threshold {cit_revenue_threshold:,.2f}")
        if total_income <= cit_revenue_threshold:
            logger.info(f"CIT: Applying small company exemption for user {user_id}")
            calculation_result = {
                'calculation_type': 'CIT',
                'entity_type': 'limited_liability',
                'tax_year': validated_tax_year,
                'total_revenue': total_income,
                'revenue_threshold': cit_revenue_threshold,
                'exemption_applied': True,
                'tax_rate': 0.0,
                'taxable_income': 0.0,
                'tax_liability': 0.0,
                'final_tax_liability': 0.0,
                'effective_tax_rate': 0.0,
                'exemption_reason': trans('tax_small_company_exemption', default=f'Small company exemption (revenue ≤₦{cit_revenue_threshold:,.0f})'),
                'calculation_note': trans('tax_no_tax_due_small_company', default='No tax liability due to small company exemption')
            }
        else:
            logger.info(f"CIT: Calculating taxable income for large company user {user_id}")
            taxable_income_breakdown = calculate_cit_taxable_income(user_id, validated_tax_year, db)
            if not taxable_income_breakdown or 'taxable_income' not in taxable_income_breakdown:
                raise TaxCalculationError(
                    trans('tax_cit_taxable_failure', default="Failed to calculate CIT taxable income"),
                    error_code='CIT_TAXABLE_INCOME_FAILURE',
                    details={'user_id': user_id, 'tax_year': validated_tax_year}
                )
            taxable_income = safe_float_conversion(
                taxable_income_breakdown.get('taxable_income', 0.0),
                'taxable_income',
                allow_negative=True
            )
            cit_rate = 0.30
            tax_liability = max(0.0, taxable_income * cit_rate)
            effective_tax_rate = (tax_liability / total_income * 100) if total_income > 0 else 0.0
            logger.info(f"CIT: Tax liability {tax_liability:,.2f} for user {user_id}")
            calculation_result = {
                'calculation_type': 'CIT',
                'entity_type': 'limited_liability',
                'tax_year': validated_tax_year,
                'total_revenue': total_income,
                'revenue_threshold': cit_revenue_threshold,
                'exemption_applied': False,
                'taxable_income_breakdown': taxable_income_breakdown,
                'taxable_income': taxable_income,
                'tax_rate': cit_rate,
                'tax_liability': tax_liability,
                'effective_tax_rate': effective_tax_rate,
                'calculation_formula': trans('tax_cit_calculation', default=f'Taxable Income × {cit_rate:.0%} = ₦{taxable_income:,.2f} × {cit_rate:.0%} = ₦{tax_liability:,.2f}')
            }
        calculation_result['calculation_timestamp'] = datetime.now(ZoneInfo("UTC")).isoformat()
        logger.info(f"Calculated CIT liability for user {user_id} in {tax_year}: ₦{calculation_result['tax_liability']:,.2f}")
        return calculation_result
    except Exception as e:
        logger.error(f"Error calculating CIT liability for user {user_id} in {tax_year}: {str(e)}")
        return {
            'calculation_type': 'CIT',
            'entity_type': 'limited_liability',
            'tax_year': tax_year,
            'total_revenue': 0.0,
            'tax_liability': 0.0,
            'effective_tax_rate': 0.0,
            'error': str(e),
            'calculation_timestamp': datetime.now(ZoneInfo("UTC")).isoformat()
        }

@handle_calculation_errors
def calculate_pit_liability(user_id, tax_year, db):
    if not user_id:
        raise DataValidationError(trans('tax_user_id_required', default="User ID is required for PIT calculation"), field='user_id', value=user_id)
    validated_tax_year = validate_tax_year(tax_year)
    if db is None:
        raise InsufficientDataError(trans('tax_db_required', default="Database connection is required"), missing_data=['database'])
    log_calculation_attempt(user_id, 'PIT', {'tax_year': validated_tax_year})
    try:
        logger.info(f"PIT Step 1: Calculating net business profit for user {user_id}")
        step1_result = calculate_net_business_profit(user_id, validated_tax_year, db)
        if not step1_result or 'net_business_profit' not in step1_result:
            raise TaxCalculationError(
                trans('tax_step1_failure', default="Failed to calculate net business profit"),
                error_code='STEP1_FAILURE',
                details={'user_id': user_id, 'tax_year': validated_tax_year}
            )
        net_business_profit = safe_float_conversion(
            step1_result.get('net_business_profit', 0.0),
            'net_business_profit',
            allow_negative=True
        )
        logger.info(f"PIT Step 2: Applying statutory deductions for user {user_id}")
        step2_result = apply_statutory_deductions(net_business_profit, user_id, validated_tax_year, db)
        if not step2_result or 'adjusted_profit_after_statutory' not in step2_result:
            raise TaxCalculationError(
                trans('tax_step2_failure', default="Failed to apply statutory deductions"),
                error_code='STEP2_FAILURE',
                details={'user_id': user_id, 'tax_year': validated_tax_year}
            )
        adjusted_profit_after_statutory = safe_float_conversion(
            step2_result.get('adjusted_profit_after_statutory', 0.0),
            'adjusted_profit_after_statutory',
            allow_negative=True
        )
        logger.info(f"PIT Step 3: Applying rent relief for user {user_id}")
        step3_result = apply_rent_relief(adjusted_profit_after_statutory, user_id, validated_tax_year, db)
        if not step3_result or 'taxable_income_after_rent_relief' not in step3_result:
            raise TaxCalculationError(
                trans('tax_step3_failure', default="Failed to apply rent relief"),
                error_code='STEP3_FAILURE',
                details={'user_id': user_id, 'tax_year': validated_tax_year}
            )
        taxable_income = safe_float_conversion(
            step3_result.get('taxable_income_after_rent_relief', 0.0),
            'taxable_income_after_rent_relief',
            allow_negative=True
        )
        logger.info(f"PIT Step 4: Applying progressive tax bands for user {user_id}")
        step4_result = apply_progressive_tax_bands(max(0, taxable_income))
        if not step4_result or 'total_tax_liability' not in step4_result:
            raise TaxCalculationError(
                trans('tax_step4_failure', default="Failed to apply progressive tax bands"),
                error_code='STEP4_FAILURE',
                details={'user_id': user_id, 'tax_year': validated_tax_year}
            )
        final_tax_liability = safe_float_conversion(
            step4_result.get('total_tax_liability', 0.0),
            'final_tax_liability'
        )
        complete_calculation = {
            'calculation_type': 'PIT',
            'entity_type': 'sole_proprietor',
            'user_id': user_id,
            'tax_year': validated_tax_year,
            'calculation_timestamp': datetime.now(ZoneInfo("UTC")).isoformat(),
            'step1_net_business_profit': step1_result,
            'step2_statutory_deductions': step2_result,
            'step3_rent_relief': step3_result,
            'step4_progressive_tax': step4_result,
            'final_tax_liability': final_tax_liability,
            'effective_tax_rate': step4_result.get('effective_tax_rate', 0.0),
            'summary': {
                'total_income': step1_result.get('total_income', 0.0),
                'total_deductible_expenses': step1_result.get('total_deductible_expenses', 0.0),
                'statutory_expenses': step2_result.get('statutory_contributions_expenses', 0.0),
                'rent_relief': step3_result.get('calculated_rent_relief', 0.0),
                'taxable_income': taxable_income,
                'final_tax_liability': final_tax_liability
            }
        }
        logger.info(f"Completed PIT calculation for user {user_id} in {tax_year}: final tax ₦{final_tax_liability:,.2f}")
        return complete_calculation
    except Exception as e:
        logger.error(f"Error in PIT calculation for user {user_id} in {tax_year}: {str(e)}")
        return {
            'calculation_type': 'PIT',
            'entity_type': 'sole_proprietor',
            'user_id': user_id,
            'tax_year': tax_year,
            'calculation_timestamp': datetime.now(ZoneInfo("UTC")).isoformat(),
            'error': str(e),
            'final_tax_liability': 0.0,
            'effective_tax_rate': 0.0
        }

@handle_calculation_errors
def calculate_tax_liability(user_id, tax_year, db):
    if not user_id:
        raise DataValidationError(trans('tax_user_id_required', default="User ID is required"), field='user_id', value=user_id)
    validated_tax_year = validate_tax_year(tax_year)
    log_calculation_attempt(user_id, 'ROUTING', {'tax_year': validated_tax_year})
    try:
        if db is None:
            raise InsufficientDataError(trans('tax_db_required', default="Database connection is required"), missing_data=['database'])
        entity_type = get_user_entity_type(user_id, db)
        logger.info(f"Calculating tax liability for user {user_id} ({entity_type}) in {validated_tax_year}")
        if entity_type == 'limited_liability':
            result = calculate_cit_liability(user_id, validated_tax_year, db)
        else:
            result = calculate_pit_liability(user_id, validated_tax_year, db)
        if not isinstance(result, dict):
            raise TaxCalculationError(trans('tax_invalid_result_format', default="Invalid calculation result format"))
        required_fields = ['final_tax_liability', 'effective_tax_rate']
        missing_fields = [field for field in required_fields if field not in result]
        if missing_fields:
            raise TaxCalculationError(
                trans('tax_missing_fields', default=f"Calculation result missing required fields: {missing_fields}"),
                error_code='INCOMPLETE_RESULT',
                details={'missing_fields': missing_fields}
            )
        result.update({
            'calculation_timestamp': datetime.now(ZoneInfo("UTC")).isoformat(),
            'calculation_version': '2.0',
            'entity_type': entity_type
        })
        logger.info(f"Tax calculation completed successfully for user {user_id}")
        return result
    except TaxCalculationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in tax calculation for user {user_id}: {str(e)}", exc_info=True)
        raise TaxCalculationError(
            trans('tax_unexpected_calculation_error', default=f"Unexpected error during tax calculation: {str(e)}"),
            error_code='CALCULATION_FAILURE',
            details={'user_id': user_id, 'tax_year': validated_tax_year}
        ) from e

def calculate_four_step_tax_liability(user_id, tax_year, db):
    return calculate_tax_liability(user_id, tax_year, db)

