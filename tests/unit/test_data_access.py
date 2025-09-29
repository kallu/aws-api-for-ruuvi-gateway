"""
Unit tests for DynamoDB data access utilities.
"""

import time
import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

from src.shared.data_access import SensorDataAccess, get_sensor_data_access, reset_sensor_data_access


class TestSensorDataAccess:
    """Test cases for SensorDataAccess class."""
    
    @pytest.fixture
    def mock_dynamodb_table(self):
        """Mock DynamoDB table."""
        with patch('boto3.resource') as mock_resource:
            mock_table = Mock()
            mock_resource.return_value.Table.return_value = mock_table
            yield mock_table
    
    @pytest.fixture
    def sensor_data_access(self, mock_dynamodb_table):
        """Create SensorDataAccess instance with mocked DynamoDB."""
        return SensorDataAccess('test-sensor-table', 'test-gsi')
    
    @pytest.fixture
    def sample_sensor_data(self):
        """Sample sensor data for testing."""
        return {
            'device_id': 'AA:BB:CC:DD:EE:FF',
            'gateway_id': '11:22:33:44:55:66',
            'timestamp': 1234567890,
            'measurements': {
                'temperature': 23.5,
                'humidity': 45.2,
                'pressure': 1013.25,
                'rssi': -65
            }
        }
    
    def test_init(self, sensor_data_access):
        """Test SensorDataAccess initialization."""
        assert sensor_data_access.table_name == 'test-sensor-table'
        assert sensor_data_access.gsi_name == 'test-gsi'
    
    def test_store_sensor_data_success(self, sensor_data_access, mock_dynamodb_table, sample_sensor_data):
        """Test storing sensor data successfully."""
        mock_dynamodb_table.put_item.return_value = {}
        
        result = sensor_data_access.store_sensor_data(
            device_id=sample_sensor_data['device_id'],
            gateway_id=sample_sensor_data['gateway_id'],
            timestamp=sample_sensor_data['timestamp'],
            measurements=sample_sensor_data['measurements'],
            ttl_days=30
        )
        
        assert result is True
        mock_dynamodb_table.put_item.assert_called_once()
        
        # Check the item structure
        call_args = mock_dynamodb_table.put_item.call_args[1]['Item']
        assert call_args['device_id'] == sample_sensor_data['device_id']
        assert call_args['gateway_id'] == sample_sensor_data['gateway_id']
        assert call_args['timestamp'] == sample_sensor_data['timestamp']
        assert call_args['measurements'] == sample_sensor_data['measurements']
        assert 'server_timestamp' in call_args
        assert 'ttl' in call_args
    
    def test_store_sensor_data_with_ruuvi_response(self, sensor_data_access, mock_dynamodb_table, sample_sensor_data):
        """Test storing sensor data with Ruuvi Cloud response."""
        mock_dynamodb_table.put_item.return_value = {}
        ruuvi_response = {'result': 'success', 'data': {'action': 'inserted'}}
        
        result = sensor_data_access.store_sensor_data(
            device_id=sample_sensor_data['device_id'],
            gateway_id=sample_sensor_data['gateway_id'],
            timestamp=sample_sensor_data['timestamp'],
            measurements=sample_sensor_data['measurements'],
            ruuvi_cloud_response=ruuvi_response
        )
        
        assert result is True
        call_args = mock_dynamodb_table.put_item.call_args[1]['Item']
        assert call_args['ruuvi_cloud_response'] == ruuvi_response
    
    def test_store_sensor_data_error(self, sensor_data_access, mock_dynamodb_table, sample_sensor_data):
        """Test handling DynamoDB errors during store."""
        mock_dynamodb_table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'ValidationException'}}, 'PutItem'
        )
        
        result = sensor_data_access.store_sensor_data(
            device_id=sample_sensor_data['device_id'],
            gateway_id=sample_sensor_data['gateway_id'],
            timestamp=sample_sensor_data['timestamp'],
            measurements=sample_sensor_data['measurements']
        )
        
        assert result is False
    
    def test_store_batch_sensor_data_success(self, sensor_data_access, mock_dynamodb_table):
        """Test batch storing sensor data successfully."""
        mock_batch_writer = MagicMock()
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_batch_writer
        mock_context_manager.__exit__.return_value = None
        mock_dynamodb_table.batch_writer.return_value = mock_context_manager
        
        sensor_data_list = [
            {
                'device_id': 'device1',
                'gateway_id': 'gateway1',
                'timestamp': 1234567890,
                'measurements': {'temp': 20.0}
            },
            {
                'device_id': 'device2',
                'gateway_id': 'gateway1',
                'timestamp': 1234567891,
                'measurements': {'temp': 21.0}
            }
        ]
        
        successful, failed = sensor_data_access.store_batch_sensor_data(sensor_data_list)
        
        assert successful == 2
        assert failed == 0
        assert mock_batch_writer.put_item.call_count == 2
    
    def test_get_current_data_success(self, sensor_data_access, mock_dynamodb_table, sample_sensor_data):
        """Test getting current data successfully."""
        mock_dynamodb_table.query.return_value = {
            'Items': [
                {
                    'device_id': sample_sensor_data['device_id'],
                    'gateway_id': sample_sensor_data['gateway_id'],
                    'timestamp': sample_sensor_data['timestamp'],
                    'server_timestamp': sample_sensor_data['timestamp'],
                    'measurements': sample_sensor_data['measurements']
                }
            ]
        }
        
        result = sensor_data_access.get_current_data(sample_sensor_data['device_id'])
        
        assert result is not None
        assert result['device_id'] == sample_sensor_data['device_id']
        assert result['measurements'] == sample_sensor_data['measurements']
        
        # Check query parameters
        mock_dynamodb_table.query.assert_called_once()
        call_kwargs = mock_dynamodb_table.query.call_args[1]
        assert call_kwargs['ScanIndexForward'] is False  # Descending order
        assert call_kwargs['Limit'] == 1
    
    def test_get_current_data_not_found(self, sensor_data_access, mock_dynamodb_table):
        """Test getting current data when device not found."""
        mock_dynamodb_table.query.return_value = {'Items': []}
        
        result = sensor_data_access.get_current_data('nonexistent_device')
        
        assert result is None
    
    def test_get_current_data_error(self, sensor_data_access, mock_dynamodb_table):
        """Test handling DynamoDB errors during get current data."""
        mock_dynamodb_table.query.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}}, 'Query'
        )
        
        result = sensor_data_access.get_current_data('device_id')
        
        assert result is None
    
    def test_get_historical_data_success(self, sensor_data_access, mock_dynamodb_table, sample_sensor_data):
        """Test getting historical data successfully."""
        mock_items = [
            {
                'device_id': sample_sensor_data['device_id'],
                'gateway_id': sample_sensor_data['gateway_id'],
                'timestamp': sample_sensor_data['timestamp'],
                'server_timestamp': sample_sensor_data['timestamp'],
                'measurements': sample_sensor_data['measurements']
            },
            {
                'device_id': sample_sensor_data['device_id'],
                'gateway_id': sample_sensor_data['gateway_id'],
                'timestamp': sample_sensor_data['timestamp'] + 60,
                'server_timestamp': sample_sensor_data['timestamp'] + 60,
                'measurements': sample_sensor_data['measurements']
            }
        ]
        
        mock_dynamodb_table.query.return_value = {
            'Items': mock_items,
            'LastEvaluatedKey': {'device_id': 'test', 'timestamp': 123}
        }
        
        result = sensor_data_access.get_historical_data(
            device_id=sample_sensor_data['device_id'],
            start_time=1234567800,
            end_time=1234567900,
            limit=50
        )
        
        assert result['count'] == 2
        assert len(result['items']) == 2
        assert 'last_evaluated_key' in result
        
        # Check query parameters
        call_kwargs = mock_dynamodb_table.query.call_args[1]
        assert call_kwargs['ScanIndexForward'] is True  # Ascending order
        assert call_kwargs['Limit'] == 50
    
    def test_get_historical_data_with_pagination(self, sensor_data_access, mock_dynamodb_table):
        """Test getting historical data with pagination."""
        mock_dynamodb_table.query.return_value = {'Items': []}
        last_key = {'device_id': 'test', 'timestamp': 123}
        
        sensor_data_access.get_historical_data(
            device_id='test_device',
            last_evaluated_key=last_key
        )
        
        call_kwargs = mock_dynamodb_table.query.call_args[1]
        assert call_kwargs['ExclusiveStartKey'] == last_key
    
    def test_get_multiple_devices_current_data(self, sensor_data_access, mock_dynamodb_table):
        """Test getting current data for multiple devices."""
        # Mock responses for different devices
        call_count = 0
        def mock_query(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call for device1
                return {
                    'Items': [{
                        'device_id': 'device1',
                        'gateway_id': 'gateway1',
                        'timestamp': 1234567890,
                        'server_timestamp': 1234567890,
                        'measurements': {'temp': 20.0}
                    }]
                }
            elif call_count == 2:  # Second call for device2
                return {
                    'Items': [{
                        'device_id': 'device2',
                        'gateway_id': 'gateway1',
                        'timestamp': 1234567891,
                        'server_timestamp': 1234567891,
                        'measurements': {'temp': 21.0}
                    }]
                }
            else:  # Third call for device3
                return {'Items': []}
        
        mock_dynamodb_table.query.side_effect = mock_query
        
        result = sensor_data_access.get_multiple_devices_current_data(['device1', 'device2', 'device3'])
        
        assert len(result) == 2
        assert 'device1' in result
        assert 'device2' in result
        assert 'device3' not in result
        assert result['device1']['measurements']['temp'] == 20.0
    
    def test_get_devices_by_gateway(self, sensor_data_access, mock_dynamodb_table):
        """Test getting devices by gateway."""
        mock_dynamodb_table.query.return_value = {
            'Items': [
                {
                    'device_id': 'device1',
                    'gateway_id': 'gateway1',
                    'timestamp': 1234567890,
                    'server_timestamp': 1234567890,
                    'measurements': {'temp': 20.0}
                }
            ]
        }
        
        result = sensor_data_access.get_devices_by_gateway('gateway1')
        
        assert result['count'] == 1
        assert len(result['items']) == 1
        
        # Check that GSI was used
        call_kwargs = mock_dynamodb_table.query.call_args[1]
        assert call_kwargs['IndexName'] == 'test-gsi'
    
    def test_get_all_devices(self, sensor_data_access, mock_dynamodb_table):
        """Test getting all devices."""
        mock_dynamodb_table.scan.return_value = {
            'Items': [
                {
                    'device_id': 'device1',
                    'gateway_id': 'gateway1',
                    'timestamp': 1234567890,
                    'server_timestamp': 1234567890
                },
                {
                    'device_id': 'device1',
                    'gateway_id': 'gateway1',
                    'timestamp': 1234567900,  # More recent
                    'server_timestamp': 1234567900
                },
                {
                    'device_id': 'device2',
                    'gateway_id': 'gateway1',
                    'timestamp': 1234567895,
                    'server_timestamp': 1234567895
                }
            ]
        }
        
        result = sensor_data_access.get_all_devices()
        
        assert len(result) == 2  # Two unique devices
        # Should be sorted by last_seen descending
        assert result[0]['device_id'] == 'device1'
        assert result[0]['last_seen'] == 1234567900  # Most recent timestamp
        assert result[1]['device_id'] == 'device2'
    
    def test_delete_old_data(self, sensor_data_access, mock_dynamodb_table):
        """Test deleting old data."""
        mock_dynamodb_table.query.return_value = {
            'Items': [
                {'device_id': 'device1', 'timestamp': 1234567800},
                {'device_id': 'device1', 'timestamp': 1234567850}
            ]
        }
        
        mock_batch_writer = MagicMock()
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_batch_writer
        mock_context_manager.__exit__.return_value = None
        mock_dynamodb_table.batch_writer.return_value = mock_context_manager
        
        result = sensor_data_access.delete_old_data('device1', 1234567900)
        
        assert result == 2
        assert mock_batch_writer.delete_item.call_count == 2
    
    def test_format_sensor_data(self, sensor_data_access):
        """Test formatting sensor data."""
        raw_item = {
            'device_id': 'device1',
            'gateway_id': 'gateway1',
            'timestamp': 1234567890,
            'server_timestamp': 1234567891,
            'measurements': {'temp': 20.0},
            'ruuvi_cloud_response': {'result': 'success'}
        }
        
        formatted = sensor_data_access._format_sensor_data(raw_item)
        
        assert formatted['device_id'] == 'device1'
        assert formatted['gateway_id'] == 'gateway1'
        assert formatted['timestamp'] == 1234567890
        assert formatted['server_timestamp'] == 1234567891
        assert formatted['measurements'] == {'temp': 20.0}
        assert formatted['ruuvi_cloud_response'] == {'result': 'success'}
    
    def test_format_sensor_data_without_ruuvi_response(self, sensor_data_access):
        """Test formatting sensor data without Ruuvi Cloud response."""
        raw_item = {
            'device_id': 'device1',
            'gateway_id': 'gateway1',
            'timestamp': 1234567890,
            'measurements': {'temp': 20.0}
        }
        
        formatted = sensor_data_access._format_sensor_data(raw_item)
        
        assert 'ruuvi_cloud_response' not in formatted
        assert formatted['server_timestamp'] == 1234567890  # Falls back to timestamp


class TestSingletonFunctions:
    """Test singleton sensor data access functions."""
    
    def teardown_method(self):
        """Reset singleton after each test."""
        reset_sensor_data_access()
    
    @patch('src.shared.data_access.SensorDataAccess')
    def test_get_sensor_data_access_first_call(self, mock_data_access_class):
        """Test first call to get_sensor_data_access."""
        mock_instance = Mock()
        mock_data_access_class.return_value = mock_instance
        
        result = get_sensor_data_access('test-table', 'test-gsi')
        
        assert result == mock_instance
        mock_data_access_class.assert_called_once_with('test-table', 'test-gsi')
    
    @patch('src.shared.data_access.SensorDataAccess')
    def test_get_sensor_data_access_subsequent_calls(self, mock_data_access_class):
        """Test subsequent calls to get_sensor_data_access."""
        mock_instance = Mock()
        mock_data_access_class.return_value = mock_instance
        
        # First call
        result1 = get_sensor_data_access('test-table')
        # Second call
        result2 = get_sensor_data_access()
        
        assert result1 == result2 == mock_instance
        # Should only be called once
        mock_data_access_class.assert_called_once()
    
    def test_get_sensor_data_access_no_table_name(self):
        """Test get_sensor_data_access without table name on first call."""
        with pytest.raises(ValueError, match="table_name is required"):
            get_sensor_data_access()
    
    @patch('src.shared.data_access.SensorDataAccess')
    def test_reset_sensor_data_access(self, mock_data_access_class):
        """Test resetting singleton."""
        mock_instance = Mock()
        mock_data_access_class.return_value = mock_instance
        
        # Create instance
        get_sensor_data_access('test-table')
        
        # Reset
        reset_sensor_data_access()
        
        # Should be able to create new instance
        get_sensor_data_access('new-table')
        
        # Should have been called twice
        assert mock_data_access_class.call_count == 2