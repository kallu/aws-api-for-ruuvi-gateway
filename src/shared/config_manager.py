"""
Configuration management utilities for Ruuvi API.
Handles reading/writing configuration from DynamoDB with in-memory caching.
"""

import json
import time
from typing import Any, Dict, Optional, Union
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """Manages configuration storage and retrieval with caching."""
    
    def __init__(self, table_name: str, cache_ttl_seconds: int = 300):
        """
        Initialize configuration manager.
        
        Args:
            table_name: DynamoDB table name for configuration storage
            cache_ttl_seconds: Cache TTL in seconds (default: 5 minutes)
        """
        self.table_name = table_name
        self.cache_ttl_seconds = cache_ttl_seconds
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        # Default configuration values
        self._defaults = {
            'forwarding_enabled': True,
            'data_retention_days': 90,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com/record',
            'ruuvi_cloud_timeout': 25,
            'max_batch_size': 25,
            'cache_ttl_seconds': 300
        }
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with caching.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        try:
            # Check cache first
            if self._is_cached_and_valid(key):
                return self._cache[key]['value']
            
            # Fetch from DynamoDB
            response = self.table.get_item(Key={'config_key': key})
            
            if 'Item' in response:
                value = self._deserialize_value(response['Item']['config_value'])
                self._update_cache(key, value)
                return value
            else:
                # Use provided default or system default
                default_value = default if default is not None else self._defaults.get(key)
                if default_value is not None:
                    logger.info(f"Using default value for config key '{key}': {default_value}")
                    return default_value
                else:
                    logger.warning(f"No configuration found for key '{key}' and no default provided")
                    return None
                    
        except ClientError as e:
            logger.error(f"Error reading configuration for key '{key}': {e}")
            # Return default on error
            default_value = default if default is not None else self._defaults.get(key)
            return default_value
    
    def set_config(self, key: str, value: Any, updated_by: str = 'system') -> bool:
        """
        Set configuration value.
        
        Args:
            key: Configuration key
            value: Configuration value
            updated_by: User/system identifier for audit
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate configuration value
            if not self._validate_config(key, value):
                logger.error(f"Invalid configuration value for key '{key}': {value}")
                return False
            
            # Store in DynamoDB
            serialized_value = self._serialize_value(value)
            timestamp = int(time.time())
            
            self.table.put_item(
                Item={
                    'config_key': key,
                    'config_value': serialized_value,
                    'last_updated': timestamp,
                    'updated_by': updated_by
                }
            )
            
            # Update cache
            self._update_cache(key, value)
            
            logger.info(f"Configuration updated: {key} = {value} by {updated_by}")
            return True
            
        except ClientError as e:
            logger.error(f"Error setting configuration for key '{key}': {e}")
            return False
    
    def get_all_config(self) -> Dict[str, Any]:
        """
        Get all configuration values.
        
        Returns:
            Dictionary of all configuration values
        """
        try:
            response = self.table.scan()
            config = {}
            
            for item in response.get('Items', []):
                key = item['config_key']
                value = self._deserialize_value(item['config_value'])
                config[key] = {
                    'value': value,
                    'last_updated': item.get('last_updated'),
                    'updated_by': item.get('updated_by', 'unknown')
                }
            
            # Add defaults for missing keys
            for key, default_value in self._defaults.items():
                if key not in config:
                    config[key] = {
                        'value': default_value,
                        'last_updated': None,
                        'updated_by': 'default'
                    }
            
            return config
            
        except ClientError as e:
            logger.error(f"Error reading all configuration: {e}")
            return {key: {'value': value, 'last_updated': None, 'updated_by': 'default'} 
                   for key, value in self._defaults.items()}
    
    def clear_cache(self) -> None:
        """Clear the configuration cache."""
        self._cache.clear()
        logger.info("Configuration cache cleared")
    
    def _is_cached_and_valid(self, key: str) -> bool:
        """Check if key is cached and cache is still valid."""
        if key not in self._cache:
            return False
        
        cache_entry = self._cache[key]
        cache_age = time.time() - cache_entry['timestamp']
        return cache_age < self.cache_ttl_seconds
    
    def _update_cache(self, key: str, value: Any) -> None:
        """Update cache with new value."""
        self._cache[key] = {
            'value': value,
            'timestamp': time.time()
        }
    
    def _serialize_value(self, value: Any) -> str:
        """Serialize value for DynamoDB storage."""
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        else:
            return str(value)
    
    def _deserialize_value(self, serialized_value: str) -> Any:
        """Deserialize value from DynamoDB storage."""
        try:
            # Try to parse as JSON first
            return json.loads(serialized_value)
        except (json.JSONDecodeError, TypeError):
            # If not JSON, try to convert to appropriate type
            if serialized_value.lower() in ('true', 'false'):
                return serialized_value.lower() == 'true'
            try:
                # Try integer
                if '.' not in serialized_value:
                    return int(serialized_value)
                # Try float
                return float(serialized_value)
            except ValueError:
                # Return as string
                return serialized_value
    
    def _validate_config(self, key: str, value: Any) -> bool:
        """Validate configuration value."""
        validators = {
            'forwarding_enabled': lambda v: isinstance(v, bool),
            'data_retention_days': lambda v: isinstance(v, int) and 1 <= v <= 3650,
            'ruuvi_cloud_endpoint': lambda v: isinstance(v, str) and v.startswith(('http://', 'https://')),
            'ruuvi_cloud_timeout': lambda v: isinstance(v, (int, float)) and 1 <= v <= 300,
            'max_batch_size': lambda v: isinstance(v, int) and 1 <= v <= 100,
            'cache_ttl_seconds': lambda v: isinstance(v, int) and 1 <= v <= 3600
        }
        
        validator = validators.get(key)
        if validator:
            return validator(value)
        
        # For unknown keys, allow any value but log warning
        logger.warning(f"No validator for configuration key '{key}', allowing value: {value}")
        return True


# Singleton instance for global use
_config_manager: Optional[ConfigurationManager] = None


def get_config_manager(table_name: str = None, cache_ttl_seconds: int = 300) -> ConfigurationManager:
    """
    Get singleton configuration manager instance.
    
    Args:
        table_name: DynamoDB table name (required for first call)
        cache_ttl_seconds: Cache TTL in seconds
        
    Returns:
        ConfigurationManager instance
    """
    global _config_manager
    
    if _config_manager is None:
        if table_name is None:
            raise ValueError("table_name is required for first initialization")
        _config_manager = ConfigurationManager(table_name, cache_ttl_seconds)
    
    return _config_manager


def reset_config_manager() -> None:
    """Reset singleton instance (mainly for testing)."""
    global _config_manager
    _config_manager = None