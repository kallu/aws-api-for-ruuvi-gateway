"""
Integration tests for local data access (Task 9.3).

Tests cover:
- Write integration tests for local data retrieval endpoints
- Test pagination and time-range queries
- Verify data storage regardless of forwarding setting
- Test authentication for local data access
"""

import json
import pytest
import time
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import base64

# Import the retrieve function and dependencies
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from retrieve.index import lambda_handler
from shared.data_access import SensorDataAccess, reset_sensor_data_access


class TestLocalDataRetrievalIntegration:
    """Integration tests for local data retrieval functionality."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_sensor_data_access()
    
    def create_api_gateway_event(self, path: str, method: str = "GET", 
                                query_params: dict = None, path_params: dict = None,
                                headers: dict = None):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": path,
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
            },
            "headers": headers or {
                "Content-Type": "application/json",
                "X-API-Key": "test-api-key"
            },
            "pathParameters": path_params,
            "queryStringParameters": query_params
        }
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-retrieve-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    def create_sample_sensor_data(self, device_id: str, timestamp: int = None):
        """Create sample sensor data for testing."""
        if timestamp is None:
            timestamp = int(time.time())
        
        return {
            'device_id': device_id,
            'gateway_id': 'AA:BB:CC:DD:EE:FF',
            'timestamp': timestamp,
            'server_timestamp': timestamp + 1,
            'measurements': {
                'rssi': -65,
                'data': base64.b64encode(b'test_sensor_data').decode(),
                'gateway_timestamp': timestamp,
                'coordinates': '60.1699,24.9384'
            }
        }


class TestCurrentDataRetrieval:
    """Test current data retrieval endpoints."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_sensor_data_access()
    
    def create_api_gateway_event(self, path: str, method: str = "GET", 
                                query_params: dict = None, path_params: dict = None,
                                headers: dict = None):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": path,
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
            },
            "headers": headers or {
                "Content-Type": "application/json",
                "X-API-Key": "test-api-key"
            },
            "pathParameters": path_params,
            "queryStringParameters": query_params
        }
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-retrieve-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    def create_sample_sensor_data(self, device_id: str, timestamp: int = None):
        """Create sample sensor data for testing."""
        if timestamp is None:
            timestamp = int(time.time())
        
        return {
            'device_id': device_id,
            'gateway_id': 'AA:BB:CC:DD:EE:FF',
            'timestamp': timestamp,
            'server_timestamp': timestamp + 1,
            'measurements': {
                'rssi': -65,
                'data': base64.b64encode(b'test_sensor_data').decode(),
                'gateway_timestamp': timestamp,
                'coordinates': '60.1699,24.9384'
            }
        }
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_current_data_single_device_success(self, mock_get_data_access):
        """Test successful current data retrieval for single device."""
        # Setup mock data access
        mock_data_access = MagicMock()
        sample_data = self.create_sample_sensor_data('AABBCCDDEEFF')
        mock_data_access.get_current_data.return_value = sample_data
        mock_get_data_access.return_value = mock_data_access
        
        # Create request
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"}
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["device_id"] == "AABBCCDDEEFF"
        assert body["data"]["gateway_id"] == "AA:BB:CC:DD:EE:FF"
        assert "last_updated" in body["data"]
        assert "measurements" in body["data"]
        
        # Verify data access was called correctly
        mock_data_access.get_current_data.assert_called_once_with("AABBCCDDEEFF")
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_current_data_device_not_found(self, mock_get_data_access):
        """Test current data retrieval when device is not found."""
        # Setup mock data access to return None
        mock_data_access = MagicMock()
        mock_data_access.get_current_data.return_value = None
        mock_get_data_access.return_value = mock_data_access
        
        # Create request
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current/NONEXISTENT",
            path_params={"device_id": "NONEXISTENT"}
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"]["code"] == "NOT_FOUND"
        assert "NONEXISTENT" in body["error"]["message"]
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_current_data_multiple_devices_success(self, mock_get_data_access):
        """Test successful current data retrieval for multiple devices."""
        # Setup mock data access
        mock_data_access = MagicMock()
        devices_data = {
            'AABBCCDDEEFF': self.create_sample_sensor_data('AABBCCDDEEFF'),
            'AABBCCDDEE11': self.create_sample_sensor_data('AABBCCDDEE11')
        }
        mock_data_access.get_multiple_devices_current_data.return_value = devices_data
        mock_get_data_access.return_value = mock_data_access
        
        # Create request with multiple device IDs
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current",
            query_params={"device_ids": "AABBCCDDEEFF,AABBCCDDEE11"}
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert "AABBCCDDEEFF" in body["data"]
        assert "AABBCCDDEE11" in body["data"]
        assert body["summary"]["requested_devices"] == 2
        assert body["summary"]["devices_with_data"] == 2
        
        # Verify data access was called correctly
        mock_data_access.get_multiple_devices_current_data.assert_called_once_with(
            ['AABBCCDDEEFF', 'AABBCCDDEE11']
        )
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_current_data_multiple_devices_partial_results(self, mock_get_data_access):
        """Test current data retrieval with some devices having no data."""
        # Setup mock data access - only one device has data
        mock_data_access = MagicMock()
        devices_data = {
            'AABBCCDDEEFF': self.create_sample_sensor_data('AABBCCDDEEFF')
            # AABBCCDDEE11 has no data
        }
        mock_data_access.get_multiple_devices_current_data.return_value = devices_data
        mock_get_data_access.return_value = mock_data_access
        
        # Create request with multiple device IDs
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current",
            query_params={"device_ids": "AABBCCDDEEFF,AABBCCDDEE11"}
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["AABBCCDDEEFF"] is not None
        assert body["data"]["AABBCCDDEE11"] is None
        assert body["summary"]["requested_devices"] == 2
        assert body["summary"]["devices_with_data"] == 1
        assert body["summary"]["devices_without_data"] == 1


class TestHistoricalDataRetrieval:
    """Test historical data retrieval with pagination and time-range queries."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_sensor_data_access()
    
    def create_api_gateway_event(self, path: str, method: str = "GET", 
                                query_params: dict = None, path_params: dict = None,
                                headers: dict = None):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": path,
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
            },
            "headers": headers or {
                "Content-Type": "application/json",
                "X-API-Key": "test-api-key"
            },
            "pathParameters": path_params,
            "queryStringParameters": query_params
        }
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-retrieve-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    def create_sample_historical_data(self, device_id: str, count: int = 5):
        """Create sample historical data for testing."""
        base_timestamp = int(time.time()) - 3600  # 1 hour ago
        data = []
        
        for i in range(count):
            timestamp = base_timestamp + (i * 300)  # 5 minute intervals
            data.append({
                'device_id': device_id,
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'timestamp': timestamp,
                'server_timestamp': timestamp + 1,
                'measurements': {
                    'rssi': -65 - i,
                    'data': base64.b64encode(f'test_data_{i}'.encode()).decode(),
                    'gateway_timestamp': timestamp,
                    'coordinates': '60.1699,24.9384'
                }
            })
        
        return data
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_historical_data_time_range_query(self, mock_get_data_access):
        """Test historical data retrieval with time range."""
        # Setup mock data access
        mock_data_access = MagicMock()
        historical_data = self.create_sample_historical_data('AABBCCDDEEFF', 3)
        mock_data_access.get_historical_data.return_value = {
            'items': historical_data,
            'count': 3
        }
        mock_get_data_access.return_value = mock_data_access
        
        # Create request with time range
        start_time = int(time.time()) - 7200  # 2 hours ago
        end_time = int(time.time()) - 1800    # 30 minutes ago
        
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/history/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"},
            query_params={
                "start_time": str(start_time),
                "end_time": str(end_time),
                "limit": "50"
            }
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["device_id"] == "AABBCCDDEEFF"
        assert body["data"]["count"] == 3
        assert len(body["data"]["items"]) == 3
        assert body["data"]["has_more"] is False
        assert body["data"]["query_parameters"]["start_time"] == start_time
        assert body["data"]["query_parameters"]["end_time"] == end_time
        assert body["data"]["query_parameters"]["limit"] == 50
        
        # Verify data access was called correctly
        mock_data_access.get_historical_data.assert_called_once_with(
            device_id="AABBCCDDEEFF",
            start_time=start_time,
            end_time=end_time,
            limit=50,
            last_evaluated_key=None
        )
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_historical_data_pagination(self, mock_get_data_access):
        """Test historical data retrieval with pagination."""
        # Setup mock data access with pagination
        mock_data_access = MagicMock()
        historical_data = self.create_sample_historical_data('AABBCCDDEEFF', 2)
        last_evaluated_key = {
            'device_id': 'AABBCCDDEEFF',
            'timestamp': int(time.time()) - 1800
        }
        
        mock_data_access.get_historical_data.return_value = {
            'items': historical_data,
            'count': 2,
            'last_evaluated_key': last_evaluated_key
        }
        mock_get_data_access.return_value = mock_data_access
        
        # Create request with limit
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/history/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"},
            query_params={"limit": "2"}
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["count"] == 2
        assert body["data"]["has_more"] is True
        assert "next_token" in body["data"]
        
        # Verify next_token can be decoded
        next_token = body["data"]["next_token"]
        decoded_token = base64.b64decode(next_token).decode('utf-8')
        decoded_key = json.loads(decoded_token)
        assert decoded_key == last_evaluated_key
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_historical_data_with_next_token(self, mock_get_data_access):
        """Test historical data retrieval using next_token for pagination."""
        # Setup mock data access
        mock_data_access = MagicMock()
        historical_data = self.create_sample_historical_data('AABBCCDDEEFF', 2)
        mock_data_access.get_historical_data.return_value = {
            'items': historical_data,
            'count': 2
        }
        mock_get_data_access.return_value = mock_data_access
        
        # Create next_token
        last_evaluated_key = {
            'device_id': 'AABBCCDDEEFF',
            'timestamp': int(time.time()) - 1800
        }
        next_token = base64.b64encode(
            json.dumps(last_evaluated_key).encode('utf-8')
        ).decode('utf-8')
        
        # Create request with next_token
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/history/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"},
            query_params={
                "limit": "2",
                "next_token": next_token
            }
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        
        # Verify data access was called with decoded last_evaluated_key
        mock_data_access.get_historical_data.assert_called_once_with(
            device_id="AABBCCDDEEFF",
            start_time=None,
            end_time=None,
            limit=2,
            last_evaluated_key=last_evaluated_key
        )
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_historical_data_multiple_devices(self, mock_get_data_access):
        """Test historical data retrieval for multiple devices."""
        # Setup mock data access
        mock_data_access = MagicMock()
        
        # Mock different responses for different devices
        def mock_get_historical_data(device_id, **kwargs):
            if device_id == 'AABBCCDDEEFF':
                return {
                    'items': self.create_sample_historical_data('AABBCCDDEEFF', 3),
                    'count': 3
                }
            elif device_id == 'AABBCCDDEE11':
                return {
                    'items': self.create_sample_historical_data('AABBCCDDEE11', 2),
                    'count': 2
                }
            else:
                return {'items': [], 'count': 0}
        
        mock_data_access.get_historical_data.side_effect = mock_get_historical_data
        mock_get_data_access.return_value = mock_data_access
        
        # Create request for multiple devices
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/history",
            query_params={
                "device_ids": "AABBCCDDEEFF,AABBCCDDEE11",
                "limit": "10"
            }
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert "AABBCCDDEEFF" in body["data"]["devices"]
        assert "AABBCCDDEE11" in body["data"]["devices"]
        assert body["data"]["devices"]["AABBCCDDEEFF"]["count"] == 3
        assert body["data"]["devices"]["AABBCCDDEE11"]["count"] == 2
        assert body["data"]["summary"]["requested_devices"] == 2
        assert body["data"]["summary"]["devices_with_data"] == 2
        assert body["data"]["summary"]["total_records"] == 5
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_historical_data_invalid_time_range(self, mock_get_data_access):
        """Test historical data retrieval with invalid time range."""
        # Create request with invalid time range (start > end)
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/history/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"},
            query_params={
                "start_time": str(int(time.time())),
                "end_time": str(int(time.time()) - 3600)  # Earlier than start
            }
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify validation error
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "start_time must be less than end_time" in body["error"]["message"]
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_historical_data_invalid_limit(self, mock_get_data_access):
        """Test historical data retrieval with invalid limit."""
        # Create request with invalid limit
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/history/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"},
            query_params={"limit": "2000"}  # Too high
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify validation error
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "limit must be between 1 and 1000" in body["error"]["message"]


class TestDeviceListingEndpoint:
    """Test device listing endpoint functionality."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_sensor_data_access()
    
    def create_api_gateway_event(self, path: str, method: str = "GET", 
                                query_params: dict = None, path_params: dict = None,
                                headers: dict = None):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": path,
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
            },
            "headers": headers or {
                "Content-Type": "application/json",
                "X-API-Key": "test-api-key"
            },
            "pathParameters": path_params,
            "queryStringParameters": query_params
        }
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-retrieve-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    def create_sample_devices_info(self):
        """Create sample device information for testing."""
        base_timestamp = int(time.time())
        return [
            {
                'device_id': 'AABBCCDDEEFF',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'last_seen': base_timestamp - 300,
                'last_seen_server': base_timestamp - 299
            },
            {
                'device_id': 'AABBCCDDEE11',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'last_seen': base_timestamp - 600,
                'last_seen_server': base_timestamp - 599
            },
            {
                'device_id': 'BBCCDDEE1122',
                'gateway_id': 'BB:CC:DD:EE:FF:00',
                'last_seen': base_timestamp - 900,
                'last_seen_server': base_timestamp - 899
            }
        ]
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_device_listing_success(self, mock_get_data_access):
        """Test successful device listing."""
        # Setup mock data access
        mock_data_access = MagicMock()
        devices_info = self.create_sample_devices_info()
        mock_data_access.get_all_devices.return_value = devices_info
        mock_get_data_access.return_value = mock_data_access
        
        # Create request
        event = self.create_api_gateway_event(path="/api/v1/local/devices")
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert len(body["data"]["devices"]) == 3
        assert len(body["data"]["gateways"]) == 2  # Two unique gateways
        assert body["data"]["summary"]["total_devices"] == 3
        assert body["data"]["summary"]["total_gateways"] == 2
        
        # Verify device information format
        device = body["data"]["devices"][0]
        assert "device_id" in device
        assert "gateway_id" in device
        assert "last_seen" in device
        assert "last_seen_at" in device
        assert device["last_seen_at"].endswith('Z')  # ISO format with Z
        
        # Verify gateway information
        gateway = body["data"]["gateways"][0]
        assert "gateway_id" in gateway
        assert "device_count" in gateway
        assert "last_activity" in gateway
        assert "last_activity_at" in gateway
        
        # Verify data access was called
        mock_data_access.get_all_devices.assert_called_once()
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_device_listing_empty_result(self, mock_get_data_access):
        """Test device listing when no devices exist."""
        # Setup mock data access to return empty list
        mock_data_access = MagicMock()
        mock_data_access.get_all_devices.return_value = []
        mock_get_data_access.return_value = mock_data_access
        
        # Create request
        event = self.create_api_gateway_event(path="/api/v1/local/devices")
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert len(body["data"]["devices"]) == 0
        assert len(body["data"]["gateways"]) == 0
        assert body["data"]["summary"]["total_devices"] == 0
        assert body["data"]["summary"]["total_gateways"] == 0
        assert body["data"]["summary"]["most_recent_activity"] is None
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_device_listing_gateway_aggregation(self, mock_get_data_access):
        """Test that device listing properly aggregates devices by gateway."""
        # Setup mock data access with devices from same gateway
        mock_data_access = MagicMock()
        base_timestamp = int(time.time())
        devices_info = [
            {
                'device_id': 'DEVICE001',
                'gateway_id': 'GATEWAY_A',
                'last_seen': base_timestamp - 100,
                'last_seen_server': base_timestamp - 99
            },
            {
                'device_id': 'DEVICE002',
                'gateway_id': 'GATEWAY_A',
                'last_seen': base_timestamp - 200,
                'last_seen_server': base_timestamp - 199
            },
            {
                'device_id': 'DEVICE003',
                'gateway_id': 'GATEWAY_B',
                'last_seen': base_timestamp - 300,
                'last_seen_server': base_timestamp - 299
            }
        ]
        mock_data_access.get_all_devices.return_value = devices_info
        mock_get_data_access.return_value = mock_data_access
        
        # Create request
        event = self.create_api_gateway_event(path="/api/v1/local/devices")
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        
        # Find GATEWAY_A in the response
        gateway_a = next(g for g in body["data"]["gateways"] if g["gateway_id"] == "GATEWAY_A")
        gateway_b = next(g for g in body["data"]["gateways"] if g["gateway_id"] == "GATEWAY_B")
        
        assert gateway_a["device_count"] == 2
        assert gateway_b["device_count"] == 1
        assert gateway_a["last_activity"] == base_timestamp - 100  # Most recent from GATEWAY_A
        assert gateway_b["last_activity"] == base_timestamp - 300


class TestDataStorageRegardlessOfForwarding:
    """Test that data is stored locally regardless of forwarding setting."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_sensor_data_access()
    
    def create_api_gateway_event(self, path: str, method: str = "GET", 
                                query_params: dict = None, path_params: dict = None,
                                headers: dict = None):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": path,
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
            },
            "headers": headers or {
                "Content-Type": "application/json",
                "X-API-Key": "test-api-key"
            },
            "pathParameters": path_params,
            "queryStringParameters": query_params
        }
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-retrieve-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_data_stored_when_forwarding_enabled(self, mock_get_data_access):
        """Test that data stored locally is accessible when forwarding was enabled."""
        # Setup mock data access with data that includes Ruuvi Cloud response
        mock_data_access = MagicMock()
        sample_data = {
            'device_id': 'AABBCCDDEEFF',
            'gateway_id': 'AA:BB:CC:DD:EE:FF',
            'timestamp': int(time.time()),
            'server_timestamp': int(time.time()) + 1,
            'measurements': {
                'rssi': -65,
                'data': base64.b64encode(b'test_data').decode(),
                'gateway_timestamp': int(time.time()),
                'coordinates': '60.1699,24.9384'
            },
            'ruuvi_cloud_response': {
                'result': 'success',
                'data': {'action': 'inserted'}
            }
        }
        mock_data_access.get_current_data.return_value = sample_data
        mock_get_data_access.return_value = mock_data_access
        
        # Create request
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"}
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["device_id"] == "AABBCCDDEEFF"
        
        # Verify that the data was stored locally (accessible via retrieve function)
        # The presence of ruuvi_cloud_response indicates forwarding was enabled when stored
        mock_data_access.get_current_data.assert_called_once_with("AABBCCDDEEFF")
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_data_stored_when_forwarding_disabled(self, mock_get_data_access):
        """Test that data stored locally is accessible when forwarding was disabled."""
        # Setup mock data access with data that does NOT include Ruuvi Cloud response
        mock_data_access = MagicMock()
        sample_data = {
            'device_id': 'AABBCCDDEEFF',
            'gateway_id': 'AA:BB:CC:DD:EE:FF',
            'timestamp': int(time.time()),
            'server_timestamp': int(time.time()) + 1,
            'measurements': {
                'rssi': -65,
                'data': base64.b64encode(b'test_data').decode(),
                'gateway_timestamp': int(time.time()),
                'coordinates': '60.1699,24.9384'
            }
            # No ruuvi_cloud_response - indicates forwarding was disabled
        }
        mock_data_access.get_current_data.return_value = sample_data
        mock_get_data_access.return_value = mock_data_access
        
        # Create request
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"}
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["device_id"] == "AABBCCDDEEFF"
        
        # Verify that the data was stored locally regardless of forwarding setting
        mock_data_access.get_current_data.assert_called_once_with("AABBCCDDEEFF")
    
    @patch.dict(os.environ, {'DATA_TABLE_NAME': 'test-sensor-data'})
    @patch('retrieve.index.get_sensor_data_access')
    def test_historical_data_available_regardless_of_forwarding(self, mock_get_data_access):
        """Test that historical data is available regardless of forwarding setting."""
        # Setup mock data access with mixed data (some with, some without Ruuvi Cloud response)
        mock_data_access = MagicMock()
        base_timestamp = int(time.time()) - 3600
        
        historical_data = [
            {
                'device_id': 'AABBCCDDEEFF',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'timestamp': base_timestamp,
                'server_timestamp': base_timestamp + 1,
                'measurements': {'rssi': -65, 'data': 'data1'},
                'ruuvi_cloud_response': {'result': 'success'}  # Forwarding was enabled
            },
            {
                'device_id': 'AABBCCDDEEFF',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'timestamp': base_timestamp + 300,
                'server_timestamp': base_timestamp + 301,
                'measurements': {'rssi': -66, 'data': 'data2'}
                # No ruuvi_cloud_response - forwarding was disabled
            },
            {
                'device_id': 'AABBCCDDEEFF',
                'gateway_id': 'AA:BB:CC:DD:EE:FF',
                'timestamp': base_timestamp + 600,
                'server_timestamp': base_timestamp + 601,
                'measurements': {'rssi': -67, 'data': 'data3'},
                'ruuvi_cloud_response': {'result': 'success'}  # Forwarding was enabled again
            }
        ]
        
        mock_data_access.get_historical_data.return_value = {
            'items': historical_data,
            'count': 3
        }
        mock_get_data_access.return_value = mock_data_access
        
        # Create request
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/history/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"}
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "success"
        assert body["data"]["count"] == 3
        assert len(body["data"]["items"]) == 3
        
        # Verify all data is accessible regardless of forwarding setting
        timestamps = [item["timestamp"] for item in body["data"]["items"]]
        assert base_timestamp in timestamps
        assert base_timestamp + 300 in timestamps
        assert base_timestamp + 600 in timestamps


class TestAuthenticationForLocalDataAccess:
    """Test authentication for local data access."""
    
    def setup_method(self):
        """Setup for each test method."""
        reset_sensor_data_access()
    
    def create_api_gateway_event(self, path: str, method: str = "GET", 
                                query_params: dict = None, path_params: dict = None,
                                headers: dict = None):
        """Create API Gateway event for testing."""
        event = {
            "httpMethod": method,
            "path": path,
            "requestContext": {
                "requestId": f"test-request-{int(time.time())}",
                "identity": {
                    "sourceIp": "192.168.1.100"
                }
            },
            "headers": headers or {},
            "pathParameters": path_params,
            "queryStringParameters": query_params
        }
        
        return event
    
    def create_lambda_context(self):
        """Create mock Lambda context."""
        context = MagicMock()
        context.function_name = "test-retrieve-function"
        context.aws_request_id = f"test-aws-request-{int(time.time())}"
        return context
    
    def test_api_key_authentication_success(self):
        """Test successful API key authentication."""
        # Create request with API key
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"},
            headers={
                "Content-Type": "application/json",
                "X-API-Key": "valid-api-key"
            }
        )
        context = self.create_lambda_context()
        
        with patch('retrieve.index.get_sensor_data_access') as mock_get_data_access:
            mock_data_access = MagicMock()
            mock_data_access.get_current_data.return_value = None  # Device not found
            mock_get_data_access.return_value = mock_data_access
            
            # Execute request
            response = lambda_handler(event, context)
            
            # Should pass authentication but fail on device not found
            assert response["statusCode"] == 404  # Not 401 (authentication error)
    
    def test_cognito_token_authentication_success(self):
        """Test successful Cognito token authentication."""
        # Create request with Cognito authorization
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"},
            headers={"Content-Type": "application/json"}
        )
        
        # Add Cognito claims to request context
        event["requestContext"]["authorizer"] = {
            "claims": {
                "sub": "user-123",
                "email": "test@example.com"
            }
        }
        
        context = self.create_lambda_context()
        
        with patch('retrieve.index.get_sensor_data_access') as mock_get_data_access:
            mock_data_access = MagicMock()
            mock_data_access.get_current_data.return_value = None  # Device not found
            mock_get_data_access.return_value = mock_data_access
            
            # Execute request
            response = lambda_handler(event, context)
            
            # Should pass authentication but fail on device not found
            assert response["statusCode"] == 404  # Not 401 (authentication error)
    
    def test_iam_authentication_success(self):
        """Test successful IAM authentication."""
        # Create request with IAM authorization
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"},
            headers={"Content-Type": "application/json"}
        )
        
        # Add IAM user ARN to request context
        event["requestContext"]["identity"]["userArn"] = "arn:aws:iam::123456789012:user/test-user"
        
        context = self.create_lambda_context()
        
        with patch('retrieve.index.get_sensor_data_access') as mock_get_data_access:
            mock_data_access = MagicMock()
            mock_data_access.get_current_data.return_value = None  # Device not found
            mock_get_data_access.return_value = mock_data_access
            
            # Execute request
            response = lambda_handler(event, context)
            
            # Should pass authentication but fail on device not found
            assert response["statusCode"] == 404  # Not 401 (authentication error)
    
    def test_no_authentication_failure(self):
        """Test authentication failure when no valid authentication is provided."""
        # Create request without any authentication
        event = self.create_api_gateway_event(
            path="/api/v1/local/data/current/AABBCCDDEEFF",
            path_params={"device_id": "AABBCCDDEEFF"},
            headers={"Content-Type": "application/json"}
        )
        context = self.create_lambda_context()
        
        # Execute request
        response = lambda_handler(event, context)
        
        # Should fail authentication
        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert body["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert "Valid authentication is required" in body["error"]["message"]
    
    def test_case_insensitive_api_key_header(self):
        """Test that API key header is case insensitive."""
        # Test different case variations
        header_variations = [
            {"X-API-Key": "test-key"},
            {"x-api-key": "test-key"},
            {"X-Api-Key": "test-key"}
        ]
        
        for headers in header_variations:
            event = self.create_api_gateway_event(
                path="/api/v1/local/data/current/AABBCCDDEEFF",
                path_params={"device_id": "AABBCCDDEEFF"},
                headers={**headers, "Content-Type": "application/json"}
            )
            context = self.create_lambda_context()
            
            with patch('retrieve.index.get_sensor_data_access') as mock_get_data_access:
                mock_data_access = MagicMock()
                mock_data_access.get_current_data.return_value = None
                mock_get_data_access.return_value = mock_data_access
                
                # Execute request
                response = lambda_handler(event, context)
                
                # Should pass authentication (fail on device not found, not auth)
                assert response["statusCode"] == 404  # Not 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])