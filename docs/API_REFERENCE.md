# Ruuvi API Reference

This document provides comprehensive API reference for the Ruuvi API proxy system, including both proxy endpoints and local data access endpoints.

## Base URL

```
https://ruuvi-api-{environment}.carriagereturn.nl
```

Where `{environment}` is one of:
- `dev` - Development environment
- `staging` - Staging environment  
- `prod` - Production environment

## Authentication

The API uses API key authentication via the `x-api-key` header.

### API Key Types

1. **Gateway API Key**: For Ruuvi Gateway devices to send sensor data
2. **Admin API Key**: For configuration management and local data access

```bash
# Example request with API key
curl -H "x-api-key: YOUR_API_KEY" \
     https://ruuvi-api-prod.carriagereturn.nl/api/v1/local/devices
```

## Proxy Endpoints

These endpoints maintain compatibility with the Ruuvi Cloud Gateway API.

### POST /api/v1/data

Send sensor data from Ruuvi Gateway devices.

**Authentication**: Gateway API Key required

**Request Body**:
```json
{
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
        "rssi": -72,
        "timestamp": 1574082640,
        "data": "base64_encoded_sensor_data"
      }
    }
  }
}
```

**Response**:
```json
{
  "result": "success",
  "data": {
    "action": "inserted"
  }
}
```

**Error Response**:
```json
{
  "result": "error",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid data format"
  }
}
```

**Behavior**:
- Data is always stored locally regardless of forwarding configuration
- If forwarding is enabled, data is also sent to Ruuvi Cloud
- Response matches Ruuvi Cloud API format for compatibility

## Local Data Access Endpoints

These endpoints provide access to locally stored sensor data.

### GET /api/v1/local/devices

List all devices that have sent data to the system.

**Authentication**: Admin API Key required

**Response**:
```json
{
  "devices": [
    {
      "device_id": "AA:BB:CC:DD:EE:01",
      "last_seen": 1574082635,
      "first_seen": 1574000000,
      "total_readings": 1440,
      "gateway_id": "AA:BB:CC:DD:EE:FF"
    },
    {
      "device_id": "AA:BB:CC:DD:EE:02", 
      "last_seen": 1574082640,
      "first_seen": 1574000100,
      "total_readings": 1435,
      "gateway_id": "AA:BB:CC:DD:EE:FF"
    }
  ],
  "total_devices": 2
}
```

### GET /api/v1/local/data/current/{device_id}

Get the most recent sensor reading for a specific device.

**Authentication**: Admin API Key required

**Path Parameters**:
- `device_id` (string): The device identifier

**Response**:
```json
{
  "device_id": "AA:BB:CC:DD:EE:01",
  "timestamp": 1574082635,
  "server_timestamp": 1574082636,
  "gateway_id": "AA:BB:CC:DD:EE:FF",
  "rssi": -65,
  "measurements": {
    "temperature": 23.5,
    "humidity": 45.2,
    "pressure": 1013.25,
    "battery_voltage": 3.2,
    "acceleration_x": 0.1,
    "acceleration_y": 0.2,
    "acceleration_z": 9.8
  }
}
```

**Error Response** (device not found):
```json
{
  "error": {
    "code": "DEVICE_NOT_FOUND",
    "message": "No data found for device AA:BB:CC:DD:EE:99"
  }
}
```

### GET /api/v1/local/data/history/{device_id}

Get historical sensor data for a specific device.

**Authentication**: Admin API Key required

**Path Parameters**:
- `device_id` (string): The device identifier

**Query Parameters**:
- `start_time` (integer, optional): Unix timestamp for start of time range
- `end_time` (integer, optional): Unix timestamp for end of time range  
- `limit` (integer, optional): Maximum number of records to return (default: 100, max: 1000)
- `next_token` (string, optional): Pagination token for next page

**Example Request**:
```bash
curl -H "x-api-key: YOUR_ADMIN_API_KEY" \
     "https://ruuvi-api-prod.carriagereturn.nl/api/v1/local/data/history/AA:BB:CC:DD:EE:01?start_time=1574000000&end_time=1574086400&limit=50"
```

**Response**:
```json
{
  "device_id": "AA:BB:CC:DD:EE:01",
  "readings": [
    {
      "timestamp": 1574082635,
      "server_timestamp": 1574082636,
      "gateway_id": "AA:BB:CC:DD:EE:FF",
      "rssi": -65,
      "measurements": {
        "temperature": 23.5,
        "humidity": 45.2,
        "pressure": 1013.25,
        "battery_voltage": 3.2,
        "acceleration_x": 0.1,
        "acceleration_y": 0.2,
        "acceleration_z": 9.8
      }
    },
    {
      "timestamp": 1574082575,
      "server_timestamp": 1574082576,
      "gateway_id": "AA:BB:CC:DD:EE:FF", 
      "rssi": -67,
      "measurements": {
        "temperature": 23.4,
        "humidity": 45.1,
        "pressure": 1013.20,
        "battery_voltage": 3.2,
        "acceleration_x": 0.1,
        "acceleration_y": 0.2,
        "acceleration_z": 9.8
      }
    }
  ],
  "total_readings": 2,
  "next_token": "eyJkZXZpY2VfaWQiOiJBQTpCQjpDQzpERDpFRTowMSIsInRpbWVzdGFtcCI6MTU3NDA4MjUxNX0="
}
```

**Pagination Example**:
```bash
# Get next page using next_token
curl -H "x-api-key: YOUR_ADMIN_API_KEY" \
     "https://ruuvi-api-prod.carriagereturn.nl/api/v1/local/data/history/AA:BB:CC:DD:EE:01?next_token=eyJkZXZpY2VfaWQiOiJBQTpCQjpDQzpERDpFRTowMSIsInRpbWVzdGFtcCI6MTU3NDA4MjUxNX0="
```

## Configuration Management Endpoints

These endpoints allow dynamic configuration of the proxy system.

### GET /api/v1/config/forwarding

Get current forwarding configuration.

**Authentication**: Admin API Key required

**Response**:
```json
{
  "forwarding_enabled": true,
  "ruuvi_cloud_endpoint": "https://network.ruuvi.com/api/v1",
  "last_updated": 1574082635,
  "updated_by": "admin"
}
```

### PUT /api/v1/config/forwarding

Update forwarding configuration.

**Authentication**: Admin API Key required

**Request Body**:
```json
{
  "enabled": false
}
```

**Response**:
```json
{
  "result": "success",
  "forwarding_enabled": false,
  "updated_at": 1574082700
}
```

## Data Formats

### Sensor Measurements

The `measurements` object contains decoded sensor data:

```json
{
  "temperature": 23.5,          // Celsius
  "humidity": 45.2,             // Percentage (0-100)
  "pressure": 1013.25,          // hPa
  "battery_voltage": 3.2,       // Volts
  "acceleration_x": 0.1,        // g-force
  "acceleration_y": 0.2,        // g-force  
  "acceleration_z": 9.8,        // g-force
  "tx_power": 4,                // dBm (optional)
  "movement_counter": 142,      // Count (optional)
  "measurement_sequence": 1234  // Sequence number (optional)
}
```

### Timestamps

- `timestamp`: Unix timestamp from the sensor/gateway
- `server_timestamp`: Unix timestamp when data was received by the proxy

### Device Identifiers

- `device_id`: MAC address of the Ruuvi sensor (format: AA:BB:CC:DD:EE:FF)
- `gateway_id`: MAC address of the Ruuvi Gateway (format: AA:BB:CC:DD:EE:FF)

## Error Codes

### HTTP Status Codes

- `200 OK`: Request successful
- `400 Bad Request`: Invalid request format or parameters
- `401 Unauthorized`: Missing or invalid API key
- `403 Forbidden`: API key doesn't have required permissions
- `404 Not Found`: Resource not found (e.g., device doesn't exist)
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `502 Bad Gateway`: Upstream service error (e.g., Ruuvi Cloud unavailable)
- `503 Service Unavailable`: Service temporarily unavailable

### Error Response Format

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable error message",
    "details": {
      "field": "Additional error details"
    }
  }
}
```

### Common Error Codes

- `VALIDATION_ERROR`: Request validation failed
- `DEVICE_NOT_FOUND`: Requested device has no data
- `INVALID_TIME_RANGE`: Invalid start_time/end_time parameters
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `FORWARDING_FAILED`: Failed to forward to Ruuvi Cloud
- `STORAGE_ERROR`: Failed to store data locally
- `CONFIG_ERROR`: Configuration update failed

## Rate Limits

### Default Limits

- **Gateway API**: 1000 requests per minute per API key
- **Admin API**: 100 requests per minute per API key
- **Burst Limit**: 2000 requests per minute (short bursts)

### Rate Limit Headers

Response headers indicate current rate limit status:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1574082700
```

## Pagination

Large result sets use cursor-based pagination:

1. **Initial Request**: Make request without `next_token`
2. **Check Response**: Look for `next_token` in response
3. **Next Page**: Use `next_token` in subsequent request
4. **Continue**: Repeat until `next_token` is null/empty

**Example Pagination Flow**:
```bash
# Page 1
curl "https://api.example.com/data/history/device1?limit=100"
# Response includes: "next_token": "abc123"

# Page 2  
curl "https://api.example.com/data/history/device1?limit=100&next_token=abc123"
# Response includes: "next_token": "def456"

# Page 3
curl "https://api.example.com/data/history/device1?limit=100&next_token=def456"
# Response includes: "next_token": null (no more pages)
```

## SDK Examples

### Python Example

```python
import requests
import json
from datetime import datetime, timedelta

class RuuviAPIClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {'x-api-key': api_key}
    
    def get_devices(self):
        """Get list of all devices."""
        response = requests.get(
            f"{self.base_url}/api/v1/local/devices",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
    
    def get_current_data(self, device_id):
        """Get current data for a device."""
        response = requests.get(
            f"{self.base_url}/api/v1/local/data/current/{device_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
    
    def get_historical_data(self, device_id, start_time=None, end_time=None, limit=100):
        """Get historical data for a device."""
        params = {'limit': limit}
        if start_time:
            params['start_time'] = int(start_time.timestamp())
        if end_time:
            params['end_time'] = int(end_time.timestamp())
        
        response = requests.get(
            f"{self.base_url}/api/v1/local/data/history/{device_id}",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def set_forwarding(self, enabled):
        """Enable or disable forwarding to Ruuvi Cloud."""
        response = requests.put(
            f"{self.base_url}/api/v1/config/forwarding",
            headers=self.headers,
            json={'enabled': enabled}
        )
        response.raise_for_status()
        return response.json()

# Usage example
client = RuuviAPIClient(
    "https://ruuvi-api-prod.carriagereturn.nl",
    "your-admin-api-key"
)

# Get all devices
devices = client.get_devices()
print(f"Found {devices['total_devices']} devices")

# Get current data for first device
if devices['devices']:
    device_id = devices['devices'][0]['device_id']
    current = client.get_current_data(device_id)
    print(f"Current temperature: {current['measurements']['temperature']}°C")
    
    # Get last 24 hours of data
    end_time = datetime.now()
    start_time = end_time - timedelta(days=1)
    history = client.get_historical_data(device_id, start_time, end_time)
    print(f"Found {history['total_readings']} historical readings")
```

### JavaScript Example

```javascript
class RuuviAPIClient {
    constructor(baseUrl, apiKey) {
        this.baseUrl = baseUrl;
        this.headers = {
            'x-api-key': apiKey,
            'Content-Type': 'application/json'
        };
    }
    
    async getDevices() {
        const response = await fetch(`${this.baseUrl}/api/v1/local/devices`, {
            headers: this.headers
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response.json();
    }
    
    async getCurrentData(deviceId) {
        const response = await fetch(
            `${this.baseUrl}/api/v1/local/data/current/${deviceId}`,
            { headers: this.headers }
        );
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response.json();
    }
    
    async getHistoricalData(deviceId, options = {}) {
        const params = new URLSearchParams();
        
        if (options.startTime) {
            params.append('start_time', Math.floor(options.startTime.getTime() / 1000));
        }
        if (options.endTime) {
            params.append('end_time', Math.floor(options.endTime.getTime() / 1000));
        }
        if (options.limit) {
            params.append('limit', options.limit);
        }
        if (options.nextToken) {
            params.append('next_token', options.nextToken);
        }
        
        const url = `${this.baseUrl}/api/v1/local/data/history/${deviceId}?${params}`;
        const response = await fetch(url, { headers: this.headers });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response.json();
    }
    
    async setForwarding(enabled) {
        const response = await fetch(`${this.baseUrl}/api/v1/config/forwarding`, {
            method: 'PUT',
            headers: this.headers,
            body: JSON.stringify({ enabled })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response.json();
    }
}

// Usage example
const client = new RuuviAPIClient(
    'https://ruuvi-api-prod.carriagereturn.nl',
    'your-admin-api-key'
);

// Get devices and current data
client.getDevices()
    .then(devices => {
        console.log(`Found ${devices.total_devices} devices`);
        
        if (devices.devices.length > 0) {
            const deviceId = devices.devices[0].device_id;
            return client.getCurrentData(deviceId);
        }
    })
    .then(current => {
        if (current) {
            console.log(`Current temperature: ${current.measurements.temperature}°C`);
        }
    })
    .catch(error => {
        console.error('API Error:', error);
    });
```

## Best Practices

### API Usage

1. **Use Appropriate Keys**: Use Gateway keys for data upload, Admin keys for data access
2. **Handle Rate Limits**: Implement exponential backoff for rate limit errors
3. **Cache Responses**: Cache device lists and configuration data when appropriate
4. **Validate Data**: Always validate API responses before using data
5. **Error Handling**: Implement proper error handling for all API calls

### Performance

1. **Batch Requests**: Use appropriate batch sizes for historical data
2. **Pagination**: Use pagination for large datasets
3. **Time Ranges**: Limit time ranges for historical queries
4. **Caching**: Cache frequently accessed data locally
5. **Connection Pooling**: Reuse HTTP connections when possible

### Security

1. **API Key Security**: Store API keys securely, never in client-side code
2. **HTTPS Only**: Always use HTTPS endpoints
3. **Key Rotation**: Rotate API keys regularly
4. **Access Control**: Use least-privilege principle for API keys
5. **Monitoring**: Monitor API usage for unusual patterns