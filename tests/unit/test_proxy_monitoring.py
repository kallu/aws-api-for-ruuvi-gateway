"""
Unit tests for proxy error handling and monitoring (Task 4.4).

Tests the circuit breaker pattern, retry logic, structured error responses,
and CloudWatch metrics functionality.
"""

import json
import pytest
import time
from unittest.mock import patch, MagicMock, Mock
import os

# Import the proxy function
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from proxy.index import (
    CircuitBreaker, 
    publish_cloudwatch_metric,
    handle_ruuvi_cloud_forwarding,
    lambda_handler,
    ruuvi_cloud_circuit_breaker
)
from shared.models import RuuviGatewayRequest


class TestCircuitBreaker:
    """Test circuit breaker pattern implementation."""
    
    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker initial state."""
        cb = CircuitBreaker()
        assert cb.state == 'CLOSED'
        assert cb.failure_count == 0
        assert cb.can_execute() is True
    
    def test_circuit_breaker_failure_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        cb = CircuitBreaker(failure_threshold=3)
        
        # Record failures below threshold
        cb.record_failure()
        assert cb.state == 'CLOSED'
        assert cb.can_execute() is True
        
        cb.record_failure()
        assert cb.state == 'CLOSED'
        assert cb.can_execute() is True
        
        # Record failure that reaches threshold
        cb.record_failure()
        assert cb.state == 'OPEN'
        assert cb.can_execute() is False
    
    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery after timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == 'OPEN'
        assert cb.can_execute() is False
        
        # Wait for recovery timeout
        time.sleep(1.1)
        assert cb.can_execute() is True
        assert cb.state == 'HALF_OPEN'
        
        # Successful execution should close the circuit
        cb.record_success()
        assert cb.state == 'CLOSED'
        assert cb.failure_count == 0
    
    def test_circuit_breaker_half_open_failure(self):
        """Test circuit breaker behavior when half-open execution fails."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == 'OPEN'
        
        # Wait for recovery and check if execution is allowed
        time.sleep(1.1)
        assert cb.can_execute() is True  # This should transition to HALF_OPEN
        assert cb.state == 'HALF_OPEN'
        
        # Failure in half-open state should reopen circuit
        cb.record_failure()
        assert cb.state == 'OPEN'
        assert cb.can_execute() is False


class TestCloudWatchMetrics:
    """Test CloudWatch metrics functionality."""
    
    @patch('proxy.index.get_cloudwatch_client')
    def test_publish_cloudwatch_metric_success(self, mock_get_cloudwatch_client):
        """Test successful CloudWatch metric publishing."""
        mock_cloudwatch = Mock()
        mock_cloudwatch.put_metric_data.return_value = {}
        mock_get_cloudwatch_client.return_value = mock_cloudwatch
        
        publish_cloudwatch_metric(
            'TestMetric', 1.0, 'Count',
            {'Service': 'Test'}, 'test-correlation-123'
        )
        
        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        
        assert call_args[1]['Namespace'] == 'RuuviAPI/Proxy'
        assert len(call_args[1]['MetricData']) == 1
        
        metric_data = call_args[1]['MetricData'][0]
        assert metric_data['MetricName'] == 'TestMetric'
        assert metric_data['Value'] == 1.0
        assert metric_data['Unit'] == 'Count'
        assert len(metric_data['Dimensions']) == 1
        assert metric_data['Dimensions'][0]['Name'] == 'Service'
        assert metric_data['Dimensions'][0]['Value'] == 'Test'
    
    @patch('proxy.index.get_cloudwatch_client')
    def test_publish_cloudwatch_metric_without_dimensions(self, mock_get_cloudwatch_client):
        """Test CloudWatch metric publishing without dimensions."""
        mock_cloudwatch = Mock()
        mock_cloudwatch.put_metric_data.return_value = {}
        mock_get_cloudwatch_client.return_value = mock_cloudwatch
        
        publish_cloudwatch_metric('SimpleMetric', 5.0, 'Milliseconds')
        
        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        
        metric_data = call_args[1]['MetricData'][0]
        assert metric_data['MetricName'] == 'SimpleMetric'
        assert metric_data['Value'] == 5.0
        assert metric_data['Unit'] == 'Milliseconds'
        assert 'Dimensions' not in metric_data
    
    @patch('proxy.index.get_cloudwatch_client')
    def test_publish_cloudwatch_metric_exception_handling(self, mock_get_cloudwatch_client):
        """Test CloudWatch metric publishing exception handling."""
        mock_cloudwatch = Mock()
        mock_cloudwatch.put_metric_data.side_effect = Exception("CloudWatch error")
        mock_get_cloudwatch_client.return_value = mock_cloudwatch
        
        # Should not raise exception
        publish_cloudwatch_metric('TestMetric', 1.0, 'Count')
        
        mock_cloudwatch.put_metric_data.assert_called_once()
    
    @patch.dict(os.environ, {'CLOUDWATCH_NAMESPACE': 'CustomNamespace'})
    @patch('proxy.index.get_cloudwatch_client')
    def test_custom_cloudwatch_namespace(self, mock_get_cloudwatch_client):
        """Test custom CloudWatch namespace from environment."""
        mock_cloudwatch = Mock()
        mock_cloudwatch.put_metric_data.return_value = {}
        mock_get_cloudwatch_client.return_value = mock_cloudwatch
        
        publish_cloudwatch_metric('TestMetric', 1.0, 'Count')
        
        call_args = mock_cloudwatch.put_metric_data.call_args
        assert call_args[1]['Namespace'] == 'CustomNamespace'
    
    @patch('proxy.index.get_cloudwatch_client')
    def test_publish_cloudwatch_metric_no_client(self, mock_get_cloudwatch_client):
        """Test CloudWatch metric publishing when client is not available."""
        mock_get_cloudwatch_client.return_value = None
        
        # Should not raise exception
        publish_cloudwatch_metric('TestMetric', 1.0, 'Count')
        
        # Should not attempt to publish
        mock_get_cloudwatch_client.assert_called_once()


class TestEnhancedForwarding:
    """Test enhanced forwarding with circuit breaker and retry logic."""
    
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
    
    def setUp(self):
        """Reset circuit breaker state before each test."""
        ruuvi_cloud_circuit_breaker.state = 'CLOSED'
        ruuvi_cloud_circuit_breaker.failure_count = 0
        ruuvi_cloud_circuit_breaker.last_failure_time = None
    
    @patch('proxy.index.publish_cloudwatch_metric')
    @patch('proxy.index.get_config_manager')
    def test_circuit_breaker_open_blocks_forwarding(self, mock_get_config_manager, mock_publish_metric):
        """Test that open circuit breaker blocks forwarding attempts."""
        self.setUp()
        
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Open the circuit breaker
        ruuvi_cloud_circuit_breaker.state = 'OPEN'
        ruuvi_cloud_circuit_breaker.failure_count = 5
        ruuvi_cloud_circuit_breaker.last_failure_time = time.time()
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        assert success is False
        assert was_forwarded is True
        assert response["result"] == "error"
        assert response["error"]["code"] == "CIRCUIT_BREAKER_OPEN"
        
        # Verify circuit breaker metric was published
        mock_publish_metric.assert_called_with(
            'CircuitBreakerOpen', 1, 'Count',
            {'Service': 'RuuviCloud'}, "test-correlation-123"
        )
    
    @patch('proxy.index.publish_cloudwatch_metric')
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    @patch('proxy.index.time.sleep')  # Mock sleep to speed up tests
    def test_retry_logic_with_retryable_errors(self, mock_sleep, mock_client_class, mock_get_config_manager, mock_publish_metric):
        """Test retry logic for retryable errors."""
        self.setUp()
        
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock Ruuvi Cloud client with retryable error then success
        mock_client = Mock()
        mock_client.send_sensor_data.side_effect = [
            (False, {"result": "error", "error": {"code": "TIMEOUT_ERROR", "message": "Timeout"}}),
            (True, {"result": "success", "data": {"action": "inserted"}})
        ]
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        assert success is True
        assert was_forwarded is True
        assert response["result"] == "success"
        
        # Verify retry was attempted
        assert mock_client.send_sensor_data.call_count == 2
        mock_sleep.assert_called_once_with(1)  # First retry delay
        
        # Verify success metric was published
        mock_publish_metric.assert_any_call(
            'ForwardingSuccess', 1, 'Count',
            {'Service': 'RuuviCloud', 'Attempt': '2'}, "test-correlation-123"
        )
    
    @patch('proxy.index.publish_cloudwatch_metric')
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    @patch('proxy.index.time.sleep')
    def test_retry_logic_exhausted(self, mock_sleep, mock_client_class, mock_get_config_manager, mock_publish_metric):
        """Test retry logic when all attempts are exhausted."""
        self.setUp()
        
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock Ruuvi Cloud client with consistent retryable errors
        mock_client = Mock()
        mock_client.send_sensor_data.return_value = (
            False, {"result": "error", "error": {"code": "TIMEOUT_ERROR", "message": "Timeout"}}
        )
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        assert success is False
        assert was_forwarded is True
        assert response["result"] == "error"
        assert response["error"]["code"] == "TIMEOUT_ERROR"
        
        # Verify all retry attempts were made (4 total: initial + 3 retries)
        assert mock_client.send_sensor_data.call_count == 4
        assert mock_sleep.call_count == 3  # 3 retry delays
        
        # Verify failure metric was published
        mock_publish_metric.assert_any_call(
            'ForwardingFailure', 1, 'Count',
            {'Service': 'RuuviCloud', 'ErrorCode': 'TIMEOUT_ERROR', 'Attempt': '4'}, 
            "test-correlation-123"
        )
    
    @patch('proxy.index.publish_cloudwatch_metric')
    @patch('proxy.index.get_config_manager')
    @patch('proxy.index.RuuviCloudClient')
    def test_non_retryable_error_no_retry(self, mock_client_class, mock_get_config_manager, mock_publish_metric):
        """Test that non-retryable errors don't trigger retries."""
        self.setUp()
        
        # Mock configuration manager
        mock_config_manager = Mock()
        mock_config_manager.get_config.side_effect = lambda key, default=None: {
            'forwarding_enabled': True,
            'ruuvi_cloud_endpoint': 'https://network.ruuvi.com',
            'ruuvi_cloud_timeout': 25
        }.get(key, default)
        mock_get_config_manager.return_value = mock_config_manager
        
        # Mock Ruuvi Cloud client with non-retryable error
        mock_client = Mock()
        mock_client.send_sensor_data.return_value = (
            False, {"result": "error", "error": {"code": "VALIDATION_ERROR", "message": "Invalid data"}}
        )
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Test forwarding
        ruuvi_request = self.create_test_request()
        success, response, was_forwarded = handle_ruuvi_cloud_forwarding(ruuvi_request, "test-correlation-123")
        
        assert success is False
        assert was_forwarded is True
        assert response["result"] == "error"
        assert response["error"]["code"] == "VALIDATION_ERROR"
        
        # Verify no retry was attempted
        assert mock_client.send_sensor_data.call_count == 1
        
        # Verify failure metric was published
        mock_publish_metric.assert_any_call(
            'ForwardingFailure', 1, 'Count',
            {'Service': 'RuuviCloud', 'ErrorCode': 'VALIDATION_ERROR', 'Attempt': '1'}, 
            "test-correlation-123"
        )


class TestLambdaHandlerMonitoring:
    """Test Lambda handler monitoring and metrics."""
    
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
    
    @patch('proxy.index.publish_cloudwatch_metric')
    @patch('proxy.index.get_sensor_data_access')
    @patch('proxy.index.get_config_manager')
    def test_lambda_handler_success_metrics(self, mock_get_config_manager, mock_get_data_access, mock_publish_metric):
        """Test that success metrics are published correctly."""
        # Mock configuration manager
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
        
        # Verify success metrics were published (check if any call matches the pattern)
        success_calls = [call for call in mock_publish_metric.call_args_list 
                        if call[0][0] == 'RequestSuccess']
        assert len(success_calls) > 0
        
        device_count_calls = [call for call in mock_publish_metric.call_args_list 
                             if call[0][0] == 'DeviceCount']
        assert len(device_count_calls) > 0
        
        # Verify processing time metric was published
        processing_time_calls = [call for call in mock_publish_metric.call_args_list 
                               if call[0][0] == 'ProcessingTime']
        assert len(processing_time_calls) > 0
    
    @patch('proxy.index.publish_cloudwatch_metric')
    def test_lambda_handler_validation_error_metrics(self, mock_publish_metric):
        """Test that validation error metrics are published correctly."""
        # Create invalid event
        event = {
            "body": "invalid json {",
            "requestContext": {
                "requestId": "test-request-123"
            },
            "httpMethod": "POST",
            "path": "/api/v1/data"
        }
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 400
        
        # Verify validation error metrics were published
        validation_error_calls = [call for call in mock_publish_metric.call_args_list 
                                 if call[0][0] == 'ValidationError']
        assert len(validation_error_calls) > 0


if __name__ == "__main__":
    pytest.main([__file__])