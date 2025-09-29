# Design Document

## Overview

The Ruuvi API system will be built as a serverless proxy service on AWS that acts as an intelligent intermediary between Ruuvi Gateway devices and the Ruuvi Cloud Gateway API. The system will store all data locally while optionally forwarding requests to Ruuvi Cloud based on dynamic configuration settings.

The architecture uses API Gateway for HTTP endpoints, Lambda functions for proxy logic and data processing, DynamoDB for local data storage and configuration management, and CloudWatch for monitoring. The system maintains full compatibility with the Ruuvi Cloud Gateway API format while providing local data access capabilities.

## Architecture

### High-Level Architecture

```mermaid
graph TB
    RG[Ruuvi Gateway] -->|POST /data| AG[API Gateway]
    WC[Web Client] -->|GET /data| AG
    AG -->|Proxy & Store| LP[Lambda Proxy Function]
    AG -->|Retrieve| LR[Lambda Retrieve Function]
    AG -->|Config| LC[Lambda Config Function]
    LP -->|Store Locally| DB[(DynamoDB Data)]
    LP -->|Check Config| CF[(DynamoDB Config)]
    LP -->|Forward (Optional)| RC[Ruuvi Cloud API]
    RC -->|Response| LP
    LR -->|Query| DB
    LC -->|Update| CF
    AG -->|Auth| AU[API Key/Cognito]
    LP -->|Logs| CW[CloudWatch]
    LR -->|Logs| CW
    LC -->|Logs| CW
```

### Technology Stack

- **API Gateway**: RESTful API endpoints with Ruuvi Cloud API compatibility
- **AWS Lambda**: Serverless compute for proxy logic and data processing (Node.js/Python)
- **DynamoDB**: NoSQL database for sensor data storage and configuration
- **CloudWatch**: Logging, monitoring, and alerting
- **API Keys**: Simple authentication for Ruuvi Gateways
- **Cognito** (optional): User authentication for web clients
- **CloudFormation**: Infrastructure as Code deployment
- **AWS Systems Manager Parameter Store** (alternative): For configuration management

## Components and Interfaces

### API Gateway Endpoints

#### Ruuvi Cloud Proxy Endpoint
- **Path**: `POST /api/v1/data` (matches Ruuvi Cloud Gateway API)
- **Authentication**: API Key required
- **Behavior**: Acts as transparent proxy to Ruuvi Cloud while storing data locally
- **Request Body**: Compatible with Ruuvi Cloud Gateway API format
- **Response**: Returns Ruuvi Cloud response or local success response based on configuration

#### Data Retrieval Endpoints (Local Access)
- **Path**: `GET /api/v1/local/data/current/{device_id}`
- **Authentication**: API Key or Cognito token
- **Response**: Latest sensor readings from local storage

- **Path**: `GET /api/v1/local/data/history/{device_id}`
- **Query Parameters**: `start_time`, `end_time`, `limit`, `next_token`
- **Authentication**: API Key or Cognito token
- **Response**: Time-series data with pagination support

- **Path**: `GET /api/v1/local/devices`
- **Authentication**: API Key or Cognito token
- **Response**: List of available devices with last seen timestamps

#### Configuration Management Endpoint
- **Path**: `PUT /api/v1/config/forwarding`
- **Authentication**: Admin API Key or Cognito token
- **Request Body**: `{"enabled": true/false}`
- **Response**: Configuration update confirmation

### Lambda Functions

#### Proxy Function
- **Runtime**: Node.js 18.x or Python 3.11
- **Memory**: 512 MB (for HTTP requests to Ruuvi Cloud)
- **Timeout**: 30 seconds
- **Responsibilities**:
  - Validate incoming data format (Ruuvi Cloud compatible)
  - Check forwarding configuration from DynamoDB
  - Forward request to Ruuvi Cloud API if enabled
  - Store data locally regardless of forwarding setting
  - Return appropriate response to Ruuvi Gateway

#### Retrieve Function
- **Runtime**: Node.js 18.x or Python 3.11
- **Memory**: 512 MB
- **Timeout**: 30 seconds
- **Responsibilities**:
  - Parse query parameters for local data access
  - Execute DynamoDB queries with proper indexing
  - Format response data for web clients
  - Handle pagination for large datasets

#### Configuration Function
- **Runtime**: Node.js 18.x or Python 3.11
- **Memory**: 256 MB
- **Timeout**: 15 seconds
- **Responsibilities**:
  - Update forwarding configuration in DynamoDB
  - Validate configuration changes
  - Return current configuration status

## Data Models

### DynamoDB Tables

#### Primary Table: `ruuvi-sensor-data`
- **Partition Key**: `device_id` (String)
- **Sort Key**: `timestamp` (Number - Unix timestamp)
- **Attributes**:
  - `gateway_id` (String)
  - `server_timestamp` (Number)
  - `measurements` (Map) - Raw Ruuvi data format
  - `ruuvi_cloud_response` (Map) - Response from Ruuvi Cloud (if forwarded)
  - `ttl` (Number - for automatic data cleanup)

#### Configuration Table: `ruuvi-api-config`
- **Partition Key**: `config_key` (String)
- **Attributes**:
  - `config_value` (String/Boolean/Number)
  - `last_updated` (Number - timestamp)
  - `updated_by` (String - user/system identifier)

#### Global Secondary Index: `gateway-timestamp-index`
- **Partition Key**: `gateway_id`
- **Sort Key**: `timestamp`
- **Purpose**: Query all devices from a specific gateway

### Ruuvi Cloud API Compatibility

Based on the Ruuvi Cloud Gateway API documentation, the system must handle:

#### Expected Request Format
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
      }
    }
  }
}
```

#### Expected Response Format
```json
{
  "result": "success",
  "data": {
    "action": "inserted"
  }
}
```

### Data Retention Strategy
- Implement TTL (Time To Live) on DynamoDB items
- Configurable retention period (default: 90 days)
- Use DynamoDB's built-in TTL feature for automatic cleanup
- Store configuration in DynamoDB config table

## Error Handling

### Proxy Function Error Handling
- **Ruuvi Cloud Unavailable**: Return local success response, log warning
- **Invalid Data Format**: Return error response matching Ruuvi Cloud format
- **Configuration Read Failure**: Default to forwarding disabled, log error
- **Local Storage Failure**: Still attempt to forward to Ruuvi Cloud if enabled

### API Gateway Level
- Rate limiting: 1000 requests per minute per API key
- Request size limits: 1MB maximum payload
- Timeout handling: 29 seconds maximum
- CORS configuration for web client access

### Lambda Function Level
- HTTP client timeout for Ruuvi Cloud requests (25 seconds)
- Retry logic for DynamoDB throttling
- Circuit breaker pattern for Ruuvi Cloud API failures
- Structured error responses with appropriate HTTP status codes

### Error Response Format (Ruuvi Cloud Compatible)
```json
{
  "result": "error",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid data format"
  }
}
```

## Configuration Management

### Dynamic Configuration
- **Storage**: DynamoDB configuration table
- **Cache**: In-memory caching in Lambda with TTL
- **Updates**: Real-time updates without function restart
- **Fallback**: Default to safe configuration if read fails

### Configuration Options
- `forwarding_enabled`: Boolean - Enable/disable Ruuvi Cloud forwarding
- `data_retention_days`: Number - TTL for local data storage
- `ruuvi_cloud_endpoint`: String - Ruuvi Cloud API endpoint URL
- `ruuvi_cloud_timeout`: Number - Timeout for Ruuvi Cloud requests

## Testing Strategy

### Unit Testing
- Lambda function logic with mocked AWS services and HTTP clients
- Data validation and transformation testing
- Configuration management testing
- Error handling scenario testing

### Integration Testing
- End-to-end proxy functionality with mock Ruuvi Cloud API
- Local data storage and retrieval testing
- Configuration update testing
- Authentication flow testing

### Load Testing
- Concurrent proxy requests with Ruuvi Cloud forwarding
- Local data retrieval performance testing
- Configuration change impact testing
- Cost monitoring under various load patterns

### Compatibility Testing
- Verify exact compatibility with Ruuvi Cloud Gateway API
- Test with actual Ruuvi Gateway devices if possible
- Validate response format matching

## Security Considerations

### Authentication
- API Keys for Ruuvi Gateways (same as would be used for Ruuvi Cloud)
- Admin API Keys for configuration management
- Optional Cognito User Pools for web client authentication
- IAM roles with least privilege access for Lambda functions

### Data Protection
- HTTPS only for all API endpoints
- Encryption in transit for Ruuvi Cloud communication
- Input sanitization and validation
- No sensitive data in CloudWatch logs

### Configuration Security
- Separate admin permissions for configuration changes
- Audit logging for all configuration updates
- Validation of configuration values before applying

## Cost Optimization

### Serverless Benefits
- Pay-per-request pricing model
- Automatic scaling to zero when not in use
- No infrastructure management overhead

### Proxy Optimization
- Connection pooling for Ruuvi Cloud API calls
- Efficient Lambda memory allocation
- Caching of configuration values to reduce DynamoDB reads

### DynamoDB Optimization
- On-demand billing for unpredictable workloads
- Efficient data modeling to minimize read/write operations
- TTL for automatic data cleanup
- Separate tables for data and configuration

### Estimated Monthly Costs (for handful of users)
- API Gateway: ~$1-5 (based on request volume)
- Lambda: ~$2-5 (includes HTTP requests to Ruuvi Cloud)
- DynamoDB: ~$3-12 (data + configuration tables)
- CloudWatch: ~$1-2 (basic monitoring)
- Data Transfer: ~$1-3 (Ruuvi Cloud API calls)
- **Total**: ~$8-27/month for typical usage

## Monitoring and Alerting

### Key Metrics
- Proxy request success/failure rates
- Ruuvi Cloud API response times and errors
- Local data storage success rates
- Configuration change frequency
- Data retention and cleanup operations

### Alarms
- High error rates for proxy operations (>5%)
- Ruuvi Cloud API unavailability
- DynamoDB throttling events
- Lambda function timeouts
- Unusual configuration change patterns

### Dashboards
- Real-time proxy operation status
- Ruuvi Cloud API health monitoring
- Local data storage metrics
- Cost tracking and optimization opportunities