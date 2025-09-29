"""
Ruuvi API Local Data Retrieval Lambda Function

This function handles GET requests for retrieving locally stored sensor data,
providing endpoints for current data, historical data, and device listing.
"""

import json
import logging
import os
import time
import uuid
from typing import Dict, Any, Optional, List
import traceback
import boto3
from datetime import datetime, timedelta

# Import shared modules
from shared.data_access import get_sensor_data_access
from shared.config_manager import get_config_manager

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

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

def create_correlation_id() -> str:
    """Generate a unique correlation ID for request tracking."""
    return str(uuid.uuid4())

def parse_api_gateway_event(event: Dict[str, Any]) -> tuple[str, Dict[str, str], Dict[str, str], str, str]:
    """
    Parse API Gateway event and extract request information.
    
    Args:
        event: API Gateway event
        
    Returns:
        Tuple of (http_method, path_parameters, query_parameters, request_id, correlation_id)
        
    Raises:
        ValueError: If event format is invalid
    """
    # Extract request context
    request_context = event.get('requestContext', {})
    request_id = request_context.get('requestId', 'unknown')
    
    # Generate correlation ID
    correlation_id = create_correlation_id()
    
    # Extract HTTP method
    http_method = event.get('httpMethod', '').upper()
    if http_method != 'GET':
        raise ValueError(f"Unsupported HTTP method: {http_method}")
    
    # Extract path parameters
    path_parameters = event.get('pathParameters') or {}
    
    # Extract query parameters
    query_parameters = event.get('queryStringParameters') or {}
    
    return http_method, path_parameters, query_parameters, request_id, correlation_id

def validate_authentication(event: Dict[str, Any], correlation_id: str) -> bool:
    """
    Validate authentication for local data access.
    
    Args:
        event: API Gateway event
        correlation_id: Request correlation ID for logging
        
    Returns:
        True if authenticated, False otherwise
    """
    try:
        # Check for API key authentication
        headers = event.get('headers', {})
        api_key = headers.get('x-api-key') or headers.get('X-API-Key')
        
        if api_key:
            logger.info(
                "API key authentication detected",
                extra={'correlation_id': correlation_id}
            )
            # API Gateway handles API key validation, so if we get here it's valid
            return True
        
        # Check for Cognito authorization
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        
        if authorizer.get('claims'):
            logger.info(
                "Cognito token authentication detected",
                extra={'correlation_id': correlation_id}
            )
            return True
        
        # Check for IAM authorization
        if request_context.get('identity', {}).get('userArn'):
            logger.info(
                "IAM authentication detected",
                extra={'correlation_id': correlation_id}
            )
            return True
        
        logger.warning(
            "No valid authentication found",
            extra={'correlation_id': correlation_id}
        )
        return False
        
    except Exception as e:
        logger.error(
            "Error validating authentication",
            extra={
                'correlation_id': correlation_id,
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        return False

def validate_query_parameters(query_params: Dict[str, str], correlation_id: str) -> Dict[str, Any]:
    """
    Validate and parse query parameters for time ranges and pagination.
    
    Args:
        query_params: Query parameters from API Gateway
        correlation_id: Request correlation ID for logging
        
    Returns:
        Dictionary with validated parameters
        
    Raises:
        ValueError: If parameters are invalid
    """
    validated = {}
    
    # Validate start_time
    if 'start_time' in query_params:
        try:
            start_time = int(query_params['start_time'])
            if start_time < 0:
                raise ValueError("start_time must be a positive integer")
            validated['start_time'] = start_time
        except ValueError as e:
            raise ValueError(f"Invalid start_time parameter: {e}")
    
    # Validate end_time
    if 'end_time' in query_params:
        try:
            end_time = int(query_params['end_time'])
            if end_time < 0:
                raise ValueError("end_time must be a positive integer")
            validated['end_time'] = end_time
        except ValueError as e:
            raise ValueError(f"Invalid end_time parameter: {e}")
    
    # Validate time range logic
    if 'start_time' in validated and 'end_time' in validated:
        if validated['start_time'] >= validated['end_time']:
            raise ValueError("start_time must be less than end_time")
    
    # Validate limit
    if 'limit' in query_params:
        try:
            limit = int(query_params['limit'])
            if limit < 1 or limit > 1000:
                raise ValueError("limit must be between 1 and 1000")
            validated['limit'] = limit
        except ValueError as e:
            raise ValueError(f"Invalid limit parameter: {e}")
    else:
        validated['limit'] = 100  # Default limit
    
    # Validate next_token (for pagination)
    if 'next_token' in query_params:
        try:
            # Decode base64 next_token to get LastEvaluatedKey
            import base64
            decoded_token = base64.b64decode(query_params['next_token']).decode('utf-8')
            last_evaluated_key = json.loads(decoded_token)
            validated['last_evaluated_key'] = last_evaluated_key
        except Exception as e:
            raise ValueError(f"Invalid next_token parameter: {e}")
    
    # Validate device_ids (for multiple device queries)
    if 'device_ids' in query_params:
        device_ids = query_params['device_ids'].split(',')
        # Validate device ID format (12 uppercase hex characters)
        import re
        for device_id in device_ids:
            if not re.match(r'^[0-9A-F]{12}$', device_id.strip()):
                raise ValueError(f"Invalid device ID format: {device_id}")
        validated['device_ids'] = [d.strip() for d in device_ids]
    
    logger.debug(
        "Query parameters validated",
        extra={
            'correlation_id': correlation_id,
            'validated_params': validated
        }
    )
    
    return validated

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
        'Access-Control-Allow-Methods': 'GET,OPTIONS'
    }
    
    if correlation_id:
        headers['X-Correlation-ID'] = correlation_id
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body)
    }

def handle_authentication_error(correlation_id: str) -> Dict[str, Any]:
    """
    Handle authentication errors.
    
    Args:
        correlation_id: Request correlation ID
        
    Returns:
        API Gateway error response
    """
    logger.error(
        "Authentication failed for local data access",
        extra={'correlation_id': correlation_id}
    )
    
    response_body = {
        'error': {
            'code': 'AUTHENTICATION_REQUIRED',
            'message': 'Valid authentication is required for local data access'
        }
    }
    
    return create_api_gateway_response(401, response_body, correlation_id)

def handle_validation_error(error_message: str, correlation_id: str) -> Dict[str, Any]:
    """
    Handle validation errors.
    
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
    
    response_body = {
        'error': {
            'code': 'VALIDATION_ERROR',
            'message': error_message
        }
    }
    
    return create_api_gateway_response(400, response_body, correlation_id)

def handle_not_found_error(resource: str, correlation_id: str) -> Dict[str, Any]:
    """
    Handle resource not found errors.
    
    Args:
        resource: Resource that was not found
        correlation_id: Request correlation ID
        
    Returns:
        API Gateway error response
    """
    logger.info(
        f"Resource not found: {resource}",
        extra={'correlation_id': correlation_id}
    )
    
    response_body = {
        'error': {
            'code': 'NOT_FOUND',
            'message': f'{resource} not found'
        }
    }
    
    return create_api_gateway_response(404, response_body, correlation_id)

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
    
    logger.error("Internal error in retrieve function", extra=error_details)
    
    response_body = {
        'error': {
            'code': 'INTERNAL_ERROR',
            'message': 'Internal server error'
        }
    }
    
    return create_api_gateway_response(500, response_body, correlation_id)

def encode_next_token(last_evaluated_key: Dict[str, Any]) -> str:
    """
    Encode LastEvaluatedKey as base64 next_token for pagination.
    
    Args:
        last_evaluated_key: DynamoDB LastEvaluatedKey
        
    Returns:
        Base64 encoded next_token
    """
    import base64
    token_json = json.dumps(last_evaluated_key)
    return base64.b64encode(token_json.encode('utf-8')).decode('utf-8')

def format_current_data_response(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format sensor data for current data API response.
    
    Args:
        sensor_data: Raw sensor data from data access layer
        
    Returns:
        Formatted response data
    """
    return {
        'device_id': sensor_data['device_id'],
        'gateway_id': sensor_data['gateway_id'],
        'timestamp': sensor_data['timestamp'],
        'server_timestamp': sensor_data['server_timestamp'],
        'measurements': sensor_data['measurements'],
        'last_updated': datetime.utcfromtimestamp(sensor_data['timestamp']).isoformat() + 'Z'
    }

def handle_current_data_request(device_id: str, data_access, correlation_id: str) -> Dict[str, Any]:
    """
    Handle current data retrieval request for a single device.
    
    Args:
        device_id: Device identifier
        data_access: SensorDataAccess instance
        correlation_id: Request correlation ID
        
    Returns:
        Response body dictionary
        
    Raises:
        ValueError: If device not found
        Exception: For other errors
    """
    try:
        logger.info(
            f"Retrieving current data for device {device_id}",
            extra={'correlation_id': correlation_id, 'device_id': device_id}
        )
        
        # Get current data from data access layer
        current_data = data_access.get_current_data(device_id)
        
        if current_data is None:
            logger.info(
                f"No data found for device {device_id}",
                extra={'correlation_id': correlation_id, 'device_id': device_id}
            )
            raise ValueError(f"Device {device_id}")
        
        # Format response
        formatted_data = format_current_data_response(current_data)
        
        logger.info(
            f"Successfully retrieved current data for device {device_id}",
            extra={
                'correlation_id': correlation_id, 
                'device_id': device_id,
                'timestamp': current_data['timestamp']
            }
        )
        
        return {
            'result': 'success',
            'data': formatted_data
        }
        
    except ValueError:
        # Re-raise ValueError for not found handling
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving current data for device {device_id}",
            extra={
                'correlation_id': correlation_id,
                'device_id': device_id,
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        raise

def handle_multiple_current_data_request(device_ids: List[str], data_access, correlation_id: str) -> Dict[str, Any]:
    """
    Handle current data retrieval request for multiple devices.
    
    Args:
        device_ids: List of device identifiers
        data_access: SensorDataAccess instance
        correlation_id: Request correlation ID
        
    Returns:
        Response body dictionary
    """
    try:
        logger.info(
            f"Retrieving current data for {len(device_ids)} devices",
            extra={'correlation_id': correlation_id, 'device_count': len(device_ids)}
        )
        
        # Get current data for multiple devices
        devices_data = data_access.get_multiple_devices_current_data(device_ids)
        
        # Format response data
        formatted_devices = {}
        for device_id, sensor_data in devices_data.items():
            formatted_devices[device_id] = format_current_data_response(sensor_data)
        
        # Include devices with no data as null entries
        for device_id in device_ids:
            if device_id not in formatted_devices:
                formatted_devices[device_id] = None
        
        logger.info(
            f"Successfully retrieved current data for {len(formatted_devices)} devices ({len(devices_data)} with data)",
            extra={
                'correlation_id': correlation_id,
                'requested_devices': len(device_ids),
                'devices_with_data': len(devices_data)
            }
        )
        
        return {
            'result': 'success',
            'data': formatted_devices,
            'summary': {
                'requested_devices': len(device_ids),
                'devices_with_data': len(devices_data),
                'devices_without_data': len(device_ids) - len(devices_data)
            }
        }
        
    except Exception as e:
        logger.error(
            f"Error retrieving current data for multiple devices",
            extra={
                'correlation_id': correlation_id,
                'device_count': len(device_ids),
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        raise

def format_historical_data_response(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format sensor data for historical data API response.
    
    Args:
        sensor_data: Raw sensor data from data access layer
        
    Returns:
        Formatted response data
    """
    return {
        'device_id': sensor_data['device_id'],
        'gateway_id': sensor_data['gateway_id'],
        'timestamp': sensor_data['timestamp'],
        'server_timestamp': sensor_data['server_timestamp'],
        'measurements': sensor_data['measurements'],
        'recorded_at': datetime.utcfromtimestamp(sensor_data['timestamp']).isoformat() + 'Z'
    }

def handle_historical_data_request(device_id: str, validated_params: Dict[str, Any], 
                                 data_access, correlation_id: str) -> Dict[str, Any]:
    """
    Handle historical data retrieval request for a single device with pagination.
    
    Args:
        device_id: Device identifier
        validated_params: Validated query parameters
        data_access: SensorDataAccess instance
        correlation_id: Request correlation ID
        
    Returns:
        Response body dictionary
    """
    try:
        start_time = validated_params.get('start_time')
        end_time = validated_params.get('end_time')
        limit = validated_params.get('limit', 100)
        last_evaluated_key = validated_params.get('last_evaluated_key')
        
        logger.info(
            f"Retrieving historical data for device {device_id}",
            extra={
                'correlation_id': correlation_id,
                'device_id': device_id,
                'start_time': start_time,
                'end_time': end_time,
                'limit': limit,
                'has_pagination_token': last_evaluated_key is not None
            }
        )
        
        # Get historical data from data access layer
        result = data_access.get_historical_data(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            last_evaluated_key=last_evaluated_key
        )
        
        # Format response data
        formatted_items = [format_historical_data_response(item) for item in result['items']]
        
        response_body = {
            'result': 'success',
            'data': {
                'device_id': device_id,
                'items': formatted_items,
                'count': result['count'],
                'query_parameters': {
                    'start_time': start_time,
                    'end_time': end_time,
                    'limit': limit
                }
            }
        }
        
        # Add pagination token if there are more results
        if 'last_evaluated_key' in result:
            response_body['data']['next_token'] = encode_next_token(result['last_evaluated_key'])
            response_body['data']['has_more'] = True
        else:
            response_body['data']['has_more'] = False
        
        logger.info(
            f"Successfully retrieved {result['count']} historical records for device {device_id}",
            extra={
                'correlation_id': correlation_id,
                'device_id': device_id,
                'record_count': result['count'],
                'has_more': 'last_evaluated_key' in result
            }
        )
        
        return response_body
        
    except Exception as e:
        logger.error(
            f"Error retrieving historical data for device {device_id}",
            extra={
                'correlation_id': correlation_id,
                'device_id': device_id,
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        raise

def handle_multiple_devices_historical_data_request(device_ids: List[str], validated_params: Dict[str, Any],
                                                  data_access, correlation_id: str) -> Dict[str, Any]:
    """
    Handle historical data retrieval request for multiple devices with pagination.
    
    Args:
        device_ids: List of device identifiers
        validated_params: Validated query parameters
        data_access: SensorDataAccess instance
        correlation_id: Request correlation ID
        
    Returns:
        Response body dictionary
    """
    try:
        start_time = validated_params.get('start_time')
        end_time = validated_params.get('end_time')
        limit = validated_params.get('limit', 100)
        
        logger.info(
            f"Retrieving historical data for {len(device_ids)} devices",
            extra={
                'correlation_id': correlation_id,
                'device_count': len(device_ids),
                'start_time': start_time,
                'end_time': end_time,
                'limit': limit
            }
        )
        
        # Get historical data for each device
        devices_data = {}
        total_records = 0
        
        for device_id in device_ids:
            result = data_access.get_historical_data(
                device_id=device_id,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                last_evaluated_key=None  # No pagination for multi-device queries
            )
            
            if result['items']:
                formatted_items = [format_historical_data_response(item) for item in result['items']]
                devices_data[device_id] = {
                    'items': formatted_items,
                    'count': result['count']
                }
                total_records += result['count']
            else:
                devices_data[device_id] = {
                    'items': [],
                    'count': 0
                }
        
        response_body = {
            'result': 'success',
            'data': {
                'devices': devices_data,
                'summary': {
                    'requested_devices': len(device_ids),
                    'devices_with_data': len([d for d in devices_data.values() if d['count'] > 0]),
                    'total_records': total_records
                },
                'query_parameters': {
                    'start_time': start_time,
                    'end_time': end_time,
                    'limit': limit
                }
            }
        }
        
        logger.info(
            f"Successfully retrieved historical data for {len(device_ids)} devices ({total_records} total records)",
            extra={
                'correlation_id': correlation_id,
                'device_count': len(device_ids),
                'total_records': total_records
            }
        )
        
        return response_body
        
    except Exception as e:
        logger.error(
            f"Error retrieving historical data for multiple devices",
            extra={
                'correlation_id': correlation_id,
                'device_count': len(device_ids),
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        raise

def format_device_info_response(device_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format device information for device listing API response.
    
    Args:
        device_info: Raw device info from data access layer
        
    Returns:
        Formatted device information
    """
    return {
        'device_id': device_info['device_id'],
        'gateway_id': device_info['gateway_id'],
        'last_seen': device_info['last_seen'],
        'last_seen_server': device_info['last_seen_server'],
        'last_seen_at': datetime.utcfromtimestamp(device_info['last_seen']).isoformat() + 'Z',
        'last_seen_server_at': datetime.utcfromtimestamp(device_info['last_seen_server']).isoformat() + 'Z'
    }

def handle_device_listing_request(data_access, correlation_id: str) -> Dict[str, Any]:
    """
    Handle device listing request to get all unique devices with last seen timestamps.
    
    Args:
        data_access: SensorDataAccess instance
        correlation_id: Request correlation ID
        
    Returns:
        Response body dictionary
    """
    try:
        logger.info(
            "Retrieving device list",
            extra={'correlation_id': correlation_id}
        )
        
        # Get all devices from data access layer
        devices_info = data_access.get_all_devices()
        
        # Format response data
        formatted_devices = [format_device_info_response(device) for device in devices_info]
        
        # Group devices by gateway for additional insights
        gateways = {}
        for device in devices_info:
            gateway_id = device['gateway_id']
            if gateway_id not in gateways:
                gateways[gateway_id] = {
                    'gateway_id': gateway_id,
                    'device_count': 0,
                    'last_activity': 0
                }
            gateways[gateway_id]['device_count'] += 1
            gateways[gateway_id]['last_activity'] = max(
                gateways[gateway_id]['last_activity'],
                device['last_seen']
            )
        
        # Convert gateways dict to list and add formatted timestamps
        gateway_list = []
        for gateway_info in gateways.values():
            gateway_list.append({
                'gateway_id': gateway_info['gateway_id'],
                'device_count': gateway_info['device_count'],
                'last_activity': gateway_info['last_activity'],
                'last_activity_at': datetime.utcfromtimestamp(gateway_info['last_activity']).isoformat() + 'Z'
            })
        
        # Sort gateways by last activity (most recent first)
        gateway_list.sort(key=lambda x: x['last_activity'], reverse=True)
        
        response_body = {
            'result': 'success',
            'data': {
                'devices': formatted_devices,
                'gateways': gateway_list,
                'summary': {
                    'total_devices': len(formatted_devices),
                    'total_gateways': len(gateway_list),
                    'most_recent_activity': max([d['last_seen'] for d in devices_info]) if devices_info else None
                }
            }
        }
        
        # Add formatted timestamp for most recent activity
        if response_body['data']['summary']['most_recent_activity']:
            response_body['data']['summary']['most_recent_activity_at'] = datetime.utcfromtimestamp(
                response_body['data']['summary']['most_recent_activity']
            ).isoformat() + 'Z'
        
        logger.info(
            f"Successfully retrieved device list with {len(formatted_devices)} devices from {len(gateway_list)} gateways",
            extra={
                'correlation_id': correlation_id,
                'device_count': len(formatted_devices),
                'gateway_count': len(gateway_list)
            }
        )
        
        return response_body
        
    except Exception as e:
        logger.error(
            "Error retrieving device list",
            extra={
                'correlation_id': correlation_id,
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        raise

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for local data retrieval functionality.
    
    This handler implements the local data retrieval function structure with:
    - Lambda handler for GET requests with path parameter parsing
    - Authentication validation for local data access
    - Query parameter validation for time ranges and pagination
    
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
        http_method, path_params, query_params, request_id, correlation_id = parse_api_gateway_event(event)
        
        # Add correlation ID to logger context
        logger.info(
            "Processing local data retrieval request",
            extra={
                'correlation_id': correlation_id,
                'request_id': request_id,
                'http_method': http_method,
                'path': event.get('path', 'unknown'),
                'path_parameters': path_params,
                'query_parameters': query_params
            }
        )
        
        # Validate authentication
        if not validate_authentication(event, correlation_id):
            return handle_authentication_error(correlation_id)
        
        # Validate query parameters
        try:
            validated_params = validate_query_parameters(query_params, correlation_id)
        except ValueError as e:
            return handle_validation_error(str(e), correlation_id)
        
        # Get data access instance
        data_table_name = os.getenv('DATA_TABLE_NAME', 'ruuvi-sensor-data')
        data_access = get_sensor_data_access(data_table_name)
        
        # Route based on path parameters
        path = event.get('path', '')
        
        # Route to appropriate handler based on path
        try:
            if '/current/' in path and path_params.get('device_id'):
                # Handle current data retrieval for specific device
                response_body = handle_current_data_request(
                    path_params['device_id'], 
                    data_access, 
                    correlation_id
                )
            elif '/current' in path and validated_params.get('device_ids'):
                # Handle current data retrieval for multiple devices
                response_body = handle_multiple_current_data_request(
                    validated_params['device_ids'], 
                    data_access, 
                    correlation_id
                )
            elif '/history/' in path and path_params.get('device_id'):
                # Handle historical data retrieval for specific device with pagination
                response_body = handle_historical_data_request(
                    path_params['device_id'],
                    validated_params,
                    data_access,
                    correlation_id
                )
            elif '/history' in path and validated_params.get('device_ids'):
                # Handle historical data retrieval for multiple devices
                response_body = handle_multiple_devices_historical_data_request(
                    validated_params['device_ids'],
                    validated_params,
                    data_access,
                    correlation_id
                )
            elif '/devices' in path:
                # Handle device listing request
                response_body = handle_device_listing_request(
                    data_access,
                    correlation_id
                )
            else:
                # Return error for unrecognized endpoints
                logger.warning(
                    f"Unrecognized endpoint: {path}",
                    extra={'correlation_id': correlation_id, 'path': path}
                )
                return handle_validation_error(
                    f"Unrecognized endpoint: {path}",
                    correlation_id
                )
        except ValueError as e:
            # Handle device not found errors
            return handle_not_found_error(str(e), correlation_id)
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000  # milliseconds
        
        logger.info(
            "Local data retrieval request processed successfully",
            extra={
                'correlation_id': correlation_id,
                'processing_time_ms': processing_time,
                'path': path
            }
        )
        
        return create_api_gateway_response(200, response_body, correlation_id)
        
    except ValueError as e:
        # Handle validation and parsing errors
        processing_time = (time.time() - start_time) * 1000
        
        logger.error(
            "Validation error in retrieve function",
            extra={
                'correlation_id': correlation_id or "unknown",
                'processing_time_ms': processing_time,
                'error': str(e)
            }
        )
        
        return handle_validation_error(str(e), correlation_id or "unknown")
        
    except Exception as e:
        # Handle all other internal errors
        processing_time = (time.time() - start_time) * 1000
        
        logger.error(
            "Internal error in retrieve function",
            extra={
                'correlation_id': correlation_id or "unknown",
                'processing_time_ms': processing_time,
                'error': str(e),
                'error_type': type(e).__name__
            }
        )
        
        return handle_internal_error(e, correlation_id or "unknown")