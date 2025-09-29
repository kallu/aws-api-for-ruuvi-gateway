# Ruuvi API Deployment Guide

This guide covers the deployment process for the Ruuvi API proxy system across different environments.

## Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.11+ installed
- Required Python packages: `pip install -r requirements.txt`
- Access to the target AWS account and region

## Required AWS Permissions

The deployment user/role needs the following permissions:

- CloudFormation: Full access for stack management
- Lambda: Create, update, and manage functions
- API Gateway: Create and manage REST APIs
- DynamoDB: Create and manage tables
- IAM: Create roles and policies for Lambda functions
- S3: Create buckets and upload objects
- CloudWatch: Create log groups and alarms
- Route53: Manage DNS records (if using custom domain)
- ACM: Access to SSL certificates

## Environment Configuration

The system supports three environments: `dev`, `staging`, and `prod`. Each environment has its own configuration file in the `config/` directory.

### Configuration Files

- `config/dev.json` - Development environment settings
- `config/staging.json` - Staging environment settings  
- `config/prod.json` - Production environment settings

### Configuration Parameters

```json
{
  "CustomDomain": "carriagereturn.nl",
  "CustomCertARN": "arn:aws:acm:eu-west-1:430997289407:certificate/...",
  "RuuviCloudAPIEndpoint": "https://network.ruuvi.com/api/v1",
  "ProxyStageName": "dev|staging|prod",
  "EnableCognitoAuth": "true|false",
  "CognitoUserPoolName": "ruuvi-api-users-{env}",
  "DataRetentionDays": 30,
  "LambdaCodeBucket": "ruuvi-api-lambda-{env}-{region}",
  "LambdaCodeKey": "lambda-functions.zip"
}
```

## Deployment Process

### Quick Deployment

For development environment:
```bash
make deploy-dev
```

For staging environment:
```bash
make deploy-staging
```

For production environment:
```bash
make deploy-prod
```

### Manual Deployment Steps

1. **Package Lambda Functions**
   ```bash
   make package
   ```

2. **Deploy to Specific Environment**
   ```bash
   python scripts/deploy.py dev
   # or
   python scripts/deploy.py staging --region eu-west-1
   ```

### Deployment Script Features

The deployment script (`scripts/deploy.py`) handles:

- **Lambda Packaging**: Automatically packages all Lambda functions with dependencies
- **S3 Management**: Creates S3 buckets and uploads Lambda packages
- **CloudFormation**: Validates and deploys/updates the stack
- **Environment Configuration**: Uses environment-specific parameters
- **Rollback Information**: Creates rollback files for easy recovery
- **Output Display**: Shows important stack outputs after deployment

## Stack Outputs

After successful deployment, the following outputs are available:

- **ProxyURI**: Main API endpoint URL
- **GatewayApiKeyId**: API key for Ruuvi Gateway devices
- **AdminApiKeyId**: Admin API key for configuration management
- **CognitoUserPoolId**: User pool ID (if Cognito is enabled)
- **DashboardURL**: CloudWatch dashboard URL
- **Function Names**: Lambda function names for monitoring

## Monitoring and Logging

### CloudWatch Dashboard

Each deployment creates a CloudWatch dashboard at:
```
https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#dashboards:name=ruuvi-api-{env}-dashboard
```

### Log Groups

- `/aws/lambda/ruuvi-api-{env}-proxy` - Proxy function logs
- `/aws/lambda/ruuvi-api-{env}-retrieve` - Retrieve function logs
- `/aws/lambda/ruuvi-api-{env}-config` - Config function logs

### Viewing Logs

```bash
# Development environment logs
make logs-proxy-dev
make logs-retrieve-dev
make logs-config-dev

# Manual log viewing
aws logs tail /aws/lambda/ruuvi-api-dev-proxy --follow
```

### Stack Status

Check deployment status:
```bash
make status-dev
make status-staging
make status-prod
```

## Rollback Procedures

### Creating Rollback Script

```bash
make rollback
```

This creates `scripts/rollback.py` for emergency rollbacks.

### Performing Rollback

1. **Find Rollback File**
   ```bash
   ls rollback/
   ```

2. **Execute Rollback**
   ```bash
   python scripts/rollback.py rollback/dev-20241201-143022.json
   ```

### Manual Rollback

If automated rollback fails:

1. **Identify Previous Version**
   ```bash
   aws s3api list-object-versions --bucket ruuvi-api-lambda-dev-eu-west-1 --prefix lambda-functions.zip
   ```

2. **Update Stack with Previous Version**
   ```bash
   aws cloudformation update-stack \
     --stack-name ruuvi-api-dev \
     --use-previous-template \
     --parameters ParameterKey=LambdaCodeKey,ParameterValue=lambda-functions.zip?versionId=PREVIOUS_VERSION_ID
   ```

## Troubleshooting

### Common Issues

1. **S3 Bucket Creation Fails**
   - Check bucket naming conflicts
   - Verify AWS permissions
   - Ensure region is correct

2. **Lambda Package Too Large**
   - Check dependencies in requirements.txt
   - Remove unnecessary packages
   - Consider using Lambda layers for large dependencies

3. **CloudFormation Stack Update Fails**
   - Check template validation
   - Review parameter values
   - Check for resource conflicts

4. **API Gateway Custom Domain Issues**
   - Verify SSL certificate ARN
   - Check Route53 hosted zone
   - Ensure certificate is in correct region

### Debug Commands

```bash
# Validate template
make validate

# Check stack events
aws cloudformation describe-stack-events --stack-name ruuvi-api-dev

# Check Lambda function status
aws lambda get-function --function-name ruuvi-api-dev-proxy

# Test API endpoints
curl -H "x-api-key: YOUR_API_KEY" https://ruuvi-api-dev.carriagereturn.nl/api/v1/local/devices
```

### Log Analysis

Common log patterns to look for:

- **Proxy Function**: Ruuvi Cloud API connection issues
- **Retrieve Function**: DynamoDB query performance
- **Config Function**: Configuration update validation

## Security Considerations

### API Keys

- Gateway API keys are automatically generated during deployment
- Admin API keys have elevated permissions for configuration management
- Store API keys securely and rotate regularly

### Network Security

- All API endpoints use HTTPS only
- API Gateway has rate limiting configured
- Lambda functions have minimal IAM permissions

### Data Protection

- DynamoDB tables have encryption at rest enabled
- Point-in-time recovery is enabled for data tables
- TTL is configured for automatic data cleanup

## Cost Optimization

### Monitoring Costs

- Use CloudWatch billing alarms
- Monitor DynamoDB consumption
- Review Lambda execution metrics

### Optimization Tips

- Adjust Lambda memory allocation based on performance metrics
- Use DynamoDB on-demand billing for unpredictable workloads
- Configure appropriate data retention periods
- Monitor and optimize API Gateway usage

## Maintenance

### Regular Tasks

1. **Monitor Stack Health**
   - Check CloudWatch alarms
   - Review error rates and performance metrics
   - Validate backup and recovery procedures

2. **Update Dependencies**
   - Keep Lambda runtime updated
   - Update Python dependencies regularly
   - Test updates in development first

3. **Security Updates**
   - Rotate API keys periodically
   - Review IAM permissions
   - Update SSL certificates before expiration

### Automated Maintenance

Consider setting up:
- Automated dependency updates
- Regular backup verification
- Performance monitoring alerts
- Cost optimization reviews

## Support and Documentation

For additional support:
- Check CloudWatch logs for detailed error information
- Review AWS service health dashboard
- Consult AWS documentation for service-specific issues
- Use AWS Support for critical production issues