"""
Shared utility functions for Ruuvi API system.

This module contains common utilities used across all Lambda functions.
"""

import json
import logging
import time
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def get_correlation_id() -> str:
    """Generate a correlation ID for request tracking."""
    return str(uuid.uuid4())

def get_current_timestamp() -> int:
    """Get current Unix timestamp."""
    return int(time.time())

def get_ttl_timestamp(retention_days: int) -> int:
    """Calculate TTL timestamp for DynamoDB items."""
    return get_current_timestamp() + (retention_days * 24 * 60 * 60)

def parse_api_gateway_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse API Gateway event and extract relevant information.
    
    Args:
        event: API Gateway event
        
    Returns:
        Parsed event data
    """
    return {
        'method': event.get('httpMethod', ''),
        'path': event.get('path', ''),
        'query_params': event.get('queryStringParameters') or {},
        'path_params': event.get('pathParameters') or {},
        'headers': event.get('headers') or {},
        'body': event.get('body', ''),
        'is_base64_encoded': event.get('isBase64Encoded', False)
    }

def create_api_response(
    status_code: int,
    body: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Create API Gateway response.
    
    Args:
        status_code: HTTP status code
        body: Response body
        headers: Optional headers
        
    Returns:
        API Gateway response
    """
    default_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    }
    
    if headers:
        default_headers.update(headers)
    
    return {
        'statusCode': status_code,
        'headers': default_headers,
        'body': json.dumps(body)
    }

def log_request(correlation_id: str, method: str, path: str, body: str = "") -> None:
    """Log incoming request details."""
    logger.info(f"[{correlation_id}] {method} {path}")
    if body and len(body) < 1000:  # Don't log very large bodies
        logger.debug(f"[{correlation_id}] Request body: {body}")

def log_response(correlation_id: str, status_code: int, response_body: str = "") -> None:
    """Log response details."""
    logger.info(f"[{correlation_id}] Response: {status_code}")
    if response_body and len(response_body) < 1000:  # Don't log very large responses
        logger.debug(f"[{correlation_id}] Response body: {response_body}")

def safe_json_parse(json_string: str) -> Optional[Dict[str, Any]]:
    """
    Safely parse JSON string.
    
    Args:
        json_string: JSON string to parse
        
    Returns:
        Parsed dictionary or None if parsing fails
    """
    try:
        return json.loads(json_string)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return None