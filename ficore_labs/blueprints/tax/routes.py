from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from . import tax_bp
import json
from datetime import datetime
import logging

# Optional dependencies with fallback
try:
    from utils import get_mongo_db, logger, get_all_expense_categories
    from translations import trans
    from tax_calculation_engine import (
        get_user_entity_type, ENTITY_TYPES, get_entity_type_info,
        calculate_tax_liability, update_user_entity_type, validate_entity_type
    )
except ImportError as e:
    # Fallback implementations
    logger = logging.getLogger(__name__)
    def get_mongo_db():
        return None
    def trans(key, default=None):
        return default or key
    def get_all_expense_categories():
        return {}
    def get_user_entity_type(user_id, db):
        return 'sole_proprietor'
    def get_entity_type_info(entity_type):
        return {
            'name': entity_type.replace('_', ' ').title(),
            'tax_type': 'PIT' if entity_type == 'sole_proprietor' else 'CIT',
            'tax_details': 'Standard tax calculation',
            'description': 'Default entity description'
        }
    ENTITY_TYPES = {
        'sole_proprietor': {
            'name': 'Sole Proprietor',
            'description': 'Individual business owner',
            'tax_type': 'PIT',
            'tax_details': 'Progressive tax rates apply'
        },
        'limited_liability': {
            'name': 'Limited Liability Company',
            'description': 'Registered company',
            'tax_type': 'CIT',
            'tax_details': 'Flat or exempt tax rates'
        }
    }
    def update_user_entity_type(user_id, entity_type, db):
        return True
    def validate_entity_type(entity_type):
        return entity_type in ENTITY_TYPES

# Progressive tax bands for Nigeria Tax Act 2025
TAX_BANDS = [
    {'min': 0, 'max': 800000, 'rate': 0.0, 'description': 'First ₦800,000 (Tax-free)'},
    {'min': 800001, 'max': 3000000, 'rate': 0.15, 'description': 'Next ₦2,200,000 (15%)'},
    {'min': 3000001, 'max': 12000000, 'rate': 0.18, 'description': 'Next ₦9,000,000 (18%)'},
    {'min': 12000001, 'max': 25000000, 'rate': 0.21, 'description': 'Next ₦13,000,000 (21%)'},
    {'min': 25000001, 'max': 50000000, 'rate': 0.23, 'description': 'Next ₦25,000,000 (23%)'},
    {'min': 50000001, 'max': float('inf'), 'rate': 0.25, 'description': 'Above ₦50,000,000 (25%)'}
]

def get_expense_categories():
    """Get expense categories with translations for tax calculator interface"""
    try:
        all_categories = get_all_expense_categories()
        translated_categories = {}
        for category_key, category_data in all_categories.items():
            name_key = f"{category_key}_cat"
            desc_key = f"{category_key}_desc"
            translated_categories[category_key] = {
                'name': trans(name_key, default=category_data.get('name', category_key)),
                'description': trans(desc_key, default=category_data.get('description', '')),
                'examples': category_data.get('examples', []),
                'tax_deductible': category_data.get('tax_deductible', False),
                'is_personal': category_data.get('is_personal', False),
                'is_statutory': category_data.get('is_statutory', False)
            }
        return translated_categories
    except Exception as e:
        logger.error(f"Error getting expense categories: {str(e)}")
        return {
            'office_admin': {
                'name': 'Office & Admin',
                'description': 'Office supplies, stationery, internet/data, utility bills',
                'examples': ['Office supplies', 'Stationery', 'Internet/Data', 'Electricity'],
                'tax_deductible': True,
                'is_personal': False,
                'is_statutory': False
            },
            'staff_wages': {
                'name': 'Staff Wages',
                'description': 'Employee salaries and wages',
                'examples': ['Salaries', 'Wages', 'Bonuses'],
                'tax_deductible': True,
                'is_personal': False,
                'is_statutory': False
            },
            'business_travel': {
                'name': 'Business Travel',
                'description': 'Travel expenses for business purposes',
                'examples': ['Flights', 'Hotels', 'Transport'],
                'tax_deductible': True,
                'is_personal': False,
                'is_statutory': False
            },
            'rent_utilities': {
                'name': 'Rent & Utilities',
                'description': 'Business premises rent and utilities',
                'examples': ['Office rent', 'Electricity', 'Water'],
                'tax_deductible': True,
                'is_personal': False,
                'is_statutory': False
            },
            'marketing_sales': {
                'name': 'Marketing & Sales',
                'description': 'Advertising and promotional expenses',
                'examples': ['Ads', 'Promotions', 'Events'],
                'tax_deductible': True,
                'is_personal': False,
                'is_statutory': False
            },
            'cogs': {
                'name': 'Cost of Goods Sold',
                'description': 'Direct costs of producing goods',
                'examples': ['Raw materials', 'Direct labor'],
                'tax_deductible': True,
                'is_personal': False,
                'is_statutory': False
            },
            'statutory_legal': {
                'name': 'Statutory & Legal Contributions',
                'description': 'Mandatory contributions and legal fees',
                'examples': ['Pension contributions', 'Tax filings', 'Legal fees'],
                'tax_deductible': True,
                'is_personal': False,
                'is_statutory': True
            },
            'personal_expenses': {
                'name': 'Personal Expenses',
                'description': 'Non-deductible personal expenses',
                'examples': ['Personal meals', 'Personal travel'],
                'tax_deductible': False,
                'is_personal': True,
                'is_statutory': False
            }
        }

def calculate_progressive_tax(taxable_income):
    """Calculate tax using progressive tax bands"""
    if taxable_income <= 0:
        return 0, []
    
    total_tax = 0
    breakdown = []
    
    for band in TAX_BANDS:
        band_min = band['min']
        band_max = band['max']
        rate = band['rate']
        
        if taxable_income < band_min:
            continue
            
        taxable_in_band = min(taxable_income, band_max) - band_min + 1
        if taxable_in_band <= 0:
            continue
            
        tax_in_band = taxable_in_band * rate
        total_tax += tax_in_band
        
        breakdown.append({
            'description': band['description'],
            'taxable_amount': taxable_in_band,
            'rate': rate,
            'tax_amount': tax_in_band,
            'formula': f'₦{taxable_in_band:,.2f} × {rate:.1%} = ₦{tax_in_band:,.2f}'
        })
    
    return total_tax, breakdown

def calculate_rent_relief(annual_rent):
    """Calculate rent relief as lower of ₦500,000 or 20% of annual rent"""
    if not annual_rent or annual_rent <= 0:
        return 0
    twenty_percent = annual_rent * 0.20
    return min(500000, twenty_percent)

def validate_calculation_inputs(total_income, expenses, annual_rent):
    """Validate and sanitize calculation inputs"""
    warnings = []
    
    try:
        validated_income = float(total_income) if total_income is not None else 0.0
        if validated_income < 0:
            warnings.append("Income was negative, adjusted to zero")
            validated_income = 0.0
    except (ValueError, TypeError):
        warnings.append("Invalid income value, using zero")
        validated_income = 0.0
    
    validated_expenses = {}
    if isinstance(expenses, dict):
        for category, amount in expenses.items():
            try:
                validated_amount = float(amount) if amount is not None else 0.0
                if validated_amount < 0:
                    warnings.append(f"Negative expense for {category}, adjusted to zero")
                    validated_amount = 0.0
                validated_expenses[category] = validated_amount
            except (ValueError, TypeError):
                warnings.append(f"Invalid expense amount for {category}, using zero")
                validated_expenses[category] = 0.0
    else:
        warnings.append("Invalid expenses data, using empty expenses")
    
    try:
        validated_rent = float(annual_rent) if annual_rent is not None else 0.0
        if validated_rent < 0:
            warnings.append("Annual rent was negative, adjusted to zero")
            validated_rent = 0.0
    except (ValueError, TypeError):
        warnings.append("Invalid annual rent value, using zero")
        validated_rent = 0.0
    
    return validated_income, validated_expenses, validated_rent, warnings

@tax_bp.route('/calculator')
@login_required
def tax_calculator():
    """Render the tax calculator page"""
    try:
        db = get_mongo_db()
        user_entity_type = get_user_entity_type(current_user.id, db)
        entity_info = get_entity_type_info(user_entity_type)
        available_entity_types = ENTITY_TYPES
        expense_categories = get_expense_categories()
        
        calculation_context = {
            'four_step_process': {
                'step1': 'Net Business Profit Calculation',
                'step2': 'Statutory & Legal Contributions Deduction',
                'step3': 'Rent Relief Application',
                'step4': 'Progressive Tax Band Application'
            },
            'deductible_categories': [key for key, data in expense_categories.items() 
                                    if data.get('tax_deductible', False) and not data.get('is_statutory', False)],
            'statutory_categories': [key for key, data in expense_categories.items() 
                                   if data.get('is_statutory', False)],
            'non_deductible_categories': [key for key, data in expense_categories.items() 
                                        if not data.get('tax_deductible', False)]
        }
        
        return render_template('tax/tax_calculator.html',
                             expense_categories=expense_categories,
                             user_annual_rent=current_user.annual_rent or 0,
                             user_entity_type=user_entity_type,
                             entity_info=entity_info,
                             available_entity_types=available_entity_types,
                             calculation_context=calculation_context)
    except Exception as e:
        logger.error(f"Error in tax_calculator route: {str(e)}")
        flash('Error loading tax calculator. Please try again.', 'error')
        return redirect(url_for('dashboard.index'))

@tax_bp.route('/calculate', methods=['POST'])
@login_required
def calculate_tax():
    """API endpoint for tax calculation with detailed breakdown"""
    try:
        db = get_mongo_db()
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided',
                'message': 'Please provide income and expense data for calculation.'
            }), 400
        
        # Validate inputs
        total_income = float(data.get('total_income', 0))
        annual_rent = float(data.get('annual_rent', current_user.annual_rent or 0))
        expenses = data.get('expenses', {})
        validated_income, validated_expenses, validated_rent, warnings = validate_calculation_inputs(
            total_income, expenses, annual_rent
        )
        
        if validated_income < 0 or any(v < 0 for v in validated_expenses.values()) or validated_rent < 0:
            return jsonify({
                'success': False,
                'error': 'Validation failed',
                'message': 'Input values cannot be negative',
                'validation_errors': warnings
            }), 400
        
        user_entity_type = get_user_entity_type(current_user.id, db)
        entity_info = get_entity_type_info(user_entity_type)
        current_year = datetime.now().year
        
        try:
            if user_entity_type == 'limited_liability':
                result = simulate_cit_calculation(validated_income, validated_expenses, entity_info)
            else:
                result = simulate_pit_four_step_calculation(validated_income, validated_expenses, validated_rent, entity_info)
            
            result['calculation_metadata'] = {
                'user_id': current_user.id,
                'calculation_timestamp': datetime.now().isoformat(),
                'tax_year': current_year,
                'calculation_version': '2.1',
                'entity_type': user_entity_type,
                'input_validation_passed': True
            }
            if warnings:
                result['calculation_warnings'] = warnings
                
            logger.info(f"Tax calculation completed for user {current_user.id}")
            return jsonify({
                'success': True,
                'breakdown': result,
                'message': 'Tax calculation completed successfully'
            })
        except Exception as calc_error:
            logger.error(f"Calculation error for user {current_user.id}: {str(calc_error)}")
            return jsonify({
                'success': False,
                'error': 'Calculation error',
                'message': 'Unable to complete tax calculation.',
                'details': str(calc_error)
            }), 400
    except Exception as e:
        logger.error(f"Unexpected error in tax calculation for user {current_user.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred.',
            'user_message': 'Please try again later.'
        }), 500

def simulate_cit_calculation(total_income, expenses, entity_info):
    """Simulate CIT calculation with detailed breakdown"""
    cit_revenue_threshold = 50000000.0
    expense_categories = get_expense_categories()
    total_expenses = sum(expenses.values())
    
    categorized_expenses = {}
    for category, amount in expenses.items():
        if category in expense_categories:
            categorized_expenses[category] = {
                'amount': amount,
                'category_name': expense_categories[category]['name'],
                'tax_deductible': expense_categories[category]['tax_deductible']
            }
    
    if total_income <= cit_revenue_threshold:
        result = {
            'calculation_type': 'CIT',
            'entity_type': 'limited_liability',
            'entity_info': entity_info,
            'total_revenue': total_income,
            'revenue_threshold': cit_revenue_threshold,
            'total_expenses': total_expenses,
            'exemption_applied': True,
            'tax_rate': 0.0,
            'taxable_income': 0.0,
            'tax_liability': 0.0,
            'effective_tax_rate': 0.0,
            'exemption_reason': f'Small company exemption (revenue ≤₦{cit_revenue_threshold:,.0f})',
            'expense_breakdown': categorized_expenses,
            'calculation_steps': [
                {
                    'step': 1,
                    'description': 'Revenue Assessment',
                    'calculation': f'Total Revenue: ₦{total_income:,.2f}',
                    'result': total_income
                },
                {
                    'step': 2,
                    'description': 'Threshold Check',
                    'calculation': f'₦{total_income:,.2f} ≤ ₦{cit_revenue_threshold:,.2f}',
                    'result': 'Exemption Applied'
                },
                {
                    'step': 3,
                    'description': 'Final Tax Liability',
                    'calculation': 'Small Company Exemption = 0% tax rate',
                    'result': 0.0
                }
            ]
        }
    else:
        taxable_income = max(0, total_income - total_expenses)
        tax_liability = taxable_income * 0.30
        effective_tax_rate = (tax_liability / total_income * 100) if total_income > 0 else 0
        
        result = {
            'calculation_type': 'CIT',
            'entity_type': 'limited_liability',
            'entity_info': entity_info,
            'total_revenue': total_income,
            'revenue_threshold': cit_revenue_threshold,
            'total_expenses': total_expenses,
            'taxable_income': taxable_income,
            'exemption_applied': False,
            'tax_rate': 0.30,
            'tax_liability': tax_liability,
            'effective_tax_rate': effective_tax_rate,
            'expense_breakdown': categorized_expenses,
            'calculation_steps': [
                {
                    'step': 1,
                    'description': 'Revenue Assessment',
                    'calculation': f'Total Revenue: ₦{total_income:,.2f}',
                    'result': total_income
                },
                {
                    'step': 2,
                    'description': 'Expense Deduction',
                    'calculation': f'₦{total_income:,.2f} - ₦{total_expenses:,.2f}',
                    'result': taxable_income
                },
                {
                    'step': 3,
                    'description': 'Tax Calculation',
                    'calculation': f'₦{taxable_income:,.2f} × 30%',
                    'result': tax_liability
                }
            ]
        }
    
    return result

def simulate_pit_four_step_calculation(total_income, expenses, annual_rent, entity_info):
    """Simulate PIT four-step calculation with detailed breakdown"""
    expense_categories = get_expense_categories()
    deductible_categories = ['office_admin', 'staff_wages', 'business_travel', 
                           'rent_utilities', 'marketing_sales', 'cogs']
    
    deductible_expenses = {}
    for category in deductible_categories:
        amount = expenses.get(category, 0)
        if amount > 0:
            deductible_expenses[category] = {
                'amount': amount,
                'category_name': expense_categories.get(category, {}).get('name', category),
                'tax_deductible': True
            }
    
    total_deductible_expenses = sum(exp['amount'] for exp in deductible_expenses.values())
    net_business_profit = total_income - total_deductible_expenses
    
    step1_breakdown = {
        'step': 1,
        'step_name': 'Net Business Profit Calculation',
        'description': 'Calculate profit using main deductible business expenses',
        'total_income': total_income,
        'deductible_expenses': deductible_expenses,
        'total_deductible_expenses': total_deductible_expenses,
        'net_business_profit': net_business_profit,
        'formula': f'₦{total_income:,.2f} - ₦{total_deductible_expenses:,.2f} = ₦{net_business_profit:,.2f}'
    }
    
    statutory_expenses = expenses.get('statutory_legal', 0)
    adjusted_profit_after_statutory = net_business_profit - statutory_expenses
    
    step2_breakdown = {
        'step': 2,
        'step_name': 'Statutory & Legal Contributions Deduction',
        'description': 'Apply statutory and legal expenses deduction',
        'net_business_profit_input': net_business_profit,
        'statutory_expenses': statutory_expenses,
        'adjusted_profit_after_statutory': adjusted_profit_after_statutory,
        'formula': f'₦{net_business_profit:,.2f} - ₦{statutory_expenses:,.2f} = ₦{adjusted_profit_after_statutory:,.2f}'
    }
    
    rent_relief = calculate_rent_relief(annual_rent)
    taxable_income_after_rent_relief = adjusted_profit_after_statutory - rent_relief
    
    step3_breakdown = {
        'step': 3,
        'step_name': 'Rent Relief Application',
        'description': 'Apply rent relief (lesser of ₦500,000 or 20% of rent)',
        'adjusted_profit_input': adjusted_profit_after_statutory,
        'annual_rent': annual_rent,
        'rent_relief': rent_relief,
        'taxable_income_after_rent_relief': taxable_income_after_rent_relief,
        'formula': f'₦{adjusted_profit_after_statutory:,.2f} - ₦{rent_relief:,.2f} = ₦{taxable_income_after_rent_relief:,.2f}'
    }
    
    final_taxable_income = max(0, taxable_income_after_rent_relief)
    tax_liability, tax_band_breakdown = calculate_progressive_tax(final_taxable_income)
    effective_tax_rate = (tax_liability / total_income * 100) if total_income > 0 else 0
    
    step4_breakdown = {
        'step': 4,
        'step_name': 'Progressive Tax Band Application',
        'description': 'Apply NTA 2025 progressive tax bands',
        'taxable_income': final_taxable_income,
        'tax_liability': tax_liability,
        'effective_tax_rate': effective_tax_rate,
        'tax_band_breakdown': tax_band_breakdown,
        'formula': f'Progressive bands applied to ₦{final_taxable_income:,.2f} = ₦{tax_liability:,.2f}'
    }
    
    personal_expenses = expenses.get('personal_expenses', 0)
    
    return {
        'calculation_type': 'PIT',
        'entity_type': 'sole_proprietor',
        'entity_info': entity_info,
        'four_step_breakdown': {
            'step1': step1_breakdown,
            'step2': step2_breakdown,
            'step3': step3_breakdown,
            'step4': step4_breakdown
        },
        'summary': {
            'total_income': total_income,
            'total_deductible_expenses': total_deductible_expenses,
            'statutory_expenses': statutory_expenses,
            'personal_expenses': personal_expenses,
            'rent_relief': rent_relief,
            'final_taxable_income': final_taxable_income,
            'tax_liability': tax_liability,
            'effective_tax_rate': effective_tax_rate
        },
        'expense_breakdown': {
            'deductible': deductible_expenses,
            'statutory': {
                'statutory_legal': {
                    'amount': statutory_expenses,
                    'category_name': 'Statutory & Legal Contributions',
                    'tax_deductible': True
                }
            } if statutory_expenses > 0 else {},
            'non_deductible': {
                'personal_expenses': {
                    'amount': personal_expenses,
                    'category_name': 'Personal Expenses',
                    'tax_deductible': False
                }
            } if personal_expenses > 0 else {}
        }
    }

@tax_bp.route('/update-rent', methods=['POST'])
@login_required
def update_annual_rent():
    """Update user's annual rent in database"""
    try:
        data = request.get_json()
        annual_rent = float(data.get('annual_rent', 0))
        
        db = get_mongo_db()
        result = db.users.update_one(
            {'_id': current_user.id},
            {'$set': {'annual_rent': annual_rent}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Updated annual rent for user {current_user.id}: {annual_rent}")
        
        return jsonify({
            'success': True,
            'message': 'Annual rent updated successfully'
        })
    except Exception as e:
        logger.error(f"Error updating annual rent for user {current_user.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@tax_bp.route('/update-entity-type', methods=['POST'])
@login_required
def update_entity_type():
    """Update user's business entity type"""
    try:
        data = request.get_json()
        entity_type = data.get('entity_type')
        
        if not validate_entity_type(entity_type):
            return jsonify({
                'success': False,
                'error': 'Invalid entity type'
            }), 400
        
        db = get_mongo_db()
        success = update_user_entity_type(current_user.id, entity_type, db)
        
        if success:
            logger.info(f"Updated entity type for user {current_user.id}: {entity_type}")
            entity_info = get_entity_type_info(entity_type)
            return jsonify({
                'success': True,
                'message': 'Entity type updated successfully',
                'entity_type': entity_type,
                'entity_info': entity_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update entity type'
            }), 500
    except Exception as e:
        logger.error(f"Error updating entity type for user {current_user.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
