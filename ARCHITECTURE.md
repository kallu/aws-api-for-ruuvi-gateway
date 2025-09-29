# Ruuvi API Proxy Architecture

## Project Structure

This project extends the existing simple HTTP proxy to create an intelligent serverless API that acts as a proxy between Ruuvi Gateway devices and the Ruuvi Cloud API while storing data locally.

### Directory Structure

```
.
├── src/                          # Lambda function source code
│   ├── proxy/                    # Proxy Lambda function
│   │   └── index.py             # Main proxy handler
│   ├── retrieve/                 # Data retrieval Lambda function
│   │   └── index.py             # Data retrieval handler
│   ├── config/                   # Configuration management Lambda function
│   │   └── index.py             # Configuration handler
│   └── shared/                   # Shared utilities and models
│       ├── models.py            # Data models and validation
│       ├── config.py            # Configuration management
│       └── utils.py             # Common utilities
├── tests/                        # Test suite
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── conftest.py              # Pytest configuration
├── scripts/                      # Build and deployment scripts
│   └── build.py                 # Lambda packaging script
├── apiproxy.yaml                # Original CloudFormation template
├── enhanced-apiproxy.yaml       # Enhanced template (to be created)
├── package.json                 # Project metadata and scripts
├── requirements.txt             # Python dependencies
└── README.md                    # Project documentation
```

## Current Implementation Analysis

The existing `apiproxy.yaml` CloudFormation template creates:

1. **API Gateway**: RESTful API with custom domain
2. **HTTP_PROXY Integration**: Direct forwarding to target API
3. **Route53 Record**: Custom domain mapping
4. **SSL Certificate**: ACM certificate integration

### Key Components from Existing Template

- **Custom Domain**: Uses Route53 and ACM for HTTPS endpoints
- **Proxy Pattern**: `{proxy+}` resource for catch-all routing
- **Regional Endpoint**: Optimized for regional access
- **Parameter-driven**: Configurable target API and domain

## Enhanced Architecture

The enhanced system will replace the HTTP_PROXY integration with Lambda functions while preserving:

- Existing domain and SSL configuration
- Parameter-based configuration approach
- Regional API Gateway setup
- Route53 integration

### New Components

1. **Lambda Functions**: Replace HTTP_PROXY with intelligent processing
2. **DynamoDB Tables**: Local data storage and configuration
3. **IAM Roles**: Least privilege access for Lambda functions
4. **CloudWatch**: Enhanced monitoring and logging

## Ruuvi Cloud API Compatibility

Based on the Ruuvi Cloud Gateway API documentation, the system must handle:

### Request Format
```json
{
  "data": {
    "coordinates": "",
    "timestamp": 1574082635,
    "gwmac": "AA:BB:CC:DD:EE:FF",
    "tags": {
      "device_id": {
        "rssi": -65,
        "timestamp": 1574082635,
        "data": "base64_encoded_sensor_data"
      }
    }
  }
}
```

### Response Format
```json
{
  "result": "success",
  "data": {
    "action": "inserted"
  }
}
```

## Development Workflow

1. **Build**: `python scripts/build.py` - Package Lambda functions
2. **Test**: `pytest tests/ -v` - Run test suite
3. **Deploy**: CloudFormation deployment with packaged functions
4. **Monitor**: CloudWatch logs and metrics

## Next Steps

The implementation will proceed through the following phases:

1. **Data Models**: Implement Ruuvi Cloud API compatibility layer
2. **Storage**: Set up DynamoDB tables and access patterns
3. **Proxy Logic**: Implement intelligent forwarding with local storage
4. **Data Access**: Create endpoints for local data retrieval
5. **Configuration**: Dynamic configuration management
6. **Infrastructure**: Enhanced CloudFormation template
7. **Testing**: Comprehensive test suite
8. **Documentation**: Deployment and usage guides