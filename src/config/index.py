"""
Lambda function for configuration management.
Handles PUT and GET requests for dynamic configuration updates.
"""

import json
import os
import logging
import time
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

# Import shared utilities
import sys
sys.path.append('/opt/python')  # Lambda layer path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from config_manager import get_config_manager
from utils import create_api_response, get_correlation_id

logger = logging.getLogger(__name__)


class ConfigurationHandler:
    """Handles configuration management requests."""
    
    def __init__(self):
        """Initialize configuration handler."""
        self.config_table = os.environ.get('CONFIG_TABLE_NAME', 'ruuvi-api-config')
        self.admin_api_key = os.environ.get('ADMIN_API_KEY')
        self.config_manager = get_config_manager(self.config_table)
        
        # Valid configuration keys that can be updated
        self.updatable_keys = {
            'forwarding_enabled',
            'data_retention_days', 
            'ruuvi_cloud_endpoint',
            'ruuvi_cloud_timeout',
            'max_batch_size',
            'cache_ttl_seconds'
        }
    
    def handle_request(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        Handle configuration management request.
        
        Args:
            event: Lambda event
            context: Lambda context
            
        Returns:
            API Gateway response
        """
        correlation_id = get_correlation_id()
        logger.info(f"Processing configuration request", extra={'correlation_id': correlation_id})
        
        try:
            # Validate authentication
            if not self._validate_admin_auth(event):
                logger.warning("Unauthorized configuration access attempt", 
                             extra={'correlation_id': correlation_id})
                return create_api_response(
                    status_code=401,
                    body={'error': 'Unauthorized access'}
                )
            
            http_method = event.get('httpMethod', '').upper()
            
            if http_method == 'PUT':
                return self._handle_update_config(event, correlation_id)
            elif http_method == 'GET':
                return self._handle_get_config(event, correlation_id)
            else:
                return create_api_response(
                    status_code=405,
                    body={'error': f'Method {http_method} not allowed'}
                )
                
        except Exception as e:
            logger.error(f"Error processing configuration request: {str(e)}", 
                        extra={'correlation_id': correlation_id}, exc_info=True)
            return create_api_response(
                status_code=500,
                body={'error': 'Internal server error'}
            )
    
    def _validate_admin_auth(self, event: Dict[str, Any]) -> bool:
        """
        Validate admin authentication.
        
        Args:
            event: Lambda event
            
        Returns:
            True if authenticated, False otherwise
        """
        # Check API key in headers
        headers = event.get('headers', {})
        api_key = headers.get('x-api-key') or headers.get('X-API-Key')
        
        if not api_key:
            logger.warning("No API key provided in configuration request")
            return False
        
        if not self.admin_api_key:
            logger.error("Admin API key not configured in environment")
            return False
        
        if api_key != self.admin_api_key:
            logger.warning("Invalid admin API key provided")
            return False
        
        return True
    
    def _handle_update_config(self, event: Dict[str, Any], correlation_id: str) -> Dict[str, Any]:
        """
        Handle configuration update request.
        
        Args:
            event: Lambda event
            correlation_id: Request correlation ID
            
        Returns:
            API Gateway response
        """
        try:
            # Parse request body
            body = event.get('body', '{}')
            if isinstance(body, str):
                request_data = json.loads(body)
            else:
                request_data = body
            
            # Validate request format
            if not isinstance(request_data, dict):
                return create_api_response(
                    status_code=400,
                    body={'error': 'Request body must be a JSON object'}
                )
            
            # Get user identifier for audit logging
            user_id = self._get_user_identifier(event)
            
            # Process configuration updates
            updated_configs = {}
            errors = {}
            
            for key, value in request_data.items():
                if key not in self.updatable_keys:
                    errors[key] = f"Configuration key '{key}' is not updatable"
                    continue
                
                # Validate and update configuration
                if self.config_manager.set_config(key, value, updated_by=user_id):
                    updated_configs[key] = value
                    logger.info(f"Configuration updated: {key} = {value}", 
                              extra={'correlation_id': correlation_id, 'user_id': user_id})
                else:
                    errors[key] = f"Failed to update configuration key '{key}'"
            
            # Clear cache to ensure immediate effect
            self.config_manager.clear_cache()
            
            # Prepare response
            response_body = {
                'result': 'success' if updated_configs else 'error',
                'updated': updated_configs,
                'timestamp': int(time.time())
            }
            
            if errors:
                response_body['errors'] = errors
            
            status_code = 200 if updated_configs else 400
            
            return create_api_response(
                status_code=status_code,
                body=response_body
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request body: {str(e)}", 
                        extra={'correlation_id': correlation_id})
            return create_api_response(
                status_code=400,
                body={'error': 'Invalid JSON in request body'}
            )
        except Exception as e:
            logger.error(f"Error updating configuration: {str(e)}", 
                        extra={'correlation_id': correlation_id}, exc_info=True)
            return create_api_response(
                status_code=500,
                body={'error': 'Failed to update configuration'}
            )
    
    def _handle_get_config(self, event: Dict[str, Any], correlation_id: str) -> Dict[str, Any]:
        """
        Handle configuration retrieval request.
        
        Args:
            event: Lambda event
            correlation_id: Request correlation ID
            
        Returns:
            API Gateway response
        """
        try:
            # Get all configuration values
            all_config = self.config_manager.get_all_config()
            
            # Format response for admin interface
            formatted_config = {}
            for key, config_data in all_config.items():
                if key in self.updatable_keys:  # Only return updatable configs
                    formatted_config[key] = {
                        'value': config_data['value'],
                        'last_updated': config_data['last_updated'],
                        'updated_by': config_data['updated_by'],
                        'is_default': config_data['last_updated'] is None
                    }
            
            logger.info(f"Configuration retrieved successfully", 
                       extra={'correlation_id': correlation_id})
            
            return create_api_response(
                status_code=200,
                body={
                    'result': 'success',
                    'configuration': formatted_config,
                    'updatable_keys': list(self.updatable_keys)
                }
            )
            
        except Exception as e:
            logger.error(f"Error retrieving configuration: {str(e)}", 
                        extra={'correlation_id': correlation_id}, exc_info=True)
            return create_api_response(
                status_code=500,
                body={'error': 'Failed to retrieve configuration'}
            )
    
    def _get_user_identifier(self, event: Dict[str, Any]) -> str:
        """
        Get user identifier for audit logging.
        
        Args:
            event: Lambda event
            
        Returns:
            User identifier string
        """
        # Try to get user from Cognito claims if available
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        
        if 'claims' in authorizer:
            claims = authorizer['claims']
            return claims.get('sub', claims.get('username', 'cognito-user'))
        
        # Fallback to API key or IP
        headers = event.get('headers', {})
        api_key = headers.get('x-api-key', headers.get('X-API-Key', 'unknown'))
        source_ip = request_context.get('identity', {}).get('sourceIp', 'unknown')
        
        return f"api-key:{api_key[-8:]}@{source_ip}"


# Global handler instance (initialized lazily)
config_handler = None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda entry point for configuration management.
    
    Args:
        event: Lambda event from API Gateway
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialize handler lazily
    global config_handler
    if config_handler is None:
        config_handler = ConfigurationHandler()
    
    return config_handler.handle_request(event, context)