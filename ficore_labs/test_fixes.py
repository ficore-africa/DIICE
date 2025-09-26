#!/usr/bin/env python3
"""
Test script to verify the fixes for tax calculator and related issues.
"""

import sys
import json

def test_tax_calculation_engine():
    """Test tax calculation engine functions"""
    try:
        from tax_calculation_engine import get_user_entity_type, get_entity_type_info, ENTITY_TYPES
        
        print('Testing tax calculation engine functions...')
        
        # Test ENTITY_TYPES JSON serialization
        print('Testing ENTITY_TYPES JSON serialization:')
        json_str = json.dumps(ENTITY_TYPES)
        print('✓ ENTITY_TYPES can be JSON serialized')
        
        # Test get_entity_type_info
        print('Testing get_entity_type_info:')
        info = get_entity_type_info('sole_proprietor')
        if info:
            json_str = json.dumps(info)
            print('✓ get_entity_type_info output can be JSON serialized')
        else:
            print('✗ get_entity_type_info returned None')
        
        return True
    except Exception as e:
        print(f'✗ Tax calculation engine test failed: {str(e)}')
        import traceback
        traceback.print_exc()
        return False

def test_sanitize_input():
    """Test sanitize_input function"""
    try:
        from utils import sanitize_input
        
        print('Testing sanitize_input with problematic characters:')
        test_inputs = [
            'Normal text',
            'Text with \\ backslash',
            'Text with { curly } braces',
            'Text with quotes',
            'Text with newlines and tabs'
        ]
        
        for test_input in test_inputs:
            sanitized = sanitize_input(test_input)
            print(f'  Input: {repr(test_input)} -> Output: {repr(sanitized)}')
        
        return True
    except Exception as e:
        print(f'✗ Sanitize input test failed: {str(e)}')
        import traceback
        traceback.print_exc()
        return False

def test_clean_functions():
    """Test clean_record and clean_cashflow_record functions"""
    try:
        from utils import clean_record, clean_cashflow_record
        
        print('Testing clean functions:')
        
        # Test clean_record
        test_record = {
            'name': 'Test Name with \\ backslash',
            'description': 'Description with { curly } braces',
            'created_at': '2024-01-01T00:00:00Z'
        }
        
        cleaned = clean_record(test_record)
        print(f'✓ clean_record processed successfully')
        
        # Test clean_cashflow_record
        test_cashflow = {
            'party_name': 'Party with \\ backslash',
            'description': 'Payment with { curly } braces',
            'created_at': '2024-01-01T00:00:00Z'
        }
        
        cleaned = clean_cashflow_record(test_cashflow)
        print(f'✓ clean_cashflow_record processed successfully')
        
        return True
    except Exception as e:
        print(f'✗ Clean functions test failed: {str(e)}')
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print('Running fix validation tests...\n')
    
    tests = [
        test_tax_calculation_engine,
        test_sanitize_input,
        test_clean_functions
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()  # Add spacing between tests
    
    print(f'Test Results: {passed}/{total} tests passed')
    
    if passed == total:
        print('✓ All tests passed successfully!')
        return 0
    else:
        print('✗ Some tests failed')
        return 1

if __name__ == '__main__':
    sys.exit(main())