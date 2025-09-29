"""
Unit tests for device listing functionality in the retrieve Lambda function.
Tests device listing endpoint with gateway grouping and summary information.
"""

import json
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

# Import the module under test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from retrieve.index import (
    lambda_handler,
    handle_device_listing_request,
    format_device_info_response
)


class TestDeviceListingFunctionality:
    """Test device listing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.correlation_id = "test-correlation-id"
        
        # Sample device information
        self.sample_devices_info = [
            {
                'device_id': 'AABBCCDDEEFF',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'last_seen': 1574082635,
                'last_seen_server': 1574082640
            },
            {
                'device_id': 'FFEEDDCCBBAA',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'last_seen': 1574082695,
                'last_seen_server': 1574082700
            },
            {
                'device_id': '112233445566',
                'gateway_id': 'FF:EE:DD:CC:BB:AA',
                'last_seen': 1574082555,
                'last_seen_server': 1574082560
            }
        ]
    
    def test_format_device_info_response(self):
        """Test formatting of device information for API response."""
        device_info = self.sample_devices_info[0]
        formatted = format_device_info_response(device_info)
        
        assert formatted['device_id'] == 'AABBCCDDEEFF'
        assert formatted['gateway_id'] == 'AA:BB:CC:DD:EE:FF'
        assert formatted['last_seen'] == 1574082635
        assert formatted['last_seen_server'] == 1574082640
        assert 'last_seen_at' in formatted
        assert 'last_seen_server_at' in formatted
        assert formatted['last_seen_at'].endswith('Z')
        assert formatted['last_seen_server_at'].endswith('Z')
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_handle_device_listing_request_success(self, mock_get_data_access):
        """Test successful device listing request."""
        # Setup mock
        mock_data_access = Mock()
        mock_data_access.get_all_devices.return_value = self.sample_devices_info
        mock_get_data_access.return_value = mock_data_access
        
        # Execute
        result = handle_device_listing_request(mock_data_access, self.correlation_id)
        
        # Verify
        assert result['result'] == 'success'
        assert len(result['data']['devices']) == 3
        assert len(result['data']['gateways']) == 2
        assert result['data']['summary']['total_devices'] == 3
        assert result['data']['summary']['total_gateways'] == 2
        assert result['data']['summary']['most_recent_activity'] == 1574082695  # Most recent timestamp
        assert 'most_recent_activity_at' in result['data']['summary']
        
        # Verify gateway grouping
        gateways = {gw['gateway_id']: gw for gw in result['data']['gateways']}
        assert 'AA:BB:CC:DD:EE:FF' in gateways
        assert 'FF:EE:DD:CC:BB:AA' in gateways
        assert gateways['AA:BB:CC:DD:EE:FF']['device_count'] == 2
        assert gateways['FF:EE:DD:CC:BB:AA']['device_count'] == 1
        
        # Verify gateways are sorted by last activity (most recent first)
        assert result['data']['gateways'][0]['last_activity'] >= result['data']['gateways'][1]['last_activity']
        
        # Verify data access call
        mock_data_access.get_all_devices.assert_called_once()
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_handle_device_listing_request_no_devices(self, mock_get_data_access):
        """Test device listing request when no devices exist."""
        # Setup mock
        mock_data_access = Mock()
        mock_data_access.get_all_devices.return_value = []
        mock_get_data_access.return_value = mock_data_access
        
        # Execute
        result = handle_device_listing_request(mock_data_access, self.correlation_id)
        
        # Verify
        assert result['result'] == 'success'
        assert len(result['data']['devices']) == 0
        assert len(result['data']['gateways']) == 0
        assert result['data']['summary']['total_devices'] == 0
        assert result['data']['summary']['total_gateways'] == 0
        assert result['data']['summary']['most_recent_activity'] is None
        assert 'most_recent_activity_at' not in result['data']['summary']
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_handle_device_listing_request_single_gateway(self, mock_get_data_access):
        """Test device listing with devices from single gateway."""
        # Setup mock with devices from single gateway
        single_gateway_devices = [
            {
                'device_id': 'AABBCCDDEEFF',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'last_seen': 1574082635,
                'last_seen_server': 1574082640
            },
            {
                'device_id': 'FFEEDDCCBBAA',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'last_seen': 1574082695,
                'last_seen_server': 1574082700
            }
        ]
        
        mock_data_access = Mock()
        mock_data_access.get_all_devices.return_value = single_gateway_devices
        mock_get_data_access.return_value = mock_data_access
        
        # Execute
        result = handle_device_listing_request(mock_data_access, self.correlation_id)
        
        # Verify
        assert result['result'] == 'success'
        assert len(result['data']['devices']) == 2
        assert len(result['data']['gateways']) == 1
        assert result['data']['gateways'][0]['gateway_id'] == 'AA:BB:CC:DD:EE:FF'
        assert result['data']['gateways'][0]['device_count'] == 2
        assert result['data']['gateways'][0]['last_activity'] == 1574082695  # Most recent from this gateway
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_handle_device_listing_request_error(self, mock_get_data_access):
        """Test device listing request when data access fails."""
        # Setup mock to raise exception
        mock_data_access = Mock()
        mock_data_access.get_all_devices.side_effect = Exception("Database error")
        mock_get_data_access.return_value = mock_data_access
        
        # Execute and verify exception is raised
        with pytest.raises(Exception) as exc_info:
            handle_device_listing_request(mock_data_access, self.correlation_id)
        
        assert "Database error" in str(exc_info.value)
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-table'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_device_listing(self, mock_get_data_access):
        """Test Lambda handler for device listing endpoint."""
        # Setup mock
        mock_data_access = Mock()
        mock_data_access.get_all_devices.return_value = self.sample_devices_info
        mock_get_data_access.return_value = mock_data_access
        
        # Create API Gateway event
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/devices',
            'pathParameters': {},
            'queryStringParameters': {},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-id'}
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert len(body['data']['devices']) == 3
        assert len(body['data']['gateways']) == 2
        assert body['data']['summary']['total_devices'] == 3
        assert body['data']['summary']['total_gateways'] == 2
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-table'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_device_listing_no_auth(self, mock_get_data_access):
        """Test Lambda handler for device listing without authentication."""
        # Setup mock
        mock_data_access = Mock()
        mock_get_data_access.return_value = mock_data_access
        
        # Create API Gateway event without authentication
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/devices',
            'pathParameters': {},
            'queryStringParameters': {},
            'headers': {},
            'requestContext': {'requestId': 'test-request-id'}
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Verify
        assert response['statusCode'] == 401
        body = json.loads(response['body'])
        assert body['error']['code'] == 'AUTHENTICATION_REQUIRED'
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-table'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_device_listing_data_access_error(self, mock_get_data_access):
        """Test Lambda handler when device listing fails."""
        # Setup mock to raise exception
        mock_data_access = Mock()
        mock_data_access.get_all_devices.side_effect = Exception("Database connection failed")
        mock_get_data_access.return_value = mock_data_access
        
        # Create API Gateway event
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/devices',
            'pathParameters': {},
            'queryStringParameters': {},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-id'}
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Verify
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INTERNAL_ERROR'
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-table'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_unrecognized_endpoint(self, mock_get_data_access):
        """Test Lambda handler with unrecognized endpoint."""
        # Setup mock
        mock_data_access = Mock()
        mock_get_data_access.return_value = mock_data_access
        
        # Create API Gateway event with unrecognized path
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/unknown',
            'pathParameters': {},
            'queryStringParameters': {},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-id'}
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Verify
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
        assert 'Unrecognized endpoint' in body['error']['message']


if __name__ == '__main__':
    pytest.main([__file__])