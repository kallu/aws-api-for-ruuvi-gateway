"""
Shared configuration utilities for Ruuvi API system.

This module provides configuration management functionality
used across all Lambda functions.
"""

import os
import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ConfigKey(Enum):
    """Configuration keys used in the system."""
    FORWARDING_ENABLED = "forwarding_enabled"
    DATA_RETENTION_DAYS = "data_retention_days"
    RUUVI_CLOUD_ENDPOINT = "ruuvi_cloud_endpoint"
    RUUVI_CLOUD_TIMEOUT = "ruuvi_cloud_timeout"

class Config:
    """Configuration manager for Lambda functions."""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300  # 5 minutes
        
    def get_env_var(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get environment variable."""
        return os.environ.get(key, default)
    
    def get_table_name(self, table_type: str) -> str:
        """Get DynamoDB table name from environment."""
        env_key = f"{table_type.upper()}_TABLE_NAME"
        table_name = self.get_env_var(env_key)
        if not table_name:
            raise ValueError(f"Missing environment variable: {env_key}")
        return table_name
    
    def get_data_table_name(self) -> str:
        """Get sensor data table name."""
        return self.get_table_name("DATA")
    
    def get_config_table_name(self) -> str:
        """Get configuration table name."""
        return self.get_table_name("CONFIG")
    
    def get_ruuvi_cloud_endpoint(self) -> str:
        """Get Ruuvi Cloud API endpoint."""
        # TODO: Implement dynamic config reading in task 3.2
        return self.get_env_var("RUUVI_CLOUD_ENDPOINT", "https://network.ruuvi.com/record")
    
    def get_forwarding_enabled(self) -> bool:
        """Get forwarding enabled status."""
        # TODO: Implement dynamic config reading in task 3.2
        return self.get_env_var("FORWARDING_ENABLED", "true").lower() == "true"
    
    def get_data_retention_days(self) -> int:
        """Get data retention period in days."""
        # TODO: Implement dynamic config reading in task 3.2
        return int(self.get_env_var("DATA_RETENTION_DAYS", "90"))

# Global config instance
config = Config()