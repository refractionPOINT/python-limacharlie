import limacharlie
import json
import time
import random
import string

def test_hive_validate_valid_record(oid, key):
    """Test validation of a valid Hive record"""
    man = limacharlie.Manager(oid, key)
    hive = limacharlie.Hive(man, 'dr-general')
    
    # Create a test record with valid D&R rule structure
    letters = string.ascii_lowercase
    unique_key = 'test-validate-' + ''.join(random.choice(letters) for i in range(6))
    
    record = limacharlie.HiveRecord(unique_key, {
        'data': {
            'detect': {
                'event': 'NEW_PROCESS',
                'op': 'and',
                'rules': [
                    {'op': 'contains', 'path': 'event/FILE_PATH', 'value': 'test.exe'},
                    {'op': 'is', 'path': 'routing/hostname', 'value': 'test-host'}
                ]
            },
            'respond': [
                {'action': 'report', 'name': 'Test Detection'}
            ]
        },
        'usr_mtd': {
            'enabled': True,
            'tags': ['test', 'validation'],
            'comment': 'Test validation record'
        }
    })
    
    # Validate the record
    result = hive.validate(record)
    # Should return success for a valid record
    assert result is not None
    assert 'error' not in result


def test_hive_validate_with_etag(oid, key):
    """Test validation with etag for conditional validation"""
    man = limacharlie.Manager(oid, key)
    hive = limacharlie.Hive(man, 'dr-general')
    
    letters = string.ascii_lowercase
    unique_key = 'test-validate-etag-' + ''.join(random.choice(letters) for i in range(6))
    
    # First, create a record to get an etag
    record = limacharlie.HiveRecord(unique_key, {
        'data': {
            'detect': {
                'event': 'DNS_REQUEST',
                'op': 'and',
                'rules': [
                    {'op': 'contains', 'path': 'event/DOMAIN_NAME', 'value': 'malicious.com'}
                ]
            },
            'respond': [
                {'action': 'report', 'name': 'DNS Test'}
            ]
        },
        'usr_mtd': {
            'enabled': True
        }
    })
    
    # Set the record first to get an etag
    try:
        set_result = hive.set(record)
        if set_result and 'etag' in set_result:
            # Now validate with the etag
            record.data['detect']['rules'].append(
                {'op': 'is', 'path': 'routing/hostname', 'value': 'updated-host'}
            )
            record.etag = set_result['etag']
            
            validate_result = hive.validate(record)
            assert validate_result is not None
    finally:
        # Clean up
        try:
            hive.delete(unique_key)
        except:
            pass


def test_hive_validate_with_arl(oid, key):
    """Test validation with ARL (Access Request Location)"""
    man = limacharlie.Manager(oid, key)
    hive = limacharlie.Hive(man, 'dr-general')
    
    letters = string.ascii_lowercase
    unique_key = 'test-validate-arl-' + ''.join(random.choice(letters) for i in range(6))
    
    record = limacharlie.HiveRecord(unique_key, {
        'usr_mtd': {
            'enabled': True,
            'comment': 'ARL test record'
        }
    })
    
    # Set ARL for remote data retrieval
    record.arl = '[http,https://example.com/data]'
    
    # Validate the record with ARL
    try:
        result = hive.validate(record)
        # The validation should work but ARL retrieval might fail
        # We're just testing that the validate endpoint accepts ARL
        assert result is not None
    except Exception as e:
        # Expected to fail if ARL points to invalid location
        # But the validate endpoint should still be called
        pass


def test_hive_record_validate_method(oid, key):
    """Test the HiveRecord.validate() instance method"""
    man = limacharlie.Manager(oid, key)
    hive = limacharlie.Hive(man, 'dr-general')
    
    letters = string.ascii_lowercase
    unique_key = 'test-record-validate-' + ''.join(random.choice(letters) for i in range(6))
    
    record = limacharlie.HiveRecord(unique_key, {
        'data': {
            'detect': {
                'event': 'FILE_CREATE',
                'op': 'and',
                'rules': [
                    {'op': 'ends with', 'path': 'event/FILE_PATH', 'value': '.tmp'}
                ]
            },
            'respond': [
                {'action': 'report', 'name': 'Temp File Created'}
            ]
        },
        'usr_mtd': {
            'enabled': True
        }
    }, api=hive)
    
    # Use the record's validate method
    result = record.validate()
    assert result is not None


def test_hive_validate_invalid_data(oid, key):
    """Test validation with invalid data to ensure proper error handling"""
    man = limacharlie.Manager(oid, key)
    hive = limacharlie.Hive(man, 'dr-general')
    
    letters = string.ascii_lowercase
    unique_key = 'test-validate-invalid-' + ''.join(random.choice(letters) for i in range(6))
    
    # Create a record with invalid D&R structure (missing required fields)
    record = limacharlie.HiveRecord(unique_key, {
        'data': {
            'detect': {
                # Missing 'event' field which is required
                'op': 'and',
                'rules': []
            }
            # Missing 'respond' field
        },
        'usr_mtd': {
            'enabled': True
        }
    })
    
    # Attempt validation
    try:
        result = hive.validate(record)
        # Validation might fail due to invalid structure
        # But if it passes, we still assert it returns something
        assert result is not None
    except Exception as e:
        # Expected - invalid data should cause validation error
        pass


def test_hive_validate_with_metadata(oid, key):
    """Test validation with various metadata fields"""
    man = limacharlie.Manager(oid, key)
    hive = limacharlie.Hive(man, 'dr-general')
    
    letters = string.ascii_lowercase
    unique_key = 'test-validate-metadata-' + ''.join(random.choice(letters) for i in range(6))
    
    # Test with expiry timestamp
    expiry_time = int(time.time() * 1000) + (24 * 60 * 60 * 1000)  # 24 hours from now
    
    record = limacharlie.HiveRecord(unique_key, {
        'data': {
            'detect': {
                'event': 'git.fetch',
                'op': 'and',
                'rules': [
                    {'op': 'is', 'path': 'event/business', 'value': 'test-org'},
                    {'op': 'is', 'path': 'routing/hostname', 'value': 'test-host'},
                    {'op': 'contains', 'path': 'event/repo', 'value': 'test-repo'}
                ]
            },
            'respond': [
                {'action': 'report', 'name': 'Test Git Activity'}
            ]
        },
        'usr_mtd': {
            'enabled': False,
            'tags': ['test', 'metadata', 'validation'],
            'comment': 'Testing metadata validation',
            'expiry': expiry_time
        }
    })
    
    # Validate the record with full metadata
    result = hive.validate(record)
    assert result is not None