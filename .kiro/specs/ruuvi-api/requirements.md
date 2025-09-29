# Requirements Document

## Introduction

This feature involves building a serverless API on AWS to receive sensor data updates from Ruuvi Gateway devices and store them in a format that enables easy retrieval by web clients. The solution must be cost-effective for a small user base while providing reliable data ingestion and retrieval capabilities.

## Requirements

### Requirement 1

**User Story:** As a Ruuvi Gateway device, I want to send sensor data to an API endpoint, so that the data can be stored and made available for retrieval.

#### Acceptance Criteria

1. WHEN a Ruuvi Gateway sends a POST request with sensor data THEN the system SHALL accept and validate the incoming data
2. WHEN valid sensor data is received THEN the system SHALL store it in AWS with proper timestamps
3. WHEN invalid or malformed data is received THEN the system SHALL return appropriate error responses
4. WHEN data is successfully stored THEN the system SHALL return a success confirmation to the gateway

### Requirement 2

**User Story:** As a web client user, I want to retrieve stored Ruuvi sensor data through an API, so that I can display current and historical sensor readings.

#### Acceptance Criteria

1. WHEN a web client requests current sensor data THEN the system SHALL return the most recent readings for specified devices
2. WHEN a web client requests historical data THEN the system SHALL return time-series data within specified date ranges
3. WHEN no data exists for a requested device THEN the system SHALL return an appropriate empty response
4. WHEN multiple devices are requested THEN the system SHALL return data for all available devices

### Requirement 3

**User Story:** As a system administrator, I want the API to use serverless AWS components, so that running costs remain minimal for a small user base.

#### Acceptance Criteria

1. WHEN the system is deployed THEN it SHALL use only serverless AWS services (Lambda, API Gateway, DynamoDB, etc.)
2. WHEN there is no traffic THEN the system SHALL incur minimal or zero compute costs
3. WHEN traffic increases THEN the system SHALL automatically scale without manual intervention
4. WHEN data storage grows THEN the system SHALL use cost-effective storage solutions

### Requirement 4

**User Story:** As a developer, I want the API to handle authentication and authorization, so that only authorized devices and users can access the system.

#### Acceptance Criteria

1. WHEN a Ruuvi Gateway attempts to send data THEN the system SHALL authenticate the device using API keys or tokens
2. WHEN a web client attempts to retrieve data THEN the system SHALL verify user authorization
3. WHEN unauthorized access is attempted THEN the system SHALL return appropriate error responses
4. WHEN authentication fails THEN the system SHALL log the attempt for security monitoring

### Requirement 5

**User Story:** As a system operator, I want the API to provide monitoring and logging capabilities, so that I can track system health and troubleshoot issues.

#### Acceptance Criteria

1. WHEN API requests are processed THEN the system SHALL log request details and response status
2. WHEN errors occur THEN the system SHALL log error details with sufficient context for debugging
3. WHEN system metrics are needed THEN the system SHALL provide visibility into request rates, error rates, and latency
4. WHEN alerts are configured THEN the system SHALL notify operators of critical issues

### Requirement 6

**User Story:** As a system operator, I want to set maximum lifetime for stored data, so that any data older than that threshold is automatically deleted to keep storage costs limited.

#### Acceptance Criteria

1. WHEN data is stored THEN the system SHALL set a TTL (Time To Live) value based on configured retention period
2. WHEN data reaches the configured age threshold THEN the system SHALL automatically delete the old data points
3. WHEN retention period is updated THEN the system SHALL apply new TTL values to future data without affecting existing data
4. WHEN storage cleanup occurs THEN the system SHALL log the cleanup activity for audit purposes

### Requirement 7

**User Story:** As a data consumer, I want the stored data to be easily queryable and retrievable, so that web clients can efficiently access the information they need.

#### Acceptance Criteria

1. WHEN data is stored THEN it SHALL be organized by device ID and timestamp for efficient querying
2. WHEN querying by time range THEN the system SHALL return results in chronological order
3. WHEN querying multiple devices THEN the system SHALL support batch retrieval operations
4. WHEN data volume is large THEN the system SHALL support pagination for large result sets

### Requirement 8

**User Story:** As a Ruuvi Gateway, I want to send my sensor data to an API proxy that behaves like the Ruuvi Cloud Gateway API, so that the proxy can forward the request to Ruuvi Cloud AND store the data locally for my own use.

#### Acceptance Criteria

1. WHEN Ruuvi Gateway sends data to the API proxy THEN it SHALL receive the same response format as the Ruuvi Cloud Gateway API would return
2. WHEN Ruuvi Gateway sends data to the API proxy THEN the data SHALL be parsed and stored locally for web client consumption
3. WHEN the API proxy receives data THEN it SHALL be compatible with the Ruuvi Cloud Gateway API format as described in https://docs.ruuvi.com/communicate-with-ruuvi-cloud/cloud/gateway-api
4. WHEN data is forwarded to Ruuvi Cloud THEN the original request format SHALL be preserved

### Requirement 9

**User Story:** As a system operator, I want to have a configuration option that allows me to enable and disable forwarding to Ruuvi Cloud Gateway API, so that I can control data flow without system downtime.

#### Acceptance Criteria

1. WHEN operator has enabled forwarding to Ruuvi Cloud THEN the system SHALL forward the request to Ruuvi Cloud Gateway API and return the response it receives
2. WHEN operator has disabled forwarding to Ruuvi Cloud THEN the system SHALL NOT call Ruuvi Cloud Gateway API and SHALL return its own success status code
3. WHEN forwarding setting changes THEN the system SHALL apply the new setting without requiring restart or redeployment
4. WHEN data is received from Ruuvi Gateway THEN the system SHALL store it locally regardless of the forwarding setting
