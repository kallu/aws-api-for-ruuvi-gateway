"""
DynamoDB data access utilities for Ruuvi sensor data.
Handles storing and retrieving sensor data with proper indexing and pagination.
"""

import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
import logging

logger = logging.getLogger(__name__)


class SensorDataAccess:
    """Handles DynamoDB operations for sensor data storage and retrieval."""
    
    def __init__(self, table_name: str, gsi_name: str = 'gateway-timestamp-index'):
        """
        Initialize sensor data access.
        
        Args:
            table_name: DynamoDB table name for sensor data
            gsi_name: Global Secondary Index name for gateway queries
        """
        self.table_name = table_name
        self.gsi_name = gsi_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
    
    def store_sensor_data(self, device_id: str, gateway_id: str, timestamp: int, 
                         measurements: Dict[str, Any], ruuvi_cloud_response: Dict[str, Any] = None,
                         ttl_days: int = 90) -> bool:
        """
        Store sensor data in DynamoDB.
        
        Args:
            device_id: Unique device identifier
            gateway_id: Gateway MAC address
            timestamp: Unix timestamp of the measurement
            measurements: Raw sensor measurements
            ruuvi_cloud_response: Response from Ruuvi Cloud API (optional)
            ttl_days: Days to retain data (for TTL)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Calculate TTL timestamp
            ttl_timestamp = int(time.time()) + (ttl_days * 24 * 60 * 60)
            
            item = {
                'device_id': device_id,
                'timestamp': timestamp,
                'gateway_id': gateway_id,
                'server_timestamp': int(time.time()),
                'measurements': measurements,
                'ttl': ttl_timestamp
            }
            
            # Add Ruuvi Cloud response if provided
            if ruuvi_cloud_response:
                item['ruuvi_cloud_response'] = ruuvi_cloud_response
            
            self.table.put_item(Item=item)
            
            logger.debug(f"Stored sensor data for device {device_id} at timestamp {timestamp}")
            return True
            
        except ClientError as e:
            logger.error(f"Error storing sensor data for device {device_id}: {e}")
            return False
    
    def store_batch_sensor_data(self, sensor_data_list: List[Dict[str, Any]], 
                               ttl_days: int = 90) -> Tuple[int, int]:
        """
        Store multiple sensor data records in batch.
        
        Args:
            sensor_data_list: List of sensor data dictionaries
            ttl_days: Days to retain data (for TTL)
            
        Returns:
            Tuple of (successful_count, failed_count)
        """
        successful_count = 0
        failed_count = 0
        ttl_timestamp = int(time.time()) + (ttl_days * 24 * 60 * 60)
        
        try:
            with self.table.batch_writer() as batch:
                for data in sensor_data_list:
                    try:
                        item = {
                            'device_id': data['device_id'],
                            'timestamp': data['timestamp'],
                            'gateway_id': data['gateway_id'],
                            'server_timestamp': int(time.time()),
                            'measurements': data['measurements'],
                            'ttl': ttl_timestamp
                        }
                        
                        if 'ruuvi_cloud_response' in data:
                            item['ruuvi_cloud_response'] = data['ruuvi_cloud_response']
                        
                        batch.put_item(Item=item)
                        successful_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error preparing batch item for device {data.get('device_id')}: {e}")
                        failed_count += 1
                        
        except ClientError as e:
            logger.error(f"Error in batch write operation: {e}")
            failed_count += len(sensor_data_list) - successful_count
            successful_count = 0
        
        logger.info(f"Batch write completed: {successful_count} successful, {failed_count} failed")
        return successful_count, failed_count
    
    def get_current_data(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent sensor data for a device.
        
        Args:
            device_id: Device identifier
            
        Returns:
            Most recent sensor data or None if not found
        """
        try:
            response = self.table.query(
                KeyConditionExpression=Key('device_id').eq(device_id),
                ScanIndexForward=False,  # Descending order (newest first)
                Limit=1
            )
            
            items = response.get('Items', [])
            if items:
                return self._format_sensor_data(items[0])
            else:
                logger.info(f"No data found for device {device_id}")
                return None
                
        except ClientError as e:
            logger.error(f"Error retrieving current data for device {device_id}: {e}")
            return None
    
    def get_historical_data(self, device_id: str, start_time: int = None, 
                           end_time: int = None, limit: int = 100, 
                           last_evaluated_key: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get historical sensor data for a device within a time range.
        
        Args:
            device_id: Device identifier
            start_time: Start timestamp (optional)
            end_time: End timestamp (optional)
            limit: Maximum number of items to return
            last_evaluated_key: For pagination
            
        Returns:
            Dictionary with 'items' and 'last_evaluated_key' for pagination
        """
        try:
            # Build key condition
            key_condition = Key('device_id').eq(device_id)
            
            if start_time and end_time:
                key_condition = key_condition & Key('timestamp').between(start_time, end_time)
            elif start_time:
                key_condition = key_condition & Key('timestamp').gte(start_time)
            elif end_time:
                key_condition = key_condition & Key('timestamp').lte(end_time)
            
            query_params = {
                'KeyConditionExpression': key_condition,
                'ScanIndexForward': True,  # Ascending order (oldest first)
                'Limit': limit
            }
            
            if last_evaluated_key:
                query_params['ExclusiveStartKey'] = last_evaluated_key
            
            response = self.table.query(**query_params)
            
            items = [self._format_sensor_data(item) for item in response.get('Items', [])]
            
            result = {
                'items': items,
                'count': len(items)
            }
            
            if 'LastEvaluatedKey' in response:
                result['last_evaluated_key'] = response['LastEvaluatedKey']
            
            logger.debug(f"Retrieved {len(items)} historical records for device {device_id}")
            return result
            
        except ClientError as e:
            logger.error(f"Error retrieving historical data for device {device_id}: {e}")
            return {'items': [], 'count': 0}
    
    def get_multiple_devices_current_data(self, device_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get current data for multiple devices.
        
        Args:
            device_ids: List of device identifiers
            
        Returns:
            Dictionary mapping device_id to current data
        """
        result = {}
        
        for device_id in device_ids:
            current_data = self.get_current_data(device_id)
            if current_data:
                result[device_id] = current_data
        
        return result
    
    def get_devices_by_gateway(self, gateway_id: str, start_time: int = None, 
                              end_time: int = None, limit: int = 100,
                              last_evaluated_key: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get sensor data for all devices from a specific gateway.
        
        Args:
            gateway_id: Gateway identifier
            start_time: Start timestamp (optional)
            end_time: End timestamp (optional)
            limit: Maximum number of items to return
            last_evaluated_key: For pagination
            
        Returns:
            Dictionary with 'items' and 'last_evaluated_key' for pagination
        """
        try:
            # Build key condition for GSI
            key_condition = Key('gateway_id').eq(gateway_id)
            
            if start_time and end_time:
                key_condition = key_condition & Key('timestamp').between(start_time, end_time)
            elif start_time:
                key_condition = key_condition & Key('timestamp').gte(start_time)
            elif end_time:
                key_condition = key_condition & Key('timestamp').lte(end_time)
            
            query_params = {
                'IndexName': self.gsi_name,
                'KeyConditionExpression': key_condition,
                'ScanIndexForward': True,  # Ascending order
                'Limit': limit
            }
            
            if last_evaluated_key:
                query_params['ExclusiveStartKey'] = last_evaluated_key
            
            response = self.table.query(**query_params)
            
            items = [self._format_sensor_data(item) for item in response.get('Items', [])]
            
            result = {
                'items': items,
                'count': len(items)
            }
            
            if 'LastEvaluatedKey' in response:
                result['last_evaluated_key'] = response['LastEvaluatedKey']
            
            logger.debug(f"Retrieved {len(items)} records for gateway {gateway_id}")
            return result
            
        except ClientError as e:
            logger.error(f"Error retrieving data for gateway {gateway_id}: {e}")
            return {'items': [], 'count': 0}
    
    def get_all_devices(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get list of all unique devices with their last seen timestamp.
        
        Args:
            limit: Maximum number of devices to scan
            
        Returns:
            List of device information dictionaries
        """
        try:
            devices = {}
            
            # Use scan to get all devices (this could be expensive for large datasets)
            scan_params = {
                'ProjectionExpression': 'device_id, gateway_id, #ts, server_timestamp',
                'ExpressionAttributeNames': {'#ts': 'timestamp'},
                'Limit': limit
            }
            
            response = self.table.scan(**scan_params)
            
            for item in response.get('Items', []):
                device_id = item['device_id']
                timestamp = item['timestamp']
                
                # Keep only the most recent timestamp for each device
                if device_id not in devices or timestamp > devices[device_id]['last_seen']:
                    devices[device_id] = {
                        'device_id': device_id,
                        'gateway_id': item['gateway_id'],
                        'last_seen': timestamp,
                        'last_seen_server': item.get('server_timestamp', timestamp)
                    }
            
            # Handle pagination if needed
            while 'LastEvaluatedKey' in response and len(devices) < limit:
                scan_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
                response = self.table.scan(**scan_params)
                
                for item in response.get('Items', []):
                    device_id = item['device_id']
                    timestamp = item['timestamp']
                    
                    if device_id not in devices or timestamp > devices[device_id]['last_seen']:
                        devices[device_id] = {
                            'device_id': device_id,
                            'gateway_id': item['gateway_id'],
                            'last_seen': timestamp,
                            'last_seen_server': item.get('server_timestamp', timestamp)
                        }
            
            device_list = list(devices.values())
            device_list.sort(key=lambda x: x['last_seen'], reverse=True)
            
            logger.info(f"Found {len(device_list)} unique devices")
            return device_list
            
        except ClientError as e:
            logger.error(f"Error retrieving device list: {e}")
            return []
    
    def delete_old_data(self, device_id: str, older_than_timestamp: int) -> int:
        """
        Delete old data for a device (mainly for testing, TTL handles automatic cleanup).
        
        Args:
            device_id: Device identifier
            older_than_timestamp: Delete data older than this timestamp
            
        Returns:
            Number of items deleted
        """
        try:
            deleted_count = 0
            
            # Query old items
            response = self.table.query(
                KeyConditionExpression=Key('device_id').eq(device_id) & Key('timestamp').lt(older_than_timestamp),
                ProjectionExpression='device_id, #ts',
                ExpressionAttributeNames={'#ts': 'timestamp'}
            )
            
            # Delete items in batches
            with self.table.batch_writer() as batch:
                for item in response.get('Items', []):
                    batch.delete_item(
                        Key={
                            'device_id': item['device_id'],
                            'timestamp': item['timestamp']
                        }
                    )
                    deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} old records for device {device_id}")
            return deleted_count
            
        except ClientError as e:
            logger.error(f"Error deleting old data for device {device_id}: {e}")
            return 0
    
    def _format_sensor_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format sensor data item for API response.
        
        Args:
            item: Raw DynamoDB item
            
        Returns:
            Formatted sensor data
        """
        formatted = {
            'device_id': item['device_id'],
            'gateway_id': item['gateway_id'],
            'timestamp': item['timestamp'],
            'server_timestamp': item.get('server_timestamp', item['timestamp']),
            'measurements': item['measurements']
        }
        
        if 'ruuvi_cloud_response' in item:
            formatted['ruuvi_cloud_response'] = item['ruuvi_cloud_response']
        
        return formatted


# Singleton instance for global use
_sensor_data_access: Optional[SensorDataAccess] = None


def get_sensor_data_access(table_name: str = None, gsi_name: str = 'gateway-timestamp-index') -> SensorDataAccess:
    """
    Get singleton sensor data access instance.
    
    Args:
        table_name: DynamoDB table name (required for first call)
        gsi_name: Global Secondary Index name
        
    Returns:
        SensorDataAccess instance
    """
    global _sensor_data_access
    
    if _sensor_data_access is None:
        if table_name is None:
            raise ValueError("table_name is required for first initialization")
        _sensor_data_access = SensorDataAccess(table_name, gsi_name)
    
    return _sensor_data_access


def reset_sensor_data_access() -> None:
    """Reset singleton instance (mainly for testing)."""
    global _sensor_data_access
    _sensor_data_access = None