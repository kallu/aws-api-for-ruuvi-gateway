#!/usr/bin/env python3
"""
Enhanced deployment script for Ruuvi API.

This script handles environment-specific deployments with proper Lambda packaging and S3 uploads.
"""

import os
import sys
import json
import boto3
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
import hashlib

class RuuviAPIDeployer:
    def __init__(self, environment: str, region: str = 'eu-west-1'):
        self.environment = environment
        self.region = region
        self.project_root = Path(__file__).parent.parent
        self.stack_name = f"ruuvi-api-{environment}"
        
        # Initialize AWS clients
        self.s3_client = boto3.client('s3', region_name=region)
        self.cf_client = boto3.client('cloudformation', region_name=region)
        
        # Load environment configuration
        self.config = self.load_environment_config()
        
    def load_environment_config(self) -> dict:
        """Load environment-specific configuration."""
        config_file = self.project_root / 'config' / f'{self.environment}.json'
        
        # Default configuration
        default_config = {
            "CustomDomain": "carriagereturn.nl",
            "CustomCertARN": "arn:aws:acm:eu-west-1:430997289407:certificate/21658128-5712-415b-a7c9-3808fc95f3c9",
            "RuuviCloudAPIEndpoint": "https://network.ruuvi.com/api/v1",
            "ProxyStageName": "default",
            "EnableCognitoAuth": "false",
            "CognitoUserPoolName": f"ruuvi-api-users-{self.environment}",
            "DataRetentionDays": 90,
            "LambdaCodeBucket": f"ruuvi-api-lambda-{self.environment}-{self.region}",
            "LambdaCodeKey": "lambda-functions.zip"
        }
        
        if config_file.exists():
            print(f"Loading configuration from {config_file}")
            with open(config_file, 'r') as f:
                env_config = json.load(f)
                default_config.update(env_config)
        else:
            print(f"No environment config found at {config_file}, using defaults")
        
        return default_config
    
    def create_s3_bucket_if_not_exists(self, bucket_name: str) -> bool:
        """Create S3 bucket if it doesn't exist."""
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            print(f"S3 bucket {bucket_name} already exists")
            return True
        except self.s3_client.exceptions.NoSuchBucket:
            print(f"Creating S3 bucket {bucket_name}")
            try:
                if self.region == 'us-east-1':
                    self.s3_client.create_bucket(Bucket=bucket_name)
                else:
                    self.s3_client.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={'LocationConstraint': self.region}
                    )
                
                # Enable versioning
                self.s3_client.put_bucket_versioning(
                    Bucket=bucket_name,
                    VersioningConfiguration={'Status': 'Enabled'}
                )
                
                print(f"S3 bucket {bucket_name} created successfully")
                return True
            except Exception as e:
                print(f"Error creating S3 bucket: {e}")
                return False
        except Exception as e:
            print(f"Error checking S3 bucket: {e}")
            return False
    
    def upload_lambda_package(self, package_path: str, bucket_name: str, key: str) -> str:
        """Upload Lambda package to S3 and return version ID."""
        print(f"Uploading {package_path} to s3://{bucket_name}/{key}")
        
        # Calculate MD5 hash for integrity check
        with open(package_path, 'rb') as f:
            package_hash = hashlib.md5(f.read()).hexdigest()
        
        try:
            response = self.s3_client.upload_file(
                package_path,
                bucket_name,
                key,
                ExtraArgs={
                    'Metadata': {
                        'deployment-timestamp': datetime.utcnow().isoformat(),
                        'environment': self.environment,
                        'package-hash': package_hash
                    }
                }
            )
            
            # Get version ID
            response = self.s3_client.head_object(Bucket=bucket_name, Key=key)
            version_id = response.get('VersionId', 'null')
            
            print(f"Lambda package uploaded successfully (Version: {version_id})")
            return version_id
            
        except Exception as e:
            print(f"Error uploading Lambda package: {e}")
            raise
    
    def build_lambda_packages(self) -> str:
        """Build Lambda packages and return path to combined package."""
        print("Building Lambda packages...")
        
        # Run the packaging script
        package_script = self.project_root / 'scripts' / 'package_lambdas.py'
        try:
            subprocess.run([sys.executable, str(package_script)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error building Lambda packages: {e}")
            raise
        
        # Return path to combined package
        combined_package = self.project_root / 'dist' / 'lambda-functions.zip'
        if not combined_package.exists():
            raise FileNotFoundError(f"Combined Lambda package not found at {combined_package}")
        
        return str(combined_package)
    
    def validate_template(self, template_path: str) -> bool:
        """Validate CloudFormation template."""
        print(f"Validating CloudFormation template: {template_path}")
        
        try:
            with open(template_path, 'r') as f:
                template_body = f.read()
            
            self.cf_client.validate_template(TemplateBody=template_body)
            print("Template validation successful")
            return True
            
        except Exception as e:
            print(f"Template validation failed: {e}")
            return False
    
    def deploy_stack(self, template_path: str, parameters: dict) -> bool:
        """Deploy CloudFormation stack."""
        print(f"Deploying stack {self.stack_name}...")
        
        # Convert parameters to CloudFormation format
        cf_parameters = [
            {'ParameterKey': key, 'ParameterValue': str(value)}
            for key, value in parameters.items()
        ]
        
        try:
            with open(template_path, 'r') as f:
                template_body = f.read()
            
            # Check if stack exists
            try:
                self.cf_client.describe_stacks(StackName=self.stack_name)
                stack_exists = True
            except self.cf_client.exceptions.ClientError:
                stack_exists = False
            
            if stack_exists:
                print(f"Updating existing stack {self.stack_name}")
                response = self.cf_client.update_stack(
                    StackName=self.stack_name,
                    TemplateBody=template_body,
                    Parameters=cf_parameters,
                    Capabilities=['CAPABILITY_IAM']
                )
                operation = 'UPDATE'
            else:
                print(f"Creating new stack {self.stack_name}")
                response = self.cf_client.create_stack(
                    StackName=self.stack_name,
                    TemplateBody=template_body,
                    Parameters=cf_parameters,
                    Capabilities=['CAPABILITY_IAM'],
                    OnFailure='ROLLBACK'
                )
                operation = 'CREATE'
            
            stack_id = response['StackId']
            print(f"Stack {operation} initiated: {stack_id}")
            
            # Wait for completion
            print("Waiting for stack operation to complete...")
            if operation == 'CREATE':
                waiter = self.cf_client.get_waiter('stack_create_complete')
            else:
                waiter = self.cf_client.get_waiter('stack_update_complete')
            
            waiter.wait(
                StackName=self.stack_name,
                WaiterConfig={'Delay': 30, 'MaxAttempts': 60}
            )
            
            print(f"Stack {operation.lower()} completed successfully!")
            return True
            
        except self.cf_client.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ValidationError' and 'No updates are to be performed' in str(e):
                print("No changes detected in stack")
                return True
            else:
                print(f"CloudFormation error: {e}")
                return False
        except Exception as e:
            print(f"Deployment error: {e}")
            return False
    
    def get_stack_outputs(self) -> dict:
        """Get stack outputs."""
        try:
            response = self.cf_client.describe_stacks(StackName=self.stack_name)
            stack = response['Stacks'][0]
            
            outputs = {}
            for output in stack.get('Outputs', []):
                outputs[output['OutputKey']] = output['OutputValue']
            
            return outputs
        except Exception as e:
            print(f"Error getting stack outputs: {e}")
            return {}
    
    def create_rollback_info(self, package_version: str):
        """Create rollback information file."""
        rollback_info = {
            'timestamp': datetime.utcnow().isoformat(),
            'environment': self.environment,
            'stack_name': self.stack_name,
            'package_version': package_version,
            'config': self.config
        }
        
        rollback_dir = self.project_root / 'rollback'
        rollback_dir.mkdir(exist_ok=True)
        
        rollback_file = rollback_dir / f'{self.environment}-{datetime.utcnow().strftime("%Y%m%d-%H%M%S")}.json'
        
        with open(rollback_file, 'w') as f:
            json.dump(rollback_info, f, indent=2)
        
        print(f"Rollback information saved to {rollback_file}")
    
    def deploy(self) -> bool:
        """Execute full deployment process."""
        print(f"Starting deployment for environment: {self.environment}")
        print(f"Region: {self.region}")
        print(f"Stack name: {self.stack_name}")
        
        try:
            # 1. Build Lambda packages
            package_path = self.build_lambda_packages()
            
            # 2. Create S3 bucket if needed
            bucket_name = self.config['LambdaCodeBucket']
            if not self.create_s3_bucket_if_not_exists(bucket_name):
                return False
            
            # 3. Upload Lambda package
            package_version = self.upload_lambda_package(
                package_path,
                bucket_name,
                self.config['LambdaCodeKey']
            )
            
            # 4. Validate CloudFormation template
            template_path = self.project_root / 'apiproxy.yaml'
            if not self.validate_template(str(template_path)):
                return False
            
            # 5. Deploy stack
            deployment_params = self.config.copy()
            if not self.deploy_stack(str(template_path), deployment_params):
                return False
            
            # 6. Create rollback information
            self.create_rollback_info(package_version)
            
            # 7. Display outputs
            outputs = self.get_stack_outputs()
            if outputs:
                print("\nDeployment Outputs:")
                for key, value in outputs.items():
                    print(f"  {key}: {value}")
            
            print(f"\nDeployment completed successfully for environment: {self.environment}")
            return True
            
        except Exception as e:
            print(f"Deployment failed: {e}")
            return False

def create_rollback_script():
    """Create rollback script."""
    rollback_script = """#!/usr/bin/env python3
\"\"\"
Rollback script for Ruuvi API deployments.
\"\"\"

import os
import sys
import json
import boto3
import argparse
from pathlib import Path

def rollback_deployment(rollback_file: str):
    \"\"\"Rollback to a previous deployment.\"\"\"
    
    if not os.path.exists(rollback_file):
        print(f"Rollback file not found: {rollback_file}")
        return False
    
    with open(rollback_file, 'r') as f:
        rollback_info = json.load(f)
    
    environment = rollback_info['environment']
    stack_name = rollback_info['stack_name']
    package_version = rollback_info['package_version']
    config = rollback_info['config']
    
    print(f"Rolling back environment {environment} to version {package_version}")
    
    # Initialize CloudFormation client
    cf_client = boto3.client('cloudformation')
    
    try:
        # Convert parameters to CloudFormation format
        cf_parameters = [
            {'ParameterKey': key, 'ParameterValue': str(value)}
            for key, value in config.items()
        ]
        
        # Update stack with previous configuration
        template_path = Path(__file__).parent.parent / 'apiproxy.yaml'
        with open(template_path, 'r') as f:
            template_body = f.read()
        
        response = cf_client.update_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Parameters=cf_parameters,
            Capabilities=['CAPABILITY_IAM']
        )
        
        print(f"Rollback initiated: {response['StackId']}")
        
        # Wait for completion
        waiter = cf_client.get_waiter('stack_update_complete')
        waiter.wait(StackName=stack_name)
        
        print("Rollback completed successfully!")
        return True
        
    except Exception as e:
        print(f"Rollback failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Rollback Ruuvi API deployment')
    parser.add_argument('rollback_file', help='Path to rollback information file')
    
    args = parser.parse_args()
    
    if not rollback_deployment(args.rollback_file):
        sys.exit(1)

if __name__ == "__main__":
    main()
"""
    
    project_root = Path(__file__).parent.parent
    rollback_script_path = project_root / 'scripts' / 'rollback.py'
    
    with open(rollback_script_path, 'w') as f:
        f.write(rollback_script)
    
    # Make executable
    os.chmod(rollback_script_path, 0o755)
    print(f"Rollback script created: {rollback_script_path}")

def main():
    parser = argparse.ArgumentParser(description='Deploy Ruuvi API')
    parser.add_argument('environment', help='Deployment environment (dev, staging, prod)')
    parser.add_argument('--region', default='eu-west-1', help='AWS region')
    parser.add_argument('--create-rollback-script', action='store_true', 
                       help='Create rollback script')
    
    args = parser.parse_args()
    
    if args.create_rollback_script:
        create_rollback_script()
        return
    
    # Validate environment
    valid_environments = ['dev', 'staging', 'prod']
    if args.environment not in valid_environments:
        print(f"Invalid environment. Must be one of: {', '.join(valid_environments)}")
        sys.exit(1)
    
    # Deploy
    deployer = RuuviAPIDeployer(args.environment, args.region)
    if not deployer.deploy():
        sys.exit(1)

if __name__ == "__main__":
    main()