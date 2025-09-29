"""
Shared data models and validation schemas for Ruuvi API system.

This module contains data models that match the Ruuvi Cloud Gateway API format
and validation utilities used across all Lambda functions.
"""

import base64
import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime
import jsonschema
from jsonschema import ValidationError

# JSON Schema for Ruuvi Cloud Gateway API request format
RUUVI_GATEWAY_REQUEST_SCHEMA = {
    "type": "object",
    "required": ["data"],
    "properties": {
        "data": {
            "type": "object",
            "required": ["timestamp", "gwmac", "tags"],
            "properties": {
                "coordinates": {
                    "type": "string",
                    "description": "GPS coordinates (optional)"
                },
                "timestamp": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Unix timestamp"
                },
                "gwmac": {
                    "type": "string",
                    "pattern": "^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$",
                    "description": "Gateway MAC address"
                },
                "tags": {
                    "type": "object",
                    "minProperties": 1,
                    "patternProperties": {
                        "^[0-9A-F]{12}$": {
                            "type": "object",
                            "required": ["rssi", "timestamp", "data"],
                            "properties": {
                                "rssi": {
                                    "type": "integer",
                                    "minimum": -120,
                                    "maximum": 0,
                                    "description": "Signal strength in dBm"
                                },
                                "timestamp": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "description": "Device timestamp"
                                },
                                "data": {
                                    "type": "string",
                                    "pattern": "^[A-Za-z0-9+/]*={0,2}$",
                                    "description": "Base64 encoded sensor data"
                                }
                            },
                            "additionalProperties": False
                        }
                    },
                    "additionalProperties": False
                }
            },
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}

@dataclass
class RuuviSensorData:
    """
    Represents sensor data from a Ruuvi device.
    Based on Ruuvi Cloud Gateway API format.
    """
    device_id: str
    rssi: int
    timestamp: int
    data: str  # Base64 encoded sensor data
    
    @classmethod
    def from_dict(cls, device_id: str, data: Dict[str, Any]) -> 'RuuviSensorData':
        """Create RuuviSensorData from dictionary with validation."""
        if not cls._validate_device_id(device_id):
            raise ValueError(f"Invalid device ID format: {device_id}")
        
        rssi = data.get('rssi', 0)
        timestamp = data.get('timestamp', 0)
        sensor_data = data.get('data', '')
        
        if not isinstance(rssi, int) or rssi < -120 or rssi > 0:
            raise ValueError(f"Invalid RSSI value: {rssi}")
        
        if not isinstance(timestamp, int) or timestamp < 0:
            raise ValueError(f"Invalid timestamp: {timestamp}")
        
        if not cls._validate_base64(sensor_data):
            raise ValueError(f"Invalid base64 data: {sensor_data}")
        
        return cls(
            device_id=device_id,
            rssi=rssi,
            timestamp=timestamp,
            data=sensor_data
        )
    
    @staticmethod
    def _validate_device_id(device_id: str) -> bool:
        """Validate device ID format (12 uppercase hex characters)."""
        return bool(re.match(r'^[0-9A-F]{12}$', device_id))
    
    @staticmethod
    def _validate_base64(data: str) -> bool:
        """Validate base64 encoded data."""
        if not data:
            return True  # Empty data is allowed
        try:
            base64.b64decode(data, validate=True)
            return True
        except Exception:
            return False

@dataclass
class RuuviGatewayRequest:
    """
    Represents a complete request from Ruuvi Gateway.
    Based on Ruuvi Cloud Gateway API format.
    """
    coordinates: str
    timestamp: int
    gwmac: str
    tags: Dict[str, Dict[str, Any]]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RuuviGatewayRequest':
        """Create RuuviGatewayRequest from dictionary with validation."""
        # Validate against schema first
        try:
            jsonschema.validate(data, RUUVI_GATEWAY_REQUEST_SCHEMA)
        except ValidationError as e:
            raise ValueError(f"Invalid request format: {e.message}")
        
        request_data = data['data']
        return cls(
            coordinates=request_data.get('coordinates', ''),
            timestamp=request_data['timestamp'],
            gwmac=request_data['gwmac'],
            tags=request_data['tags']
        )
    
    def get_sensor_data_list(self) -> List[RuuviSensorData]:
        """Extract list of sensor data from tags with validation."""
        sensor_data = []
        for device_id, data in self.tags.items():
            try:
                sensor_data.append(RuuviSensorData.from_dict(device_id, data))
            except ValueError as e:
                # Log error but continue processing other sensors
                print(f"Warning: Skipping invalid sensor data for {device_id}: {e}")
        return sensor_data
    
    def validate_mac_address(self) -> bool:
        """Validate gateway MAC address format."""
        mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
        return bool(re.match(mac_pattern, self.gwmac))
    
    def validate_timestamp(self) -> bool:
        """Validate timestamp is reasonable (not too old or in future)."""
        current_time = int(datetime.now().timestamp())
        # Allow timestamps within 24 hours of current time
        return abs(current_time - self.timestamp) <= 86400

@dataclass
class RuuviCloudResponse:
    """
    Represents response format compatible with Ruuvi Cloud API.
    """
    result: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        response = {'result': self.result}
        if self.data:
            response['data'] = self.data
        if self.error:
            response['error'] = self.error
        return response
    
    @classmethod
    def success(cls, action: str = "inserted", **kwargs) -> 'RuuviCloudResponse':
        """Create a success response compatible with Ruuvi Cloud API."""
        data = {"action": action}
        data.update(kwargs)
        return cls(result="success", data=data, error=None)
    
    @classmethod
    def error(cls, code: str, message: str) -> 'RuuviCloudResponse':
        """Create an error response compatible with Ruuvi Cloud API."""
        return cls(
            result="error",
            data=None,
            error={"code": code, "message": message}
        )

class ValidationResult:
    """Result of validation with details about any errors."""
    
    def __init__(self, is_valid: bool, errors: Optional[List[str]] = None):
        self.is_valid = is_valid
        self.errors = errors or []
    
    def add_error(self, error: str):
        """Add an error to the validation result."""
        self.errors.append(error)
        self.is_valid = False

def validate_ruuvi_request(data: Dict[str, Any]) -> ValidationResult:
    """
    Comprehensive validation of incoming request against Ruuvi Cloud Gateway API format.
    
    Args:
        data: Request data to validate
        
    Returns:
        ValidationResult with validation status and any errors
    """
    result = ValidationResult(True)
    
    # Basic structure validation
    if not isinstance(data, dict):
        result.add_error("Request must be a JSON object")
        return result
    
    # Schema validation
    try:
        jsonschema.validate(data, RUUVI_GATEWAY_REQUEST_SCHEMA)
    except ValidationError as e:
        result.add_error(f"Schema validation failed: {e.message}")
        return result
    
    # Additional business logic validation
    try:
        request = RuuviGatewayRequest.from_dict(data)
        
        # Validate MAC address format
        if not request.validate_mac_address():
            result.add_error(f"Invalid gateway MAC address format: {request.gwmac}")
        
        # Validate timestamp reasonableness
        if not request.validate_timestamp():
            result.add_error(f"Timestamp is too old or in the future: {request.timestamp}")
        
        # Validate sensor data
        sensor_data_list = request.get_sensor_data_list()
        if not sensor_data_list:
            result.add_error("No valid sensor data found in tags")
        
    except ValueError as e:
        result.add_error(str(e))
    
    return result

def format_ruuvi_cloud_response(success: bool, action: str = "inserted", 
                               error_code: str = None, error_message: str = None) -> Dict[str, Any]:
    """
    Format response to match Ruuvi Cloud API response format exactly.
    
    Args:
        success: Whether the operation was successful
        action: Action performed (for success responses)
        error_code: Error code (for error responses)
        error_message: Error message (for error responses)
        
    Returns:
        Dictionary formatted as Ruuvi Cloud API response
    """
    if success:
        return RuuviCloudResponse.success(action).to_dict()
    else:
        return RuuviCloudResponse.error(error_code or "UNKNOWN_ERROR", 
                                      error_message or "An error occurred").to_dict()

# Legacy functions for backward compatibility
def create_success_response(action: str = "inserted") -> RuuviCloudResponse:
    """Create a success response compatible with Ruuvi Cloud API."""
    return RuuviCloudResponse.success(action)

def create_error_response(code: str, message: str) -> RuuviCloudResponse:
    """Create an error response compatible with Ruuvi Cloud API."""
    return RuuviCloudResponse.error(code, message)