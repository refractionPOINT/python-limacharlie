#!/usr/bin/env python3
"""
Example demonstrating the Hive validation API endpoint.

This script shows how to validate Hive records before actually storing them,
which helps prevent invalid configurations from being committed.
"""

import limacharlie
import json
import sys

def main():
    # Initialize the LimaCharlie manager
    # You can pass credentials directly or use environment variables
    man = limacharlie.Manager()
    
    # Example 1: Validate a simple record
    print("Example 1: Validating a simple record")
    print("-" * 40)
    
    hive = limacharlie.Hive(man, 'config_rules')
    
    # Create a record to validate
    record = limacharlie.HiveRecord('test_rule', {
        'data': {
            'rule_type': 'detection',
            'criteria': {
                'event_type': 'NEW_PROCESS',
                'filters': [
                    {'field': 'FILE_PATH', 'op': 'contains', 'value': 'suspicious.exe'}
                ]
            },
            'action': 'alert'
        },
        'usr_mtd': {
            'enabled': True,
            'tags': ['test', 'validation'],
            'comment': 'Test detection rule for validation'
        }
    })
    
    # Validate the record
    try:
        result = hive.validate(record)
        if 'error' not in result:
            print("✓ Record validation successful")
        else:
            print(f"✗ Validation failed: {result['error']}")
    except Exception as e:
        print(f"✗ Validation error: {e}")
    
    print()
    
    # Example 2: Validate with conditional update (etag)
    print("Example 2: Validating with etag for conditional updates")
    print("-" * 40)
    
    # In a real scenario, you would fetch an existing record first to get its etag
    existing_record = limacharlie.HiveRecord('existing_rule', {
        'data': {'config': 'value'},
        'sys_mtd': {'etag': 'abc123'}  # This would come from a previous fetch
    })
    
    # Modify the record and validate with etag
    existing_record.data['config'] = 'new_value'
    existing_record.etag = 'abc123'  # Use the etag for conditional validation
    
    try:
        result = hive.validate(existing_record)
        print("✓ Conditional validation completed")
    except Exception as e:
        if 'ETAG_MISMATCH' in str(e):
            print("✗ Etag mismatch - record was modified by another process")
        else:
            print(f"✗ Validation error: {e}")
    
    print()
    
    # Example 3: Using the record's validate method
    print("Example 3: Using HiveRecord.validate() method")
    print("-" * 40)
    
    # Create a record with the hive API reference
    record_with_api = limacharlie.HiveRecord('api_test_rule', {
        'data': {
            'setting': 'value'
        }
    }, api=hive)
    
    # Call validate directly on the record
    try:
        result = record_with_api.validate()
        print("✓ Record validation via instance method successful")
    except Exception as e:
        print(f"✗ Validation error: {e}")
    
    print()
    
    # Example 4: Validate before update workflow
    print("Example 4: Validate-then-update workflow")
    print("-" * 40)
    
    new_record = limacharlie.HiveRecord('production_rule', {
        'data': {
            'critical_config': {
                'threshold': 100,
                'enabled': True
            }
        },
        'usr_mtd': {
            'enabled': True,
            'comment': 'Critical production configuration'
        }
    })
    
    # First validate
    try:
        validation_result = hive.validate(new_record)
        if 'error' not in validation_result:
            print("✓ Validation passed, safe to apply changes")
            
            # Now you could proceed with actually setting the record
            # result = hive.set(new_record)
            # print("✓ Record successfully stored")
        else:
            print(f"✗ Validation failed, not applying changes: {validation_result['error']}")
    except Exception as e:
        print(f"✗ Cannot proceed with update: {e}")

if __name__ == '__main__':
    main()