"""
Unit tests for configuration management Lambda function - basic functionality.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from config.index import ConfigurationHandler, lambda_handler


class TestConfigurationHandler:
    """Test configuration handler functionality."""
    
    @pytest.fixture
    def handler(self):
        """Create configuration handler for testing."""
        with patch.dict(os.environ, {
            'CONFIG_TABLE_NAME': 'test-config-table',
            'ADMIN_API_KEY': 'test-admin-key-123'
        }):
            with patch('config.index.get_config_manager') as mock_get_config:
                mock_config_manager = Mock()
                mock_get_config.return_value = mock_config_manager
                
                handler = ConfigurationHandler()
                handler.config_manager = mock_config_manager
                return handler
    
    @pytest.fixture
    def valid_auth_event(self):
        """Create event with valid admin authentication."""
        return {
            'httpMethod': 'PUT',
            'headers': {
                'x-api-key': 'test-admin-key-123'
            },
            'body': json.dumps({
                'forwarding_enabled': False
            }),
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            }
        }
    
    @pytest.fixture
    def invalid_auth_event(self):
        """Create event with invalid authentication."""
        return {
            'httpMethod': 'PUT',
            'headers': {
                'x-api-key': 'invalid-key'
            },
            'body': json.dumps({
                'forwarding_enabled': False
            }),
            'requestContext': {
                'requestId': 'test-request-123'
            }
        }
    
    def test_init_configuration_handler(self, handler):
        """Test configuration handler initialization."""
        assert handler.config_table == 'test-config-table'
        assert handler.admin_api_key == 'test-admin-key-123'
        assert 'forwarding_enabled' in handler.updatable_keys
        assert 'data_retention_days' in handler.updatable_keys
    
    def test_validate_admin_auth_valid_key(self, handler, valid_auth_event):
        """Test admin authentication with valid API key."""
        result = handler._validate_admin_auth(valid_auth_event)
        assert result is True
    
    def test_validate_admin_auth_invalid_key(self, handler, invalid_auth_event):
        """Test admin authentication with invalid API key."""
        result = handler._validate_admin_auth(invalid_auth_event)
        assert result is False
    
    def test_validate_admin_auth_missing_key(self, handler):
        """Test admin authentication with missing API key."""
        event = {
            'headers': {}
        }
        result = handler._validate_admin_auth(event)
        assert result is False
    
    def test_validate_admin_auth_case_insensitive_header(self, handler):
        """Test admin authentication with case-insensitive header."""
        event = {
            'headers': {
                'X-API-Key': 'test-admin-key-123'  # Different case
            }
        }
        result = handler._validate_admin_auth(event)
        assert result is True
    
    @patch.dict(os.environ, {'ADMIN_API_KEY': ''})
    def test_validate_admin_auth_no_env_key(self, handler):
        """Test admin authentication when admin key not configured."""
        handler.admin_api_key = None
        event = {
            'headers': {
                'x-api-key': 'any-key'
            }
        }
        result = handler._validate_admin_auth(event)
        assert result is False
    
    def test_get_user_identifier_with_cognito(self, handler):
        """Test user identifier extraction with Cognito claims."""
        event = {
            'requestContext': {
                'authorizer': {
                    'claims': {
                        'sub': 'user-123',
                        'username': 'testuser'
                    }
                }
            }
        }
        result = handler._get_user_identifier(event)
        assert result == 'user-123'
    
    def test_get_user_identifier_with_api_key(self, handler):
        """Test user identifier extraction with API key fallback."""
        event = {
            'headers': {
                'x-api-key': 'test-api-key-12345678'
            },
            'requestContext': {
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            }
        }
        result = handler._get_user_identifier(event)
        assert result == 'api-key:12345678@192.168.1.1'
    
    def test_get_user_identifier_fallback(self, handler):
        """Test user identifier extraction with minimal info."""
        event = {
            'headers': {},
            'requestContext': {}
        }
        result = handler._get_user_identifier(event)
        assert result == 'api-key:unknown@unknown'
    
    def test_handle_request_unauthorized(self, handler, invalid_auth_event):
        """Test handling unauthorized request."""
        context = Mock()
        
        response = handler.handle_request(invalid_auth_event, context)
        
        assert response['statusCode'] == 401
        body = json.loads(response['body'])
        assert body['error'] == 'Unauthorized access'
    
    def test_handle_request_unsupported_method(self, handler, valid_auth_event):
        """Test handling unsupported HTTP method."""
        valid_auth_event['httpMethod'] = 'DELETE'
        context = Mock()
        
        response = handler.handle_request(valid_auth_event, context)
        
        assert response['statusCode'] == 405
        body = json.loads(response['body'])
        assert 'Method DELETE not allowed' in body['error']
    
    @patch('config.index.logging.basicConfig')
    def test_lambda_handler_entry_point(self, mock_basic_config):
        """Test lambda handler entry point."""
        event = {'test': 'event'}
        context = Mock()
        
        with patch('config.index.config_handler') as mock_handler:
            mock_handler.handle_request.return_value = {'statusCode': 200}
            
            result = lambda_handler(event, context)
            
            mock_basic_config.assert_called_once()
            mock_handler.handle_request.assert_called_once_with(event, context)
            assert result == {'statusCode': 200}