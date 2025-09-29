"""
Unit tests for configuration management Lambda function - retrieval functionality.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from config.index import ConfigurationHandler


class TestConfigurationRetrieval:
    """Test configuration retrieval functionality."""
    
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
    def valid_get_event(self):
        """Create valid configuration retrieval event."""
        return {
            'httpMethod': 'GET',
            'headers': {
                'x-api-key': 'test-admin-key-123'
            },
            'requestContext': {
                'requestId': 'test-request-123',
                'identity': {
                    'sourceIp': '192.168.1.1'
                }
            }
        }
    
    def test_handle_get_config_success(self, handler, valid_get_event):
        """Test successful configuration retrieval."""
        context = Mock()
        
        # Mock configuration data
        mock_config_data = {
            'forwarding_enabled': {
                'value': True,
                'last_updated': 1640995200,
                'updated_by': 'admin-user'
            },
            'data_retention_days': {
                'value': 90,
                'last_updated': None,  # Default value
                'updated_by': 'default'
            },
            'ruuvi_cloud_endpoint': {
                'value': 'https://network.ruuvi.com/record',
                'last_updated': 1640995300,
                'updated_by': 'system'
            },
            'non_updatable_key': {  # This should be filtered out
                'value': 'some_value',
                'last_updated': 1640995400,
                'updated_by': 'system'
            }
        }
        
        handler.config_manager.get_all_config.return_value = mock_config_data
        
        response = handler.handle_request(valid_get_event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        
        # Check that only updatable keys are returned
        config = body['configuration']
        assert 'forwarding_enabled' in config
        assert 'data_retention_days' in config
        assert 'ruuvi_cloud_endpoint' in config
        assert 'non_updatable_key' not in config
        
        # Check configuration format
        forwarding_config = config['forwarding_enabled']
        assert forwarding_config['value'] is True
        assert forwarding_config['last_updated'] == 1640995200
        assert forwarding_config['updated_by'] == 'admin-user'
        assert forwarding_config['is_default'] is False
        
        # Check default value handling
        retention_config = config['data_retention_days']
        assert retention_config['value'] == 90
        assert retention_config['is_default'] is True
        
        # Check updatable keys list
        assert 'updatable_keys' in body
        assert isinstance(body['updatable_keys'], list)
        assert 'forwarding_enabled' in body['updatable_keys']
    
    def test_handle_get_config_empty_response(self, handler, valid_get_event):
        """Test configuration retrieval with empty response."""
        context = Mock()
        
        # Mock empty configuration data
        handler.config_manager.get_all_config.return_value = {}
        
        response = handler.handle_request(valid_get_event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['result'] == 'success'
        assert body['configuration'] == {}
        assert isinstance(body['updatable_keys'], list)
    
    def test_handle_get_config_exception_handling(self, handler, valid_get_event):
        """Test configuration retrieval exception handling."""
        context = Mock()
        
        # Mock exception in config manager
        handler.config_manager.get_all_config.side_effect = Exception("Database error")
        
        response = handler.handle_request(valid_get_event, context)
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Failed to retrieve configuration' in body['error']
    
    def test_handle_get_config_filters_updatable_keys(self, handler, valid_get_event):
        """Test that GET config only returns updatable configuration keys."""
        context = Mock()
        
        # Mock configuration with mix of updatable and non-updatable keys
        mock_config_data = {
            'forwarding_enabled': {
                'value': True,
                'last_updated': 1640995200,
                'updated_by': 'admin'
            },
            'internal_system_key': {  # Not in updatable_keys
                'value': 'secret',
                'last_updated': 1640995200,
                'updated_by': 'system'
            },
            'data_retention_days': {
                'value': 30,
                'last_updated': 1640995300,
                'updated_by': 'admin'
            },
            'another_internal_key': {  # Not in updatable_keys
                'value': 'internal',
                'last_updated': 1640995400,
                'updated_by': 'system'
            }
        }
        
        handler.config_manager.get_all_config.return_value = mock_config_data
        
        response = handler.handle_request(valid_get_event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Only updatable keys should be in response
        config = body['configuration']
        assert len(config) == 2
        assert 'forwarding_enabled' in config
        assert 'data_retention_days' in config
        assert 'internal_system_key' not in config
        assert 'another_internal_key' not in config
    
    def test_handle_get_config_default_value_detection(self, handler, valid_get_event):
        """Test that default values are properly detected."""
        context = Mock()
        
        # Mock configuration with mix of set and default values
        mock_config_data = {
            'forwarding_enabled': {
                'value': False,
                'last_updated': 1640995200,  # Has timestamp - not default
                'updated_by': 'admin'
            },
            'data_retention_days': {
                'value': 90,
                'last_updated': None,  # No timestamp - is default
                'updated_by': 'default'
            },
            'ruuvi_cloud_timeout': {
                'value': 25,
                'last_updated': 0,  # Zero timestamp - still not default
                'updated_by': 'system'
            }
        }
        
        handler.config_manager.get_all_config.return_value = mock_config_data
        
        response = handler.handle_request(valid_get_event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        config = body['configuration']
        
        # Check is_default flag
        assert config['forwarding_enabled']['is_default'] is False
        assert config['data_retention_days']['is_default'] is True
        assert config['ruuvi_cloud_timeout']['is_default'] is False
    
    def test_handle_get_config_unauthorized(self, handler):
        """Test configuration retrieval with unauthorized access."""
        event = {
            'httpMethod': 'GET',
            'headers': {
                'x-api-key': 'invalid-key'
            },
            'requestContext': {
                'requestId': 'test-request-123'
            }
        }
        context = Mock()
        
        response = handler.handle_request(event, context)
        
        assert response['statusCode'] == 401
        body = json.loads(response['body'])
        assert body['error'] == 'Unauthorized access'
        
        # Config manager should not be called
        handler.config_manager.get_all_config.assert_not_called()
    
    def test_updatable_keys_list_completeness(self, handler, valid_get_event):
        """Test that updatable_keys list contains all expected keys."""
        context = Mock()
        
        handler.config_manager.get_all_config.return_value = {}
        
        response = handler.handle_request(valid_get_event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        updatable_keys = body['updatable_keys']
        expected_keys = [
            'forwarding_enabled',
            'data_retention_days',
            'ruuvi_cloud_endpoint',
            'ruuvi_cloud_timeout',
            'max_batch_size',
            'cache_ttl_seconds'
        ]
        
        # Convert to sets for comparison (order doesn't matter)
        assert set(updatable_keys) == set(expected_keys)
    
    def test_configuration_response_format(self, handler, valid_get_event):
        """Test that configuration response has correct format."""
        context = Mock()
        
        mock_config_data = {
            'forwarding_enabled': {
                'value': True,
                'last_updated': 1640995200,
                'updated_by': 'admin-user'
            }
        }
        
        handler.config_manager.get_all_config.return_value = mock_config_data
        
        response = handler.handle_request(valid_get_event, context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Check top-level structure
        assert 'result' in body
        assert 'configuration' in body
        assert 'updatable_keys' in body
        
        # Check configuration item structure
        config_item = body['configuration']['forwarding_enabled']
        required_fields = ['value', 'last_updated', 'updated_by', 'is_default']
        
        for field in required_fields:
            assert field in config_item, f"Missing field: {field}"