"""
Unit tests for Ruuvi Cloud API data models and validation.

Tests cover:
- Data model creation and validation
- JSON schema validation
- Response formatting
- Error handling
"""

import pytest
import base64
from datetime import datetime, timedelta
from src.shared.models import (
    RuuviSensorData,
    RuuviGatewayRequest,
    RuuviCloudResponse,
    ValidationResult,
    validate_ruuvi_request,
    format_ruuvi_cloud_response,
    RUUVI_GATEWAY_REQUEST_SCHEMA
)


class TestRuuviSensorData:
    """Test cases for RuuviSensorData model."""
    
    def test_valid_sensor_data_creation(self):
        """Test creating valid sensor data."""
        device_id = "AABBCCDDEEFF"
        data = {
            "rssi": -65,
            "timestamp": 1574082635,
            "data": base64.b64encode(b"test_sensor_data").decode()
        }
        
        sensor = RuuviSensorData.from_dict(device_id, data)
        
        assert sensor.device_id == device_id
        assert sensor.rssi == -65
        assert sensor.timestamp == 1574082635
        assert sensor.data == data["data"]
    
    def test_invalid_device_id_format(self):
        """Test validation of device ID format."""
        invalid_ids = [
            "AABBCCDDEE",  # Too short
            "AABBCCDDEEFFGG",  # Too long
            "AABBCCDDEE-F",  # Invalid character
            "aabbccddeeff",  # Lowercase (should be uppercase)
            ""  # Empty
        ]
        
        data = {"rssi": -65, "timestamp": 1574082635, "data": ""}
        
        for invalid_id in invalid_ids:
            with pytest.raises(ValueError, match="Invalid device ID format"):
                RuuviSensorData.from_dict(invalid_id, data)
    
    def test_invalid_rssi_values(self):
        """Test validation of RSSI values."""
        device_id = "AABBCCDDEEFF"
        invalid_rssi_values = [-121, 1, 100, "invalid"]
        
        for invalid_rssi in invalid_rssi_values:
            data = {"rssi": invalid_rssi, "timestamp": 1574082635, "data": ""}
            with pytest.raises(ValueError, match="Invalid RSSI value"):
                RuuviSensorData.from_dict(device_id, data)
    
    def test_invalid_timestamp_values(self):
        """Test validation of timestamp values."""
        device_id = "AABBCCDDEEFF"
        invalid_timestamps = [-1, "invalid", 1.5]
        
        for invalid_timestamp in invalid_timestamps:
            data = {"rssi": -65, "timestamp": invalid_timestamp, "data": ""}
            with pytest.raises(ValueError, match="Invalid timestamp"):
                RuuviSensorData.from_dict(device_id, data)
    
    def test_invalid_base64_data(self):
        """Test validation of base64 encoded data."""
        device_id = "AABBCCDDEEFF"
        invalid_data_values = ["invalid_base64!", "not@base64"]
        
        for invalid_data in invalid_data_values:
            data = {"rssi": -65, "timestamp": 1574082635, "data": invalid_data}
            with pytest.raises(ValueError, match="Invalid base64 data"):
                RuuviSensorData.from_dict(device_id, data)
    
    def test_empty_base64_data_allowed(self):
        """Test that empty base64 data is allowed."""
        device_id = "AABBCCDDEEFF"
        data = {"rssi": -65, "timestamp": 1574082635, "data": ""}
        
        sensor = RuuviSensorData.from_dict(device_id, data)
        assert sensor.data == ""


class TestRuuviGatewayRequest:
    """Test cases for RuuviGatewayRequest model."""
    
    def get_valid_request_data(self):
        """Get a valid request data structure."""
        return {
            "data": {
                "coordinates": "60.1699,24.9384",
                "timestamp": 1574082635,
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "AABBCCDDEEFF": {
                        "rssi": -65,
                        "timestamp": 1574082635,
                        "data": base64.b64encode(b"test_data").decode()
                    },
                    "112233445566": {
                        "rssi": -70,
                        "timestamp": 1574082636,
                        "data": base64.b64encode(b"test_data2").decode()
                    }
                }
            }
        }
    
    def test_valid_request_creation(self):
        """Test creating valid gateway request."""
        request_data = self.get_valid_request_data()
        
        request = RuuviGatewayRequest.from_dict(request_data)
        
        assert request.coordinates == "60.1699,24.9384"
        assert request.timestamp == 1574082635
        assert request.gwmac == "AA:BB:CC:DD:EE:FF"
        assert len(request.tags) == 2
        assert "AABBCCDDEEFF" in request.tags
        assert "112233445566" in request.tags
    
    def test_missing_required_fields(self):
        """Test validation when required fields are missing."""
        base_data = self.get_valid_request_data()
        
        # Test missing 'data' field
        with pytest.raises(ValueError, match="Invalid request format"):
            RuuviGatewayRequest.from_dict({})
        
        # Test missing required fields in 'data'
        required_fields = ["timestamp", "gwmac", "tags"]
        for field in required_fields:
            invalid_data = base_data.copy()
            del invalid_data["data"][field]
            with pytest.raises(ValueError, match="Invalid request format"):
                RuuviGatewayRequest.from_dict(invalid_data)
    
    def test_invalid_mac_address_format(self):
        """Test validation of MAC address format."""
        request_data = self.get_valid_request_data()
        invalid_macs = [
            "AA:BB:CC:DD:EE",  # Too short
            "AA:BB:CC:DD:EE:FF:GG",  # Too long
            "AA-BB-CC-DD-EE-FF",  # Wrong separator (should work actually)
            "AABBCCDDEEFF",  # No separators
            "GG:BB:CC:DD:EE:FF"  # Invalid hex
        ]
        
        for invalid_mac in invalid_macs:
            test_data = request_data.copy()
            test_data["data"]["gwmac"] = invalid_mac
            if invalid_mac == "AA-BB-CC-DD-EE-FF":
                # This should actually be valid
                request = RuuviGatewayRequest.from_dict(test_data)
                assert request.validate_mac_address()
            else:
                with pytest.raises(ValueError, match="Invalid request format"):
                    RuuviGatewayRequest.from_dict(test_data)
    
    def test_get_sensor_data_list(self):
        """Test extracting sensor data list from tags."""
        request_data = self.get_valid_request_data()
        request = RuuviGatewayRequest.from_dict(request_data)
        
        sensor_data_list = request.get_sensor_data_list()
        
        assert len(sensor_data_list) == 2
        device_ids = [sensor.device_id for sensor in sensor_data_list]
        assert "AABBCCDDEEFF" in device_ids
        assert "112233445566" in device_ids
    
    def test_get_sensor_data_list_with_invalid_data(self):
        """Test sensor data extraction with some invalid entries."""
        # Create a request object directly to test sensor data extraction
        # bypassing schema validation
        request = RuuviGatewayRequest(
            coordinates="60.1699,24.9384",
            timestamp=1574082635,
            gwmac="AA:BB:CC:DD:EE:FF",
            tags={
                "AABBCCDDEEFF": {
                    "rssi": -65,
                    "timestamp": 1574082635,
                    "data": base64.b64encode(b"test_data").decode()
                },
                "112233445566": {
                    "rssi": -70,
                    "timestamp": 1574082636,
                    "data": base64.b64encode(b"test_data2").decode()
                },
                "AABBCCDDEE11": {
                    "rssi": 200,  # Invalid RSSI (too high)
                    "timestamp": 1574082635,
                    "data": "invalid_base64!"  # Invalid base64
                }
            }
        )
        
        sensor_data_list = request.get_sensor_data_list()
        
        # Should only return valid sensor data (2 valid ones, 1 invalid skipped)
        assert len(sensor_data_list) == 2
    
    def test_validate_timestamp_reasonable(self):
        """Test timestamp validation for reasonable values."""
        request_data = self.get_valid_request_data()
        current_time = int(datetime.now().timestamp())
        
        # Test current time (should be valid)
        request_data["data"]["timestamp"] = current_time
        request = RuuviGatewayRequest.from_dict(request_data)
        assert request.validate_timestamp()
        
        # Test time 1 hour ago (should be valid)
        request_data["data"]["timestamp"] = current_time - 3600
        request = RuuviGatewayRequest.from_dict(request_data)
        assert request.validate_timestamp()
        
        # Test time 25 hours ago (should be invalid)
        request_data["data"]["timestamp"] = current_time - 90000
        request = RuuviGatewayRequest.from_dict(request_data)
        assert not request.validate_timestamp()


class TestRuuviCloudResponse:
    """Test cases for RuuviCloudResponse model."""
    
    def test_success_response_creation(self):
        """Test creating success response."""
        response = RuuviCloudResponse.success("inserted")
        
        assert response.result == "success"
        assert response.data == {"action": "inserted"}
        assert response.error is None
        
        response_dict = response.to_dict()
        assert response_dict == {
            "result": "success",
            "data": {"action": "inserted"}
        }
    
    def test_success_response_with_extra_data(self):
        """Test creating success response with additional data."""
        response = RuuviCloudResponse.success("inserted", count=5, processed_at="2023-01-01")
        
        assert response.data == {
            "action": "inserted",
            "count": 5,
            "processed_at": "2023-01-01"
        }
    
    def test_error_response_creation(self):
        """Test creating error response."""
        response = RuuviCloudResponse.error("VALIDATION_ERROR", "Invalid data format")
        
        assert response.result == "error"
        assert response.data is None
        assert response.error == {
            "code": "VALIDATION_ERROR",
            "message": "Invalid data format"
        }
        
        response_dict = response.to_dict()
        assert response_dict == {
            "result": "error",
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid data format"
            }
        }


class TestValidationResult:
    """Test cases for ValidationResult class."""
    
    def test_valid_result(self):
        """Test creating valid validation result."""
        result = ValidationResult(True)
        
        assert result.is_valid
        assert result.errors == []
    
    def test_invalid_result_with_errors(self):
        """Test creating invalid validation result with errors."""
        result = ValidationResult(False, ["Error 1", "Error 2"])
        
        assert not result.is_valid
        assert len(result.errors) == 2
        assert "Error 1" in result.errors
        assert "Error 2" in result.errors
    
    def test_add_error(self):
        """Test adding error to validation result."""
        result = ValidationResult(True)
        result.add_error("New error")
        
        assert not result.is_valid
        assert "New error" in result.errors


class TestValidateRuuviRequest:
    """Test cases for validate_ruuvi_request function."""
    
    def get_valid_request_data(self):
        """Get a valid request data structure."""
        return {
            "data": {
                "coordinates": "60.1699,24.9384",
                "timestamp": int(datetime.now().timestamp()),
                "gwmac": "AA:BB:CC:DD:EE:FF",
                "tags": {
                    "AABBCCDDEEFF": {
                        "rssi": -65,
                        "timestamp": int(datetime.now().timestamp()),
                        "data": base64.b64encode(b"test_data").decode()
                    }
                }
            }
        }
    
    def test_valid_request_validation(self):
        """Test validation of valid request."""
        request_data = self.get_valid_request_data()
        result = validate_ruuvi_request(request_data)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_invalid_request_not_dict(self):
        """Test validation when request is not a dictionary."""
        result = validate_ruuvi_request("not a dict")
        
        assert not result.is_valid
        assert "Request must be a JSON object" in result.errors
    
    def test_invalid_request_schema_validation(self):
        """Test validation against JSON schema."""
        invalid_requests = [
            {},  # Missing 'data'
            {"data": {}},  # Missing required fields
            {"data": {"timestamp": "invalid", "gwmac": "AA:BB:CC:DD:EE:FF", "tags": {}}},  # Invalid timestamp type
        ]
        
        for invalid_request in invalid_requests:
            result = validate_ruuvi_request(invalid_request)
            assert not result.is_valid
            assert any("Schema validation failed" in error for error in result.errors)
    
    def test_invalid_mac_address_validation(self):
        """Test MAC address validation in business logic."""
        request_data = self.get_valid_request_data()
        request_data["data"]["gwmac"] = "INVALID_MAC"
        
        result = validate_ruuvi_request(request_data)
        
        assert not result.is_valid
        # This should fail at schema level first
        assert any("Schema validation failed" in error for error in result.errors)
    
    def test_old_timestamp_validation(self):
        """Test validation of old timestamps."""
        request_data = self.get_valid_request_data()
        # Set timestamp to 2 days ago
        old_timestamp = int((datetime.now() - timedelta(days=2)).timestamp())
        request_data["data"]["timestamp"] = old_timestamp
        request_data["data"]["tags"]["AABBCCDDEEFF"]["timestamp"] = old_timestamp
        
        result = validate_ruuvi_request(request_data)
        
        assert not result.is_valid
        assert any("too old or in the future" in error for error in result.errors)


class TestFormatRuuviCloudResponse:
    """Test cases for format_ruuvi_cloud_response function."""
    
    def test_format_success_response(self):
        """Test formatting success response."""
        response = format_ruuvi_cloud_response(True, "inserted")
        
        expected = {
            "result": "success",
            "data": {"action": "inserted"}
        }
        assert response == expected
    
    def test_format_success_response_custom_action(self):
        """Test formatting success response with custom action."""
        response = format_ruuvi_cloud_response(True, "updated")
        
        expected = {
            "result": "success",
            "data": {"action": "updated"}
        }
        assert response == expected
    
    def test_format_error_response(self):
        """Test formatting error response."""
        response = format_ruuvi_cloud_response(
            False, 
            error_code="VALIDATION_ERROR", 
            error_message="Invalid data format"
        )
        
        expected = {
            "result": "error",
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid data format"
            }
        }
        assert response == expected
    
    def test_format_error_response_defaults(self):
        """Test formatting error response with default values."""
        response = format_ruuvi_cloud_response(False)
        
        expected = {
            "result": "error",
            "error": {
                "code": "UNKNOWN_ERROR",
                "message": "An error occurred"
            }
        }
        assert response == expected


if __name__ == "__main__":
    pytest.main([__file__])