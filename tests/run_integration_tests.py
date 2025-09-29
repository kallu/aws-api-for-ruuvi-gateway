#!/usr/bin/env python3
"""
Test runner for Ruuvi API integration tests.

This script runs all integration tests for the comprehensive test suite,
including proxy functionality, configuration management, and local data access.
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def run_tests(test_pattern=None, verbose=False, coverage=False):
    """
    Run integration tests with optional filtering and coverage.
    
    Args:
        test_pattern: Optional pattern to filter tests
        verbose: Enable verbose output
        coverage: Enable coverage reporting
    """
    # Base pytest command
    cmd = ['python', '-m', 'pytest']
    
    # Add test directory
    test_dir = os.path.join(os.path.dirname(__file__), 'integration')
    cmd.append(test_dir)
    
    # Add verbose flag
    if verbose:
        cmd.append('-v')
    
    # Add test pattern if specified
    if test_pattern:
        cmd.extend(['-k', test_pattern])
    
    # Add coverage if requested
    if coverage:
        cmd.extend([
            '--cov=src',
            '--cov-report=html',
            '--cov-report=term-missing'
        ])
    
    # Add other useful flags
    cmd.extend([
        '--tb=short',  # Shorter traceback format
        '--strict-markers',  # Strict marker checking
        '--disable-warnings'  # Disable warnings for cleaner output
    ])
    
    print(f"Running command: {' '.join(cmd)}")
    print("-" * 80)
    
    # Run the tests
    result = subprocess.run(cmd, cwd=os.path.dirname(__file__))
    return result.returncode

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Run Ruuvi API integration tests')
    parser.add_argument(
        '-k', '--pattern',
        help='Only run tests matching this pattern'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Enable coverage reporting'
    )
    parser.add_argument(
        '--proxy',
        action='store_true',
        help='Run only proxy integration tests'
    )
    parser.add_argument(
        '--config',
        action='store_true',
        help='Run only configuration management tests'
    )
    parser.add_argument(
        '--data-access',
        action='store_true',
        help='Run only local data access tests'
    )
    
    args = parser.parse_args()
    
    # Determine test pattern based on flags
    test_pattern = args.pattern
    
    if args.proxy:
        test_pattern = 'test_proxy_integration'
    elif args.config:
        test_pattern = 'test_config_integration'
    elif args.data_access:
        test_pattern = 'test_local_data_access_integration'
    
    # Run tests
    exit_code = run_tests(
        test_pattern=test_pattern,
        verbose=args.verbose,
        coverage=args.coverage
    )
    
    if exit_code == 0:
        print("\n" + "=" * 80)
        print("✅ All integration tests passed!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ Some integration tests failed!")
        print("=" * 80)
    
    sys.exit(exit_code)

if __name__ == '__main__':
    main()