# Configuration Management Guide

This guide covers how to manage and configure the Ruuvi API proxy system for optimal operation.

## Overview

The Ruuvi API proxy system supports dynamic configuration management, allowing operators to modify system behavior without redeployment. Configuration is stored in DynamoDB and cached in Lambda functions for optimal performance.

## Configuration Architecture

### Storage Layer
- **Primary Storage**: DynamoDB configuration table
- **Caching**: In-memory caching in Lambda functions (5-minute TTL)
- **Fallback**: Default values hardcoded in Lambda functions

### Configuration Hierarchy
1. **Runtime Configuration**: Dynamic settings stored in DynamoDB
2. **Environment Configuration**: Environment-specific settings from deployment
3. **Default Configuration**: Hardcoded fallback values

## Configuration Parameters

### Core Settings

#### Forwarding Configuration
Controls whether data is forwarded to Ruuvi Cloud API.

```json
{
  "config_key": "forwarding_enabled",
  "config_value": true,
  "last_updated": 1574082635,
  "updated_by": "admin"
}
```

**Values**:
- `true`: Forward data to Ruuvi Cloud API
- `false`: Store data locally only

**Impact**: Takes effect within 5 minutes due to caching

#### Data Retention Configuration
Controls how long data is retained in local storage.

```json
{
  "config_key": "data_retention_days",
  "config_value": 90,
  "last_updated": 1574082635,
  "updated_by": "admin"
}
```

**Values**: Integer (1-3650 days)
**Impact**: Applies to new data only; existing TTL values unchanged

#### Ruuvi Cloud Endpoint Configuration
Specifies the Ruuvi Cloud API endpoint for forwarding.

```json
{
  "config_key": "ruuvi_cloud_endpoint",
  "config_value": "https://network.ruuvi.com/api/v1",
  "last_updated": 1574082635,
  "updated_by": "admin"
}
```

**Values**: Valid HTTPS URL
**Impact**: Takes effect within 5 minutes due to caching

#### Request Timeout Configuration
Controls timeout for Ruuvi Cloud API requests.

```json
{
  "config_key": "ruuvi_cloud_timeout",
  "config_value": 25,
  "last_updated": 1574082635,
  "updated_by": "admin"
}
```

**Values**: Integer (5-25 seconds)
**Impact**: Takes effect within 5 minutes due to caching

### Advanced Settings

#### Batch Processing Configuration
Controls how sensor data is processed and stored.

```json
{
  "config_key": "batch_size",
  "config_value": 25,
  "last_updated": 1574082635,
  "updated_by": "admin"
}
```

**Values**: Integer (1-100)
**Impact**: Affects DynamoDB write efficiency

#### Retry Configuration
Controls retry behavior for failed operations.

```json
{
  "config_key": "max_retries",
  "config_value": 3,
  "last_updated": 1574082635,
  "updated_by": "admin"
}
```

**Values**: Integer (0-10)
**Impact**: Affects error handling and recovery

#### Circuit Breaker Configuration
Controls circuit breaker behavior for Ruuvi Cloud API calls.

```json
{
  "config_key": "circuit_breaker_threshold",
  "config_value": 5,
  "last_updated": 1574082635,
  "updated_by": "admin"
}
```

**Values**: Integer (1-20)
**Impact**: Number of consecutive failures before circuit opens

## Configuration Management

### Using the API

#### Get Current Configuration

```bash
# Get forwarding configuration
curl -H "x-api-key: YOUR_ADMIN_API_KEY" \
     https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding

# Response
{
  "forwarding_enabled": true,
  "ruuvi_cloud_endpoint": "https://network.ruuvi.com/api/v1",
  "last_updated": 1574082635,
  "updated_by": "admin"
}
```

#### Update Configuration

```bash
# Enable forwarding
curl -X PUT \
  -H "x-api-key: YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}' \
  https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding

# Disable forwarding
curl -X PUT \
  -H "x-api-key: YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}' \
  https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding
```

### Using AWS CLI

#### Direct DynamoDB Access

```bash
# Get all configuration items
aws dynamodb scan --table-name ruuvi-api-prod-config

# Get specific configuration
aws dynamodb get-item \
  --table-name ruuvi-api-prod-config \
  --key '{"config_key": {"S": "forwarding_enabled"}}'

# Update configuration
aws dynamodb put-item \
  --table-name ruuvi-api-prod-config \
  --item '{
    "config_key": {"S": "forwarding_enabled"},
    "config_value": {"BOOL": false},
    "last_updated": {"N": "'$(date +%s)'"},
    "updated_by": {"S": "admin-cli"}
  }'
```

#### Using Parameter Store (Alternative)

```bash
# Store configuration in Parameter Store
aws ssm put-parameter \
  --name "/ruuvi-api/prod/forwarding_enabled" \
  --value "true" \
  --type "String" \
  --overwrite

# Retrieve configuration
aws ssm get-parameter \
  --name "/ruuvi-api/prod/forwarding_enabled" \
  --query 'Parameter.Value' \
  --output text
```

### Configuration Scripts

#### Bulk Configuration Update Script

```python
#!/usr/bin/env python3
"""
Bulk configuration update script for Ruuvi API.
"""

import boto3
import json
import sys
from datetime import datetime

def update_configurations(table_name, configs, updated_by="script"):
    """Update multiple configuration values."""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    
    timestamp = int(datetime.utcnow().timestamp())
    
    with table.batch_writer() as batch:
        for config_key, config_value in configs.items():
            batch.put_item(Item={
                'config_key': config_key,
                'config_value': config_value,
                'last_updated': timestamp,
                'updated_by': updated_by
            })
    
    print(f"Updated {len(configs)} configuration items")

def main():
    if len(sys.argv) != 3:
        print("Usage: python update_config.py <environment> <config_file>")
        sys.exit(1)
    
    environment = sys.argv[1]
    config_file = sys.argv[2]
    
    table_name = f"ruuvi-api-{environment}-config"
    
    with open(config_file, 'r') as f:
        configs = json.load(f)
    
    update_configurations(table_name, configs)

if __name__ == "__main__":
    main()
```

#### Configuration Backup Script

```python
#!/usr/bin/env python3
"""
Configuration backup script for Ruuvi API.
"""

import boto3
import json
import sys
from datetime import datetime

def backup_configuration(table_name, output_file):
    """Backup all configuration to JSON file."""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    
    response = table.scan()
    items = response['Items']
    
    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response['Items'])
    
    backup_data = {
        'timestamp': datetime.utcnow().isoformat(),
        'table_name': table_name,
        'configurations': items
    }
    
    with open(output_file, 'w') as f:
        json.dump(backup_data, f, indent=2, default=str)
    
    print(f"Backed up {len(items)} configuration items to {output_file}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python backup_config.py <environment> <output_file>")
        sys.exit(1)
    
    environment = sys.argv[1]
    output_file = sys.argv[2]
    
    table_name = f"ruuvi-api-{environment}-config"
    backup_configuration(table_name, output_file)

if __name__ == "__main__":
    main()
```

## Environment-Specific Configuration

### Development Environment

**Recommended Settings**:
```json
{
  "forwarding_enabled": false,
  "data_retention_days": 30,
  "ruuvi_cloud_timeout": 15,
  "batch_size": 10,
  "max_retries": 2,
  "circuit_breaker_threshold": 3
}
```

**Rationale**:
- Forwarding disabled to avoid test data in production Ruuvi Cloud
- Shorter retention for cost optimization
- Lower timeouts for faster development cycles
- Smaller batch sizes for easier debugging

### Staging Environment

**Recommended Settings**:
```json
{
  "forwarding_enabled": true,
  "data_retention_days": 60,
  "ruuvi_cloud_timeout": 20,
  "batch_size": 20,
  "max_retries": 3,
  "circuit_breaker_threshold": 5
}
```

**Rationale**:
- Forwarding enabled to test integration
- Medium retention for testing scenarios
- Production-like settings for realistic testing

### Production Environment

**Recommended Settings**:
```json
{
  "forwarding_enabled": true,
  "data_retention_days": 90,
  "ruuvi_cloud_timeout": 25,
  "batch_size": 25,
  "max_retries": 3,
  "circuit_breaker_threshold": 5
}
```

**Rationale**:
- Forwarding enabled for full functionality
- Longer retention for historical analysis
- Optimized settings for performance and reliability

## Configuration Monitoring

### CloudWatch Metrics

Monitor configuration-related metrics:

```bash
# Configuration update frequency
aws cloudwatch put-metric-data \
  --namespace RuuviAPI \
  --metric-data MetricName=ConfigurationUpdates,Value=1,Unit=Count

# Forwarding status changes
aws cloudwatch put-metric-data \
  --namespace RuuviAPI \
  --metric-data MetricName=ForwardingToggled,Value=1,Unit=Count
```

### Configuration Audit Log

Track all configuration changes:

```python
def log_configuration_change(config_key, old_value, new_value, updated_by):
    """Log configuration changes for audit purposes."""
    audit_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'config_key': config_key,
        'old_value': old_value,
        'new_value': new_value,
        'updated_by': updated_by,
        'source_ip': get_source_ip(),
        'user_agent': get_user_agent()
    }
    
    # Store in CloudWatch Logs
    logger.info(f"CONFIG_CHANGE: {json.dumps(audit_entry)}")
    
    # Store in DynamoDB audit table (optional)
    audit_table.put_item(Item=audit_entry)
```

### Configuration Validation

Validate configuration changes before applying:

```python
def validate_configuration(config_key, config_value):
    """Validate configuration values before storing."""
    validators = {
        'forwarding_enabled': lambda x: isinstance(x, bool),
        'data_retention_days': lambda x: isinstance(x, int) and 1 <= x <= 3650,
        'ruuvi_cloud_timeout': lambda x: isinstance(x, int) and 5 <= x <= 25,
        'batch_size': lambda x: isinstance(x, int) and 1 <= x <= 100,
        'max_retries': lambda x: isinstance(x, int) and 0 <= x <= 10,
        'circuit_breaker_threshold': lambda x: isinstance(x, int) and 1 <= x <= 20
    }
    
    validator = validators.get(config_key)
    if validator and not validator(config_value):
        raise ValueError(f"Invalid value for {config_key}: {config_value}")
    
    return True
```

## Configuration Best Practices

### Change Management

1. **Test in Development First**
   - Always test configuration changes in development environment
   - Verify impact on system behavior
   - Monitor for unexpected side effects

2. **Gradual Rollout**
   - Apply changes to staging before production
   - Monitor system metrics after changes
   - Have rollback plan ready

3. **Documentation**
   - Document all configuration changes
   - Include rationale for changes
   - Update operational procedures

### Security Considerations

1. **Access Control**
   - Use admin API keys for configuration changes
   - Implement proper IAM policies
   - Audit configuration access regularly

2. **Validation**
   - Validate all configuration values
   - Sanitize input data
   - Use type checking and range validation

3. **Audit Trail**
   - Log all configuration changes
   - Include user identification
   - Store audit logs securely

### Performance Optimization

1. **Caching Strategy**
   - Use appropriate cache TTL values
   - Implement cache invalidation when needed
   - Monitor cache hit rates

2. **Batch Updates**
   - Group related configuration changes
   - Use batch operations for multiple updates
   - Minimize DynamoDB write operations

3. **Configuration Polling**
   - Use efficient polling strategies
   - Implement exponential backoff
   - Cache configuration locally

## Troubleshooting Configuration Issues

### Common Problems

#### Configuration Changes Not Taking Effect

**Symptoms**: Changes made via API don't affect system behavior

**Diagnosis**:
```bash
# Check if configuration was stored
aws dynamodb get-item \
  --table-name ruuvi-api-prod-config \
  --key '{"config_key": {"S": "forwarding_enabled"}}'

# Check Lambda function logs for configuration reads
aws logs filter-log-events \
  --log-group-name /aws/lambda/ruuvi-api-prod-proxy \
  --filter-pattern "CONFIG"
```

**Solutions**:
- Wait up to 5 minutes for cache expiration
- Restart Lambda functions to clear cache
- Verify configuration table permissions

#### Invalid Configuration Values

**Symptoms**: Configuration API returns validation errors

**Diagnosis**:
```bash
# Check configuration validation logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/ruuvi-api-prod-config \
  --filter-pattern "VALIDATION_ERROR"
```

**Solutions**:
- Verify value types and ranges
- Check configuration schema
- Use proper JSON formatting

#### Configuration Table Access Issues

**Symptoms**: Cannot read or write configuration

**Diagnosis**:
```bash
# Check IAM permissions
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::ACCOUNT:role/ruuvi-api-prod-lambda-role \
  --action-names dynamodb:GetItem,dynamodb:PutItem \
  --resource-arns arn:aws:dynamodb:REGION:ACCOUNT:table/ruuvi-api-prod-config
```

**Solutions**:
- Verify Lambda execution role permissions
- Check DynamoDB table policies
- Ensure table exists and is accessible

### Emergency Configuration Reset

If configuration becomes corrupted or causes system issues:

1. **Disable Problematic Features**
   ```bash
   # Disable forwarding immediately
   aws dynamodb put-item \
     --table-name ruuvi-api-prod-config \
     --item '{
       "config_key": {"S": "forwarding_enabled"},
       "config_value": {"BOOL": false},
       "last_updated": {"N": "'$(date +%s)'"},
       "updated_by": {"S": "emergency-reset"}
     }'
   ```

2. **Reset to Default Values**
   ```bash
   # Use backup script to restore known good configuration
   python restore_config.py prod config-backup-20241201.json
   ```

3. **Clear Lambda Cache**
   ```bash
   # Update Lambda environment variable to force cache clear
   aws lambda update-function-configuration \
     --function-name ruuvi-api-prod-proxy \
     --environment Variables='{CONFIG_CACHE_BUST="'$(date +%s)'"}'
   ```

## Configuration Templates

### Basic Configuration Template

```json
{
  "forwarding_enabled": true,
  "data_retention_days": 90,
  "ruuvi_cloud_endpoint": "https://network.ruuvi.com/api/v1",
  "ruuvi_cloud_timeout": 25,
  "batch_size": 25,
  "max_retries": 3,
  "circuit_breaker_threshold": 5
}
```

### High-Performance Configuration Template

```json
{
  "forwarding_enabled": true,
  "data_retention_days": 30,
  "ruuvi_cloud_endpoint": "https://network.ruuvi.com/api/v1",
  "ruuvi_cloud_timeout": 20,
  "batch_size": 50,
  "max_retries": 2,
  "circuit_breaker_threshold": 3
}
```

### Conservative Configuration Template

```json
{
  "forwarding_enabled": true,
  "data_retention_days": 180,
  "ruuvi_cloud_endpoint": "https://network.ruuvi.com/api/v1",
  "ruuvi_cloud_timeout": 30,
  "batch_size": 10,
  "max_retries": 5,
  "circuit_breaker_threshold": 10
}
```

## Automation and Integration

### Configuration as Code

Store configuration in version control:

```yaml
# config/prod.yaml
forwarding_enabled: true
data_retention_days: 90
ruuvi_cloud_endpoint: "https://network.ruuvi.com/api/v1"
ruuvi_cloud_timeout: 25
batch_size: 25
max_retries: 3
circuit_breaker_threshold: 5
```

### CI/CD Integration

```bash
#!/bin/bash
# deploy-config.sh

ENVIRONMENT=$1
CONFIG_FILE="config/${ENVIRONMENT}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Validate configuration
python scripts/validate_config.py "$CONFIG_FILE"

# Apply configuration
python scripts/update_config.py "$ENVIRONMENT" "$CONFIG_FILE"

echo "Configuration deployed for environment: $ENVIRONMENT"
```

### Monitoring Integration

```python
def send_config_alert(config_key, old_value, new_value):
    """Send alert when critical configuration changes."""
    critical_configs = ['forwarding_enabled', 'data_retention_days']
    
    if config_key in critical_configs:
        sns_client.publish(
            TopicArn='arn:aws:sns:region:account:ruuvi-api-alerts',
            Subject=f'Critical Configuration Change: {config_key}',
            Message=f'Configuration {config_key} changed from {old_value} to {new_value}'
        )
```

This comprehensive configuration management approach ensures reliable, auditable, and maintainable operation of the Ruuvi API proxy system.