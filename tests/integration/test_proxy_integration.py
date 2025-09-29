"""
Integration tests for proxy functionality (Task 9.1).

Tests cover:
- End-to-end tests for proxy with mock Ruuvi Cloud API
- Test forwarding enabled and disabled scenarios
- Verify Ruuvi Cloud API compatibility with actual request/response formats
- Test error handling when Ruuvi Cloud is unavailable
"""

import json
import pytest
import responses
import time
from unittest.mock import patch, MagicMock
import base64
from datetime import datetime

# Import the proxy function and dependencies
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from proxy.index import lambda_handler
from shared.models import RuuviGatewayRequest


class TestProxyIntegration:
    """Integration tests for proxy functionality."""
    
    def create_valid_ruuvi_request(self, device_count=1):
        """Create a valid Ruuvi Gateway request."""
        current_timestamp = int(time.time())
        tags = {}
        
        for i in range(device_count):
            device_id = f"AABBCCDDEEF{i:01X}"
            tags[device_id] = {
                "rssi": -65 - i,
                "timestamp": current_timestamp,
                "data": base64.b64encode(f"test_data_{i}".encode()).decode()
            }
        
        return {
            "data": {
                "coordinates": "60.1699,24.9384",
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": tags
            }
        }
    
    def create_api_gateway_event(self, request_data):
        """Create API Gateway event for testing."""
        return {
            "body": json.dumps(request_data),
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}"
            },
            "httpMethod": "POST",
            "path": "/api/v1/data",
            "headers": {
                "Content-Type": "application/json",
                "X-Api-Key": "test-api-key"
            },
            "isBase64Encoded": False
        }
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-proxy-function"
        context.function_version = "1"
        context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-proxy-function"
        context.memory_limit_in_mb = 512
        context.remaining_time_in_millis = lambda: 30000
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context


class TestForwardingEnabledScenarios:
    """Test proxy behavior when forwarding is enabled."""
    
    def create_valid_ruuvi_request(self, device_count=1):
        """Create a valid Ruuvi Gateway request."""
        current_timestamp = int(time.time())
        tags = {}
        
        for i in range(device_count):
            device_id = f"AABBCCDDEEF{i:01X}"
            tags[device_id] = {
                "rssi": -65 - i,
                "timestamp": current_timestamp,
                "data": base64.b64encode(f"test_data_{i}".encode()).decode()
            }
        
        return {
            "data": {
                "coordinates": "60.1699,24.9384",
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": tags
            }
        }
    
    def create_api_gateway_event(self, request_data):
        """Create API Gateway event for testing."""
        return {
            "body": json.dumps(request_data),
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}"
            },
            "httpMethod": "POST",
            "path": "/api/v1/data",
            "headers": {
                "Content-Type": "application/json",
                "X-Api-Key": "test-api-key"
            },
            "isBase64Encoded": False
        }
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-proxy-function"
        context.function_version = "1"
        context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-proxy-function"
        context.memory_limit_in_mb = 512
        context.remaining_time_in_millis = lambda: 30000
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    @responses.activate
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    def test_successful_forwarding_with_local_storage(self, mock_data_access, mock_config_manager):
        """Test successful forwarding to Ruuvi Cloud with local storage."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25,
            'data_retention_days': 90
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.return_value = (1, 0)  # 1 success, 0 failures
        mock_data_access.return_value = mock_data_access_instance
        
        # Mock successful Ruuvi Cloud response
        ruuvi_cloud_response = {
            "result": "success",
            "data": {"action": "inserted"}
        }
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/record",
            json=ruuvi_cloud_response,
            status=200
        )
        
        # Create test request
        request_data = self.create_valid_ruuvi_request()
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Execute proxy function
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        assert "X-Correlation-ID" in response["headers"]
        
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
        
        # Verify Ruuvi Cloud was called
        assert len(responses.calls) == 1
        ruuvi_request = json.loads(responses.calls[0].request.body)
        assert ruuvi_request["data"]["gwmac"] == "AA:BB:CC:DD:EE:FF"
        assert "AABBCCDDEEF0" in ruuvi_request["data"]["tags"]
        
        # Verify local storage was called
        mock_data_access_instance.store_batch_sensor_data.assert_called_once()
        stored_data, ttl_days = mock_data_access_instance.store_batch_sensor_data.call_args[0]
        assert len(stored_data) == 1
        assert stored_data[0]["device_id"] == "AABBCCDDEEF0"
        assert stored_data[0]["gateway_id"] == "AA:BB:CC:DD:EE:FF"
        assert "ruuvi_cloud_response" in stored_data[0]
        assert ttl_days == 90
    
    @responses.activate
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    def test_multiple_devices_forwarding(self, mock_data_access, mock_config_manager):
        """Test forwarding with multiple devices."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25,
            'data_retention_days': 90
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.return_value = (3, 0)  # 3 success, 0 failures
        mock_data_access.return_value = mock_data_access_instance
        
        # Mock successful Ruuvi Cloud response
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/record",
            json={"result": "success", "data": {"action": "inserted"}},
            status=200
        )
        
        # Create test request with 3 devices
        request_data = self.create_valid_ruuvi_request(device_count=3)
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Execute proxy function
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        
        # Verify all devices were sent to Ruuvi Cloud
        ruuvi_request = json.loads(responses.calls[0].request.body)
        assert len(ruuvi_request["data"]["tags"]) == 3
        assert "AABBCCDDEEF0" in ruuvi_request["data"]["tags"]
        assert "AABBCCDDEEF1" in ruuvi_request["data"]["tags"]
        assert "AABBCCDDEEF2" in ruuvi_request["data"]["tags"]
        
        # Verify all devices were stored locally
        stored_data, _ = mock_data_access_instance.store_batch_sensor_data.call_args[0]
        assert len(stored_data) == 3
        device_ids = [item["device_id"] for item in stored_data]
        assert "AABBCCDDEEF0" in device_ids
        assert "AABBCCDDEEF1" in device_ids
        assert "AABBCCDDEEF2" in device_ids
    
    @responses.activate
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    def test_ruuvi_cloud_api_compatibility(self, mock_data_access, mock_config_manager):
        """Test exact compatibility with Ruuvi Cloud Gateway API format."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25,
            'data_retention_days': 90
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.return_value = (1, 0)
        mock_data_access.return_value = mock_data_access_instance
        
        # Mock Ruuvi Cloud response with exact format from documentation
        ruuvi_cloud_response = {
            "result": "success",
            "data": {
                "action": "inserted"
            }
        }
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/record",
            json=ruuvi_cloud_response,
            status=200
        )
        
        # Create request with exact format from Ruuvi Cloud documentation
        current_timestamp = int(time.time())
        request_data = {
            "data": {
                "coordinates": "",  # Empty coordinates as in documentation
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "device_id_1": {  # Using device_id_1 as in documentation
                        "rssi": -65,
                        "timestamp": current_timestamp,
                        "data": "base64_encoded_sensor_data"
                    }
                }
            }
        }
        
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Execute proxy function
        response = lambda_handler(event, context)
        
        # Verify response format matches Ruuvi Cloud exactly
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body == ruuvi_cloud_response
        
        # Verify request sent to Ruuvi Cloud preserves original format
        assert len(responses.calls) == 1
        sent_request = json.loads(responses.calls[0].request.body)
        assert sent_request == request_data
        
        # Verify headers
        request_headers = responses.calls[0].request.headers
        assert request_headers["Content-Type"] == "application/json"
        assert request_headers["User-Agent"] == "RuuviAPIProxy/1.0"


class TestForwardingDisabledScenarios:
    """Test proxy behavior when forwarding is disabled."""
    
    def create_valid_ruuvi_request(self):
        """Create a valid Ruuvi Gateway request."""
        current_timestamp = int(time.time())
        return {
            "data": {
                "coordinates": "60.1699,24.9384",
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "AABBCCDDEEF0": {
                        "rssi": -65,
                        "timestamp": current_timestamp,
                        "data": base64.b64encode(b"test_data").decode()
                    }
                }
            }
        }
    
    def create_api_gateway_event(self, request_data):
        """Create API Gateway event for testing."""
        return {
            "body": json.dumps(request_data),
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}"
            },
            "httpMethod": "POST",
            "path": "/api/v1/data",
            "headers": {
                "Content-Type": "application/json",
                "X-Api-Key": "test-api-key"
            },
            "isBase64Encoded": False
        }
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-proxy-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    @responses.activate
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    def test_forwarding_disabled_local_storage_only(self, mock_data_access, mock_config_manager):
        """Test that data is stored locally when forwarding is disabled."""
        # Setup mocks - forwarding disabled
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': False,  # Forwarding disabled
            'data_retention_days': 90
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.return_value = (1, 0)
        mock_data_access.return_value = mock_data_access_instance
        
        # Create test request
        request_data = self.create_valid_ruuvi_request()
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Execute proxy function
        response = lambda_handler(event, context)
        
        # Verify response - should return local success
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
        
        # Verify NO calls were made to Ruuvi Cloud
        assert len(responses.calls) == 0
        
        # Verify local storage was still called
        mock_data_access_instance.store_batch_sensor_data.assert_called_once()
        stored_data, ttl_days = mock_data_access_instance.store_batch_sensor_data.call_args[0]
        assert len(stored_data) == 1
        assert stored_data[0]["device_id"] == "AABBCCDDEEF0"
        # Should NOT have ruuvi_cloud_response since forwarding was disabled
        assert "ruuvi_cloud_response" not in stored_data[0]
    
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    def test_forwarding_disabled_configuration_check(self, mock_data_access, mock_config_manager):
        """Test that configuration is properly checked when forwarding is disabled."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': False,
            'data_retention_days': 30
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.return_value = (1, 0)
        mock_data_access.return_value = mock_data_access_instance
        
        # Create test request
        request_data = self.create_valid_ruuvi_request()
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Execute proxy function
        response = lambda_handler(event, context)
        
        # Verify configuration was checked
        mock_config.get_config.assert_any_call('forwarding_enabled', default=True)
        mock_config.get_config.assert_any_call('data_retention_days', default=90)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"


class TestErrorHandlingScenarios:
    """Test error handling when Ruuvi Cloud is unavailable."""
    
    def create_valid_ruuvi_request(self):
        """Create a valid Ruuvi Gateway request."""
        current_timestamp = int(time.time())
        return {
            "data": {
                "coordinates": "60.1699,24.9384",
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "AABBCCDDEEF0": {
                        "rssi": -65,
                        "timestamp": current_timestamp,
                        "data": base64.b64encode(b"test_data").decode()
                    }
                }
            }
        }
    
    def create_api_gateway_event(self, request_data):
        """Create API Gateway event for testing."""
        return {
            "body": json.dumps(request_data),
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}"
            },
            "httpMethod": "POST",
            "path": "/api/v1/data",
            "headers": {
                "Content-Type": "application/json",
                "X-Api-Key": "test-api-key"
            },
            "isBase64Encoded": False
        }
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-proxy-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    @responses.activate
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    def test_ruuvi_cloud_http_error_fallback(self, mock_data_access, mock_config_manager):
        """Test fallback to local success when Ruuvi Cloud returns HTTP error."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25,
            'data_retention_days': 90
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.return_value = (1, 0)
        mock_data_access.return_value = mock_data_access_instance
        
        # Mock Ruuvi Cloud HTTP error
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/record",
            json={"error": "Internal Server Error"},
            status=500
        )
        
        # Create test request
        request_data = self.create_valid_ruuvi_request()
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Execute proxy function
        response = lambda_handler(event, context)
        
        # Should still return success (fallback to local success)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
        
        # Verify Ruuvi Cloud was attempted
        assert len(responses.calls) == 1
        
        # Verify local storage still occurred
        mock_data_access_instance.store_batch_sensor_data.assert_called_once()
        stored_data, _ = mock_data_access_instance.store_batch_sensor_data.call_args[0]
        # Should NOT have ruuvi_cloud_response since forwarding failed
        assert "ruuvi_cloud_response" not in stored_data[0]
    
    @responses.activate
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    def test_ruuvi_cloud_timeout_fallback(self, mock_data_access, mock_config_manager):
        """Test fallback when Ruuvi Cloud request times out."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 1,  # Very short timeout
            'data_retention_days': 90
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.return_value = (1, 0)
        mock_data_access.return_value = mock_data_access_instance
        
        # Mock slow Ruuvi Cloud response (will timeout)
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/record",
            json={"result": "success"},
            status=200
        )
        
        # Create test request
        request_data = self.create_valid_ruuvi_request()
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Mock timeout in RuuviCloudClient
        with patch('proxy.index.RuuviCloudClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.send_sensor_data.return_value = (False, {
                "result": "error",
                "error": {
                    "code": "TIMEOUT_ERROR",
                    "message": "Request timeout after 1 seconds"
                }
            })
            mock_client_class.return_value = mock_client
            
            # Execute proxy function
            response = lambda_handler(event, context)
        
        # Should still return success (fallback to local success)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
        
        # Verify local storage still occurred
        mock_data_access_instance.store_batch_sensor_data.assert_called_once()
    
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    def test_circuit_breaker_open_scenario(self, mock_data_access, mock_config_manager):
        """Test behavior when circuit breaker is open."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25,
            'data_retention_days': 90
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.return_value = (1, 0)
        mock_data_access.return_value = mock_data_access_instance
        
        # Create test request
        request_data = self.create_valid_ruuvi_request()
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Mock circuit breaker in OPEN state
        with patch('proxy.index.ruuvi_cloud_circuit_breaker') as mock_circuit_breaker:
            mock_circuit_breaker.can_execute.return_value = False
            mock_circuit_breaker.state = 'OPEN'
            mock_circuit_breaker.failure_count = 5
            
            # Execute proxy function
            response = lambda_handler(event, context)
        
        # Should still return success (fallback to local success)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
        
        # Verify local storage still occurred
        mock_data_access_instance.store_batch_sensor_data.assert_called_once()
    
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    def test_local_storage_failure_handling(self, mock_data_access, mock_config_manager):
        """Test handling when local storage fails."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': False,  # Disable forwarding to focus on storage
            'data_retention_days': 90
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        # Mock storage failure
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.side_effect = Exception("DynamoDB error")
        mock_data_access.return_value = mock_data_access_instance
        
        # Create test request
        request_data = self.create_valid_ruuvi_request()
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Execute proxy function
        response = lambda_handler(event, context)
        
        # Should still return success even if storage fails
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"


class TestRetryLogicScenarios:
    """Test retry logic for transient failures."""
    
    def create_valid_ruuvi_request(self):
        """Create a valid Ruuvi Gateway request."""
        current_timestamp = int(time.time())
        return {
            "data": {
                "coordinates": "60.1699,24.9384",
                "timestamp": current_timestamp,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "AABBCCDDEEF0": {
                        "rssi": -65,
                        "timestamp": current_timestamp,
                        "data": base64.b64encode(b"test_data").decode()
                    }
                }
            }
        }
    
    def create_api_gateway_event(self, request_data):
        """Create API Gateway event for testing."""
        return {
            "body": json.dumps(request_data),
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}"
            },
            "httpMethod": "POST",
            "path": "/api/v1/data",
            "headers": {
                "Content-Type": "application/json",
                "X-Api-Key": "test-api-key"
            },
            "isBase64Encoded": False
        }
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-proxy-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.get_sensor_data_access')
    @patch('time.sleep')  # Mock sleep to speed up tests
    def test_retry_logic_eventual_success(self, mock_sleep, mock_data_access, mock_config_manager):
        """Test that retry logic eventually succeeds after transient failures."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25,
            'data_retention_days': 90
        }.get(key, default)
        mock_config_manager.return_value = mock_config
        
        mock_data_access_instance = MagicMock()
        mock_data_access_instance.store_batch_sensor_data.return_value = (1, 0)
        mock_data_access.return_value = mock_data_access_instance
        
        # Create test request
        request_data = self.create_valid_ruuvi_request()
        event = self.create_api_gateway_event(request_data)
        context = self.create_lambda_context()
        
        # Mock RuuviCloudClient with retry behavior
        with patch('proxy.index.RuuviCloudClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            
            # First two attempts fail with retryable errors, third succeeds
            mock_client.send_sensor_data.side_effect = [
                (False, {"result": "error", "error": {"code": "HTTP_503", "message": "Service Unavailable"}}),
                (False, {"result": "error", "error": {"code": "TIMEOUT_ERROR", "message": "Timeout"}}),
                (True, {"result": "success", "data": {"action": "inserted"}})
            ]
            mock_client_class.return_value = mock_client
            
            # Execute proxy function
            response = lambda_handler(event, context)
        
        # Should return success after retries
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
        
        # Verify retry attempts were made
        assert mock_client.send_sensor_data.call_count == 3
        
        # Verify sleep was called for backoff
        assert mock_sleep.call_count == 2  # Two retries, so two sleeps


if __name__ == "__main__":
    pytest.main([__file__, "-v"])