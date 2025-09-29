"""
Unit tests for Ruuvi API local data retrieval Lambda function - current data functionality.
Tests the current data retrieval endpoints for single and multiple devices.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from retrieve.index import (
    lambda_handler,
    handle_current_data_request,
    handle_multiple_current_data_request,
    format_current_data_response
)


class TestCurrentDataFormatting:
    """Test current data response formatting."""
    
    def test_format_current_data_response(self):
        """Test formatting sensor data for current data response."""
        sensor_data = {
            'device_id': 'AABBCCDDEEFF',
            'gateway_id': 'AA:BB:CC:DD:EE:FF',
            'timestamp': 1640995200,  # 2022-01-01 00:00:00 UTC
            'server_timestamp': 1640995205,
            'measurements': {
                'temperature': 23.5,
                'humidity': 45.2,
                'pressure': 1013.25,
                'battery': 3.2
            }
        }
        
        result = format_current_data_response(sensor_data)
        
        assert result['device_id'] == 'AABBCCDDEEFF'
        assert result['gateway_id'] == 'AA:BB:CC:DD:EE:FF'
        assert result['timestamp'] == 1640995200
        assert result['server_timestamp'] == 1640995205
        assert result['measurements'] == sensor_data['measurements']
        assert result['last_updated'] == '2022-01-01T00:00:00Z'
    
    def test_format_current_data_response_with_different_timestamp(self):
        """Test formatting with different timestamp."""
        sensor_data = {
            'device_id': '112233445566',
            'gateway_id': 'FF:EE:DD:CC:BB:AA',
            'timestamp': 1641081600,  # 2022-01-02 00:00:00 UTC
            'server_timestamp': 1641081610,
            'measurements': {
                'temperature': 20.1,
                'humidity': 55.8
            }
        }
        
        result = format_current_data_response(sensor_data)
        
        assert result['device_id'] == '112233445566'
        assert result['last_updated'] == '2022-01-02T00:00:00Z'


class TestSingleDeviceCurrentData:
    """Test current data retrieval for single device."""
    
    def test_handle_current_data_request_success(self):
        """Test successful current data retrieval for single device."""
        # Mock data access
        mock_data_access = Mock()
        mock_sensor_data = {
            'device_id': 'AABBCCDDEEFF',
            'gateway_id': 'AA:BB:CC:DD:EE:FF',
            'timestamp': 1640995200,
            'server_timestamp': 1640995205,
            'measurements': {
                'temperature': 23.5,
                'humidity': 45.2,
                'pressure': 1013.25
            }
        }
        mock_data_access.get_current_data.return_value = mock_sensor_data
        
        result = handle_current_data_request('AABBCCDDEEFF', mock_data_access, 'test-correlation-id')
        
        # Verify data access was called correctly
        mock_data_access.get_current_data.assert_called_once_with('AABBCCDDEEFF')
        
        # Verify response format
        assert result['result'] == 'success'
        assert result['data']['device_id'] == 'AABBCCDDEEFF'
        assert result['data']['gateway_id'] == 'AA:BB:CC:DD:EE:FF'
        assert result['data']['timestamp'] == 1640995200
        assert result['data']['measurements'] == mock_sensor_data['measurements']
        assert result['data']['last_updated'] == '2022-01-01T00:00:00Z'
    
    def test_handle_current_data_request_device_not_found(self):
        """Test current data retrieval when device is not found."""
        # Mock data access to return None (device not found)
        mock_data_access = Mock()
        mock_data_access.get_current_data.return_value = None
        
        with pytest.raises(ValueError, match="Device AABBCCDDEEFF"):
            handle_current_data_request('AABBCCDDEEFF', mock_data_access, 'test-correlation-id')
        
        # Verify data access was called correctly
        mock_data_access.get_current_data.assert_called_once_with('AABBCCDDEEFF')
    
    def test_handle_current_data_request_data_access_error(self):
        """Test current data retrieval when data access raises exception."""
        # Mock data access to raise exception
        mock_data_access = Mock()
        mock_data_access.get_current_data.side_effect = Exception('DynamoDB connection failed')
        
        with pytest.raises(Exception, match='DynamoDB connection failed'):
            handle_current_data_request('AABBCCDDEEFF', mock_data_access, 'test-correlation-id')
        
        # Verify data access was called correctly
        mock_data_access.get_current_data.assert_called_once_with('AABBCCDDEEFF')


class TestMultipleDevicesCurrentData:
    """Test current data retrieval for multiple devices."""
    
    def test_handle_multiple_current_data_request_success(self):
        """Test successful current data retrieval for multiple devices."""
        # Mock data access
        mock_data_access = Mock()
        mock_devices_data = {
            'AABBCCDDEEFF': {
                'device_id': 'AABBCCDDEEFF',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'timestamp': 1640995200,
                'server_timestamp': 1640995205,
                'measurements': {'temperature': 23.5, 'humidity': 45.2}
            },
            '112233445566': {
                'device_id': '112233445566',
                'gateway_id': 'FF:EE:DD:CC:BB:AA',
                'timestamp': 1641081600,
                'server_timestamp': 1641081610,
                'measurements': {'temperature': 20.1, 'humidity': 55.8}
            }
        }
        mock_data_access.get_multiple_devices_current_data.return_value = mock_devices_data
        
        device_ids = ['AABBCCDDEEFF', '112233445566', 'FFEEDDCCBBAA']
        result = handle_multiple_current_data_request(device_ids, mock_data_access, 'test-correlation-id')
        
        # Verify data access was called correctly
        mock_data_access.get_multiple_devices_current_data.assert_called_once_with(device_ids)
        
        # Verify response format
        assert result['result'] == 'success'
        assert len(result['data']) == 3  # All requested devices
        
        # Verify devices with data
        assert result['data']['AABBCCDDEEFF']['device_id'] == 'AABBCCDDEEFF'
        assert result['data']['AABBCCDDEEFF']['last_updated'] == '2022-01-01T00:00:00Z'
        assert result['data']['112233445566']['device_id'] == '112233445566'
        assert result['data']['112233445566']['last_updated'] == '2022-01-02T00:00:00Z'
        
        # Verify device without data
        assert result['data']['FFEEDDCCBBAA'] is None
        
        # Verify summary
        assert result['summary']['requested_devices'] == 3
        assert result['summary']['devices_with_data'] == 2
        assert result['summary']['devices_without_data'] == 1
    
    def test_handle_multiple_current_data_request_no_devices_found(self):
        """Test multiple devices current data when no devices are found."""
        # Mock data access to return empty dict
        mock_data_access = Mock()
        mock_data_access.get_multiple_devices_current_data.return_value = {}
        
        device_ids = ['AABBCCDDEEFF', '112233445566']
        result = handle_multiple_current_data_request(device_ids, mock_data_access, 'test-correlation-id')
        
        # Verify response format
        assert result['result'] == 'success'
        assert len(result['data']) == 2
        assert result['data']['AABBCCDDEEFF'] is None
        assert result['data']['112233445566'] is None
        
        # Verify summary
        assert result['summary']['requested_devices'] == 2
        assert result['summary']['devices_with_data'] == 0
        assert result['summary']['devices_without_data'] == 2
    
    def test_handle_multiple_current_data_request_data_access_error(self):
        """Test multiple devices current data when data access raises exception."""
        # Mock data access to raise exception
        mock_data_access = Mock()
        mock_data_access.get_multiple_devices_current_data.side_effect = Exception('DynamoDB throttling')
        
        device_ids = ['AABBCCDDEEFF', '112233445566']
        
        with pytest.raises(Exception, match='DynamoDB throttling'):
            handle_multiple_current_data_request(device_ids, mock_data_access, 'test-correlation-id')


class TestLambdaHandlerCurrentData:
    """Test Lambda handler with current data endpoints."""
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_single_device_current_success(self, mock_get_data_access):
        """Test Lambda handler for single device current data - success case."""
        # Mock data access
        mock_data_access = Mock()
        mock_sensor_data = {
            'device_id': 'AABBCCDDEEFF',
            'gateway_id': 'AA:BB:CC:DD:EE:FF',
            'timestamp': 1640995200,
            'server_timestamp': 1640995205,
            'measurements': {'temperature': 23.5, 'humidity': 45.2}
        }
        mock_data_access.get_current_data.return_value = mock_sensor_data
        mock_get_data_access.return_value = mock_data_access
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/current/AABBCCDDEEFF',
            'pathParameters': {'device_id': 'AABBCCDDEEFF'},
            'queryStringParameters': {},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-123'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 200
        assert 'X-Correlation-ID' in response['headers']
        
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert body['data']['device_id'] == 'AABBCCDDEEFF'
        assert body['data']['timestamp'] == 1640995200
        assert body['data']['measurements'] == mock_sensor_data['measurements']
        
        # Verify data access was called
        mock_data_access.get_current_data.assert_called_once_with('AABBCCDDEEFF')
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_single_device_current_not_found(self, mock_get_data_access):
        """Test Lambda handler for single device current data - device not found."""
        # Mock data access to return None
        mock_data_access = Mock()
        mock_data_access.get_current_data.return_value = None
        mock_get_data_access.return_value = mock_data_access
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/current/AABBCCDDEEFF',
            'pathParameters': {'device_id': 'AABBCCDDEEFF'},
            'queryStringParameters': {},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-456'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 404
        assert 'X-Correlation-ID' in response['headers']
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'NOT_FOUND'
        assert 'Device AABBCCDDEEFF' in body['error']['message']
        
        # Verify data access was called
        mock_data_access.get_current_data.assert_called_once_with('AABBCCDDEEFF')
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_multiple_devices_current_success(self, mock_get_data_access):
        """Test Lambda handler for multiple devices current data - success case."""
        # Mock data access
        mock_data_access = Mock()
        mock_devices_data = {
            'AABBCCDDEEFF': {
                'device_id': 'AABBCCDDEEFF',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'timestamp': 1640995200,
                'server_timestamp': 1640995205,
                'measurements': {'temperature': 23.5}
            }
        }
        mock_data_access.get_multiple_devices_current_data.return_value = mock_devices_data
        mock_get_data_access.return_value = mock_data_access
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/current',
            'pathParameters': {},
            'queryStringParameters': {'device_ids': 'AABBCCDDEEFF,112233445566'},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-789'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 200
        assert 'X-Correlation-ID' in response['headers']
        
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert len(body['data']) == 2
        assert body['data']['AABBCCDDEEFF']['device_id'] == 'AABBCCDDEEFF'
        assert body['data']['112233445566'] is None  # No data for this device
        assert body['summary']['requested_devices'] == 2
        assert body['summary']['devices_with_data'] == 1
        
        # Verify data access was called
        mock_data_access.get_multiple_devices_current_data.assert_called_once_with(['AABBCCDDEEFF', '112233445566'])
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_current_data_internal_error(self, mock_get_data_access):
        """Test Lambda handler for current data with internal error."""
        # Mock data access to raise exception
        mock_data_access = Mock()
        mock_data_access.get_current_data.side_effect = Exception('DynamoDB connection failed')
        mock_get_data_access.return_value = mock_data_access
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/current/AABBCCDDEEFF',
            'pathParameters': {'device_id': 'AABBCCDDEEFF'},
            'queryStringParameters': {},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-101'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 500
        assert 'X-Correlation-ID' in response['headers']
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INTERNAL_ERROR'
        assert body['error']['message'] == 'Internal server error'
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_current_data_with_invalid_device_ids(self, mock_get_data_access):
        """Test Lambda handler for multiple devices with invalid device ID format."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/current',
            'pathParameters': {},
            'queryStringParameters': {'device_ids': 'INVALID,AABBCCDDEEFF'},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-202'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 400
        assert 'X-Correlation-ID' in response['headers']
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
        assert 'Invalid device ID format: INVALID' in body['error']['message']
        
        # Verify data access was not called due to validation error
        mock_get_data_access.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__])