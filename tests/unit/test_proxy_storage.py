"""
Unit tests for proxy local data storage (Task 4.3).

Tests the data parsing, transformation, and DynamoDB storage functionality
with proper error handling and batch operations.
"""

import json
import pytest
import time
from unittest.mock import patch, MagicMock, Mock
import os

# Import the proxy function
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from proxy.index import store_sensor_data_locally, lambda_handler
from shared.models import RuuviGatewayRequest


class TestLocalDataStorage:
    """Test local data storage functionality."""
    
    def create_test_request(self):
        """Create a test Ruuvi Gateway request with multiple devices."""
        current_timestamp = int(time.time())
        request_data = {
            "data": {
                "coordinates": "60.1699,24.9384",
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "AABBCCDDEEFF": {
                        "rssi": -65,
                        "timestamp": current_timestamp,
                        "data": "dGVzdERhdGEx"
                    },
                    "112233445566": {
                        "rssi": -72,
                        "timestamp": current_timestamp - 1,
                        "data": "dGVzdERhdGEy"
                    }
                }
            }
        }
        return RuuviGatewayRequest.from_dict(request_data)
    
    @patch('proxy.index.get_sensor_data_access')
    @patch('proxy.index.get_config_manager')
    def test_store_sensor_data_locally_success(self, mock_get_config_manager, mock_get_data_access):
        """Test successful local data storage."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = 90  # TTL days
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock data access
        mock_data_access = Mock()
        mock_data_access.store_batch_sensor_data.return_value = (2, 0)  # 2 successful, 0 failed
        mock_get_data_access.return_value = mock_data_access
        
        # Test storage
        ruuvi_request = self.create_test_request()
        ruuvi_cloud_response = {"result": "success", "data": {"action": "inserted"}}
        
        success = store_sensor_data_locally(
            ruuvi_request, ruuvi_cloud_response, "test-correlation-123"
        )
        
        assert success is True
        
        # Verify data access was called correctly (table name may be prefixed in test environment)
        mock_get_data_access.assert_called_once()
        mock_data_access.store_batch_sensor_data.assert_called_once()
        
        # Verify the sensor data structure
        call_args = mock_data_access.store_batch_sensor_data.call_args
        sensor_data_list = call_args[0][0]
        ttl_days = call_args[0][1]
        
        assert len(sensor_data_list) == 2
        assert ttl_days == 90
        
        # Check first device data
        device1_data = next(item for item in sensor_data_list if item['device_id'] == 'AABBCCDDEEFF')
        assert device1_data['gateway_id'] == 'AA:BB:CC:DD:EE:FF'
        assert device1_data['measurements']['rssi'] == -65
        assert device1_data['measurements']['data'] == 'dGVzdERhdGEx'
        assert device1_data['measurements']['coordinates'] == '60.1699,24.9384'
        assert 'ruuvi_cloud_response' in device1_data
        
        # Check second device data
        device2_data = next(item for item in sensor_data_list if item['device_id'] == '112233445566')
        assert device2_data['gateway_id'] == 'AA:BB:CC:DD:EE:FF'
        assert device2_data['measurements']['rssi'] == -72
        assert device2_data['measurements']['data'] == 'dGVzdERhdGEy'
    
    @patch('proxy.index.get_sensor_data_access')
    @patch('proxy.index.get_config_manager')
    def test_store_sensor_data_locally_without_ruuvi_response(self, mock_get_config_manager, mock_get_data_access):
        """Test local storage without Ruuvi Cloud response."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = 30  # Custom TTL
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock data access
        mock_data_access = Mock()
        mock_data_access.store_batch_sensor_data.return_value = (2, 0)
        mock_get_data_access.return_value = mock_data_access
        
        # Test storage without Ruuvi Cloud response
        ruuvi_request = self.create_test_request()
        
        success = store_sensor_data_locally(
            ruuvi_request, None, "test-correlation-123"
        )
        
        assert success is True
        
        # Verify the sensor data doesn't include Ruuvi Cloud response
        call_args = mock_data_access.store_batch_sensor_data.call_args
        sensor_data_list = call_args[0][0]
        ttl_days = call_args[0][1]
        
        assert len(sensor_data_list) == 2
        assert ttl_days == 30
        
        for item in sensor_data_list:
            assert 'ruuvi_cloud_response' not in item
    
    @patch('proxy.index.get_sensor_data_access')
    @patch('proxy.index.get_config_manager')
    def test_store_sensor_data_locally_partial_failure(self, mock_get_config_manager, mock_get_data_access):
        """Test local storage with partial batch failure."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = 90
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock data access with partial failure
        mock_data_access = Mock()
        mock_data_access.store_batch_sensor_data.return_value = (1, 1)  # 1 successful, 1 failed
        mock_get_data_access.return_value = mock_data_access
        
        # Test storage
        ruuvi_request = self.create_test_request()
        
        success = store_sensor_data_locally(
            ruuvi_request, None, "test-correlation-123"
        )
        
        # Should still return True if at least some data was stored
        assert success is True
    
    @patch('proxy.index.get_sensor_data_access')
    @patch('proxy.index.get_config_manager')
    def test_store_sensor_data_locally_complete_failure(self, mock_get_config_manager, mock_get_data_access):
        """Test local storage with complete batch failure."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = 90
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock data access with complete failure
        mock_data_access = Mock()
        mock_data_access.store_batch_sensor_data.return_value = (0, 2)  # 0 successful, 2 failed
        mock_get_data_access.return_value = mock_data_access
        
        # Test storage
        ruuvi_request = self.create_test_request()
        
        success = store_sensor_data_locally(
            ruuvi_request, None, "test-correlation-123"
        )
        
        # Should return False if no data was stored
        assert success is False
    
    @patch('proxy.index.get_sensor_data_access')
    def test_store_sensor_data_locally_exception_handling(self, mock_get_data_access):
        """Test exception handling in local storage."""
        # Mock data access to raise exception
        mock_get_data_access.side_effect = Exception("DynamoDB connection failed")
        
        # Test storage
        ruuvi_request = self.create_test_request()
        
        success = store_sensor_data_locally(
            ruuvi_request, None, "test-correlation-123"
        )
        
        # Should return False on exception
        assert success is False
    
    @patch.dict(os.environ, {
        'DATA_TABLE_NAME': 'custom-sensor-data',
        'CONFIG_TABLE_NAME': 'custom-config'
    })
    @patch('proxy.index.get_sensor_data_access')
    @patch('proxy.index.get_config_manager')
    def test_custom_table_names(self, mock_get_config_manager, mock_get_data_access):
        """Test that custom table names from environment are used."""
        # Mock managers
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = 90
        mock_get_config_manager.return_value = mock_config_manager
        
        mock_data_access = Mock()
        mock_data_access.store_batch_sensor_data.return_value = (2, 0)
        mock_get_data_access.return_value = mock_data_access
        
        # Test storage
        ruuvi_request = self.create_test_request()
        store_sensor_data_locally(ruuvi_request, None, "test-correlation-123")
        
        # Verify custom table names were used
        mock_get_data_access.assert_called_once_with('custom-sensor-data')
        mock_get_config_manager.assert_called_once_with('custom-config')


class TestIntegratedStorage:
    """Test storage logic integrated with Lambda handler."""
    
    def create_valid_event(self):
        """Create a valid API Gateway event for testing."""
        current_timestamp = int(time.time())
        request_data = {
            "data": {
                "coordinates": "60.1699,24.9384",
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "AABBCCDDEEFF": {
                        "rssi": -65,
                        "timestamp": current_timestamp,
                        "data": "dGVzdERhdGE="
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
    
    @patch('proxy.index.get_sensor_data_access')
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    def test_lambda_handler_with_storage_and_forwarding(self, mock_client_class, mock_get_config_manager, mock_get_data_access):
        """Test Lambda handler with both storage and forwarding enabled."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25,
            'data_retention_days': 90
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock successful Ruuvi Cloud response
        mock_client = Mock()
        mock_client.send_sensor_data.return_value = (True, {
            "result": "success",
            "data": {"action": "inserted", "received": 1}
        })
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Mock successful data storage
        mock_data_access = Mock()
        mock_data_access.store_batch_sensor_data.return_value = (1, 0)
        mock_get_data_access.return_value = mock_data_access
        
        # Test Lambda handler
        event = self.create_valid_event()
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 200
        
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["received"] == 1  # From Ruuvi Cloud response
        
        # Verify both forwarding and storage were called
        mock_client.send_sensor_data.assert_called_once()
        mock_data_access.store_batch_sensor_data.assert_called_once()
    
    @patch('proxy.index.get_sensor_data_access')
    @patch('proxy.index.get_config_manager')
    def test_lambda_handler_storage_only(self, mock_get_config_manager, mock_get_data_access):
        """Test Lambda handler with only local storage (forwarding disabled)."""
        # Mock configuration manager with forwarding disabled
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': False,
            'data_retention_days': 90
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock successful data storage
        mock_data_access = Mock()
        mock_data_access.store_batch_sensor_data.return_value = (1, 0)
        mock_get_data_access.return_value = mock_data_access
        
        # Test Lambda handler
        event = self.create_valid_event()
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 200
        
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
        
        # Verify storage was called
        mock_data_access.store_batch_sensor_data.assert_called_once()
        
        # Verify sensor data was stored without Ruuvi Cloud response
        call_args = mock_data_access.store_batch_sensor_data.call_args
        sensor_data_list = call_args[0][0]
        assert len(sensor_data_list) == 1
        assert 'ruuvi_cloud_response' not in sensor_data_list[0]
    
    @patch('proxy.index.get_sensor_data_access')
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    def test_lambda_handler_forwarding_fails_storage_succeeds(self, mock_client_class, mock_get_config_manager, mock_get_data_access):
        """Test Lambda handler when forwarding fails but storage succeeds."""
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25,
            'data_retention_days': 90
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock failed Ruuvi Cloud response
        mock_client = Mock()
        mock_client.send_sensor_data.return_value = (False, {
            "result": "error",
            "error": {"code": "TIMEOUT_ERROR", "message": "Request timeout"}
        })
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Mock successful data storage
        mock_data_access = Mock()
        mock_data_access.store_batch_sensor_data.return_value = (1, 0)
        mock_get_data_access.return_value = mock_data_access
        
        # Test Lambda handler
        event = self.create_valid_event()
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        # Should still return 200 with local success response
        assert response["statusCode"] == 200
        
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
        
        # Verify both forwarding and storage were attempted (TIMEOUT_ERROR is retryable, so 4 attempts)
        assert mock_client.send_sensor_data.call_count == 4  # 1 initial + 3 retries
        mock_data_access.store_batch_sensor_data.assert_called_once()
        
        # Verify sensor data was stored without Ruuvi Cloud response
        call_args = mock_data_access.store_batch_sensor_data.call_args
        sensor_data_list = call_args[0][0]
        assert 'ruuvi_cloud_response' not in sensor_data_list[0]


if __name__ == "__main__":
    pytest.main([__file__])