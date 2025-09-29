"""
Unit tests for Ruuvi API local data retrieval Lambda function basic structure.
Tests the core function structure, authentication validation, and query parameter validation.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from retrieve.index import (
    lambda_handler,
    parse_api_gateway_event,
    validate_authentication,
    validate_query_parameters,
    create_api_gateway_response,
    handle_authentication_error,
    handle_validation_error,
    handle_not_found_error,
    handle_internal_error,
    encode_next_token
)


class TestAPIGatewayEventParsing:
    """Test API Gateway event parsing functionality."""
    
    def test_parse_valid_get_event(self):
        """Test parsing a valid GET request event."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/current/AABBCCDDEEFF',
            'pathParameters': {'device_id': 'AABBCCDDEEFF'},
            'queryStringParameters': {'limit': '50'},
            'requestContext': {'requestId': 'test-request-123'}
        }
        
        method, path_params, query_params, request_id, correlation_id = parse_api_gateway_event(event)
        
        assert method == 'GET'
        assert path_params == {'device_id': 'AABBCCDDEEFF'}
        assert query_params == {'limit': '50'}
        assert request_id == 'test-request-123'
        assert correlation_id is not None
        assert len(correlation_id) == 36  # UUID format
    
    def test_parse_event_with_no_query_params(self):
        """Test parsing event with no query parameters."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/devices',
            'pathParameters': None,
            'queryStringParameters': None,
            'requestContext': {'requestId': 'test-request-456'}
        }
        
        method, path_params, query_params, request_id, correlation_id = parse_api_gateway_event(event)
        
        assert method == 'GET'
        assert path_params == {}
        assert query_params == {}
        assert request_id == 'test-request-456'
    
    def test_parse_event_unsupported_method(self):
        """Test parsing event with unsupported HTTP method."""
        event = {
            'httpMethod': 'POST',
            'path': '/api/v1/local/data',
            'requestContext': {'requestId': 'test-request-789'}
        }
        
        with pytest.raises(ValueError, match="Unsupported HTTP method: POST"):
            parse_api_gateway_event(event)
    
    def test_parse_event_missing_request_context(self):
        """Test parsing event with missing request context."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/devices'
        }
        
        method, path_params, query_params, request_id, correlation_id = parse_api_gateway_event(event)
        
        assert method == 'GET'
        assert request_id == 'unknown'
        assert correlation_id is not None


class TestAuthentication:
    """Test authentication validation functionality."""
    
    def test_validate_api_key_authentication(self):
        """Test validation with API key authentication."""
        event = {
            'headers': {'x-api-key': 'test-api-key-123'},
            'requestContext': {}
        }
        
        result = validate_authentication(event, 'test-correlation-id')
        assert result is True
    
    def test_validate_api_key_authentication_case_insensitive(self):
        """Test validation with API key authentication (case insensitive header)."""
        event = {
            'headers': {'X-API-Key': 'test-api-key-456'},
            'requestContext': {}
        }
        
        result = validate_authentication(event, 'test-correlation-id')
        assert result is True
    
    def test_validate_cognito_authentication(self):
        """Test validation with Cognito token authentication."""
        event = {
            'headers': {},
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'user-123',
                        'email': 'test@example.com'
                    }
                }
            }
        }
        
        result = validate_authentication(event, 'test-correlation-id')
        assert result is True
    
    def test_validate_iam_authentication(self):
        """Test validation with IAM authentication."""
        event = {
            'headers': {},
            'requestContext': {
                'identity': {
                    'userArn': 'arn:aws:iam::123456789012:user/test-user'
                }
            }
        }
        
        result = validate_authentication(event, 'test-correlation-id')
        assert result is True
    
    def test_validate_no_authentication(self):
        """Test validation with no authentication."""
        event = {
            'headers': {},
            'requestContext': {}
        }
        
        result = validate_authentication(event, 'test-correlation-id')
        assert result is False
    
    def test_validate_authentication_exception(self):
        """Test authentication validation with exception."""
        # Malformed event that causes exception
        event = None
        
        result = validate_authentication(event, 'test-correlation-id')
        assert result is False


class TestQueryParameterValidation:
    """Test query parameter validation functionality."""
    
    def test_validate_empty_parameters(self):
        """Test validation with no query parameters."""
        result = validate_query_parameters({}, 'test-correlation-id')
        
        assert result == {'limit': 100}  # Default limit
    
    def test_validate_time_range_parameters(self):
        """Test validation with time range parameters."""
        query_params = {
            'start_time': '1640995200',  # 2022-01-01 00:00:00 UTC
            'end_time': '1641081600',    # 2022-01-02 00:00:00 UTC
            'limit': '50'
        }
        
        result = validate_query_parameters(query_params, 'test-correlation-id')
        
        assert result['start_time'] == 1640995200
        assert result['end_time'] == 1641081600
        assert result['limit'] == 50
    
    def test_validate_pagination_parameters(self):
        """Test validation with pagination parameters."""
        import base64
        last_key = {'device_id': 'AABBCCDDEEFF', 'timestamp': 1640995200}
        next_token = base64.b64encode(json.dumps(last_key).encode('utf-8')).decode('utf-8')
        
        query_params = {
            'limit': '25',
            'next_token': next_token
        }
        
        result = validate_query_parameters(query_params, 'test-correlation-id')
        
        assert result['limit'] == 25
        assert result['last_evaluated_key'] == last_key
    
    def test_validate_device_ids_parameter(self):
        """Test validation with device IDs parameter."""
        query_params = {
            'device_ids': 'AABBCCDDEEFF,112233445566,FFEEDDCCBBAA'
        }
        
        result = validate_query_parameters(query_params, 'test-correlation-id')
        
        assert result['device_ids'] == ['AABBCCDDEEFF', '112233445566', 'FFEEDDCCBBAA']
    
    def test_validate_invalid_start_time(self):
        """Test validation with invalid start_time."""
        query_params = {'start_time': 'invalid'}
        
        with pytest.raises(ValueError, match="Invalid start_time parameter"):
            validate_query_parameters(query_params, 'test-correlation-id')
    
    def test_validate_negative_start_time(self):
        """Test validation with negative start_time."""
        query_params = {'start_time': '-100'}
        
        with pytest.raises(ValueError, match="start_time must be a positive integer"):
            validate_query_parameters(query_params, 'test-correlation-id')
    
    def test_validate_invalid_end_time(self):
        """Test validation with invalid end_time."""
        query_params = {'end_time': 'not-a-number'}
        
        with pytest.raises(ValueError, match="Invalid end_time parameter"):
            validate_query_parameters(query_params, 'test-correlation-id')
    
    def test_validate_invalid_time_range(self):
        """Test validation with invalid time range (start >= end)."""
        query_params = {
            'start_time': '1641081600',
            'end_time': '1640995200'
        }
        
        with pytest.raises(ValueError, match="start_time must be less than end_time"):
            validate_query_parameters(query_params, 'test-correlation-id')
    
    def test_validate_invalid_limit_too_small(self):
        """Test validation with limit too small."""
        query_params = {'limit': '0'}
        
        with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
            validate_query_parameters(query_params, 'test-correlation-id')
    
    def test_validate_invalid_limit_too_large(self):
        """Test validation with limit too large."""
        query_params = {'limit': '1001'}
        
        with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
            validate_query_parameters(query_params, 'test-correlation-id')
    
    def test_validate_invalid_next_token(self):
        """Test validation with invalid next_token."""
        query_params = {'next_token': 'invalid-base64'}
        
        with pytest.raises(ValueError, match="Invalid next_token parameter"):
            validate_query_parameters(query_params, 'test-correlation-id')
    
    def test_validate_invalid_device_id_format(self):
        """Test validation with invalid device ID format."""
        query_params = {'device_ids': 'INVALID,AABBCCDDEEFF'}
        
        with pytest.raises(ValueError, match="Invalid device ID format: INVALID"):
            validate_query_parameters(query_params, 'test-correlation-id')


class TestResponseHelpers:
    """Test response helper functions."""
    
    def test_create_api_gateway_response(self):
        """Test creating API Gateway response."""
        body = {'message': 'success', 'data': []}
        correlation_id = 'test-correlation-123'
        
        response = create_api_gateway_response(200, body, correlation_id)
        
        assert response['statusCode'] == 200
        assert response['headers']['Content-Type'] == 'application/json'
        assert response['headers']['X-Correlation-ID'] == correlation_id
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
        assert json.loads(response['body']) == body
    
    def test_create_api_gateway_response_no_correlation_id(self):
        """Test creating API Gateway response without correlation ID."""
        body = {'error': 'test error'}
        
        response = create_api_gateway_response(400, body)
        
        assert response['statusCode'] == 400
        assert 'X-Correlation-ID' not in response['headers']
        assert json.loads(response['body']) == body
    
    def test_handle_authentication_error(self):
        """Test authentication error handler."""
        correlation_id = 'test-correlation-456'
        
        response = handle_authentication_error(correlation_id)
        
        assert response['statusCode'] == 401
        assert response['headers']['X-Correlation-ID'] == correlation_id
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'AUTHENTICATION_REQUIRED'
        assert 'authentication is required' in body['error']['message'].lower()
    
    def test_handle_validation_error(self):
        """Test validation error handler."""
        error_message = 'Invalid parameter value'
        correlation_id = 'test-correlation-789'
        
        response = handle_validation_error(error_message, correlation_id)
        
        assert response['statusCode'] == 400
        assert response['headers']['X-Correlation-ID'] == correlation_id
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
        assert body['error']['message'] == error_message
    
    def test_handle_not_found_error(self):
        """Test not found error handler."""
        resource = 'Device AABBCCDDEEFF'
        correlation_id = 'test-correlation-101'
        
        response = handle_not_found_error(resource, correlation_id)
        
        assert response['statusCode'] == 404
        assert response['headers']['X-Correlation-ID'] == correlation_id
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'NOT_FOUND'
        assert resource in body['error']['message']
    
    def test_handle_internal_error(self):
        """Test internal error handler."""
        error = Exception('Test internal error')
        correlation_id = 'test-correlation-202'
        
        response = handle_internal_error(error, correlation_id)
        
        assert response['statusCode'] == 500
        assert response['headers']['X-Correlation-ID'] == correlation_id
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INTERNAL_ERROR'
        assert body['error']['message'] == 'Internal server error'
    
    def test_encode_next_token(self):
        """Test next token encoding."""
        last_key = {'device_id': 'AABBCCDDEEFF', 'timestamp': 1640995200}
        
        token = encode_next_token(last_key)
        
        # Decode and verify
        import base64
        decoded = json.loads(base64.b64decode(token).decode('utf-8'))
        assert decoded == last_key


class TestLambdaHandler:
    """Test main Lambda handler functionality."""
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_basic_structure(self, mock_get_data_access):
        """Test Lambda handler basic structure with valid authentication."""
        # Mock data access
        mock_data_access = Mock()
        mock_data_access.get_all_devices.return_value = []  # Mock device listing
        mock_get_data_access.return_value = mock_data_access
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/devices',
            'pathParameters': {},
            'queryStringParameters': {'limit': '50'},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-123'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 200
        assert 'X-Correlation-ID' in response['headers']
        
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert 'devices' in body['data']
        assert 'gateways' in body['data']
        assert body['data']['summary']['total_devices'] == 0
    
    def test_lambda_handler_authentication_failure(self):
        """Test Lambda handler with authentication failure."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/devices',
            'pathParameters': {},
            'queryStringParameters': {},
            'headers': {},  # No authentication
            'requestContext': {'requestId': 'test-request-456'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 401
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'AUTHENTICATION_REQUIRED'
    
    def test_lambda_handler_validation_error(self):
        """Test Lambda handler with query parameter validation error."""
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/data/history/AABBCCDDEEFF',
            'pathParameters': {'device_id': 'AABBCCDDEEFF'},
            'queryStringParameters': {'limit': '2000'},  # Invalid limit
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-789'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 400
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
        assert 'limit must be between 1 and 1000' in body['error']['message']
    
    def test_lambda_handler_unsupported_method(self):
        """Test Lambda handler with unsupported HTTP method."""
        event = {
            'httpMethod': 'POST',
            'path': '/api/v1/local/devices',
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-101'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 400
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'VALIDATION_ERROR'
        assert 'Unsupported HTTP method: POST' in body['error']['message']
    
    @patch('retrieve.index.get_sensor_data_access')
    def test_lambda_handler_internal_error(self, mock_get_data_access):
        """Test Lambda handler with internal error."""
        # Mock data access to raise exception
        mock_get_data_access.side_effect = Exception('Database connection failed')
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/v1/local/devices',
            'pathParameters': {},
            'queryStringParameters': {},
            'headers': {'x-api-key': 'test-key'},
            'requestContext': {'requestId': 'test-request-202'}
        }
        
        context = Mock()
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 500
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INTERNAL_ERROR'
        assert body['error']['message'] == 'Internal server error'


if __name__ == '__main__':
    pytest.main([__file__])