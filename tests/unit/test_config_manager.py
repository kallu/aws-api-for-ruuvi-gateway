"""
Unit tests for configuration management utilities.
"""

import json
import time
import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from src.shared.config_manager import ConfigurationManager, get_config_manager, reset_config_manager


class TestConfigurationManager:
    """Test cases for ConfigurationManager class."""
    
    @pytest.fixture
    def mock_dynamodb_table(self):
        """Mock DynamoDB table."""
        with patch('boto3.resource') as mock_resource:
            mock_table = Mock()
            mock_resource.return_value.Table.return_value = mock_table
            yield mock_table
    
    @pytest.fixture
    def config_manager(self, mock_dynamodb_table):
        """Create ConfigurationManager instance with mocked DynamoDB."""
        return ConfigurationManager('test-config-table', cache_ttl_seconds=60)
    
    def test_init(self, config_manager):
        """Test ConfigurationManager initialization."""
        assert config_manager.table_name == 'test-config-table'
        assert config_manager.cache_ttl_seconds == 60
        assert config_manager._cache == {}
        assert 'forwarding_enabled' in config_manager._defaults
    
    def test_get_config_from_dynamodb(self, config_manager, mock_dynamodb_table):
        """Test getting configuration from DynamoDB."""
        # Mock DynamoDB response
        mock_dynamodb_table.get_item.return_value = {
            'Item': {
                'config_key': 'forwarding_enabled',
                'config_value': 'true',
                'last_updated': 1234567890
            }
        }
        
        result = config_manager.get_config('forwarding_enabled')
        
        assert result is True
        mock_dynamodb_table.get_item.assert_called_once_with(Key={'config_key': 'forwarding_enabled'})
        # Check cache was updated
        assert 'forwarding_enabled' in config_manager._cache
    
    def test_get_config_from_cache(self, config_manager, mock_dynamodb_table):
        """Test getting configuration from cache."""
        # Pre-populate cache
        config_manager._cache['test_key'] = {
            'value': 'cached_value',
            'timestamp': time.time()
        }
        
        result = config_manager.get_config('test_key')
        
        assert result == 'cached_value'
        # DynamoDB should not be called
        mock_dynamodb_table.get_item.assert_not_called()
    
    def test_get_config_expired_cache(self, config_manager, mock_dynamodb_table):
        """Test getting configuration with expired cache."""
        # Pre-populate cache with old timestamp
        config_manager._cache['test_key'] = {
            'value': 'old_cached_value',
            'timestamp': time.time() - 3600  # 1 hour ago
        }
        
        # Mock DynamoDB response
        mock_dynamodb_table.get_item.return_value = {
            'Item': {
                'config_key': 'test_key',
                'config_value': 'fresh_value'
            }
        }
        
        result = config_manager.get_config('test_key')
        
        assert result == 'fresh_value'
        mock_dynamodb_table.get_item.assert_called_once()
    
    def test_get_config_not_found_with_default(self, config_manager, mock_dynamodb_table):
        """Test getting configuration that doesn't exist with default."""
        mock_dynamodb_table.get_item.return_value = {}
        
        result = config_manager.get_config('nonexistent_key', 'default_value')
        
        assert result == 'default_value'
    
    def test_get_config_not_found_system_default(self, config_manager, mock_dynamodb_table):
        """Test getting configuration that doesn't exist with system default."""
        mock_dynamodb_table.get_item.return_value = {}
        
        result = config_manager.get_config('forwarding_enabled')
        
        assert result is True  # System default
    
    def test_get_config_dynamodb_error(self, config_manager, mock_dynamodb_table):
        """Test handling DynamoDB errors."""
        mock_dynamodb_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}}, 'GetItem'
        )
        
        result = config_manager.get_config('forwarding_enabled', 'fallback_value')
        
        assert result == 'fallback_value'
    
    def test_set_config_success(self, config_manager, mock_dynamodb_table):
        """Test setting configuration successfully."""
        mock_dynamodb_table.put_item.return_value = {}
        
        result = config_manager.set_config('forwarding_enabled', False, 'test_user')
        
        assert result is True
        mock_dynamodb_table.put_item.assert_called_once()
        call_args = mock_dynamodb_table.put_item.call_args[1]['Item']
        assert call_args['config_key'] == 'forwarding_enabled'
        assert call_args['config_value'] == 'False'
        assert call_args['updated_by'] == 'test_user'
        assert 'last_updated' in call_args
    
    def test_set_config_invalid_value(self, config_manager, mock_dynamodb_table):
        """Test setting invalid configuration value."""
        result = config_manager.set_config('data_retention_days', -1)
        
        assert result is False
        mock_dynamodb_table.put_item.assert_not_called()
    
    def test_set_config_dynamodb_error(self, config_manager, mock_dynamodb_table):
        """Test handling DynamoDB errors during set."""
        mock_dynamodb_table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'ValidationException'}}, 'PutItem'
        )
        
        result = config_manager.set_config('forwarding_enabled', True)
        
        assert result is False
    
    def test_get_all_config(self, config_manager, mock_dynamodb_table):
        """Test getting all configuration values."""
        mock_dynamodb_table.scan.return_value = {
            'Items': [
                {
                    'config_key': 'forwarding_enabled',
                    'config_value': 'false',
                    'last_updated': 1234567890,
                    'updated_by': 'admin'
                },
                {
                    'config_key': 'data_retention_days',
                    'config_value': '30',
                    'last_updated': 1234567891,
                    'updated_by': 'system'
                }
            ]
        }
        
        result = config_manager.get_all_config()
        
        assert 'forwarding_enabled' in result
        assert result['forwarding_enabled']['value'] is False
        assert result['forwarding_enabled']['updated_by'] == 'admin'
        assert 'data_retention_days' in result
        assert result['data_retention_days']['value'] == 30
        # Should include defaults for missing keys
        assert 'ruuvi_cloud_endpoint' in result
        assert result['ruuvi_cloud_endpoint']['updated_by'] == 'default'
    
    def test_clear_cache(self, config_manager):
        """Test clearing cache."""
        config_manager._cache['test_key'] = {'value': 'test', 'timestamp': time.time()}
        
        config_manager.clear_cache()
        
        assert config_manager._cache == {}
    
    def test_serialize_deserialize_values(self, config_manager):
        """Test value serialization and deserialization."""
        test_cases = [
            (True, 'True', True),
            (False, 'False', False),
            (42, '42', 42),
            (3.14, '3.14', 3.14),
            ('string', 'string', 'string'),
            ({'key': 'value'}, '{"key": "value"}', {'key': 'value'}),
            ([1, 2, 3], '[1, 2, 3]', [1, 2, 3])
        ]
        
        for original, expected_serialized, expected_deserialized in test_cases:
            serialized = config_manager._serialize_value(original)
            assert serialized == expected_serialized
            
            deserialized = config_manager._deserialize_value(serialized)
            assert deserialized == expected_deserialized
    
    def test_validate_config(self, config_manager):
        """Test configuration validation."""
        # Valid values
        assert config_manager._validate_config('forwarding_enabled', True)
        assert config_manager._validate_config('data_retention_days', 90)
        assert config_manager._validate_config('ruuvi_cloud_endpoint', 'https://api.example.com')
        assert config_manager._validate_config('ruuvi_cloud_timeout', 25)
        
        # Invalid values
        assert not config_manager._validate_config('forwarding_enabled', 'not_boolean')
        assert not config_manager._validate_config('data_retention_days', 0)
        assert not config_manager._validate_config('data_retention_days', 5000)
        assert not config_manager._validate_config('ruuvi_cloud_endpoint', 'not_a_url')
        assert not config_manager._validate_config('ruuvi_cloud_timeout', 0)
        assert not config_manager._validate_config('ruuvi_cloud_timeout', 500)
        
        # Unknown key (should be allowed with warning)
        assert config_manager._validate_config('unknown_key', 'any_value')


class TestSingletonFunctions:
    """Test singleton configuration manager functions."""
    
    def teardown_method(self):
        """Reset singleton after each test."""
        reset_config_manager()
    
    @patch('src.shared.config_manager.ConfigurationManager')
    def test_get_config_manager_first_call(self, mock_config_class):
        """Test first call to get_config_manager."""
        mock_instance = Mock()
        mock_config_class.return_value = mock_instance
        
        result = get_config_manager('test-table', 120)
        
        assert result == mock_instance
        mock_config_class.assert_called_once_with('test-table', 120)
    
    @patch('src.shared.config_manager.ConfigurationManager')
    def test_get_config_manager_subsequent_calls(self, mock_config_class):
        """Test subsequent calls to get_config_manager."""
        mock_instance = Mock()
        mock_config_class.return_value = mock_instance
        
        # First call
        result1 = get_config_manager('test-table')
        # Second call
        result2 = get_config_manager()
        
        assert result1 == result2 == mock_instance
        # Should only be called once
        mock_config_class.assert_called_once()
    
    def test_get_config_manager_no_table_name(self):
        """Test get_config_manager without table name on first call."""
        with pytest.raises(ValueError, match="table_name is required"):
            get_config_manager()
    
    @patch('src.shared.config_manager.ConfigurationManager')
    def test_reset_config_manager(self, mock_config_class):
        """Test resetting singleton."""
        mock_instance = Mock()
        mock_config_class.return_value = mock_instance
        
        # Create instance
        get_config_manager('test-table')
        
        # Reset
        reset_config_manager()
        
        # Should be able to create new instance
        get_config_manager('new-table')
        
        # Should have been called twice
        assert mock_config_class.call_count == 2