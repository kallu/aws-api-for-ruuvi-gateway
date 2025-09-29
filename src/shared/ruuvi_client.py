"""
HTTP client for Ruuvi Cloud Gateway API.

This module provides utilities for making HTTP requests to the Ruuvi Cloud Gateway API
with proper timeout handling, error recovery, and logging.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urljoin
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from .models import RuuviGatewayRequest, RuuviCloudResponse, format_ruuvi_cloud_response

# Configure logging
logger = logging.getLogger(__name__)

class RuuviCloudClient:
    """
    HTTP client for communicating with Ruuvi Cloud Gateway API.
    
    Provides methods for sending sensor data to Ruuvi Cloud with proper
    error handling, retries, and logging.
    """
    
    def __init__(self, 
                 base_url: str = "https://network.ruuvi.com",
                 timeout: int = 30,
                 max_retries: int = 3,
                 backoff_factor: float = 0.3,
                 enable_logging: bool = True):
        """
        Initialize Ruuvi Cloud client.
        
        Args:
            base_url: Base URL for Ruuvi Cloud API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            backoff_factor: Backoff factor for retries
            enable_logging: Whether to enable request/response logging
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.enable_logging = enable_logging
        
        # Configure session with retry strategy
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"],
            backoff_factor=backoff_factor
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'RuuviAPIProxy/1.0'
        })
    
    def send_sensor_data(self, 
                        gateway_request: RuuviGatewayRequest,
                        endpoint: str = "/record") -> Tuple[bool, Dict[str, Any]]:
        """
        Send sensor data to Ruuvi Cloud Gateway API.
        
        Args:
            gateway_request: Validated gateway request data
            endpoint: API endpoint to send data to
            
        Returns:
            Tuple of (success: bool, response: dict)
        """
        url = urljoin(self.base_url, endpoint)
        
        # Prepare request payload
        payload = {
            "data": {
                "coordinates": gateway_request.coordinates,
                "timestamp": gateway_request.timestamp,
                "gwmac": gateway_request.gwmac,
                "tags": gateway_request.tags
            }
        }
        
        try:
            if self.enable_logging:
                logger.info(f"Sending request to {url}")
                logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
            
            start_time = time.time()
            
            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            
            elapsed_time = time.time() - start_time
            
            if self.enable_logging:
                logger.info(f"Request completed in {elapsed_time:.2f}s with status {response.status_code}")
                logger.debug(f"Response headers: {dict(response.headers)}")
                logger.debug(f"Response body: {response.text}")
            
            # Handle response
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    return True, response_data
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    return False, format_ruuvi_cloud_response(
                        False, 
                        error_code="JSON_PARSE_ERROR",
                        error_message=f"Invalid JSON response: {str(e)}"
                    )
            else:
                logger.warning(f"HTTP error {response.status_code}: {response.text}")
                return False, format_ruuvi_cloud_response(
                    False,
                    error_code=f"HTTP_{response.status_code}",
                    error_message=f"HTTP {response.status_code}: {response.reason}"
                )
                
        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout after {self.timeout}s: {e}")
            return False, format_ruuvi_cloud_response(
                False,
                error_code="TIMEOUT_ERROR",
                error_message=f"Request timeout after {self.timeout} seconds"
            )
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            return False, format_ruuvi_cloud_response(
                False,
                error_code="CONNECTION_ERROR",
                error_message=f"Failed to connect to Ruuvi Cloud: {str(e)}"
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return False, format_ruuvi_cloud_response(
                False,
                error_code="REQUEST_ERROR",
                error_message=f"Request failed: {str(e)}"
            )
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False, format_ruuvi_cloud_response(
                False,
                error_code="UNKNOWN_ERROR",
                error_message=f"Unexpected error: {str(e)}"
            )
    
    def health_check(self, endpoint: str = "/health") -> Tuple[bool, Dict[str, Any]]:
        """
        Perform health check against Ruuvi Cloud API.
        
        Args:
            endpoint: Health check endpoint
            
        Returns:
            Tuple of (success: bool, response: dict)
        """
        url = urljoin(self.base_url, endpoint)
        
        try:
            if self.enable_logging:
                logger.info(f"Performing health check: {url}")
            
            response = self.session.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                return True, {"status": "healthy", "timestamp": int(time.time())}
            else:
                return False, {
                    "status": "unhealthy", 
                    "error": f"HTTP {response.status_code}: {response.reason}",
                    "timestamp": int(time.time())
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Health check failed: {e}")
            return False, {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": int(time.time())
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False, {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": int(time.time())
            }
    
    def close(self):
        """Close the HTTP session."""
        if self.session:
            self.session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Utility functions for backward compatibility and convenience
def create_ruuvi_client(base_url: str = "https://network.ruuvi.com", 
                       timeout: int = 30,
                       **kwargs) -> RuuviCloudClient:
    """
    Create a configured Ruuvi Cloud client.
    
    Args:
        base_url: Base URL for Ruuvi Cloud API
        timeout: Request timeout in seconds
        **kwargs: Additional client configuration options
        
    Returns:
        Configured RuuviCloudClient instance
    """
    return RuuviCloudClient(base_url=base_url, timeout=timeout, **kwargs)


def send_to_ruuvi_cloud(gateway_request: RuuviGatewayRequest,
                       base_url: str = "https://network.ruuvi.com",
                       timeout: int = 30) -> Tuple[bool, Dict[str, Any]]:
    """
    Convenience function to send data to Ruuvi Cloud.
    
    Args:
        gateway_request: Validated gateway request data
        base_url: Base URL for Ruuvi Cloud API
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (success: bool, response: dict)
    """
    with create_ruuvi_client(base_url=base_url, timeout=timeout) as client:
        return client.send_sensor_data(gateway_request)