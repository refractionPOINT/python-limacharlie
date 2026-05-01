#!/usr/bin/env python

"""
Demo script showing how to use the Hive Batch API to perform bulk operations.

This script demonstrates:
1. Creating batch operations
2. Adding multiple operations to a batch
3. Executing the batch in a single API call
4. Handling batch responses
"""

import sys
import os
import json

# Add parent directory to path to import limacharlie
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from limacharlie import Manager
from limacharlie.Hive import Hive, HiveID, RecordID, ConfigRecordMutation


def demo_batch_operations():
    """Demonstrate batch operations on a hive"""
    
    # Initialize the manager (this will use environment variables or config file)
    man = Manager()
    
    # Create a hive instance
    hive_name = 'dr'  # Example hive name
    hive = Hive(man, hive_name)
    
    print(f"Creating batch operations for hive '{hive_name}'...")
    
    # Create a new batch operations context
    batch = hive.new_batch_operations()
    
    # Create HiveID for our records
    hive_id = HiveID(hive_name, man._oid)
    
    # Example 1: Get multiple records
    print("\n1. Adding GET operations to batch...")
    record_ids = [
        RecordID(hive_id, 'rule1'),
        RecordID(hive_id, 'rule2'),
        RecordID(hive_id, 'rule3')
    ]
    
    for record_id in record_ids:
        batch.get_record(record_id)
        print(f"   - Added GET for record: {record_id.name}")
    
    # Example 2: Set/Update multiple records
    print("\n2. Adding SET operations to batch...")
    new_rule_config = ConfigRecordMutation(
        data={
            'detect': {
                'op': 'is',
                'path': 'event_type',
                'value': 'NEW_PROCESS'
            },
            'respond': {
                'action': 'report',
                'name': 'suspicious-process'
            }
        },
        usr_mtd={
            'enabled': True,
            'tags': ['demo', 'batch'],
            'comment': 'Created via batch API demo'
        }
    )
    
    batch.set_record(
        RecordID(hive_id, 'demo_batch_rule'),
        new_rule_config
    )
    print("   - Added SET for new rule: demo_batch_rule")
    
    # Example 3: Delete a record
    print("\n3. Adding DELETE operation to batch...")
    batch.del_record(RecordID(hive_id, 'old_rule_to_delete'))
    print("   - Added DELETE for record: old_rule_to_delete")
    
    # Example 4: Get metadata only
    print("\n4. Adding GET metadata operations to batch...")
    batch.get_record_mtd(RecordID(hive_id, 'rule_metadata_check'))
    print("   - Added GET metadata for record: rule_metadata_check")
    
    # Execute all operations in a single API call
    print("\n5. Executing batch operations...")
    print(f"   Total operations in batch: {len(batch._requests)}")
    
    try:
        responses = batch.execute()
        
        print(f"\n6. Processing {len(responses)} responses...")
        for i, response in enumerate(responses):
            if 'error' in response:
                print(f"   Operation {i+1}: ERROR - {response['error']}")
            else:
                print(f"   Operation {i+1}: SUCCESS")
                if 'data' in response and response['data']:
                    # Print a snippet of the data
                    data_str = json.dumps(response['data'])
                    if len(data_str) > 100:
                        data_str = data_str[:100] + "..."
                    print(f"      Data: {data_str}")
    
    except Exception as e:
        print(f"Error executing batch: {e}")
        return 1
    
    # Example 5: Using dict-based record IDs (alternative approach)
    print("\n7. Alternative: Using dict-based record IDs...")
    batch2 = hive.new_batch_operations()
    
    # You can also pass dicts instead of RecordID objects
    record_dict = {
        'hive': {'name': hive_name, 'partition': man._oid},
        'name': 'another_rule'
    }
    batch2.get_record(record_dict)
    
    config_dict = {
        'data': {'some': 'config'},
        'usr_mtd': {'enabled': False}
    }
    batch2.set_record(record_dict, config_dict)
    
    print(f"   Added {len(batch2._requests)} operations using dict format")
    
    print("\nDemo completed successfully!")
    return 0


def demo_batch_with_transactions():
    """Demonstrate using batch operations for transactional updates"""
    
    man = Manager()
    hive = Hive(man, 'dr')
    
    print("Demonstrating transactional batch operations...")
    
    # Create a batch for reading multiple records
    batch_read = hive.new_batch_operations()
    hive_id = HiveID('dr', man._oid)
    
    rules_to_check = ['rule1', 'rule2', 'rule3']
    for rule_name in rules_to_check:
        batch_read.get_record(RecordID(hive_id, rule_name))
    
    print(f"Reading {len(rules_to_check)} rules...")
    responses = batch_read.execute()
    
    # Process responses and prepare updates
    batch_update = hive.new_batch_operations()
    
    for i, response in enumerate(responses):
        if 'data' in response and response['data']:
            # Modify the rule (example: add a tag)
            rule_data = response['data']
            usr_mtd = rule_data.get('usr_mtd', {})
            tags = usr_mtd.get('tags', [])
            tags.append('batch-processed')
            
            # Use etag for transactional safety
            sys_mtd = rule_data.get('sys_mtd', {})
            etag = sys_mtd.get('etag')
            
            # Add update operation
            batch_update.set_record_mtd(
                RecordID(hive_id, rules_to_check[i]),
                {'tags': tags, 'enabled': usr_mtd.get('enabled', True)},
                {'etag': etag} if etag else {}
            )
            print(f"Prepared update for {rules_to_check[i]}")
    
    if batch_update._requests:
        print(f"Executing {len(batch_update._requests)} updates...")
        update_responses = batch_update.execute()
        print(f"Updates completed: {len(update_responses)} responses")
    
    print("Transactional batch demo completed!")


if __name__ == '__main__':
    print("=" * 60)
    print("LimaCharlie Hive Batch API Demo")
    print("=" * 60)
    
    # Run the main demo
    result = demo_batch_operations()
    
    print("\n" + "=" * 60)
    
    # Optionally run the transactional demo
    # demo_batch_with_transactions()
    
    sys.exit(result)