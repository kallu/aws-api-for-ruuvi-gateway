"""
Unit tests for basic proxy function structure (Task 4.1).

Tests the Lambda handler's event parsing, request validation, 
structured logging, and error handling framework.
"""

import json
import pytest
import uuid
from unittest.mock import patch, MagicMock
import base64

# Import the proxy function
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from proxy.index import (
    lambda_handler,
    parse_api_gateway_event,
    create_api_gateway_response,
    handle_validation_error,
    handle_internal_error,
    create_correlation_id
)

class TestBasicProxyStructure:
    """Test basic proxy function structure and event handling."""
    
    def test_create_correlation_id(self):
        """Test correlation ID generation."""
        correlation_id = create_correlation_id()
        assert isinstance(correlation_id, str)
        assert len(correlation_id) == 36  # UUID4 format
        
        # Ensure uniqueness
        correlation_id2 = create_correlation_id()
        assert correlation_id != correlation_id2
    
    def test_parse_api_gateway_event_valid(self):
        """Test parsing valid API Gateway event."""
        import time
        current_timestamp = int(time.time())
        test_data = {
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
        
        event = {
            "body": json.dumps(test_data),
            "requestContext": {
                "requestId": "test-request-123"
            },
            "isBase64Encoded": False
        }
        
        request_data, request_id, correlation_id = parse_api_gateway_event(event)
        
        assert request_data == test_data
        assert request_id == "test-request-123"
        assert isinstance(correlation_id, str)
        assert len(correlation_id) == 36
    
    def test_parse_api_gateway_event_base64_encoded(self):
        """Test parsing base64 encoded API Gateway event."""
        import time
        current_timestamp = int(time.time())
        test_data = {
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
        
        json_body = json.dumps(test_data)
        encoded_body = base64.b64encode(json_body.encode('utf-8')).decode('utf-8')
        
        event = {
            "body": encoded_body,
            "requestContext": {
                "requestId": "test-request-123"
            },
            "isBase64Encoded": True
        }
        
        request_data, request_id, correlation_id = parse_api_gateway_event(event)
        
        assert request_data == test_data
        assert request_id == "test-request-123"
    
    def test_parse_api_gateway_event_no_body(self):
        """Test parsing event with no body."""
        event = {
            "requestContext": {
                "requestId": "test-request-123"
            }
        }
        
        with pytest.raises(ValueError, match="Request body is required"):
            parse_api_gateway_event(event)
    
    def test_parse_api_gateway_event_invalid_json(self):
        """Test parsing event with invalid JSON."""
        event = {
            "body": "invalid json {",
            "requestContext": {
                "requestId": "test-request-123"
            }
        }
        
        with pytest.raises(ValueError, match="Invalid JSON in request body"):
            parse_api_gateway_event(event)
    
    def test_create_api_gateway_response(self):
        """Test API Gateway response creation."""
        body = {"result": "success", "data": {"action": "inserted"}}
        correlation_id = "test-correlation-123"
        
        response = create_api_gateway_response(200, body, correlation_id)
        
        assert response["statusCode"] == 200
        assert response["headers"]["Content-Type"] == "application/json"
        assert response["headers"]["X-Correlation-ID"] == correlation_id
        assert "Access-Control-Allow-Origin" in response["headers"]
        assert json.loads(response["body"]) == body
    
    def test_create_api_gateway_response_no_correlation_id(self):
        """Test API Gateway response creation without correlation ID."""
        body = {"result": "error"}
        
        response = create_api_gateway_response(400, body)
        
        assert response["statusCode"] == 400
        assert "X-Correlation-ID" not in response["headers"]
        assert json.loads(response["body"]) == body
    
    def test_handle_validation_error(self):
        """Test validation error handling."""
        error_message = "Invalid request format"
        correlation_id = "test-correlation-123"
        
        response = handle_validation_error(error_message, correlation_id)
        
        assert response["statusCode"] == 400
        assert response["headers"]["X-Correlation-ID"] == correlation_id
        
        body = json.loads(response["body"])
        assert body["result"] == "error"
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["message"] == error_message
    
    def test_handle_internal_error(self):
        """Test internal error handling."""
        test_error = ValueError("Test error")
        correlation_id = "test-correlation-123"
        
        response = handle_internal_error(test_error, correlation_id)
        
        assert response["statusCode"] == 500
        assert response["headers"]["X-Correlation-ID"] == correlation_id
        
        body = json.loads(response["body"])
        assert body["result"] == "error"
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert body["error"]["message"] == "Internal server error"

class TestLambdaHandler:
    """Test the main Lambda handler function."""
    
    def create_valid_event(self, request_data=None):
        """Create a valid API Gateway event for testing."""
        if request_data is None:
            import time
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
    
    def test_lambda_handler_valid_request(self):
        """Test Lambda handler with valid request."""
        event = self.create_valid_event()
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 200
        assert "X-Correlation-ID" in response["headers"]
        
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["action"] == "inserted"
    
    def test_lambda_handler_invalid_request_format(self):
        """Test Lambda handler with invalid request format."""
        invalid_data = {"invalid": "format"}
        event = self.create_valid_event(invalid_data)
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 400
        
        body = json.loads(response["body"])
        assert body["result"] == "error"
        assert body["error"]["code"] == "VALIDATION_ERROR"
    
    def test_lambda_handler_missing_required_fields(self):
        """Test Lambda handler with missing required fields."""
        import time
        current_timestamp = int(time.time())
        invalid_data = {
            "data": {
                "timestamp": current_timestamp,
                # Missing gwmac and tags
            }
        }
        event = self.create_valid_event(invalid_data)
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 400
        
        body = json.loads(response["body"])
        assert body["result"] == "error"
        assert body["error"]["code"] == "VALIDATION_ERROR"
    
    def test_lambda_handler_invalid_mac_address(self):
        """Test Lambda handler with invalid MAC address."""
        import time
        current_timestamp = int(time.time())
        invalid_data = {
            "data": {
                "coordinates": "",
                "timestamp": current_timestamp,
                "gwmac": "invalid-mac",
                "tags": {
                    "AABBCCDDEEFF": {
                        "rssi": -65,
                        "timestamp": current_timestamp,
                        "data": "dGVzdA=="
                    }
                }
            }
        }
        event = self.create_valid_event(invalid_data)
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 400
        
        body = json.loads(response["body"])
        assert body["result"] == "error"
        assert body["error"]["code"] == "VALIDATION_ERROR"
    
    def test_lambda_handler_no_body(self):
        """Test Lambda handler with no request body."""
        event = {
            "requestContext": {
                "requestId": "test-request-123"
            },
            "httpMethod": "POST",
            "path": "/api/v1/data"
        }
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 400
        
        body = json.loads(response["body"])
        assert body["result"] == "error"
        assert body["error"]["code"] == "VALIDATION_ERROR"
    
    def test_lambda_handler_invalid_json(self):
        """Test Lambda handler with invalid JSON body."""
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
        
        body = json.loads(response["body"])
        assert body["result"] == "error"
        assert body["error"]["code"] == "VALIDATION_ERROR"
    
    @patch('proxy.index.logger')
    def test_lambda_handler_logging(self, mock_logger):
        """Test that proper logging occurs during request processing."""
        event = self.create_valid_event()
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 200
        
        # Verify logging calls were made
        assert mock_logger.info.called
        
        # Check that correlation ID was included in log calls
        log_calls = mock_logger.info.call_args_list
        assert any('correlation_id' in str(call) for call in log_calls)
    
    def test_lambda_handler_correlation_id_consistency(self):
        """Test that correlation ID is consistent across response."""
        event = self.create_valid_event()
        context = MagicMock()
        
        response = lambda_handler(event, context)
        
        assert response["statusCode"] == 200
        correlation_id = response["headers"]["X-Correlation-ID"]
        assert isinstance(correlation_id, str)
        assert len(correlation_id) == 36  # UUID4 format

if __name__ == "__main__":
    pytest.main([__file__])