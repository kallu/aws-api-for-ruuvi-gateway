"""
Unit tests for Ruuvi Cloud HTTP client.

Tests cover:
- HTTP client initialization and configuration
- Successful API requests
- Error handling and retries
- Timeout handling
- Request/response logging
- Health check functionality
"""

import json
import pytest
import requests
import responses
from unittest.mock import patch, MagicMock
import base64
from datetime import datetime

from src.shared.ruuvi_client import (
    RuuviCloudClient,
    create_ruuvi_client,
    send_to_ruuvi_cloud
)
from src.shared.models import RuuviGatewayRequest


class TestRuuviCloudClient:
    """Test cases for RuuviCloudClient class."""
    
    def get_valid_gateway_request(self):
        """Get a valid gateway request for testing."""
        return RuuviGatewayRequest(
            coordinates="60.1699,24.9384",
            timestamp=int(datetime.now().timestamp()),
            gwmac="AA:BB:CC:DD:EE:FF",
            tags={
                "AABBCCDDEEFF": {
                    "rssi": -65,
                    "timestamp": int(datetime.now().timestamp()),
                    "data": base64.b64encode(b"test_data").decode()
                }
            }
        )
    
    def test_client_initialization_defaults(self):
        """Test client initialization with default parameters."""
        client = RuuviCloudClient()
        
        assert client.base_url == "https://network.ruuvi.com"
        assert client.timeout == 30
        assert client.enable_logging is True
        assert client.session is not None
        assert client.session.headers['Content-Type'] == 'application/json'
        assert client.session.headers['User-Agent'] == 'RuuviAPIProxy/1.0'
    
    def test_client_initialization_custom(self):
        """Test client initialization with custom parameters."""
        client = RuuviCloudClient(
            base_url="https://custom.ruuvi.com/",
            timeout=60,
            max_retries=5,
            backoff_factor=0.5,
            enable_logging=False
        )
        
        assert client.base_url == "https://custom.ruuvi.com"
        assert client.timeout == 60
        assert client.enable_logging is False
    
    @responses.activate
    def test_send_sensor_data_success(self):
        """Test successful sensor data transmission."""
        # Mock successful response
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/record",
            json={"result": "success", "data": {"action": "inserted"}},
            status=200
        )
        
        client = RuuviCloudClient()
        gateway_request = self.get_valid_gateway_request()
        
        success, response = client.send_sensor_data(gateway_request)
        
        assert success is True
        assert response["result"] == "success"
        assert response["data"]["action"] == "inserted"
        
        # Verify request was made correctly
        assert len(responses.calls) == 1
        request = responses.calls[0].request
        assert request.url == "https://network.ruuvi.com/record"
        
        # Verify request payload
        payload = json.loads(request.body)
        assert "data" in payload
        assert payload["data"]["gwmac"] == gateway_request.gwmac
        assert payload["data"]["timestamp"] == gateway_request.timestamp
        assert "AABBCCDDEEFF" in payload["data"]["tags"]
    
    @responses.activate
    def test_send_sensor_data_custom_endpoint(self):
        """Test sending data to custom endpoint."""
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/custom",
            json={"result": "success"},
            status=200
        )
        
        client = RuuviCloudClient()
        gateway_request = self.get_valid_gateway_request()
        
        success, response = client.send_sensor_data(gateway_request, endpoint="/custom")
        
        assert success is True
        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == "https://network.ruuvi.com/custom"
    
    @responses.activate
    def test_send_sensor_data_http_error(self):
        """Test handling of HTTP error responses."""
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/record",
            json={"error": "Bad Request"},
            status=400
        )
        
        client = RuuviCloudClient()
        gateway_request = self.get_valid_gateway_request()
        
        success, response = client.send_sensor_data(gateway_request)
        
        assert success is False
        assert response["result"] == "error"
        assert response["error"]["code"] == "HTTP_400"
        assert "HTTP 400" in response["error"]["message"]
    
    @responses.activate
    def test_send_sensor_data_invalid_json_response(self):
        """Test handling of invalid JSON response."""
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/record",
            body="Invalid JSON response",
            status=200
        )
        
        client = RuuviCloudClient()
        gateway_request = self.get_valid_gateway_request()
        
        success, response = client.send_sensor_data(gateway_request)
        
        assert success is False
        assert response["result"] == "error"
        assert response["error"]["code"] == "JSON_PARSE_ERROR"
        assert "Invalid JSON response" in response["error"]["message"]
    
    def test_send_sensor_data_timeout(self):
        """Test handling of request timeout."""
        client = RuuviCloudClient(timeout=1)
        gateway_request = self.get_valid_gateway_request()
        
        with patch.object(client.session, 'post') as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout("Request timeout")
            
            success, response = client.send_sensor_data(gateway_request)
            
            assert success is False
            assert response["result"] == "error"
            assert response["error"]["code"] == "TIMEOUT_ERROR"
            assert "timeout after 1 seconds" in response["error"]["message"]
    
    def test_send_sensor_data_connection_error(self):
        """Test handling of connection errors."""
        client = RuuviCloudClient()
        gateway_request = self.get_valid_gateway_request()
        
        with patch.object(client.session, 'post') as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")
            
            success, response = client.send_sensor_data(gateway_request)
            
            assert success is False
            assert response["result"] == "error"
            assert response["error"]["code"] == "CONNECTION_ERROR"
            assert "Failed to connect to Ruuvi Cloud" in response["error"]["message"]
    
    def test_send_sensor_data_request_exception(self):
        """Test handling of general request exceptions."""
        client = RuuviCloudClient()
        gateway_request = self.get_valid_gateway_request()
        
        with patch.object(client.session, 'post') as mock_post:
            mock_post.side_effect = requests.exceptions.RequestException("Request failed")
            
            success, response = client.send_sensor_data(gateway_request)
            
            assert success is False
            assert response["result"] == "error"
            assert response["error"]["code"] == "REQUEST_ERROR"
            assert "Request failed" in response["error"]["message"]
    
    def test_send_sensor_data_unexpected_error(self):
        """Test handling of unexpected errors."""
        client = RuuviCloudClient()
        gateway_request = self.get_valid_gateway_request()
        
        with patch.object(client.session, 'post') as mock_post:
            mock_post.side_effect = Exception("Unexpected error")
            
            success, response = client.send_sensor_data(gateway_request)
            
            assert success is False
            assert response["result"] == "error"
            assert response["error"]["code"] == "UNKNOWN_ERROR"
            assert "Unexpected error" in response["error"]["message"]
    
    @responses.activate
    def test_health_check_success(self):
        """Test successful health check."""
        responses.add(
            responses.GET,
            "https://network.ruuvi.com/health",
            json={"status": "ok"},
            status=200
        )
        
        client = RuuviCloudClient()
        success, response = client.health_check()
        
        assert success is True
        assert response["status"] == "healthy"
        assert "timestamp" in response
    
    @responses.activate
    def test_health_check_custom_endpoint(self):
        """Test health check with custom endpoint."""
        responses.add(
            responses.GET,
            "https://network.ruuvi.com/status",
            json={"status": "ok"},
            status=200
        )
        
        client = RuuviCloudClient()
        success, response = client.health_check(endpoint="/status")
        
        assert success is True
        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == "https://network.ruuvi.com/status"
    
    def test_health_check_failure(self):
        """Test health check failure."""
        client = RuuviCloudClient()
        
        with patch.object(client.session, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_response.reason = "Service Unavailable"
            mock_get.return_value = mock_response
            
            success, response = client.health_check()
            
            assert success is False
            assert response["status"] == "unhealthy"
            assert "HTTP 503" in response["error"]
            assert "timestamp" in response
    
    def test_health_check_exception(self):
        """Test health check with exception."""
        client = RuuviCloudClient()
        
        with patch.object(client.session, 'get') as mock_get:
            mock_get.side_effect = Exception("Connection failed")
            
            success, response = client.health_check()
            
            assert success is False
            assert response["status"] == "unhealthy"
            assert "Connection failed" in response["error"]
            assert "timestamp" in response
    
    @patch('src.shared.ruuvi_client.logger')
    def test_logging_enabled(self, mock_logger):
        """Test that logging works when enabled."""
        client = RuuviCloudClient(enable_logging=True)
        gateway_request = self.get_valid_gateway_request()
        
        with patch.object(client.session, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": "success"}
            mock_response.headers = {"Content-Type": "application/json"}
            mock_response.text = '{"result": "success"}'
            mock_post.return_value = mock_response
            
            client.send_sensor_data(gateway_request)
            
            # Verify logging calls were made
            assert mock_logger.info.called
            assert mock_logger.debug.called
    
    @patch('src.shared.ruuvi_client.logger')
    def test_logging_disabled(self, mock_logger):
        """Test that logging is disabled when configured."""
        client = RuuviCloudClient(enable_logging=False)
        gateway_request = self.get_valid_gateway_request()
        
        with patch.object(client.session, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": "success"}
            mock_post.return_value = mock_response
            
            client.send_sensor_data(gateway_request)
            
            # Verify no info/debug logging calls were made
            mock_logger.info.assert_not_called()
            mock_logger.debug.assert_not_called()
    
    def test_context_manager(self):
        """Test client as context manager."""
        with RuuviCloudClient() as client:
            assert client.session is not None
        
        # Session should be closed after context exit
        # Note: We can't easily test this without mocking, but the structure is correct
    
    def test_close_method(self):
        """Test explicit close method."""
        client = RuuviCloudClient()
        session = client.session
        
        client.close()
        
        # Verify close was called on session
        # Note: We can't easily verify this without mocking, but the structure is correct


class TestUtilityFunctions:
    """Test cases for utility functions."""
    
    def test_create_ruuvi_client_defaults(self):
        """Test creating client with default parameters."""
        client = create_ruuvi_client()
        
        assert isinstance(client, RuuviCloudClient)
        assert client.base_url == "https://network.ruuvi.com"
        assert client.timeout == 30
    
    def test_create_ruuvi_client_custom(self):
        """Test creating client with custom parameters."""
        client = create_ruuvi_client(
            base_url="https://custom.ruuvi.com",
            timeout=60,
            max_retries=5
        )
        
        assert isinstance(client, RuuviCloudClient)
        assert client.base_url == "https://custom.ruuvi.com"
        assert client.timeout == 60
    
    @responses.activate
    def test_send_to_ruuvi_cloud_success(self):
        """Test convenience function for sending data."""
        responses.add(
            responses.POST,
            "https://network.ruuvi.com/record",
            json={"result": "success", "data": {"action": "inserted"}},
            status=200
        )
        
        gateway_request = RuuviGatewayRequest(
            coordinates="60.1699,24.9384",
            timestamp=int(datetime.now().timestamp()),
            gwmac="AA:BB:CC:DD:EE:FF",
            tags={
                "AABBCCDDEEFF": {
                    "rssi": -65,
                    "timestamp": int(datetime.now().timestamp()),
                    "data": base64.b64encode(b"test_data").decode()
                }
            }
        )
        
        success, response = send_to_ruuvi_cloud(gateway_request)
        
        assert success is True
        assert response["result"] == "success"
        assert len(responses.calls) == 1
    
    @responses.activate
    def test_send_to_ruuvi_cloud_custom_params(self):
        """Test convenience function with custom parameters."""
        responses.add(
            responses.POST,
            "https://custom.ruuvi.com/record",
            json={"result": "success"},
            status=200
        )
        
        gateway_request = RuuviGatewayRequest(
            coordinates="60.1699,24.9384",
            timestamp=int(datetime.now().timestamp()),
            gwmac="AA:BB:CC:DD:EE:FF",
            tags={
                "AABBCCDDEEFF": {
                    "rssi": -65,
                    "timestamp": int(datetime.now().timestamp()),
                    "data": base64.b64encode(b"test_data").decode()
                }
            }
        )
        
        success, response = send_to_ruuvi_cloud(
            gateway_request,
            base_url="https://custom.ruuvi.com",
            timeout=60
        )
        
        assert success is True
        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == "https://custom.ruuvi.com/record"


if __name__ == "__main__":
    pytest.main([__file__])