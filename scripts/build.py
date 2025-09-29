#!/usr/bin/env python3
"""
Build script for Ruuvi API Lambda functions.

This script packages Lambda functions for deployment.
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

def create_lambda_package(function_name: str, source_dir: str, output_dir: str) -> str:
    """
    Create a deployment package for a Lambda function.
    
    Args:
        function_name: Name of the Lambda function
        source_dir: Source directory containing the function code
        output_dir: Output directory for the package
        
    Returns:
        Path to the created package
    """
    print(f"Building package for {function_name}...")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Package file path
    package_path = os.path.join(output_dir, f"{function_name}.zip")
    
    # Remove existing package
    if os.path.exists(package_path):
        os.remove(package_path)
    
    # Create zip file
    with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add function code
        function_dir = os.path.join(source_dir, function_name)
        if os.path.exists(function_dir):
            for root, dirs, files in os.walk(function_dir):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, function_dir)
                        zipf.write(file_path, arcname)
        
        # Add shared modules
        shared_dir = os.path.join(source_dir, 'shared')
        if os.path.exists(shared_dir):
            for root, dirs, files in os.walk(shared_dir):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        arcname = os.path.join('shared', os.path.relpath(file_path, shared_dir))
                        zipf.write(file_path, arcname)
    
    print(f"Package created: {package_path}")
    return package_path

def main():
    """Main build function."""
    # Get project root directory
    project_root = Path(__file__).parent.parent
    source_dir = os.path.join(project_root, 'src')
    output_dir = os.path.join(project_root, 'dist')
    
    # Lambda functions to build
    functions = ['proxy', 'retrieve', 'config']
    
    print("Building Lambda function packages...")
    
    for function in functions:
        try:
            create_lambda_package(function, source_dir, output_dir)
        except Exception as e:
            print(f"Error building {function}: {e}")
            sys.exit(1)
    
    print("Build completed successfully!")

if __name__ == "__main__":
    main()