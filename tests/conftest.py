"""
Pytest configuration and shared fixtures for Ruuvi API tests.
"""

import pytest
import json
import os
from typing import Dict, Any
from unittest.mock import Mock

# Set test environment variables
os.environ['DATA_TABLE_NAME'] = 'test-ruuvi-sensor-data'
os.environ['CONFIG_TABLE_NAME'] = 'test-ruuvi-api-config'
os.environ['RUUVI_CLOUD_ENDPOINT'] = 'https://test.ruuvi.com/api'
os.environ['FORWARDING_ENABLED'] = 'true'
os.environ['DATA_RETENTION_DAYS'] = '30'

@pytest.fixture
def sample_ruuvi_request() -> Dict[str, Any]:
    """Sample Ruuvi Gateway request data."""
    return {
        "data": {
            "coordinates": "",
            "timestamp": 1574082635,
            "gwmac": "AA:BB:CC:DD:EE:FF",
            "tags": {
                "device_id_1": {
                    "rssi": -65,
                    "timestamp": 1574082635,
                    "data": "base64_encoded_sensor_data"
                },
                "device_id_2": {
                    "rssi": -70,
                    "timestamp": 1574082635,
                    "data": "another_base64_encoded_data"
                }
            }
        }
    }

@pytest.fixture
def api_gateway_event() -> Dict[str, Any]:
    """Sample API Gateway event."""
    return {
        "httpMethod": "POST",
        "path": "/api/v1/data",
        "queryStringParameters": None,
        "pathParameters": None,
        "headers": {
            "Content-Type": "application/json",
            "X-Api-Key": "test-api-key"
        },
        "body": "",
        "isBase64Encoded": False
    }

@pytest.fixture
def lambda_context():
    """Mock Lambda context."""
    context = Mock()
    context.function_name = "test-function"
    context.function_version = "1"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    context.memory_limit_in_mb = 512
    context.remaining_time_in_millis = lambda: 30000
    context.aws_request_id = "test-request-id"
    return context

@pytest.fixture
def mock_dynamodb_table():
    """Mock DynamoDB table."""
    table = Mock()
    table.put_item = Mock()
    table.query = Mock()
    table.scan = Mock()
    return table