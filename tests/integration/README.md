# Ruuvi API Integration Tests

This directory contains comprehensive integration tests for the Ruuvi API system, covering all major functionality including proxy operations, configuration management, and local data access.

## Test Structure

### 1. Proxy Integration Tests (`test_proxy_integration.py`)

Tests the end-to-end proxy functionality that acts as an intermediary between Ruuvi Gateway devices and the Ruuvi Cloud API.

**Test Coverage:**
- **Forwarding Enabled Scenarios:**
  - Successful forwarding to Ruuvi Cloud with local storage
  - Multiple devices forwarding
  - Ruuvi Cloud API compatibility verification
  
- **Forwarding Disabled Scenarios:**
  - Local storage only when forwarding is disabled
  - Configuration checking behavior
  
- **Error Handling Scenarios:**
  - Ruuvi Cloud HTTP error fallback
  - Timeout handling
  - Circuit breaker functionality
  - Local storage failure handling
  
- **Retry Logic:**
  - Transient failure recovery
  - Exponential backoff testing

**Key Requirements Tested:**
- Requirement 8.1: Ruuvi Cloud API compatibility
- Requirement 8.2: Local data storage
- Requirement 9.1: Forwarding configuration
- Requirement 9.2: Dynamic configuration updates

### 2. Configuration Management Tests (`test_config_integration.py`)

Tests the dynamic configuration management system that allows runtime updates without system restart.

**Test Coverage:**
- **Dynamic Configuration Updates:**
  - Single configuration updates
  - Multiple configuration updates
  - Invalid configuration key handling
  - Update failure handling
  
- **Caching and Fallback:**
  - Configuration value caching
  - Cache expiration behavior
  - Fallback to default values
  - Cache clearing functionality
  - Value serialization/deserialization
  
- **Admin Authentication:**
  - Valid admin API key authentication
  - Invalid API key rejection
  - Missing API key handling
  - Case-insensitive header handling
  
- **Audit Logging:**
  - Configuration update logging
  - User identifier extraction from Cognito
  - Fallback user identification
  - Audit field storage in DynamoDB

**Key Requirements Tested:**
- Requirement 9.3: Configuration management
- Requirement 9.4: Dynamic updates without restart

### 3. Local Data Access Tests (`test_local_data_access_integration.py`)

Tests the local data retrieval system that provides web clients access to stored sensor data.

**Test Coverage:**
- **Current Data Retrieval:**
  - Single device current data
  - Device not found handling
  - Multiple devices current data
  - Partial results handling
  
- **Historical Data Retrieval:**
  - Time range queries
  - Pagination support
  - Next token handling
  - Multiple device queries
  - Invalid parameter validation
  
- **Device Listing:**
  - Complete device listing
  - Empty result handling
  - Gateway aggregation
  
- **Data Storage Verification:**
  - Data accessibility when forwarding enabled
  - Data accessibility when forwarding disabled
  - Historical data availability regardless of forwarding
  
- **Authentication:**
  - API key authentication
  - Cognito token authentication
  - IAM authentication
  - Authentication failure handling
  - Case-insensitive headers

**Key Requirements Tested:**
- Requirement 2.1: Current data retrieval
- Requirement 2.2: Historical data retrieval
- Requirement 8.2: Local data storage
- Requirement 9.4: Data storage regardless of forwarding

## Running the Tests

### Prerequisites

1. Install test dependencies:
```bash
pip install pytest pytest-cov responses
```

2. Set up environment variables (tests use mocked services):
```bash
export DATA_TABLE_NAME=test-ruuvi-sensor-data
export CONFIG_TABLE_NAME=test-ruuvi-api-config
export ADMIN_API_KEY=test-admin-key
```

### Running All Integration Tests

```bash
# Run all integration tests
python tests/run_integration_tests.py

# Run with verbose output
python tests/run_integration_tests.py -v

# Run with coverage reporting
python tests/run_integration_tests.py --coverage
```

### Running Specific Test Suites

```bash
# Run only proxy tests
python tests/run_integration_tests.py --proxy

# Run only configuration management tests
python tests/run_integration_tests.py --config

# Run only local data access tests
python tests/run_integration_tests.py --data-access
```

### Running Specific Test Patterns

```bash
# Run tests matching a pattern
python tests/run_integration_tests.py -k "forwarding_enabled"

# Run tests for authentication
python tests/run_integration_tests.py -k "authentication"

# Run tests for pagination
python tests/run_integration_tests.py -k "pagination"
```

### Direct pytest Usage

```bash
# Run all integration tests directly
pytest tests/integration/ -v

# Run specific test file
pytest tests/integration/test_proxy_integration.py -v

# Run specific test class
pytest tests/integration/test_proxy_integration.py::TestForwardingEnabledScenarios -v

# Run specific test method
pytest tests/integration/test_proxy_integration.py::TestForwardingEnabledScenarios::test_successful_forwarding_with_local_storage -v
```

## Test Architecture

### Mocking Strategy

The integration tests use comprehensive mocking to simulate AWS services and external dependencies:

- **DynamoDB**: Mocked using `unittest.mock` to simulate table operations
- **Ruuvi Cloud API**: Mocked using `responses` library for HTTP interactions
- **AWS Lambda Context**: Mocked using `MagicMock` for Lambda runtime context
- **Configuration Manager**: Mocked to simulate configuration storage and retrieval
- **Data Access Layer**: Mocked to simulate sensor data operations

### Test Data Generation

Each test suite includes helper methods for generating realistic test data:

- `create_valid_ruuvi_request()`: Generates Ruuvi Gateway API requests
- `create_api_gateway_event()`: Creates API Gateway Lambda events
- `create_sample_sensor_data()`: Generates sensor data records
- `create_lambda_context()`: Creates Lambda execution context

### Assertion Patterns

Tests follow consistent assertion patterns:

1. **Response Structure Validation**: Verify HTTP status codes and response format
2. **Business Logic Verification**: Check that core functionality works correctly
3. **Integration Point Testing**: Verify interactions between components
4. **Error Handling Validation**: Ensure proper error responses and logging

## Test Coverage Goals

The integration test suite aims for comprehensive coverage of:

- ✅ **Happy Path Scenarios**: All primary use cases work correctly
- ✅ **Error Handling**: Graceful handling of various error conditions
- ✅ **Edge Cases**: Boundary conditions and unusual inputs
- ✅ **Integration Points**: Proper interaction between system components
- ✅ **Authentication/Authorization**: Security controls work correctly
- ✅ **Configuration Management**: Dynamic configuration updates
- ✅ **Data Consistency**: Data storage and retrieval consistency

## Continuous Integration

These tests are designed to run in CI/CD pipelines with:

- Fast execution (mocked dependencies)
- Deterministic results (no external dependencies)
- Clear failure reporting
- Coverage metrics generation

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `src` directory is in Python path
2. **Mock Setup**: Verify all required mocks are properly configured
3. **Environment Variables**: Check that test environment variables are set
4. **Dependency Versions**: Ensure compatible versions of pytest and mock libraries

### Debug Mode

Run tests with additional debugging:

```bash
# Enable debug logging
PYTHONPATH=src pytest tests/integration/ -v -s --log-cli-level=DEBUG

# Run single test with full traceback
pytest tests/integration/test_proxy_integration.py::TestForwardingEnabledScenarios::test_successful_forwarding_with_local_storage -v -s --tb=long
```

## Contributing

When adding new integration tests:

1. Follow the existing test structure and naming conventions
2. Include comprehensive docstrings explaining test purpose
3. Mock all external dependencies appropriately
4. Test both success and failure scenarios
5. Verify proper error handling and logging
6. Update this README with new test coverage information