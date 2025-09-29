#!/usr/bin/env python3
"""
Enhanced Lambda packaging script for Ruuvi API deployment.

This script creates deployment packages for Lambda functions with proper dependency management.
"""

import os
import sys
import shutil
import zipfile
import subprocess
import tempfile
from pathlib import Path
import json

def install_dependencies(requirements_file: str, target_dir: str) -> bool:
    """
    Install Python dependencies to target directory.
    
    Args:
        requirements_file: Path to requirements.txt file
        target_dir: Directory to install dependencies
        
    Returns:
        True if successful, False otherwise
    """
    if not os.path.exists(requirements_file):
        print(f"No requirements file found at {requirements_file}")
        return True
    
    print(f"Installing dependencies from {requirements_file} to {target_dir}")
    
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install",
            "-r", requirements_file,
            "-t", target_dir,
            "--no-deps",  # Don't install dependencies of dependencies
            "--upgrade"
        ], check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return False

def create_lambda_package(function_name: str, source_dir: str, output_dir: str, include_deps: bool = True) -> str:
    """
    Create a deployment package for a Lambda function.
    
    Args:
        function_name: Name of the Lambda function
        source_dir: Source directory containing the function code
        output_dir: Output directory for the package
        include_deps: Whether to include Python dependencies
        
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
    
    # Create temporary directory for building
    with tempfile.TemporaryDirectory() as temp_dir:
        # Install dependencies if requested
        if include_deps:
            requirements_file = os.path.join(source_dir, "requirements.txt")
            if not install_dependencies(requirements_file, temp_dir):
                raise Exception(f"Failed to install dependencies for {function_name}")
        
        # Create zip file
        with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add dependencies first
            if include_deps and os.path.exists(temp_dir):
                for root, dirs, files in os.walk(temp_dir):
                    # Skip __pycache__ directories
                    dirs[:] = [d for d in dirs if d != '__pycache__']
                    
                    for file in files:
                        if not file.endswith('.pyc'):
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arcname)
            
            # Add function code
            function_dir = os.path.join(source_dir, function_name)
            if os.path.exists(function_dir):
                for root, dirs, files in os.walk(function_dir):
                    # Skip __pycache__ directories
                    dirs[:] = [d for d in dirs if d != '__pycache__']
                    
                    for file in files:
                        if file.endswith('.py'):
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, function_dir)
                            zipf.write(file_path, arcname)
            
            # Add shared modules
            shared_dir = os.path.join(source_dir, 'shared')
            if os.path.exists(shared_dir):
                for root, dirs, files in os.walk(shared_dir):
                    # Skip __pycache__ directories
                    dirs[:] = [d for d in dirs if d != '__pycache__']
                    
                    for file in files:
                        if file.endswith('.py'):
                            file_path = os.path.join(root, file)
                            arcname = os.path.join('shared', os.path.relpath(file_path, shared_dir))
                            zipf.write(file_path, arcname)
    
    # Get package size
    package_size = os.path.getsize(package_path)
    print(f"Package created: {package_path} ({package_size / 1024 / 1024:.2f} MB)")
    
    return package_path

def create_combined_package(source_dir: str, output_dir: str) -> str:
    """
    Create a single deployment package containing all Lambda functions.
    
    Args:
        source_dir: Source directory containing function code
        output_dir: Output directory for the package
        
    Returns:
        Path to the created package
    """
    print("Building combined Lambda package...")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Package file path
    package_path = os.path.join(output_dir, "lambda-functions.zip")
    
    # Remove existing package
    if os.path.exists(package_path):
        os.remove(package_path)
    
    # Create temporary directory for building
    with tempfile.TemporaryDirectory() as temp_dir:
        # Install dependencies
        requirements_file = os.path.join(os.path.dirname(source_dir), "requirements.txt")
        if not install_dependencies(requirements_file, temp_dir):
            raise Exception("Failed to install dependencies for combined package")
        
        # Create zip file
        with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add dependencies first
            for root, dirs, files in os.walk(temp_dir):
                # Skip __pycache__ directories
                dirs[:] = [d for d in dirs if d != '__pycache__']
                
                for file in files:
                    if not file.endswith('.pyc'):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, arcname)
            
            # Add all function code and shared modules
            for root, dirs, files in os.walk(source_dir):
                # Skip __pycache__ directories
                dirs[:] = [d for d in dirs if d != '__pycache__']
                
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        zipf.write(file_path, arcname)
    
    # Get package size
    package_size = os.path.getsize(package_path)
    print(f"Combined package created: {package_path} ({package_size / 1024 / 1024:.2f} MB)")
    
    return package_path

def main():
    """Main packaging function."""
    # Get project root directory
    project_root = Path(__file__).parent.parent
    source_dir = os.path.join(project_root, 'src')
    output_dir = os.path.join(project_root, 'dist')
    
    # Lambda functions to build
    functions = ['proxy', 'retrieve', 'config']
    
    print("Building Lambda function packages...")
    
    try:
        # Create individual packages (for development/testing)
        for function in functions:
            create_lambda_package(function, source_dir, output_dir, include_deps=False)
        
        # Create combined package (for deployment)
        create_combined_package(source_dir, output_dir)
        
        print("All packages built successfully!")
        
        # Display package information
        print("\nPackage Summary:")
        for package in os.listdir(output_dir):
            if package.endswith('.zip'):
                package_path = os.path.join(output_dir, package)
                size_mb = os.path.getsize(package_path) / 1024 / 1024
                print(f"  {package}: {size_mb:.2f} MB")
        
    except Exception as e:
        print(f"Error during packaging: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()