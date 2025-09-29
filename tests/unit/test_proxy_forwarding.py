"""
Unit tests for proxy forwarding logic (Task 4.2).

Tests the configuration-based forwarding logic, Ruuvi Cloud API integration,
and error handling for forwarding failures.
"""

import json
import pytest
import time
from unittest.mock import patch, MagicMock, Mock
import os

# Import the proxy function
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from proxy.index import handle_ruuvi_cloud_forwarding, lambda_handler
from shared.models import RuuviGatewayRequest


class TestForwardingLogic:
    """Test configuration-based forwarding logic."""
    
    def create_test_request(self):
        """Create a test Ruuvi Gateway request."""
        current_timestamp = int(time.time())
        request_data = {
            "data": {
                "coordinates": "",
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "AABBCCDDEEFF": {
                        "rssi": -65,
                        "timestamp": current_timestamp,
                        "data": "dGVzdA=="
                    }
                }
            }
        }
        return RuuviGatewayRequest.from_dict(request_data)
    
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    def test_forwarding_enabled_success(self, mock_client_class, mock_get_config_manager):
        """Test successful forwarding when enabled."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock Ruuvi Cloud client
        mock_client = Mock()
        mock_client.send_sensor_data.return_value = (True, {
            "result": "success",
            "data": {"action": "inserted"}
        })
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        assert success is True
        assert response["result"] == "success"
        assert response["data"]["action"] == "inserted"
        assert was_forwarded is True
        
        # Verify client was called correctly
        mock_client.send_sensor_data.assert_called_once_with(ruuvi_request)
        mock_client_class.assert_called_once_with(
            base_url='https://network.ruuvi.com',
            timeout=25,
            enable_logging=True
        )
    
    @patch('proxy.index.get_config_manager')
    def test_forwarding_disabled(self, mock_get_config_manager):
        """Test behavior when forwarding is disabled."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': False
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        assert success is True
        assert response["result"] == "success"
        assert response["data"]["action"] == "inserted"
        assert was_forwarded is False
        
        # Verify config was checked
        mock_config_manager.get_config.assert_called_with('forwarding_enabled', default=True)
    
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    def test_forwarding_enabled_failure(self, mock_client_class, mock_get_config_manager):
        """Test handling of Ruuvi Cloud API failures."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock Ruuvi Cloud client failure
        mock_client = Mock()
        mock_client.send_sensor_data.return_value = (False, {
            "result": "error",
            "error": {"code": "CONNECTION_ERROR", "message": "Failed to connect"}
        })
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        assert success is False
        assert response["result"] == "error"
        assert response["error"]["code"] == "CONNECTION_ERROR"
        assert was_forwarded is True
        
        # Verify client was called multiple times due to retry logic (CONNECTION_ERROR is retryable)
        assert mock_client.send_sensor_data.call_count == 4  # 1 initial + 3 retries
        mock_client.send_sensor_data.assert_called_with(ruuvi_request)
    
    @patch('proxy.index.get_config_manager')
    def test_configuration_error_fallback(self, mock_get_config_manager):
        """Test fallback behavior when configuration reading fails."""
        # Mock configuration manager to raise exception
        mock_get_config_manager.side_effect = Exception("DynamoDB connection failed")
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        # Should fallback to local success response
        assert success is True
        assert response["result"] == "success"
        assert response["data"]["action"] == "inserted"
        assert was_forwarded is False
    
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    def test_custom_endpoint_and_timeout(self, mock_client_class, mock_get_config_manager):
        """Test forwarding with custom endpoint and timeout configuration."""
        # Mock configuration manager with custom values
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://custom.ruuvi.endpoint.com',
            'ruuvi_cloud_timeout': 15
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock Ruuvi Cloud client
        mock_client = Mock()
        mock_client.send_sensor_data.return_value = (True, {
            "result": "success",
            "data": {"action": "inserted"}
        })
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        assert success is True
        assert was_forwarded is True
        
        # Verify client was created with custom configuration
        mock_client_class.assert_called_once_with(
            base_url='https://custom.ruuvi.endpoint.com',
            timeout=15,
            enable_logging=True
        )
    
    @patch.dict(os.environ, {'CONFIG_TABLE_NAME': 'custom-config-table'})
    @patch('proxy.index.get_config_manager')
    def test_custom_config_table_name(self, mock_get_config_manager):
        """Test that custom config table name from environment is used."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = False  # forwarding disabled
        mock_get_config_manager.return_value = mock_config_manager
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        # Verify config manager was called with custom table name
        mock_get_config_manager.assert_called_once_with('custom-config-table')


class TestIntegratedForwarding:
    """Test forwarding logic integrated with Lambda handler."""
    
    def create_valid_event(self):
        """Create a valid API Gateway event for testing."""
        current_timestamp = int(time.time())
        request_data = {
            "data": {
                "coordinates": "",
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "AABBCCDDEEFF": {
                        "rssi": -65,
                        "timestamp": current_timestamp,
                        "data": "dGVzdA=="
                    }
                }
            }
        }
        
        return {
            "body": json.dumps(request_data),
            "requestContext": {
                "requestId": "test-request-123"
            },
            "httpMethod": "POST",
            "path": "/api/v1/data",
            "isBase64Encoded": False
        }
    
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    def test_lambda_handler_with_forwarding_enabled(self, mock_client_class, mock_get_config_manager):
        """Test Lambda handler with forwarding enabled."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock successful Ruuvi Cloud response
        mock_client = Mock()
        mock_client.send_sensor_data.return_value = (True, {
            "result": "success",
            "data": {"action": "inserted", "received": 1}
        })
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Test Lambda handler
        event = self.create_valid_event()
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 200
        
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
        assert body["data"]["received"] == 1  # From Ruuvi Cloud response
    
    @patch('proxy.index.get_config_manager')
    def test_lambda_handler_with_forwarding_disabled(self, mock_get_config_manager):
        """Test Lambda handler with forwarding disabled."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': False
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Test Lambda handler
        event = self.create_valid_event()
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 200
        
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
    
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    def test_lambda_handler_forwarding_failure_fallback(self, mock_client_class, mock_get_config_manager):
        """Test Lambda handler fallback when forwarding fails."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock failed Ruuvi Cloud response
        mock_client = Mock()
        mock_client.send_sensor_data.return_value = (False, {
            "result": "error",
            "error": {"code": "TIMEOUT_ERROR", "message": "Request timeout"}
        })
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Test Lambda handler
        event = self.create_valid_event()
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        # Should still return 200 with local success response
        assert response["statusCode"] == 200
        
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"


if __name__ == "__main__":
    pytest.main([__file__])