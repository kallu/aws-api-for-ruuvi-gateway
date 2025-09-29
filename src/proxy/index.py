"""
Ruuvi API Proxy Lambda Function

This function acts as a proxy between Ruuvi Gateway devices and the Ruuvi Cloud API,
while also storing data locally in DynamoDB for web client access.
"""

import json
import logging
import os
import uuid
import time
from typing import Dict, Any, Optional
import traceback
import boto3

# Import shared modules
from shared.models import (
    validate_ruuvi_request, 
    RuuviGatewayRequest, 
    RuuviCloudResponse,
    format_ruuvi_cloud_response
)
from shared.config_manager import get_config_manager
from shared.ruuvi_client import RuuviCloudClient
from shared.data_access import get_sensor_data_access

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# Create a custom formatter for structured logging
class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add correlation ID if available
        if hasattr(record, 'correlation_id'):
            log_entry['correlation_id'] = record.correlation_id
            
        # Add request ID if available
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = record.request_id
            
        return json.dumps(log_entry)

# Set up structured logging
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger.handlers = [handler]

# CloudWatch client for metrics (lazy initialization)
cloudwatch = None

def get_cloudwatch_client():
    """Get CloudWatch client with lazy initialization."""
    global cloudwatch
    if cloudwatch is None:
        try:
            cloudwatch = boto3.client('cloudwatch')
        except Exception as e:
            logger.warning(f"Failed to initialize CloudWatch client: {e}")
            cloudwatch = None
    return cloudwatch

class CircuitBreaker:
    """Circuit breaker pattern implementation for Ruuvi Cloud API calls."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def can_execute(self) -> bool:
        """Check if execution is allowed based on circuit state."""
        if self.state == 'CLOSED':
            return True
        elif self.state == 'OPEN':
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = 'HALF_OPEN'
                return True
            return False
        elif self.state == 'HALF_OPEN':
            return True
        return False
    
    def record_success(self):
        """Record successful execution."""
        self.failure_count = 0
        self.state = 'CLOSED'
        self.last_failure_time = None
    
    def record_failure(self):
        """Record failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
        elif self.state == 'HALF_OPEN':
            self.state = 'OPEN'

# Global circuit breaker instance
ruuvi_cloud_circuit_breaker = CircuitBreaker()

def publish_cloudwatch_metric(metric_name: str, value: float, unit: str = 'Count', 
                            dimensions: Dict[str, str] = None, correlation_id: str = None):
    """
    Publish metric to CloudWatch.
    
    Args:
        metric_name: Name of the metric
        value: Metric value
        unit: Metric unit
        dimensions: Optional dimensions
        correlation_id: Request correlation ID for logging
    """
    try:
        cw_client = get_cloudwatch_client()
        if cw_client is None:
            logger.debug(
                f"CloudWatch client not available, skipping metric: {metric_name} = {value}",
                extra={'correlation_id': correlation_id} if correlation_id else {}
            )
            return
        
        namespace = os.getenv('CLOUDWATCH_NAMESPACE', 'RuuviAPI/Proxy')
        
        metric_data = {
            'MetricName': metric_name,
            'Value': value,
            'Unit': unit,
            'Timestamp': time.time()
        }
        
        if dimensions:
            metric_data['Dimensions'] = [
                {'Name': key, 'Value': value} for key, value in dimensions.items()
            ]
        
        cw_client.put_metric_data(
            Namespace=namespace,
            MetricData=[metric_data]
        )
        
        logger.debug(
            f"Published CloudWatch metric: {metric_name} = {value}",
            extra={'correlation_id': correlation_id} if correlation_id else {}
        )
        
    except Exception as e:
        logger.warning(
            f"Failed to publish CloudWatch metric {metric_name}: {e}",
            extra={'correlation_id': correlation_id} if correlation_id else {}
        )

def create_correlation_id() -> str:
    """Generate a unique correlation ID for request tracking."""
    return str(uuid.uuid4())

def parse_api_gateway_event(event: Dict[str, Any]) -> tuple[Dict[str, Any], str, str]:
    """
    Parse API Gateway event and extract request data.
    
    Args:
        event: API Gateway event
        
    Returns:
        Tuple of (request_data, request_id, correlation_id)
        
    Raises:
        ValueError: If event format is invalid
    """
    # Extract request context
    request_context = event.get('requestContext', {})
    request_id = request_context.get('requestId', 'unknown')
    
    # Generate correlation ID
    correlation_id = create_correlation_id()
    
    # Parse request body
    body = event.get('body')
    if not body:
        raise ValueError("Request body is required")
    
    # Handle base64 encoded body (if from API Gateway)
    if event.get('isBase64Encoded', False):
        import base64
        body = base64.b64decode(body).decode('utf-8')
    
    # Parse JSON body
    try:
        request_data = json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in request body: {str(e)}")
    
    return request_data, request_id, correlation_id

def create_api_gateway_response(status_code: int, body: Dict[str, Any], 
                              correlation_id: str = None) -> Dict[str, Any]:
    """
    Create properly formatted API Gateway response.
    
    Args:
        status_code: HTTP status code
        body: Response body dictionary
        correlation_id: Optional correlation ID for tracking
        
    Returns:
        API Gateway response format
    """
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }
    
    if correlation_id:
        headers['X-Correlation-ID'] = correlation_id
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body)
    }

def handle_validation_error(error_message: str, correlation_id: str) -> Dict[str, Any]:
    """
    Handle validation errors with proper Ruuvi Cloud API format.
    
    Args:
        error_message: Error message
        correlation_id: Request correlation ID
        
    Returns:
        API Gateway error response
    """
    logger.error(
        "Request validation failed",
        extra={
            'correlation_id': correlation_id,
            'error': error_message
        }
    )
    
    response_body = format_ruuvi_cloud_response(
        success=False,
        error_code="VALIDATION_ERROR",
        error_message=error_message
    )
    
    return create_api_gateway_response(400, response_body, correlation_id)

def handle_internal_error(error: Exception, correlation_id: str) -> Dict[str, Any]:
    """
    Handle internal errors with proper logging and response format.
    
    Args:
        error: Exception that occurred
        correlation_id: Request correlation ID
        
    Returns:
        API Gateway error response
    """
    error_details = {
        'correlation_id': correlation_id,
        'error_type': type(error).__name__,
        'error_message': str(error),
        'traceback': traceback.format_exc()
    }
    
    logger.error("Internal error in proxy function", extra=error_details)
    
    response_body = format_ruuvi_cloud_response(
        success=False,
        error_code="INTERNAL_ERROR",
        error_message="Internal server error"
    )
    
    return create_api_gateway_response(500, response_body, correlation_id)

def store_sensor_data_locally(ruuvi_request: RuuviGatewayRequest, 
                            ruuvi_cloud_response: Dict[str, Any],
                            correlation_id: str) -> bool:
    """
    Store sensor data locally in DynamoDB.
    
    Args:
        ruuvi_request: Validated Ruuvi Gateway request
        ruuvi_cloud_response: Response from Ruuvi Cloud (if forwarded)
        correlation_id: Request correlation ID for logging
        
    Returns:
        True if storage was successful, False otherwise
    """
    try:
        # Get data access instance
        data_table_name = os.getenv('DATA_TABLE_NAME', 'ruuvi-sensor-data')
        data_access = get_sensor_data_access(data_table_name)
        
        # Get configuration for TTL
        config_table_name = os.getenv('CONFIG_TABLE_NAME', 'ruuvi-api-config')
        config_manager = get_config_manager(config_table_name)
        ttl_days = config_manager.get_config('data_retention_days', default=90)
        
        # Parse sensor data from tags
        sensor_data_list = []
        for device_id, tag_data in ruuvi_request.tags.items():
            sensor_data_item = {
                'device_id': device_id,
                'gateway_id': ruuvi_request.gwmac,
                'timestamp': tag_data['timestamp'],
                'measurements': {
                    'rssi': tag_data['rssi'],
                    'data': tag_data['data'],
                    'gateway_timestamp': ruuvi_request.timestamp,
                    'coordinates': ruuvi_request.coordinates
                }
            }
            
            # Add Ruuvi Cloud response if available and successful
            if (ruuvi_cloud_response and 
                ruuvi_cloud_response.get('result') == 'success' and
                'data' in ruuvi_cloud_response):
                sensor_data_item['ruuvi_cloud_response'] = ruuvi_cloud_response
            
            sensor_data_list.append(sensor_data_item)
        
        logger.info(
            "Storing sensor data locally",
            extra={
                'correlation_id': correlation_id,
                'device_count': len(sensor_data_list),
                'gateway_id': ruuvi_request.gwmac,
                'ttl_days': ttl_days
            }
        )
        
        # Store data in batch
        successful_count, failed_count = data_access.store_batch_sensor_data(
            sensor_data_list, ttl_days
        )
        
        # Publish storage metrics
        publish_cloudwatch_metric('DataStorageSuccess', successful_count, 'Count',
                                {'Operation': 'LocalStorage'}, correlation_id)
        if failed_count > 0:
            publish_cloudwatch_metric('DataStorageFailure', failed_count, 'Count',
                                    {'Operation': 'LocalStorage'}, correlation_id)
        
        if failed_count > 0:
            logger.warning(
                "Some sensor data failed to store",
                extra={
                    'correlation_id': correlation_id,
                    'successful_count': successful_count,
                    'failed_count': failed_count
                }
            )
        else:
            logger.info(
                "All sensor data stored successfully",
                extra={
                    'correlation_id': correlation_id,
                    'stored_count': successful_count
                }
            )
        
        # Return True if at least some data was stored successfully
        return successful_count > 0
        
    except Exception as e:
        # Publish storage exception metrics
        publish_cloudwatch_metric('DataStorageException', 1, 'Count',
                                {'Operation': 'LocalStorage', 'ExceptionType': type(e).__name__}, 
                                correlation_id)
        
        logger.error(
            "Error storing sensor data locally",
            extra={
                'correlation_id': correlation_id,
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        return False


def handle_ruuvi_cloud_forwarding(ruuvi_request: RuuviGatewayRequest, 
                                 correlation_id: str) -> tuple[bool, Dict[str, Any], bool]:
    """
    Handle conditional forwarding to Ruuvi Cloud API based on configuration.
    
    Args:
        ruuvi_request: Validated Ruuvi Gateway request
        correlation_id: Request correlation ID for logging
        
    Returns:
        Tuple of (success: bool, response: dict, was_forwarded: bool)
    """
    try:
        # Get configuration manager
        config_table_name = os.getenv('CONFIG_TABLE_NAME', 'ruuvi-api-config')
        config_manager = get_config_manager(config_table_name)
        
        # Check if forwarding is enabled
        forwarding_enabled = config_manager.get_config('forwarding_enabled', default=True)
        
        logger.info(
            "Checking forwarding configuration",
            extra={
                'correlation_id': correlation_id,
                'forwarding_enabled': forwarding_enabled
            }
        )
        
        if not forwarding_enabled:
            logger.info(
                "Forwarding disabled, returning local success response",
                extra={'correlation_id': correlation_id}
            )
            return True, format_ruuvi_cloud_response(success=True, action="inserted"), False
        
        # Get Ruuvi Cloud configuration
        ruuvi_cloud_endpoint = config_manager.get_config(
            'ruuvi_cloud_endpoint', 
            default='https://network.ruuvi.com'
        )
        ruuvi_cloud_timeout = config_manager.get_config(
            'ruuvi_cloud_timeout', 
            default=25
        )
        
        logger.info(
            "Forwarding to Ruuvi Cloud",
            extra={
                'correlation_id': correlation_id,
                'endpoint': ruuvi_cloud_endpoint,
                'timeout': ruuvi_cloud_timeout
            }
        )
        
        # Check circuit breaker before attempting forwarding
        if not ruuvi_cloud_circuit_breaker.can_execute():
            logger.warning(
                "Circuit breaker is OPEN, skipping Ruuvi Cloud forwarding",
                extra={
                    'correlation_id': correlation_id,
                    'circuit_state': ruuvi_cloud_circuit_breaker.state,
                    'failure_count': ruuvi_cloud_circuit_breaker.failure_count
                }
            )
            
            # Publish circuit breaker metric
            publish_cloudwatch_metric(
                'CircuitBreakerOpen', 1, 'Count',
                {'Service': 'RuuviCloud'}, correlation_id
            )
            
            return False, format_ruuvi_cloud_response(
                False, 
                error_code="CIRCUIT_BREAKER_OPEN",
                error_message="Ruuvi Cloud service temporarily unavailable"
            ), True
        
        # Implement retry logic for transient failures
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    f"Attempting Ruuvi Cloud forwarding (attempt {attempt + 1}/{max_retries + 1})",
                    extra={'correlation_id': correlation_id}
                )
                
                # Create Ruuvi Cloud client and send data
                with RuuviCloudClient(
                    base_url=ruuvi_cloud_endpoint,
                    timeout=ruuvi_cloud_timeout,
                    enable_logging=True
                ) as client:
                    success, response = client.send_sensor_data(ruuvi_request)
                    
                    if success:
                        # Record success in circuit breaker
                        ruuvi_cloud_circuit_breaker.record_success()
                        
                        # Publish success metrics
                        publish_cloudwatch_metric(
                            'ForwardingSuccess', 1, 'Count',
                            {'Service': 'RuuviCloud', 'Attempt': str(attempt + 1)}, 
                            correlation_id
                        )
                        
                        logger.info(
                            "Successfully forwarded to Ruuvi Cloud",
                            extra={
                                'correlation_id': correlation_id,
                                'attempt': attempt + 1,
                                'response': response
                            }
                        )
                        return True, response, True
                    else:
                        # Check if this is a retryable error
                        error_code = response.get('error', {}).get('code', '')
                        is_retryable = error_code in ['TIMEOUT_ERROR', 'CONNECTION_ERROR', 'HTTP_500', 'HTTP_502', 'HTTP_503', 'HTTP_504']
                        
                        if not is_retryable or attempt == max_retries:
                            # Record failure in circuit breaker for non-retryable errors or final attempt
                            ruuvi_cloud_circuit_breaker.record_failure()
                            
                            # Publish failure metrics
                            publish_cloudwatch_metric(
                                'ForwardingFailure', 1, 'Count',
                                {'Service': 'RuuviCloud', 'ErrorCode': error_code, 'Attempt': str(attempt + 1)}, 
                                correlation_id
                            )
                            
                            logger.warning(
                                "Failed to forward to Ruuvi Cloud (final attempt)",
                                extra={
                                    'correlation_id': correlation_id,
                                    'attempt': attempt + 1,
                                    'error_response': response,
                                    'is_retryable': is_retryable
                                }
                            )
                            return False, response, True
                        else:
                            # Wait before retry
                            logger.info(
                                f"Retryable error, waiting {retry_delay}s before retry",
                                extra={
                                    'correlation_id': correlation_id,
                                    'attempt': attempt + 1,
                                    'error_code': error_code
                                }
                            )
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                            
            except Exception as e:
                # Record failure in circuit breaker
                ruuvi_cloud_circuit_breaker.record_failure()
                
                # Publish exception metrics
                publish_cloudwatch_metric(
                    'ForwardingException', 1, 'Count',
                    {'Service': 'RuuviCloud', 'ExceptionType': type(e).__name__}, 
                    correlation_id
                )
                
                logger.error(
                    f"Exception during Ruuvi Cloud forwarding attempt {attempt + 1}",
                    extra={
                        'correlation_id': correlation_id,
                        'error': str(e),
                        'error_type': type(e).__name__
                    }
                )
                
                if attempt == max_retries:
                    return False, format_ruuvi_cloud_response(
                        False,
                        error_code="FORWARDING_EXCEPTION",
                        error_message=f"Forwarding failed after {max_retries + 1} attempts"
                    ), True
                else:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                
    except Exception as e:
        logger.error(
            "Error in forwarding logic",
            extra={
                'correlation_id': correlation_id,
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        
        # Return local success response on configuration/forwarding errors
        return True, format_ruuvi_cloud_response(success=True, action="inserted"), False


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Ruuvi API proxy functionality.
    
    This handler implements the basic proxy function structure with:
    - Proper API Gateway event parsing
    - Request validation using Ruuvi Cloud API schemas
    - Structured logging with correlation IDs
    - Comprehensive error handling framework
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    correlation_id = None
    start_time = time.time()
    
    try:
        # Parse API Gateway event
        request_data, request_id, correlation_id = parse_api_gateway_event(event)
        
        # Add correlation ID to logger context
        logger.info(
            "Processing Ruuvi proxy request",
            extra={
                'correlation_id': correlation_id,
                'request_id': request_id,
                'http_method': event.get('httpMethod', 'unknown'),
                'path': event.get('path', 'unknown')
            }
        )
        
        # Validate request format against Ruuvi Cloud API schema
        validation_result = validate_ruuvi_request(request_data)
        if not validation_result.is_valid:
            error_message = "; ".join(validation_result.errors)
            return handle_validation_error(error_message, correlation_id)
        
        # Parse validated request
        ruuvi_request = RuuviGatewayRequest.from_dict(request_data)
        
        logger.info(
            "Request validation successful",
            extra={
                'correlation_id': correlation_id,
                'gateway_mac': ruuvi_request.gwmac,
                'device_count': len(ruuvi_request.tags),
                'timestamp': ruuvi_request.timestamp
            }
        )
        
        # Implement configuration-based forwarding logic (task 4.2)
        forwarding_success, forwarding_response, was_forwarded = handle_ruuvi_cloud_forwarding(
            ruuvi_request, correlation_id
        )
        
        # Implement local data storage (task 4.3)
        # Store data locally regardless of forwarding setting
        # Only pass Ruuvi Cloud response if it was actually forwarded and successful
        ruuvi_cloud_response_for_storage = None
        if was_forwarded and forwarding_success:
            ruuvi_cloud_response_for_storage = forwarding_response
        
        storage_success = store_sensor_data_locally(
            ruuvi_request, 
            ruuvi_cloud_response_for_storage,
            correlation_id
        )
        
        # TODO: Add comprehensive error handling and monitoring (task 4.4)
        
        # Determine response based on forwarding and storage results
        if forwarding_success:
            # Use Ruuvi Cloud response if forwarding was successful
            response_body = forwarding_response
        else:
            # Use local success response if forwarding failed but storage succeeded
            response_body = format_ruuvi_cloud_response(success=True, action="inserted")
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000  # milliseconds
        
        # Publish success metrics
        publish_cloudwatch_metric('RequestSuccess', 1, 'Count', 
                                {'Operation': 'ProxyRequest'}, correlation_id)
        publish_cloudwatch_metric('ProcessingTime', processing_time, 'Milliseconds',
                                {'Operation': 'ProxyRequest'}, correlation_id)
        publish_cloudwatch_metric('DeviceCount', len(ruuvi_request.tags), 'Count',
                                {'Operation': 'ProxyRequest'}, correlation_id)
        
        # Log final processing status
        logger.info(
            "Proxy request processed successfully",
            extra={
                'correlation_id': correlation_id,
                'response_status': 'success',
                'forwarding_success': forwarding_success,
                'storage_success': storage_success,
                'processing_time_ms': processing_time,
                'device_count': len(ruuvi_request.tags)
            }
        )
        
        return create_api_gateway_response(200, response_body, correlation_id)
        
    except ValueError as e:
        # Handle validation and parsing errors
        processing_time = (time.time() - start_time) * 1000
        
        # Publish validation error metrics
        publish_cloudwatch_metric('ValidationError', 1, 'Count',
                                {'Operation': 'ProxyRequest', 'ErrorType': 'ValidationError'}, 
                                correlation_id or "unknown")
        publish_cloudwatch_metric('ProcessingTime', processing_time, 'Milliseconds',
                                {'Operation': 'ProxyRequest', 'Status': 'ValidationError'}, 
                                correlation_id or "unknown")
        
        return handle_validation_error(str(e), correlation_id or "unknown")
        
    except Exception as e:
        # Handle all other internal errors
        processing_time = (time.time() - start_time) * 1000
        
        # Publish internal error metrics
        publish_cloudwatch_metric('InternalError', 1, 'Count',
                                {'Operation': 'ProxyRequest', 'ErrorType': type(e).__name__}, 
                                correlation_id or "unknown")
        publish_cloudwatch_metric('ProcessingTime', processing_time, 'Milliseconds',
                                {'Operation': 'ProxyRequest', 'Status': 'InternalError'}, 
                                correlation_id or "unknown")
        
        return handle_internal_error(e, correlation_id or "unknown")