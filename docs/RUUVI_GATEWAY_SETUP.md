# Ruuvi Gateway Setup Guide

This guide explains how to configure your Ruuvi Gateway to work with the Ruuvi API proxy system.

## Overview

The Ruuvi API proxy acts as a drop-in replacement for the Ruuvi Cloud Gateway API. Your Ruuvi Gateway can send data to the proxy instead of (or in addition to) the official Ruuvi Cloud service.

## Benefits of Using the Proxy

- **Local Data Storage**: Keep your sensor data locally while optionally forwarding to Ruuvi Cloud
- **Data Control**: Full control over your sensor data and retention policies
- **Reduced Dependency**: Continue collecting data even if Ruuvi Cloud is unavailable
- **Custom Processing**: Add custom logic and integrations to your sensor data pipeline

## Prerequisites

- Ruuvi Gateway device (firmware version 1.0.0 or later)
- Access to Ruuvi Gateway configuration interface
- Deployed Ruuvi API proxy system
- API key from the proxy deployment

## Configuration Steps

### 1. Obtain API Key

After deploying the Ruuvi API proxy, you'll need the Gateway API key:

```bash
# Get the API key ID from CloudFormation outputs
aws cloudformation describe-stacks --stack-name ruuvi-api-prod --query 'Stacks[0].Outputs[?OutputKey==`GatewayApiKeyId`].OutputValue' --output text

# Get the actual API key value
aws apigateway get-api-key --api-key YOUR_API_KEY_ID --include-value --query 'value' --output text
```

### 2. Configure Ruuvi Gateway

#### Option A: Web Interface Configuration

1. **Access Gateway Interface**
   - Connect to your Ruuvi Gateway's web interface
   - Navigate to "Cloud Settings" or "API Configuration"

2. **Update API Endpoint**
   - Change the API endpoint from `https://network.ruuvi.com/api/v1` to your proxy URL
   - Example: `https://ruuvi-api-prod.carriagereturn.nl/api/v1`

3. **Set API Key**
   - Enter the Gateway API key obtained in step 1
   - Save the configuration

#### Option B: Configuration File Method

If your gateway supports configuration files:

```json
{
  "cloud": {
    "api_endpoint": "https://ruuvi-api-prod.carriagereturn.nl/api/v1",
    "api_key": "YOUR_GATEWAY_API_KEY",
    "upload_interval": 60,
    "retry_attempts": 3
  }
}
```

#### Option C: Environment Variables

For gateways that support environment variable configuration:

```bash
export RUUVI_CLOUD_ENDPOINT="https://ruuvi-api-prod.carriagereturn.nl/api/v1"
export RUUVI_API_KEY="YOUR_GATEWAY_API_KEY"
export RUUVI_UPLOAD_INTERVAL=60
```

### 3. Verify Configuration

#### Test Data Upload

1. **Check Gateway Logs**
   - Look for successful HTTP 200 responses
   - Verify data is being sent to the correct endpoint

2. **Monitor Proxy Logs**
   ```bash
   aws logs tail /aws/lambda/ruuvi-api-prod-proxy --follow
   ```

3. **Verify Data Storage**
   ```bash
   # List devices to confirm data is being stored
   curl -H "x-api-key: YOUR_ADMIN_API_KEY" \
        https://ruuvi-api-prod.carriagereturn.nl/api/v1/local/devices
   ```

## Gateway Configuration Examples

### Standard Configuration

For most users, this configuration works well:

```json
{
  "api_endpoint": "https://ruuvi-api-prod.carriagereturn.nl/api/v1",
  "api_key": "YOUR_GATEWAY_API_KEY",
  "upload_interval": 60,
  "batch_size": 10,
  "timeout": 30
}
```

### High-Frequency Configuration

For applications requiring frequent updates:

```json
{
  "api_endpoint": "https://ruuvi-api-prod.carriagereturn.nl/api/v1",
  "api_key": "YOUR_GATEWAY_API_KEY",
  "upload_interval": 10,
  "batch_size": 5,
  "timeout": 15
}
```

### Reliable Configuration

For environments with unreliable connectivity:

```json
{
  "api_endpoint": "https://ruuvi-api-prod.carriagereturn.nl/api/v1",
  "api_key": "YOUR_GATEWAY_API_KEY",
  "upload_interval": 300,
  "batch_size": 50,
  "timeout": 60,
  "retry_attempts": 5,
  "retry_delay": 30
}
```

## Data Format Compatibility

The proxy maintains full compatibility with the Ruuvi Cloud Gateway API format:

### Request Format

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

### Response Format

```json
{
  "result": "success",
  "data": {
    "action": "inserted"
  }
}
```

## Forwarding Configuration

The proxy can be configured to forward data to Ruuvi Cloud while storing locally:

### Enable Forwarding

```bash
curl -X PUT \
  -H "x-api-key: YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}' \
  https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding
```

### Disable Forwarding

```bash
curl -X PUT \
  -H "x-api-key: YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}' \
  https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding
```

### Check Forwarding Status

```bash
curl -H "x-api-key: YOUR_ADMIN_API_KEY" \
     https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding
```

## Troubleshooting

### Common Issues

#### 1. Authentication Errors (401/403)

**Symptoms**: Gateway receives authentication errors
**Solutions**:
- Verify API key is correct
- Check API key hasn't expired
- Ensure API key has proper permissions

#### 2. Connection Timeouts

**Symptoms**: Gateway logs show timeout errors
**Solutions**:
- Check network connectivity
- Verify proxy endpoint URL
- Increase timeout values in gateway configuration

#### 3. Data Not Appearing

**Symptoms**: Gateway sends data but it doesn't appear in local storage
**Solutions**:
- Check proxy function logs for errors
- Verify DynamoDB table permissions
- Check data format compatibility

#### 4. High Error Rates

**Symptoms**: Many failed requests in gateway logs
**Solutions**:
- Check CloudWatch alarms
- Review proxy function performance
- Verify API Gateway rate limits

### Diagnostic Commands

#### Check Gateway Status

```bash
# View recent proxy function logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/ruuvi-api-prod-proxy \
  --start-time $(date -d '1 hour ago' +%s)000

# Check API Gateway metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Count \
  --dimensions Name=ApiName,Value=ruuvi-api-prod \
  --start-time $(date -d '1 hour ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Sum
```

#### Test API Connectivity

```bash
# Test basic connectivity
curl -v -H "x-api-key: YOUR_GATEWAY_API_KEY" \
     https://ruuvi-api-prod.carriagereturn.nl/api/v1/data

# Test with sample data
curl -X POST \
  -H "x-api-key: YOUR_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "coordinates": "",
      "timestamp": '$(date +%s)',
      "gwmac": "AA:BB:CC:DD:EE:FF",
      "tags": {
        "test_device": {
          "rssi": -65,
          "timestamp": '$(date +%s)',
          "data": "dGVzdCBkYXRh"
        }
      }
    }
  }' \
  https://ruuvi-api-prod.carriagereturn.nl/api/v1/data
```

## Security Considerations

### API Key Management

- **Rotation**: Rotate API keys regularly (recommended: every 90 days)
- **Storage**: Store API keys securely on the gateway device
- **Access**: Limit API key access to necessary personnel only

### Network Security

- **HTTPS Only**: Always use HTTPS endpoints
- **Firewall**: Configure gateway firewall to allow only necessary outbound connections
- **Monitoring**: Monitor for unusual API usage patterns

### Data Privacy

- **Local Storage**: Data is stored locally in your AWS account
- **Encryption**: All data is encrypted in transit and at rest
- **Access Control**: Use proper IAM policies to control data access

## Performance Optimization

### Upload Frequency

Balance between data freshness and system load:

- **High Frequency** (10-30 seconds): Real-time applications
- **Medium Frequency** (1-5 minutes): Most monitoring applications
- **Low Frequency** (5-15 minutes): Basic environmental monitoring

### Batch Size

Optimize batch sizes based on your sensor count:

- **Small Batches** (1-5 sensors): Low latency, higher API calls
- **Medium Batches** (5-20 sensors): Balanced approach
- **Large Batches** (20+ sensors): Efficient for many sensors

### Error Handling

Configure appropriate retry behavior:

```json
{
  "retry_attempts": 3,
  "retry_delay": 30,
  "exponential_backoff": true,
  "max_retry_delay": 300
}
```

## Migration from Ruuvi Cloud

### Gradual Migration

1. **Deploy Proxy**: Set up the proxy system
2. **Test Configuration**: Verify with a single gateway
3. **Parallel Operation**: Run both proxy and cloud temporarily
4. **Switch Over**: Update all gateways to use proxy
5. **Disable Cloud** (optional): Stop sending to Ruuvi Cloud

### Data Continuity

- Historical data remains in Ruuvi Cloud
- New data flows to your proxy system
- Use data export tools if you need to migrate historical data

## Support

### Getting Help

1. **Check Logs**: Review gateway and proxy logs first
2. **Documentation**: Consult this guide and the API documentation
3. **Community**: Check Ruuvi community forums
4. **Issues**: Report bugs via the project issue tracker

### Useful Resources

- [Ruuvi Gateway Documentation](https://docs.ruuvi.com/)
- [Ruuvi Cloud Gateway API](https://docs.ruuvi.com/communicate-with-ruuvi-cloud/cloud/gateway-api)
- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/)
- [API Gateway Documentation](https://docs.aws.amazon.com/apigateway/)