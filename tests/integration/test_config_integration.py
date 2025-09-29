"""
Integration tests for configuration management (Task 9.2).

Tests cover:
- Test dynamic configuration updates without restart
- Verify configuration caching and fallback behavior
- Test admin authentication for configuration changes
- Create tests for configuration audit logging
"""

import json
import pytest
import time
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Import the configuration function and dependencies
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from config.index import lambda_handler, ConfigurationHandler
from shared.config_manager import ConfigurationManager, get_config_manager, reset_config_manager


class TestConfigurationManagementIntegration:
    """Integration tests for configuration management functionality."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Reset singleton to ensure clean state
        reset_config_manager()
    
    def create_api_gateway_event(self, method: str, body: dict = None, api_key: str = None):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": "/api/v1/config",
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
            },
            "headers": {
                "Content-Type": "application/json"
            }
        }
        
        if api_key:
            event["headers"]["X-API-Key"] = api_key
        
        if body:
            event["body"] = json.dumps(body)
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-config-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context


class TestDynamicConfigurationUpdates:
    """Test dynamic configuration updates without restart."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_config_manager()
    
    def create_api_gateway_event(self, method: str, body: dict = None, api_key: str = "test-admin-key"):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": "/api/v1/config",
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
            },
            "headers": {
                "Content-Type": "application/json",
                "X-API-Key": api_key
            }
        }
        
        if body:
            event["body"] = json.dumps(body)
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-config-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'test-admin-key'
    })
    @patch('config.index.get_config_manager')
    def test_update_forwarding_configuration(self, mock_get_config_manager):
        """Test updating forwarding configuration dynamically."""
        # Setup mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.set_config.return_value = True
        mock_config_manager.clear_cache.return_value = None
        mock_get_config_manager.return_value = mock_config_manager
        
        # Create update request
        update_data = {
            "forwarding_enabled": False
        }
        event = self.create_api_gateway_event("PUT", update_data)
        context = self.create_lambda_context()
        
        # Execute configuration update
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["updated"]["forwarding_enabled"] is False
        assert "timestamp" in body
        
        # Verify config manager was called correctly
        mock_config_manager.set_config.assert_called_once_with(
            "forwarding_enabled", False, updated_by=mock_get_config_manager.return_value.set_config.call_args[1]['updated_by']
        )
        mock_config_manager.clear_cache.assert_called_once()
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'test-admin-key'
    })
    @patch('config.index.get_config_manager')
    def test_update_multiple_configurations(self, mock_get_config_manager):
        """Test updating multiple configuration values at once."""
        # Setup mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.set_config.return_value = True
        mock_config_manager.clear_cache.return_value = None
        mock_get_config_manager.return_value = mock_config_manager
        
        # Create update request with multiple configs
        update_data = {
            "forwarding_enabled": True,
            "data_retention_days": 30,
            "ruuvi_cloud_timeout": 15
        }
        event = self.create_api_gateway_event("PUT", update_data)
        context = self.create_lambda_context()
        
        # Execute configuration update
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["updated"]["forwarding_enabled"] is True
        assert body["updated"]["data_retention_days"] == 30
        assert body["updated"]["ruuvi_cloud_timeout"] == 15
        
        # Verify all configs were set
        assert mock_config_manager.set_config.call_count == 3
        mock_config_manager.clear_cache.assert_called_once()
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'test-admin-key'
    })
    @patch('config.index.get_config_manager')
    def test_update_invalid_configuration_key(self, mock_get_config_manager):
        """Test handling of invalid configuration keys."""
        # Setup mock config manager
        mock_config_manager = MagicMock()
        mock_get_config_manager.return_value = mock_config_manager
        
        # Create update request with invalid key
        update_data = {
            "invalid_config_key": "some_value",
            "forwarding_enabled": True  # Valid key
        }
        event = self.create_api_gateway_event("PUT", update_data)
        context = self.create_lambda_context()
        
        # Execute configuration update
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200  # Partial success
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert "forwarding_enabled" in body["updated"]
        assert "errors" in body
        assert "invalid_config_key" in body["errors"]
        assert "not updatable" in body["errors"]["invalid_config_key"]
        
        # Verify only valid config was set
        mock_config_manager.set_config.assert_called_once_with(
            "forwarding_enabled", True, updated_by=mock_config_manager.set_config.call_args[1]['updated_by']
        )
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'test-admin-key'
    })
    @patch('config.index.get_config_manager')
    def test_configuration_update_failure_handling(self, mock_get_config_manager):
        """Test handling when configuration update fails."""
        # Setup mock config manager to fail
        mock_config_manager = MagicMock()
        mock_config_manager.set_config.return_value = False  # Simulate failure
        mock_get_config_manager.return_value = mock_config_manager
        
        # Create update request
        update_data = {
            "forwarding_enabled": True
        }
        event = self.create_api_gateway_event("PUT", update_data)
        context = self.create_lambda_context()
        
        # Execute configuration update
        response = lambda_handler(event, context)
        
        # Verify response indicates failure
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["result"] == "error"
        assert "errors" in body
        assert "forwarding_enabled" in body["errors"]
        assert "Failed to update" in body["errors"]["forwarding_enabled"]


class TestConfigurationCachingAndFallback:
    """Test configuration caching and fallback behavior."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_config_manager()
    
    @patch('shared.config_manager.boto3')
    def test_configuration_caching_behavior(self, mock_boto3):
        """Test that configuration values are cached properly."""
        # Setup mock DynamoDB
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'config_key': 'forwarding_enabled',
                'config_value': 'true',
                'last_updated': int(time.time()),
                'updated_by': 'test-user'
            }
        }
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_resource
        
        # Create config manager with short cache TTL for testing
        config_manager = ConfigurationManager('test-table', cache_ttl_seconds=2)
        
        # First call should hit DynamoDB
        value1 = config_manager.get_config('forwarding_enabled')
        assert value1 is True
        assert mock_table.get_item.call_count == 1
        
        # Second call should use cache
        value2 = config_manager.get_config('forwarding_enabled')
        assert value2 is True
        assert mock_table.get_item.call_count == 1  # No additional call
        
        # Wait for cache to expire
        time.sleep(2.1)
        
        # Third call should hit DynamoDB again
        value3 = config_manager.get_config('forwarding_enabled')
        assert value3 is True
        assert mock_table.get_item.call_count == 2  # Additional call made
    
    @patch('shared.config_manager.boto3')
    def test_configuration_fallback_to_defaults(self, mock_boto3):
        """Test fallback to default values when DynamoDB is unavailable."""
        # Setup mock DynamoDB to raise exception
        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception("DynamoDB unavailable")
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_resource
        
        # Create config manager
        config_manager = ConfigurationManager('test-table')
        
        # Should return default value when DynamoDB fails
        value = config_manager.get_config('forwarding_enabled')
        assert value is True  # Default value
        
        # Should return provided default when no system default exists
        value = config_manager.get_config('unknown_key', default='custom_default')
        assert value == 'custom_default'
        
        # Should return None when no default is available
        value = config_manager.get_config('unknown_key')
        assert value is None
    
    @patch('shared.config_manager.boto3')
    def test_cache_clear_functionality(self, mock_boto3):
        """Test that cache clearing works properly."""
        # Setup mock DynamoDB
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'config_key': 'forwarding_enabled',
                'config_value': 'true',
                'last_updated': int(time.time()),
                'updated_by': 'test-user'
            }
        }
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_resource
        
        # Create config manager
        config_manager = ConfigurationManager('test-table', cache_ttl_seconds=300)
        
        # First call should hit DynamoDB
        value1 = config_manager.get_config('forwarding_enabled')
        assert value1 is True
        assert mock_table.get_item.call_count == 1
        
        # Second call should use cache
        value2 = config_manager.get_config('forwarding_enabled')
        assert mock_table.get_item.call_count == 1
        
        # Clear cache
        config_manager.clear_cache()
        
        # Next call should hit DynamoDB again
        value3 = config_manager.get_config('forwarding_enabled')
        assert mock_table.get_item.call_count == 2
    
    @patch('shared.config_manager.boto3')
    def test_configuration_value_serialization(self, mock_boto3):
        """Test proper serialization/deserialization of different value types."""
        # Setup mock DynamoDB
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_resource
        
        # Create config manager
        config_manager = ConfigurationManager('test-table')
        
        # Test different value types
        test_values = [
            ('boolean_true', True, 'true'),
            ('boolean_false', False, 'false'),
            ('integer', 42, '42'),
            ('float', 3.14, '3.14'),
            ('string', 'test_string', 'test_string'),
            ('dict', {'key': 'value'}, '{"key": "value"}'),
            ('list', [1, 2, 3], '[1, 2, 3]')
        ]
        
        for key, original_value, expected_serialized in test_values:
            # Test serialization
            serialized = config_manager._serialize_value(original_value)
            assert serialized == expected_serialized
            
            # Test deserialization
            deserialized = config_manager._deserialize_value(serialized)
            assert deserialized == original_value


class TestAdminAuthentication:
    """Test admin authentication for configuration changes."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_config_manager()
    
    def create_api_gateway_event(self, method: str, body: dict = None, api_key: str = None):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": "/api/v1/config",
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
            },
            "headers": {
                "Content-Type": "application/json"
            }
        }
        
        if api_key:
            event["headers"]["X-API-Key"] = api_key
        
        if body:
            event["body"] = json.dumps(body)
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-config-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'correct-admin-key'
    })
    def test_valid_admin_authentication(self, mock_get_config_manager=None):
        """Test successful authentication with valid admin API key."""
        with patch('config.index.get_config_manager') as mock_get_config_manager:
            # Setup mock config manager
            mock_config_manager = MagicMock()
            mock_config_manager.get_all_config.return_value = {
                'forwarding_enabled': {
                    'value': True,
                    'last_updated': int(time.time()),
                    'updated_by': 'test-user'
                }
            }
            mock_get_config_manager.return_value = mock_config_manager
            
            # Create request with valid API key
            event = self.create_api_gateway_event("GET", api_key="correct-admin-key")
            context = self.create_lambda_context()
            
            # Execute request
            response = lambda_handler(event, context)
            
            # Verify successful authentication
            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert body["result"] == "success"
            assert "configuration" in body
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'correct-admin-key'
    })
    def test_invalid_admin_api_key(self):
        """Test rejection of invalid admin API key."""
        # Create request with invalid API key
        event = self.create_api_gateway_event("GET", api_key="invalid-key")
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify authentication failure
        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert body["error"] == "Unauthorized access"
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'correct-admin-key'
    })
    def test_missing_api_key(self):
        """Test rejection when no API key is provided."""
        # Create request without API key
        event = self.create_api_gateway_event("GET")
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify authentication failure
        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert body["error"] == "Unauthorized access"
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table'
        # Note: ADMIN_API_KEY not set
    })
    def test_missing_admin_key_configuration(self):
        """Test handling when admin API key is not configured."""
        # Create request with any API key
        event = self.create_api_gateway_event("GET", api_key="any-key")
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify authentication failure due to missing configuration
        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert body["error"] == "Unauthorized access"
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'correct-admin-key'
    })
    def test_case_insensitive_api_key_header(self):
        """Test that API key header is case insensitive."""
        with patch('config.index.get_config_manager') as mock_get_config_manager:
            # Setup mock config manager
            mock_config_manager = MagicMock()
            mock_config_manager.get_all_config.return_value = {}
            mock_get_config_manager.return_value = mock_config_manager
            
            # Test different case variations
            header_variations = [
                {"X-API-Key": "correct-admin-key"},
                {"x-api-key": "correct-admin-key"},
                {"X-Api-Key": "correct-admin-key"}
            ]
            
            for headers in header_variations:
                event = {
                    "httpMethod": "GET",
                    "path": "/api/v1/config",
                    "requestContext": {
                        "requestId": f"test-request-{int(time.time())}",
                        "identity": {"sourceIp": "192.168.1.100"}
                    },
                    "headers": {**headers, "Content-Type": "application/json"}
                }
                context = self.create_lambda_context()
                
                # Execute request
                response = lambda_handler(event, context)
                
                # Verify successful authentication
                assert response["statusCode"] == 200


class TestConfigurationAuditLogging:
    """Test configuration audit logging functionality."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_config_manager()
    
    def create_api_gateway_event(self, method: str, body: dict = None, api_key: str = "test-admin-key"):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": "/api/v1/config",
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                },
                "authorizer": {
                    "claims": {
                        "sub": "user-123",
                        "username": "test-admin"
                    }
                }
            },
            "headers": {
                "Content-Type": "application/json",
                "X-API-Key": api_key
            }
        }
        
        if body:
            event["body"] = json.dumps(body)
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-config-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'test-admin-key'
    })
    @patch('config.index.get_config_manager')
    @patch('config.index.logger')
    def test_configuration_update_audit_logging(self, mock_logger, mock_get_config_manager):
        """Test that configuration updates are properly logged for audit."""
        # Setup mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.set_config.return_value = True
        mock_config_manager.clear_cache.return_value = None
        mock_get_config_manager.return_value = mock_config_manager
        
        # Create update request
        update_data = {
            "forwarding_enabled": False,
            "data_retention_days": 30
        }
        event = self.create_api_gateway_event("PUT", update_data)
        context = self.create_lambda_context()
        
        # Execute configuration update
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        
        # Verify audit logging occurred
        mock_logger.info.assert_called()
        
        # Check that user identifier was passed to config manager
        set_config_calls = mock_config_manager.set_config.call_args_list
        assert len(set_config_calls) == 2
        
        # Verify user identifier is included in calls
        for call in set_config_calls:
            assert 'updated_by' in call[1]
            user_id = call[1]['updated_by']
            assert 'user-123' in user_id or 'test-admin' in user_id
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'test-admin-key'
    })
    @patch('config.index.get_config_manager')
    def test_user_identifier_from_cognito_claims(self, mock_get_config_manager):
        """Test user identifier extraction from Cognito claims."""
        # Setup mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.set_config.return_value = True
        mock_config_manager.clear_cache.return_value = None
        mock_get_config_manager.return_value = mock_config_manager
        
        # Create update request with Cognito claims
        update_data = {"forwarding_enabled": True}
        event = self.create_api_gateway_event("PUT", update_data)
        context = self.create_lambda_context()
        
        # Execute configuration update
        response = lambda_handler(event, context)
        
        # Verify user identifier from Cognito was used
        mock_config_manager.set_config.assert_called_once()
        call_args = mock_config_manager.set_config.call_args
        user_id = call_args[1]['updated_by']
        assert user_id == 'user-123'  # Should use 'sub' from claims
    
    @patch.dict(os.environ, {
        'CONFIG_TABLE_NAME': 'test-config-table',
        'ADMIN_API_KEY': 'test-admin-key'
    })
    @patch('config.index.get_config_manager')
    def test_user_identifier_fallback_to_api_key(self, mock_get_config_manager):
        """Test user identifier fallback when no Cognito claims available."""
        # Setup mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.set_config.return_value = True
        mock_config_manager.clear_cache.return_value = None
        mock_get_config_manager.return_value = mock_config_manager
        
        # Create update request without Cognito claims
        update_data = {"forwarding_enabled": True}
        event = {
            "httpMethod": "PUT",
            "path": "/api/v1/config",
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
                # No authorizer/claims
            },
            "headers": {
                "Content-Type": "application/json",
                "X-API-Key": "test-admin-key-12345678"
            },
            "body": json.dumps(update_data)
        }
        context = self.create_lambda_context()
        
        # Execute configuration update
        response = lambda_handler(event, context)
        
        # Verify user identifier fallback was used
        mock_config_manager.set_config.assert_called_once()
        call_args = mock_config_manager.set_config.call_args
        user_id = call_args[1]['updated_by']
        assert 'api-key:12345678@192.168.1.100' == user_id
    
    @patch('shared.config_manager.boto3')
    def test_configuration_manager_audit_fields(self, mock_boto3):
        """Test that configuration manager stores proper audit fields."""
        # Setup mock DynamoDB
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_resource
        
        # Create config manager
        config_manager = ConfigurationManager('test-table')
        
        # Set configuration with audit info
        test_time = int(time.time())
        with patch('time.time', return_value=test_time):
            result = config_manager.set_config('forwarding_enabled', True, updated_by='test-user')
        
        # Verify DynamoDB put_item was called with audit fields
        assert result is True
        mock_table.put_item.assert_called_once()
        
        put_item_args = mock_table.put_item.call_args[1]
        item = put_item_args['Item']
        
        assert item['config_key'] == 'forwarding_enabled'
        assert item['config_value'] == 'true'
        assert item['last_updated'] == test_time
        assert item['updated_by'] == 'test-user'
    
    @patch('shared.config_manager.boto3')
    def test_get_all_config_includes_audit_info(self, mock_boto3):
        """Test that get_all_config returns audit information."""
        # Setup mock DynamoDB
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [
                {
                    'config_key': 'forwarding_enabled',
                    'config_value': 'true',
                    'last_updated': 1640995200,
                    'updated_by': 'admin-user'
                },
                {
                    'config_key': 'data_retention_days',
                    'config_value': '30',
                    'last_updated': 1640995300,
                    'updated_by': 'system'
                }
            ]
        }
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_resource
        
        # Create config manager
        config_manager = ConfigurationManager('test-table')
        
        # Get all configuration
        all_config = config_manager.get_all_config()
        
        # Verify audit information is included
        assert 'forwarding_enabled' in all_config
        forwarding_config = all_config['forwarding_enabled']
        assert forwarding_config['value'] is True
        assert forwarding_config['last_updated'] == 1640995200
        assert forwarding_config['updated_by'] == 'admin-user'
        
        assert 'data_retention_days' in all_config
        retention_config = all_config['data_retention_days']
        assert retention_config['value'] == 30
        assert retention_config['last_updated'] == 1640995300
        assert retention_config['updated_by'] == 'system'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])