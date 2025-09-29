"""
Unit tests for configuration management Lambda function - update functionality.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from config.index import ConfigurationHandler


class TestConfigurationUpdate:
    """Test configuration update functionality."""
    
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
    def valid_update_event(self):
        """Create valid configuration update event."""
        return {
            'httpMethod': 'PUT',
            'headers': {
                'x-api-key': 'test-admin-key-123'
            },
            'body': json.dumps({
                'forwarding_enabled': False,
                'data_retention_days': 30
            }),
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            }
        }
    
    def test_handle_update_config_success(self, handler, valid_update_event):
        """Test successful configuration update."""
        context = Mock()
        context.aws_request_id = 'test-request-123'
        
        # Mock successful config updates
        handler.config_manager.set_config.return_value = True
        
        response = handler.handle_request(valid_update_event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert body['updated']['forwarding_enabled'] is False
        assert body['updated']['data_retention_days'] == 30
        
        # Verify config manager calls
        assert handler.config_manager.set_config.call_count == 2
        handler.config_manager.clear_cache.assert_called_once()
    
    def test_handle_update_config_partial_success(self, handler, valid_update_event):
        """Test partial configuration update success."""
        context = Mock()
        
        # Mock partial success - first call succeeds, second fails
        handler.config_manager.set_config.side_effect = [True, False]
        
        response = handler.handle_request(valid_update_event, context)
        
        assert response['statusCode'] == 200  # Still 200 because some succeeded
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert 'forwarding_enabled' in body['updated']
        assert 'data_retention_days' in body['errors']
    
    def test_handle_update_config_all_failed(self, handler, valid_update_event):
        """Test configuration update with all failures."""
        context = Mock()
        
        # Mock all failures
        handler.config_manager.set_config.return_value = False
        
        response = handler.handle_request(valid_update_event, context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['result'] == 'error'
        assert len(body['errors']) == 2
    
    def test_handle_update_config_invalid_key(self, handler):
        """Test configuration update with invalid key."""
        event = {
            'httpMethod': 'PUT',
            'headers': {
                'x-api-key': 'test-admin-key-123'
            },
            'body': json.dumps({
                'invalid_key': 'some_value',
                'forwarding_enabled': True
            }),
            'requestContext': {
                'requestId': 'test-request-123'
            }
        }
        context = Mock()
        
        # Mock successful config update for valid key
        handler.config_manager.set_config.return_value = True
        
        response = handler.handle_request(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'forwarding_enabled' in body['updated']
        assert 'invalid_key' in body['errors']
        assert 'not updatable' in body['errors']['invalid_key']
    
    def test_handle_update_config_invalid_json(self, handler):
        """Test configuration update with invalid JSON."""
        event = {
            'httpMethod': 'PUT',
            'headers': {
                'x-api-key': 'test-admin-key-123'
            },
            'body': 'invalid json {',
            'requestContext': {
                'requestId': 'test-request-123'
            }
        }
        context = Mock()
        
        response = handler.handle_request(event, context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Invalid JSON' in body['error']
    
    def test_handle_update_config_non_dict_body(self, handler):
        """Test configuration update with non-dictionary body."""
        event = {
            'httpMethod': 'PUT',
            'headers': {
                'x-api-key': 'test-admin-key-123'
            },
            'body': json.dumps(['not', 'a', 'dict']),
            'requestContext': {
                'requestId': 'test-request-123'
            }
        }
        context = Mock()
        
        response = handler.handle_request(event, context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'must be a JSON object' in body['error']
    
    def test_handle_update_config_empty_body(self, handler):
        """Test configuration update with empty body."""
        event = {
            'httpMethod': 'PUT',
            'headers': {
                'x-api-key': 'test-admin-key-123'
            },
            'body': json.dumps({}),
            'requestContext': {
                'requestId': 'test-request-123'
            }
        }
        context = Mock()
        
        response = handler.handle_request(event, context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['result'] == 'error'
        assert body['updated'] == {}
    
    def test_handle_update_config_dict_body_object(self, handler):
        """Test configuration update with body already as dict object."""
        event = {
            'httpMethod': 'PUT',
            'headers': {
                'x-api-key': 'test-admin-key-123'
            },
            'body': {  # Already a dict, not JSON string
                'forwarding_enabled': True
            },
            'requestContext': {
                'requestId': 'test-request-123'
            }
        }
        context = Mock()
        
        # Mock successful config update
        handler.config_manager.set_config.return_value = True
        
        response = handler.handle_request(event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert body['updated']['forwarding_enabled'] is True
    
    def test_handle_update_config_exception_handling(self, handler, valid_update_event):
        """Test configuration update exception handling."""
        context = Mock()
        
        # Mock exception in config manager
        handler.config_manager.set_config.side_effect = Exception("Database error")
        
        response = handler.handle_request(valid_update_event, context)
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Failed to update configuration' in body['error']
    
    def test_updatable_keys_validation(self, handler):
        """Test that only specific keys are updatable."""
        expected_keys = {
            'forwarding_enabled',
            'data_retention_days', 
            'ruuvi_cloud_endpoint',
            'ruuvi_cloud_timeout',
            'max_batch_size',
            'cache_ttl_seconds'
        }
        
        assert handler.updatable_keys == expected_keys
    
    def test_audit_logging_user_identification(self, handler):
        """Test that user identification works for audit logging."""
        event = {
            'httpMethod': 'PUT',
            'headers': {
                'x-api-key': 'test-admin-key-123'
            },
            'body': json.dumps({
                'forwarding_enabled': False
            }),
            'requestContext': {
                'requestId': 'test-request-123',
                'authorizer': {
                    'claims': {
                        'sub': 'admin-user-123',
                        'username': 'admin'
                    }
                }
            }
        }
        context = Mock()
        
        # Mock successful config update
        handler.config_manager.set_config.return_value = True
        
        response = handler.handle_request(event, context)
        
        assert response['statusCode'] == 200
        
        # Verify the user ID was passed to set_config
        handler.config_manager.set_config.assert_called_with(
            'forwarding_enabled', False, updated_by='admin-user-123'
        )