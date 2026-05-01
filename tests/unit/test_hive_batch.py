import unittest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the parent directory to the path so we can import limacharlie
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from limacharlie.Hive import Hive, HiveBatch, HiveID, RecordID, ConfigRecordMutation


class TestHiveBatch(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_manager = Mock()
        self.mock_manager._oid = 'test-org-id'
        self.hive = Hive(self.mock_manager, 'test-hive', 'test-partition')
        self.batch = self.hive.new_batch_operations()
    
    def test_create_batch_operations(self):
        """Test creating a new batch operations context"""
        batch = self.hive.new_batch_operations()
        self.assertIsInstance(batch, HiveBatch)
        self.assertEqual(batch._hive, self.hive)
        self.assertEqual(batch._requests, [])
    
    def test_hive_id_creation(self):
        """Test HiveID creation and serialization"""
        hive_id = HiveID('test-hive', 'test-partition')
        self.assertEqual(hive_id.name, 'test-hive')
        self.assertEqual(hive_id.partition, 'test-partition')
        
        expected = {
            'name': 'test-hive',
            'partition': 'test-partition'
        }
        self.assertEqual(hive_id.to_dict(), expected)
    
    def test_record_id_creation(self):
        """Test RecordID creation and serialization"""
        hive_id = HiveID('test-hive', 'test-partition')
        record_id = RecordID(hive_id, 'test-record', 'test-guid')
        
        expected = {
            'hive': {
                'name': 'test-hive',
                'partition': 'test-partition'
            },
            'name': 'test-record',
            'guid': 'test-guid'
        }
        self.assertEqual(record_id.to_dict(), expected)
        
        # Test without guid
        record_id_no_guid = RecordID(hive_id, 'test-record')
        expected_no_guid = {
            'hive': {
                'name': 'test-hive',
                'partition': 'test-partition'
            },
            'name': 'test-record'
        }
        self.assertEqual(record_id_no_guid.to_dict(), expected_no_guid)
    
    def test_config_record_mutation(self):
        """Test ConfigRecordMutation creation and serialization"""
        config = ConfigRecordMutation(
            data={'key': 'value'},
            usr_mtd={'enabled': True},
            sys_mtd={'etag': 'test-etag'},
            arl='test-arl'
        )
        
        expected = {
            'data': {'key': 'value'},
            'usr_mtd': {'enabled': True},
            'sys_mtd': {'etag': 'test-etag'},
            'arl': 'test-arl'
        }
        self.assertEqual(config.to_dict(), expected)
        
        # Test with minimal data
        config_minimal = ConfigRecordMutation(data={'key': 'value'})
        expected_minimal = {
            'data': {'key': 'value'}
        }
        self.assertEqual(config_minimal.to_dict(), expected_minimal)
    
    def test_get_record(self):
        """Test adding a get record operation to the batch"""
        hive_id = HiveID('test-hive', 'test-partition')
        record_id = RecordID(hive_id, 'test-record')
        
        self.batch.get_record(record_id)
        
        self.assertEqual(len(self.batch._requests), 1)
        expected = {
            'get_record': {
                'record_id': {
                    'hive': {
                        'name': 'test-hive',
                        'partition': 'test-partition'
                    },
                    'name': 'test-record'
                }
            }
        }
        self.assertEqual(self.batch._requests[0], expected)
    
    def test_get_record_mtd(self):
        """Test adding a get record metadata operation to the batch"""
        hive_id = HiveID('test-hive', 'test-partition')
        record_id = RecordID(hive_id, 'test-record')
        
        self.batch.get_record_mtd(record_id)
        
        self.assertEqual(len(self.batch._requests), 1)
        expected = {
            'get_record_mtd': {
                'record_id': {
                    'hive': {
                        'name': 'test-hive',
                        'partition': 'test-partition'
                    },
                    'name': 'test-record'
                }
            }
        }
        self.assertEqual(self.batch._requests[0], expected)
    
    def test_set_record(self):
        """Test adding a set record operation to the batch"""
        hive_id = HiveID('test-hive', 'test-partition')
        record_id = RecordID(hive_id, 'test-record')
        config = ConfigRecordMutation(data={'key': 'value'})
        
        self.batch.set_record(record_id, config)
        
        self.assertEqual(len(self.batch._requests), 1)
        expected = {
            'set_record': {
                'record_id': {
                    'hive': {
                        'name': 'test-hive',
                        'partition': 'test-partition'
                    },
                    'name': 'test-record'
                },
                'record': {
                    'data': {'key': 'value'}
                }
            }
        }
        self.assertEqual(self.batch._requests[0], expected)
    
    def test_set_record_mtd(self):
        """Test adding a set record metadata operation to the batch"""
        hive_id = HiveID('test-hive', 'test-partition')
        record_id = RecordID(hive_id, 'test-record')
        usr_mtd = {'enabled': True}
        sys_mtd = {'etag': 'test-etag'}
        
        self.batch.set_record_mtd(record_id, usr_mtd, sys_mtd)
        
        self.assertEqual(len(self.batch._requests), 1)
        expected = {
            'set_record_mtd': {
                'record_id': {
                    'hive': {
                        'name': 'test-hive',
                        'partition': 'test-partition'
                    },
                    'name': 'test-record'
                },
                'usr_mtd': {'enabled': True},
                'sys_mtd': {'etag': 'test-etag'}
            }
        }
        self.assertEqual(self.batch._requests[0], expected)
    
    def test_del_record(self):
        """Test adding a delete record operation to the batch"""
        hive_id = HiveID('test-hive', 'test-partition')
        record_id = RecordID(hive_id, 'test-record')
        
        self.batch.del_record(record_id)
        
        self.assertEqual(len(self.batch._requests), 1)
        expected = {
            'delete_record': {
                'record_id': {
                    'hive': {
                        'name': 'test-hive',
                        'partition': 'test-partition'
                    },
                    'name': 'test-record'
                }
            }
        }
        self.assertEqual(self.batch._requests[0], expected)
    
    def test_multiple_operations(self):
        """Test adding multiple operations to the batch"""
        hive_id = HiveID('test-hive', 'test-partition')
        record_id1 = RecordID(hive_id, 'test-record-1')
        record_id2 = RecordID(hive_id, 'test-record-2')
        config = ConfigRecordMutation(data={'key': 'value'})
        
        self.batch.get_record(record_id1)
        self.batch.set_record(record_id2, config)
        self.batch.del_record(record_id1)
        
        self.assertEqual(len(self.batch._requests), 3)
    
    def test_execute_empty_batch(self):
        """Test executing an empty batch"""
        result = self.batch.execute()
        self.assertEqual(result, [])
        self.mock_manager._apiCall.assert_not_called()
    
    def test_execute_batch(self):
        """Test executing a batch with operations"""
        # Set up the mock response
        mock_response = {
            'responses': [
                {'data': {'key': 'value1'}},
                {'error': 'Record not found'}
            ]
        }
        self.mock_manager._apiCall.return_value = mock_response
        
        # Add some operations
        hive_id = HiveID('test-hive', 'test-partition')
        record_id1 = RecordID(hive_id, 'test-record-1')
        record_id2 = RecordID(hive_id, 'test-record-2')
        
        self.batch.get_record(record_id1)
        self.batch.get_record(record_id2)
        
        # Execute the batch
        result = self.batch.execute()
        
        # Verify the API call was made correctly
        self.mock_manager._apiCall.assert_called_once()
        call_args = self.mock_manager._apiCall.call_args
        self.assertEqual(call_args[0][0], 'hive')  # URL
        self.assertEqual(call_args[0][1], 'POST')  # Method
        
        # Check that the requests were properly formatted
        params = call_args[0][2]
        self.assertIn('request', params)
        self.assertEqual(len(params['request']), 2)
        
        # Verify the response
        self.assertEqual(result, mock_response['responses'])
    
    def test_record_id_from_dict(self):
        """Test creating RecordID from dict in batch operations"""
        record_dict = {
            'hive': {'name': 'test-hive', 'partition': 'test-partition'},
            'name': 'test-record',
            'guid': 'test-guid'
        }
        
        self.batch.get_record(record_dict)
        
        self.assertEqual(len(self.batch._requests), 1)
        expected = {
            'get_record': {
                'record_id': {
                    'hive': {
                        'name': 'test-hive',
                        'partition': 'test-partition'
                    },
                    'name': 'test-record',
                    'guid': 'test-guid'
                }
            }
        }
        self.assertEqual(self.batch._requests[0], expected)


if __name__ == '__main__':
    unittest.main()