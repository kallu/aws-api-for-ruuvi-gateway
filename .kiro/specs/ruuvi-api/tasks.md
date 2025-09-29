# Implementation Plan

- [x] 1. Analyze existing proxy and set up enhanced project structure
  - Analyze existing apiproxy.yaml CloudFormation template to understand current proxy implementation
  - Research Ruuvi Cloud Gateway API format from https://docs.ruuvi.com/communicate-with-ruuvi-cloud/cloud/gateway-api
  - Create directory structure for Lambda functions extending the existing proxy approach
  - Set up package.json with AWS SDK and testing dependencies for Lambda functions
  - _Requirements: 8.3, 9.1_

- [x] 2. Implement Ruuvi Cloud API compatibility layer
  - [x] 2.1 Create Ruuvi Cloud API data models and validation
    - Write TypeScript interfaces for Ruuvi Cloud Gateway API request format
    - Implement validation schemas for incoming Ruuvi Gateway data
    - Create response formatting functions that match Ruuvi Cloud API responses
    - Write unit tests for data validation and response formatting
    - _Requirements: 8.1, 8.3, 1.1, 1.3_

  - [x] 2.2 Implement HTTP client for Ruuvi Cloud API
    - Create HTTP client utility for making requests to Ruuvi Cloud Gateway API
    - Implement proper timeout handling and error recovery
    - Add request/response logging for debugging
    - Write unit tests with mocked HTTP responses
    - _Requirements: 8.4, 9.1_

- [x] 3. Create DynamoDB tables and configuration management
  - [x] 3.1 Write CloudFormation template for DynamoDB tables
    - Define sensor data table with device_id and timestamp keys
    - Create configuration table for dynamic settings storage
    - Set up Global Secondary Indexes for efficient querying
    - Configure TTL for automatic data cleanup
    - _Requirements: 6.1, 6.2, 9.3_

  - [x] 3.2 Implement configuration management utilities
    - Create functions to read/write configuration from DynamoDB
    - Implement in-memory caching for configuration values
    - Add configuration validation and default value handling
    - Write unit tests for configuration management
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 3.3 Implement DynamoDB data access utilities
    - Create connection and configuration utilities for DynamoDB client
    - Write helper functions for storing sensor data with proper indexing
    - Implement query functions for data retrieval with pagination
    - Create unit tests for DynamoDB operations
    - _Requirements: 7.1, 7.2, 7.4_

- [x] 4. Implement Lambda proxy function
  - [x] 4.1 Create basic proxy function structure
    - Set up Lambda handler with proper event parsing for API Gateway
    - Implement request validation using Ruuvi Cloud API schemas
    - Add structured logging with correlation IDs
    - Create basic error handling framework
    - _Requirements: 8.1, 8.2, 5.1, 5.2_

  - [x] 4.2 Implement configuration-based forwarding logic
    - Add configuration reading with caching and fallback
    - Implement conditional forwarding to Ruuvi Cloud API
    - Handle Ruuvi Cloud API failures gracefully
    - Return appropriate responses based on forwarding success/failure
    - _Requirements: 9.1, 9.2, 8.1_

  - [x] 4.3 Implement local data storage
    - Add data parsing and transformation for local storage
    - Implement batch writing to DynamoDB with error handling
    - Store both original data and Ruuvi Cloud responses
    - Ensure data is stored regardless of forwarding setting
    - _Requirements: 8.2, 9.4, 1.2_

  - [x] 4.4 Add comprehensive error handling and monitoring
    - Implement circuit breaker pattern for Ruuvi Cloud API calls
    - Add retry logic for transient failures
    - Create structured error responses matching Ruuvi Cloud format
    - Add CloudWatch metrics for proxy operations
    - _Requirements: 1.3, 5.1, 5.2, 5.3_

- [x] 5. Implement Lambda retrieve function for local data access
  - [x] 5.1 Create local data retrieval function structure
    - Set up Lambda handler for GET requests with path parameter parsing
    - Implement authentication validation for local data access
    - Add query parameter validation for time ranges and pagination
    - _Requirements: 2.1, 2.2, 4.2_

  - [x] 5.2 Implement current data retrieval
    - Write DynamoDB query logic to get latest readings for devices
    - Implement response formatting for current sensor data
    - Add error handling for non-existent devices
    - Create unit tests for current data queries
    - _Requirements: 2.1, 2.3_

  - [x] 5.3 Implement historical data retrieval with pagination
    - Write DynamoDB query logic for time-range queries
    - Implement pagination using DynamoDB's LastEvaluatedKey
    - Add support for querying multiple devices
    - Create unit tests for historical data queries and pagination
    - _Requirements: 2.2, 2.4, 7.4_

  - [x] 5.4 Implement device listing endpoint
    - Write DynamoDB scan/query logic to get all unique devices
    - Add last-seen timestamp information for each device
    - Implement response formatting for device list
    - Create unit tests for device listing functionality
    - _Requirements: 2.4_

- [x] 6. Implement Lambda configuration management function
  - [x] 6.1 Create configuration update function
    - Set up Lambda handler for PUT requests to update configuration
    - Implement admin authentication validation
    - Add configuration value validation before updates
    - Create audit logging for configuration changes
    - _Requirements: 9.3, 4.2, 5.4_

  - [x] 6.2 Implement configuration retrieval endpoint
    - Add GET endpoint to retrieve current configuration status
    - Implement proper authorization for configuration access
    - Format configuration response for admin interfaces
    - Create unit tests for configuration management
    - _Requirements: 9.3_

- [x] 7. Enhance existing API Gateway CloudFormation template
  - [x] 7.1 Modify apiproxy.yaml to support Lambda integration
    - Update existing apiproxy.yaml to replace HTTP_PROXY with Lambda integration
    - Modify proxy method to call Lambda function instead of direct HTTP proxy
    - Preserve existing custom domain and Route53 configuration
    - Update parameters to include Ruuvi Cloud API endpoint configuration
    - _Requirements: 8.3, 4.2_

  - [x] 7.2 Add local data access endpoints to existing template
    - Extend existing API Gateway with additional resources for local data access
    - Define GET endpoints for local data retrieval (separate from proxy path)
    - Set up configuration management endpoints
    - Maintain existing authentication structure while adding new endpoints
    - _Requirements: 2.1, 2.2, 9.3_

  - [x] 7.3 Enhance authentication in existing template
    - Extend existing API structure with API key authentication
    - Configure separate admin API keys for configuration management
    - Add optional Cognito authorizer for web clients
    - Preserve existing domain and SSL certificate configuration
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 8. Complete enhanced CloudFormation template
  - [x] 8.1 Integrate all components into existing template structure
    - Add DynamoDB tables to the existing apiproxy.yaml template
    - Integrate Lambda functions with existing API Gateway structure
    - Add IAM roles and policies with least privilege access
    - Configure environment variables for Ruuvi Cloud API endpoint using existing parameter pattern
    - Preserve existing outputs while adding new API endpoints and configuration
    - _Requirements: 3.1, 3.2, 4.4_

  - [x] 8.2 Implement monitoring and alerting
    - Create CloudWatch dashboard for proxy operations
    - Set up alarms for Ruuvi Cloud API failures and high error rates
    - Configure log groups with proper retention policies
    - Add custom metrics for forwarding success/failure rates
    - _Requirements: 5.3, 5.4_

- [x] 9. Create comprehensive test suite
  - [x] 9.1 Write integration tests for proxy functionality
    - Create end-to-end tests for proxy with mock Ruuvi Cloud API
    - Test forwarding enabled and disabled scenarios
    - Verify Ruuvi Cloud API compatibility with actual request/response formats
    - Test error handling when Ruuvi Cloud is unavailable
    - _Requirements: 8.1, 8.2, 9.1, 9.2_

  - [x] 9.2 Implement configuration management tests
    - Test dynamic configuration updates without restart
    - Verify configuration caching and fallback behavior
    - Test admin authentication for configuration changes
    - Create tests for configuration audit logging
    - _Requirements: 9.3, 9.4_

  - [x] 9.3 Create local data access tests
    - Write integration tests for local data retrieval endpoints
    - Test pagination and time-range queries
    - Verify data storage regardless of forwarding setting
    - Test authentication for local data access
    - _Requirements: 2.1, 2.2, 8.2, 9.4_

- [x] 10. Create deployment scripts and documentation
  - [x] 10.1 Write deployment automation building on existing approach
    - Create build scripts for Lambda function packaging
    - Enhance existing CloudFormation deployment approach with Lambda packaging
    - Add environment-specific configuration management using existing parameter pattern
    - Create rollback procedures for failed deployments
    - _Requirements: 3.1, 3.2_

  - [x] 10.2 Create comprehensive documentation
    - Document Ruuvi Gateway setup and API key configuration
    - Create examples showing proxy behavior with/without forwarding
    - Document local data access API for web clients
    - Add troubleshooting guide for common proxy issues
    - Create configuration management guide for operators
    - _Requirements: 8.1, 9.3, 2.1_