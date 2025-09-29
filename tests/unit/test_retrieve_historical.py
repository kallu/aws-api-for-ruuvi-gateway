"""
Unit tests for historical data retrieval functionality in the retrieve Lambda function.
Tests historical data queries with pagination and multiple device support.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import base64

# Import the module under test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from retrieve.index import (
    lambda_handler,
    handle_historical_data_request,
    handle_multiple_devices_historical_data_request,
    format_historical_data_response,
    encode_next_token
)


class TestHistoricalDataRetrieval:
    """Test historical data retrieval functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.correlation_id = "test-correlation-id"
        self.device_id = "AABBCCDDEEFF"
        self.gateway_id = "AA:BB:CC:DD:EE:FF"
        
        # Sample sensor data
        self.sample_sensor_data = {
            'device_id': self.device_id,
            'gateway_id': self.gateway_id,
            'timestamp': 1574082635,
            'server_timestamp': 1574082640,
            'measurements': {
                'temperature': 23.5,
                'humidity': 45.2,
                'pressure': 1013.25
            }
        }
        
        # Sample historical data result
        self.sample_historical_result = {
            'items': [
                {
                    'device_id': self.device_id,
                    'gateway_id': self.gateway_id,
                    'timestamp': 1574082635,
                    'server_timestamp': 1574082640,
                    'measurements': {'temperature': 23.5, 'humidity': 45.2}
                },
                {
                    'device_id': self.device_id,
                    'gateway_id': self.gateway_id,
                    'timestamp': 1574082695,
                    'server_timestamp': 1574082700,
                    'measurements': {'temperature': 24.1, 'humidity': 44.8}
                }
            ],
            'count': 2
        }
        
        # Sample historical result with pagination
        self.sample_paginated_result = {
            'items': [self.sample_historical_result['items'][0]],
            'count': 1,
            'last_evaluated_key': {
                'device_id': self.device_id,
                'timestamp': 1574082635
            }
        }
    
    def test_format_historical_data_response(self):
        """Test formatting of historical sensor data for API response."""
        formatted = format_historical_data_response(self.sample_sensor_data)
        
        assert formatted['device_id'] == self.device_id
        assert formatted['gateway_id'] == self.gateway_id
        assert formatted['timestamp'] == 1574082635
        assert formatted['server_timestamp'] == 1574082640
        assert formatted['measurements'] == self.sample_sensor_data['measurements']
        assert 'recorded_at' in formatted
        assert formatted['recorded_at'].endswith('Z')
    
    def test_encode_next_token(self):
        """Test encoding of pagination token."""
        last_evaluated_key = {
            'device_id': self.device_id,
            'timestamp': 1574082635
        }
        
        token = encode_next_token(last_evaluated_key)
        
        # Verify token can be decoded back
        decoded = json.loads(base64.b64decode(token).decode('utf-8'))
        assert decoded == last_evaluated_key
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_handle_historical_data_request_success(self, mock_get_data_access):
        """Test successful historical data retrieval for single device."""
        # Setup mock
        mock_data_access = Mock()
        mock_data_access.get_historical_data.return_value = self.sample_historical_result
        mock_get_data_access.return_value = mock_data_access
        
        validated_params = {
            'start_time': 1574082600,
            'end_time': 1574082700,
            'limit': 100
        }
        
        # Execute
        result = handle_historical_data_request(
            self.device_id, 
            validated_params, 
            mock_data_access, 
            self.correlation_id
        )
        
        # Verify
        assert result['result'] == 'success'
        assert result['data']['device_id'] == self.device_id
        assert result['data']['count'] == 2
        assert len(result['data']['items']) == 2
        assert result['data']['has_more'] is False
        assert 'next_token' not in result['data']
        
        # Verify data access call
        mock_data_access.get_historical_data.assert_called_once_with(
            device_id=self.device_id,
            start_time=1574082600,
            end_time=1574082700,
            limit=100,
            last_evaluated_key=None
        )
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_handle_historical_data_request_with_pagination(self, mock_get_data_access):
        """Test historical data retrieval with pagination."""
        # Setup mock
        mock_data_access = Mock()
        mock_data_access.get_historical_data.return_value = self.sample_paginated_result
        mock_get_data_access.return_value = mock_data_access
        
        validated_params = {
            'start_time': 1574082600,
            'end_time': 1574082700,
            'limit': 1,
            'last_evaluated_key': {'device_id': self.device_id, 'timestamp': 1574082600}
        }
        
        # Execute
        result = handle_historical_data_request(
            self.device_id, 
            validated_params, 
            mock_data_access, 
            self.correlation_id
        )
        
        # Verify
        assert result['result'] == 'success'
        assert result['data']['count'] == 1
        assert result['data']['has_more'] is True
        assert 'next_token' in result['data']
        
        # Verify pagination token
        token = result['data']['next_token']
        decoded = json.loads(base64.b64decode(token).decode('utf-8'))
        assert decoded == self.sample_paginated_result['last_evaluated_key']
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_handle_historical_data_request_no_data(self, mock_get_data_access):
        """Test historical data retrieval when no data exists."""
        # Setup mock
        mock_data_access = Mock()
        mock_data_access.get_historical_data.return_value = {'items': [], 'count': 0}
        mock_get_data_access.return_value = mock_data_access
        
        validated_params = {
            'start_time': 1574082600,
            'end_time': 1574082700,
            'limit': 100
        }
        
        # Execute
        result = handle_historical_data_request(
            self.device_id, 
            validated_params, 
            mock_data_access, 
            self.correlation_id
        )
        
        # Verify
        assert result['result'] == 'success'
        assert result['data']['count'] == 0
        assert len(result['data']['items']) == 0
        assert result['data']['has_more'] is False
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_handle_multiple_devices_historical_data_request(self, mock_get_data_access):
        """Test historical data retrieval for multiple devices."""
        # Setup mock
        mock_data_access = Mock()
        device_ids = [self.device_id, "FFEEDDCCBBAA"]
        
        # Mock returns data for first device, no data for second
        def mock_get_historical_data(device_id, **kwargs):
            if device_id == self.device_id:
                return self.sample_historical_result
            else:
                return {'items': [], 'count': 0}
        
        mock_data_access.get_historical_data.side_effect = mock_get_historical_data
        mock_get_data_access.return_value = mock_data_access
        
        validated_params = {
            'start_time': 1574082600,
            'end_time': 1574082700,
            'limit': 100,
            'device_ids': device_ids
        }
        
        # Execute
        result = handle_multiple_devices_historical_data_request(
            device_ids, 
            validated_params, 
            mock_data_access, 
            self.correlation_id
        )
        
        # Verify
        assert result['result'] == 'success'
        assert len(result['data']['devices']) == 2
        assert result['data']['devices'][self.device_id]['count'] == 2
        assert result['data']['devices']["FFEEDDCCBBAA"]['count'] == 0
        assert result['data']['summary']['requested_devices'] == 2
        assert result['data']['summary']['devices_with_data'] == 1
        assert result['data']['summary']['total_records'] == 2
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-table'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_historical_data_single_device(self, mock_get_data_access):
        """Test Lambda handler for historical data retrieval - single device."""
        # Setup mock
        mock_data_access = Mock()
        mock_data_access.get_historical_data.return_value = self.sample_historical_result
        mock_get_data_access.return_value = mock_data_access
        
        # Create API Gateway event
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/history/AABBCCDDEEFF',
            'pathParameters': {'device_id': 'AABBCCDDEEFF'},
            'queryStringParameters': {
                'start_time': '1574082600',
                'end_time': '1574082700',
                'limit': '50'
            },
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-id'}
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert body['data']['device_id'] == 'AABBCCDDEEFF'
        assert body['data']['count'] == 2
        assert len(body['data']['items']) == 2
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-table'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_historical_data_multiple_devices(self, mock_get_data_access):
        """Test Lambda handler for historical data retrieval - multiple devices."""
        # Setup mock
        mock_data_access = Mock()
        mock_data_access.get_historical_data.return_value = self.sample_historical_result
        mock_get_data_access.return_value = mock_data_access
        
        # Create API Gateway event
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/history',
            'pathParameters': {},
            'queryStringParameters': {
                'device_ids': 'AABBCCDDEEFF,FFEEDDCCBBAA',
                'start_time': '1574082600',
                'end_time': '1574082700'
            },
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-id'}
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert 'devices' in body['data']
        assert len(body['data']['devices']) == 2
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-table'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_historical_data_with_pagination(self, mock_get_data_access):
        """Test Lambda handler for historical data with pagination token."""
        # Setup mock
        mock_data_access = Mock()
        mock_data_access.get_historical_data.return_value = self.sample_paginated_result
        mock_get_data_access.return_value = mock_data_access
        
        # Create pagination token
        last_evaluated_key = {'device_id': 'AABBCCDDEEFF', 'timestamp': 1574082600}
        next_token = base64.b64encode(json.dumps(last_evaluated_key).encode('utf-8')).decode('utf-8')
        
        # Create API Gateway event
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/history/AABBCCDDEEFF',
            'pathParameters': {'device_id': 'AABBCCDDEEFF'},
            'queryStringParameters': {
                'start_time': '1574082600',
                'limit': '1',
                'next_token': next_token
            },
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-id'}
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Verify
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert body['data']['has_more'] is True
        assert 'next_token' in body['data']
        
        # Verify data access was called with pagination
        mock_data_access.get_historical_data.assert_called_once()
        call_args = mock_data_access.get_historical_data.call_args
        assert call_args[1]['last_evaluated_key'] == last_evaluated_key
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-table'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_invalid_pagination_token(self, mock_get_data_access):
        """Test Lambda handler with invalid pagination token."""
        # Setup mock
        mock_data_access = Mock()
        mock_get_data_access.return_value = mock_data_access
        
        # Create API Gateway event with invalid token
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/history/AABBCCDDEEFF',
            'pathParameters': {'device_id': 'AABBCCDDEEFF'},
            'queryStringParameters': {
                'next_token': 'invalid-token'
            },
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-id'}
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Verify
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
        assert 'Invalid next_token parameter' in body['error']['message']
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-table'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_invalid_time_range(self, mock_get_data_access):
        """Test Lambda handler with invalid time range."""
        # Setup mock
        mock_data_access = Mock()
        mock_get_data_access.return_value = mock_data_access
        
        # Create API Gateway event with invalid time range
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/history/AABBCCDDEEFF',
            'pathParameters': {'device_id': 'AABBCCDDEEFF'},
            'queryStringParameters': {
                'start_time': '1574082700',
                'end_time': '1574082600'  # end_time before start_time
            },
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-id'}
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Verify
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
        assert 'start_time must be less than end_time' in body['error']['message']


if __name__ == '__main__':
    pytest.main([__file__])