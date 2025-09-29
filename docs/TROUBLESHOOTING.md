# Troubleshooting Guide

This guide helps diagnose and resolve common issues with the Ruuvi API proxy system.

## Quick Diagnostic Checklist

Before diving into specific issues, run through this quick checklist:

1. **Check System Status**
   ```bash
   # Check stack status
   aws cloudformation describe-stacks --stack-name ruuvi-api-prod --query 'Stacks[0].StackStatus'
   
   # Check recent alarms
   aws cloudwatch describe-alarms --state-value ALARM --query 'MetricAlarms[?StateUpdatedTimestamp>=`2024-01-01`]'
   ```

2. **Verify API Connectivity**
   ```bash
   # Test basic connectivity
   curl -I https://ruuvi-api-prod.carriagereturn.nl/api/v1/local/devices
   ```

3. **Check Recent Logs**
   ```bash
   # Check proxy function logs (last 1 hour)
   aws logs filter-log-events \
     --log-group-name /aws/lambda/ruuvi-api-prod-proxy \
     --start-time $(date -d '1 hour ago' +%s)000
   ```

## Common Issues and Solutions

### 1. Gateway Cannot Send Data

#### Symptoms
- Gateway logs show connection errors
- No data appearing in local storage
- HTTP 4xx or 5xx errors from gateway

#### Diagnostic Steps

1. **Check API Key**
   ```bash
   # Get API key value
   aws apigateway get-api-key --api-key YOUR_API_KEY_ID --include-value
   ```

2. **Test API Endpoint**
   ```bash
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

3. **Check Proxy Function Logs**
   ```bash
   aws logs tail /aws/lambda/ruuvi-api-prod-proxy --follow
   ```

#### Common Solutions

**Invalid API Key (401/403 errors)**
- Verify API key is correct and hasn't expired
- Check API key permissions in API Gateway
- Regenerate API key if necessary

**Network Connectivity Issues**
- Verify gateway can reach the internet
- Check firewall rules on gateway network
- Test DNS resolution: `nslookup ruuvi-api-prod.carriagereturn.nl`

**Rate Limiting (429 errors)**
- Check API Gateway usage plan limits
- Implement exponential backoff in gateway
- Consider increasing rate limits if needed

**Data Format Issues (400 errors)**
- Verify request format matches Ruuvi Cloud API spec
- Check Content-Type header is set to `application/json`
- Validate JSON structure and required fields

### 2. Local Data Access Issues

#### Symptoms
- Web clients cannot retrieve data
- Empty responses from data endpoints
- Authentication errors for admin operations

#### Diagnostic Steps

1. **Check Admin API Key**
   ```bash
   # Test admin endpoints
   curl -H "x-api-key: YOUR_ADMIN_API_KEY" \
        https://ruuvi-api-prod.carriagereturn.nl/api/v1/local/devices
   ```

2. **Verify Data Storage**
   ```bash
   # Check DynamoDB table
   aws dynamodb scan --table-name ruuvi-api-prod-sensor-data --limit 5
   ```

3. **Check Retrieve Function Logs**
   ```bash
   aws logs tail /aws/lambda/ruuvi-api-prod-retrieve --follow
   ```

#### Common Solutions

**No Data Returned**
- Verify data is being stored: check DynamoDB table contents
- Check time range parameters in historical queries
- Ensure device_id exists in the system

**Authentication Issues**
- Use admin API key (not gateway API key) for data access
- Verify API key has proper permissions
- Check API key hasn't expired

**Performance Issues**
- Reduce query time ranges for large datasets
- Use pagination for large result sets
- Check DynamoDB read capacity and throttling

### 3. Forwarding to Ruuvi Cloud Issues

#### Symptoms
- Data stored locally but not appearing in Ruuvi Cloud
- Forwarding errors in proxy logs
- Inconsistent forwarding behavior

#### Diagnostic Steps

1. **Check Forwarding Configuration**
   ```bash
   curl -H "x-api-key: YOUR_ADMIN_API_KEY" \
        https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding
   ```

2. **Test Ruuvi Cloud Connectivity**
   ```bash
   # Test direct connection to Ruuvi Cloud
   curl -I https://network.ruuvi.com/api/v1
   ```

3. **Check Proxy Logs for Forwarding Errors**
   ```bash
   aws logs filter-log-events \
     --log-group-name /aws/lambda/ruuvi-api-prod-proxy \
     --filter-pattern "ERROR" \
     --start-time $(date -d '1 hour ago' +%s)000
   ```

#### Common Solutions

**Forwarding Disabled**
- Enable forwarding via configuration API
- Verify configuration is being read correctly

**Ruuvi Cloud API Issues**
- Check Ruuvi Cloud service status
- Verify original API key works with Ruuvi Cloud directly
- Check for API changes or deprecations

**Network/Timeout Issues**
- Increase Lambda timeout if needed
- Check Lambda function's internet connectivity
- Verify NAT Gateway/Internet Gateway configuration

### 4. Performance Issues

#### Symptoms
- Slow API responses
- Lambda function timeouts
- High error rates

#### Diagnostic Steps

1. **Check Lambda Metrics**
   ```bash
   # Check function duration
   aws cloudwatch get-metric-statistics \
     --namespace AWS/Lambda \
     --metric-name Duration \
     --dimensions Name=FunctionName,Value=ruuvi-api-prod-proxy \
     --start-time $(date -d '1 hour ago' --iso-8601) \
     --end-time $(date --iso-8601) \
     --period 300 \
     --statistics Average,Maximum
   ```

2. **Check DynamoDB Metrics**
   ```bash
   # Check DynamoDB throttling
   aws cloudwatch get-metric-statistics \
     --namespace AWS/DynamoDB \
     --metric-name ThrottledRequests \
     --dimensions Name=TableName,Value=ruuvi-api-prod-sensor-data \
     --start-time $(date -d '1 hour ago' --iso-8601) \
     --end-time $(date --iso-8601) \
     --period 300 \
     --statistics Sum
   ```

3. **Analyze Function Logs**
   ```bash
   # Look for performance patterns
   aws logs filter-log-events \
     --log-group-name /aws/lambda/ruuvi-api-prod-proxy \
     --filter-pattern "[timestamp, requestId, level=ERROR]" \
     --start-time $(date -d '1 hour ago' +%s)000
   ```

#### Common Solutions

**Lambda Timeout Issues**
- Increase Lambda timeout (max 15 minutes)
- Optimize function code for better performance
- Check for inefficient database queries

**DynamoDB Throttling**
- Switch to on-demand billing mode
- Optimize query patterns
- Add appropriate indexes

**Memory Issues**
- Increase Lambda memory allocation
- Monitor memory usage patterns
- Optimize data processing logic

**Cold Start Issues**
- Consider provisioned concurrency for critical functions
- Optimize function initialization code
- Use connection pooling where appropriate

### 5. Configuration Management Issues

#### Symptoms
- Configuration changes not taking effect
- Unable to update forwarding settings
- Configuration API errors

#### Diagnostic Steps

1. **Check Configuration Table**
   ```bash
   aws dynamodb scan --table-name ruuvi-api-prod-config
   ```

2. **Test Configuration API**
   ```bash
   # Get current config
   curl -H "x-api-key: YOUR_ADMIN_API_KEY" \
        https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding
   
   # Update config
   curl -X PUT \
     -H "x-api-key: YOUR_ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"enabled": true}' \
     https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding
   ```

3. **Check Config Function Logs**
   ```bash
   aws logs tail /aws/lambda/ruuvi-api-prod-config --follow
   ```

#### Common Solutions

**Configuration Not Persisting**
- Check DynamoDB write permissions
- Verify configuration table exists and is accessible
- Check for validation errors in config function

**Cache Issues**
- Configuration changes may take up to 5 minutes to take effect due to caching
- Restart Lambda functions if immediate effect needed
- Check cache TTL settings

**Permission Issues**
- Verify admin API key has configuration permissions
- Check IAM roles for config function
- Ensure proper API Gateway method permissions

### 6. Monitoring and Alerting Issues

#### Symptoms
- Missing CloudWatch metrics
- Alarms not triggering
- Dashboard showing no data

#### Diagnostic Steps

1. **Check CloudWatch Dashboard**
   ```bash
   # Get dashboard URL from stack outputs
   aws cloudformation describe-stacks \
     --stack-name ruuvi-api-prod \
     --query 'Stacks[0].Outputs[?OutputKey==`DashboardURL`].OutputValue' \
     --output text
   ```

2. **Verify Alarm Configuration**
   ```bash
   aws cloudwatch describe-alarms --alarm-names ruuvi-api-prod-proxy-function-errors
   ```

3. **Check Custom Metrics**
   ```bash
   aws cloudwatch list-metrics --namespace RuuviAPI
   ```

#### Common Solutions

**Missing Metrics**
- Verify Lambda functions are publishing custom metrics
- Check CloudWatch permissions in Lambda execution role
- Ensure metric namespace is correct

**Alarms Not Triggering**
- Check alarm thresholds and evaluation periods
- Verify alarm actions (SNS topics, etc.)
- Test alarm manually with put-metric-data

**Dashboard Issues**
- Verify dashboard JSON configuration
- Check metric names and dimensions
- Ensure proper time ranges are set

## Advanced Troubleshooting

### Lambda Function Debugging

1. **Enable X-Ray Tracing**
   ```bash
   aws lambda update-function-configuration \
     --function-name ruuvi-api-prod-proxy \
     --tracing-config Mode=Active
   ```

2. **Add Debug Logging**
   ```python
   import logging
   logging.getLogger().setLevel(logging.DEBUG)
   ```

3. **Use Lambda Insights**
   - Enable Lambda Insights for performance monitoring
   - Analyze memory usage, CPU utilization, and network activity

### DynamoDB Debugging

1. **Enable Point-in-Time Recovery**
   ```bash
   aws dynamodb update-continuous-backups \
     --table-name ruuvi-api-prod-sensor-data \
     --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
   ```

2. **Monitor Table Metrics**
   ```bash
   # Check consumed capacity
   aws dynamodb describe-table --table-name ruuvi-api-prod-sensor-data \
     --query 'Table.BillingModeSummary'
   ```

3. **Analyze Access Patterns**
   - Use DynamoDB Contributor Insights
   - Review query patterns and optimize indexes

### Network Debugging

1. **VPC Flow Logs** (if using VPC)
   ```bash
   aws ec2 create-flow-logs \
     --resource-type VPC \
     --resource-ids vpc-12345678 \
     --traffic-type ALL \
     --log-destination-type cloud-watch-logs \
     --log-group-name VPCFlowLogs
   ```

2. **DNS Resolution Testing**
   ```bash
   # Test from Lambda environment
   nslookup network.ruuvi.com
   dig network.ruuvi.com
   ```

3. **SSL Certificate Verification**
   ```bash
   # Check certificate validity
   openssl s_client -connect ruuvi-api-prod.carriagereturn.nl:443 -servername ruuvi-api-prod.carriagereturn.nl
   ```

## Log Analysis Patterns

### Common Log Patterns to Look For

1. **Authentication Errors**
   ```
   ERROR: Invalid API key
   ERROR: Missing x-api-key header
   ERROR: API key not found
   ```

2. **Data Validation Errors**
   ```
   ERROR: Invalid JSON format
   ERROR: Missing required field: data.timestamp
   ERROR: Invalid device_id format
   ```

3. **External Service Errors**
   ```
   ERROR: Ruuvi Cloud API timeout
   ERROR: Failed to forward to Ruuvi Cloud
   WARNING: Ruuvi Cloud returned 5xx error
   ```

4. **Database Errors**
   ```
   ERROR: DynamoDB throttling
   ERROR: Failed to write to sensor data table
   ERROR: Configuration read failed
   ```

### Log Analysis Commands

```bash
# Find all errors in the last hour
aws logs filter-log-events \
  --log-group-name /aws/lambda/ruuvi-api-prod-proxy \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s)000

# Find specific error patterns
aws logs filter-log-events \
  --log-group-name /aws/lambda/ruuvi-api-prod-proxy \
  --filter-pattern "[timestamp, requestId, level=ERROR, message=\"*timeout*\"]" \
  --start-time $(date -d '1 hour ago' +%s)000

# Count errors by type
aws logs filter-log-events \
  --log-group-name /aws/lambda/ruuvi-api-prod-proxy \
  --filter-pattern "ERROR" \
  --start-time $(date -d '24 hours ago' +%s)000 \
  | jq -r '.events[].message' | sort | uniq -c | sort -nr
```

## Performance Optimization

### Lambda Optimization

1. **Memory Allocation**
   - Monitor memory usage and adjust accordingly
   - Higher memory = more CPU power
   - Find the sweet spot for cost vs performance

2. **Connection Pooling**
   ```python
   # Reuse connections outside handler
   import boto3
   dynamodb = boto3.resource('dynamodb')
   
   def lambda_handler(event, context):
       # Use existing connection
       pass
   ```

3. **Provisioned Concurrency**
   ```bash
   aws lambda put-provisioned-concurrency-config \
     --function-name ruuvi-api-prod-proxy \
     --qualifier $LATEST \
     --provisioned-concurrency-units 10
   ```

### DynamoDB Optimization

1. **Query Optimization**
   - Use appropriate indexes
   - Limit result sets with pagination
   - Use projection expressions to reduce data transfer

2. **Batch Operations**
   ```python
   # Use batch_writer for multiple items
   with table.batch_writer() as batch:
       for item in items:
           batch.put_item(Item=item)
   ```

3. **Auto Scaling**
   ```bash
   aws application-autoscaling register-scalable-target \
     --service-namespace dynamodb \
     --resource-id table/ruuvi-api-prod-sensor-data \
     --scalable-dimension dynamodb:table:WriteCapacityUnits \
     --min-capacity 5 \
     --max-capacity 100
   ```

## Emergency Procedures

### System Outage Response

1. **Immediate Assessment**
   ```bash
   # Check all stack resources
   aws cloudformation describe-stack-resources --stack-name ruuvi-api-prod
   
   # Check service health
   aws cloudformation describe-stacks --stack-name ruuvi-api-prod --query 'Stacks[0].StackStatus'
   ```

2. **Enable Bypass Mode**
   ```bash
   # Disable forwarding to reduce load
   curl -X PUT \
     -H "x-api-key: YOUR_ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"enabled": false}' \
     https://ruuvi-api-prod.carriagereturn.nl/api/v1/config/forwarding
   ```

3. **Scale Resources**
   ```bash
   # Increase Lambda concurrency if needed
   aws lambda put-function-concurrency \
     --function-name ruuvi-api-prod-proxy \
     --reserved-concurrent-executions 100
   ```

### Data Recovery

1. **Point-in-Time Recovery**
   ```bash
   # Restore DynamoDB table to specific time
   aws dynamodb restore-table-to-point-in-time \
     --source-table-name ruuvi-api-prod-sensor-data \
     --target-table-name ruuvi-api-prod-sensor-data-restored \
     --restore-date-time 2024-01-01T12:00:00Z
   ```

2. **Backup Verification**
   ```bash
   # List available backups
   aws dynamodb list-backups --table-name ruuvi-api-prod-sensor-data
   ```

### Rollback Procedures

1. **Identify Rollback Point**
   ```bash
   ls rollback/
   cat rollback/prod-20241201-143022.json
   ```

2. **Execute Rollback**
   ```bash
   python scripts/rollback.py rollback/prod-20241201-143022.json
   ```

3. **Verify Rollback**
   ```bash
   # Check stack status
   aws cloudformation describe-stacks --stack-name ruuvi-api-prod
   
   # Test functionality
   curl -H "x-api-key: YOUR_API_KEY" \
        https://ruuvi-api-prod.carriagereturn.nl/api/v1/local/devices
   ```

## Getting Help

### Internal Resources

1. **Check Documentation**
   - Review API documentation
   - Check deployment guide
   - Consult architecture documentation

2. **Log Analysis**
   - Use CloudWatch Insights for complex queries
   - Check all relevant log groups
   - Look for patterns and correlations

3. **Monitoring Data**
   - Review CloudWatch dashboard
   - Check alarm history
   - Analyze performance trends

### External Resources

1. **AWS Support**
   - Use AWS Support for service-specific issues
   - Check AWS Service Health Dashboard
   - Review AWS documentation

2. **Community Resources**
   - Ruuvi community forums
   - AWS community forums
   - Stack Overflow for specific technical issues

3. **Vendor Support**
   - Contact Ruuvi support for gateway-specific issues
   - Check for firmware updates
   - Review Ruuvi Cloud API documentation

### Escalation Procedures

1. **Level 1**: Self-service troubleshooting using this guide
2. **Level 2**: Engage team members or internal experts
3. **Level 3**: Contact AWS Support or vendor support
4. **Level 4**: Emergency escalation for critical production issues

Remember to document any issues and solutions for future reference!