# Ruuvi API Proxy Makefile

.PHONY: help install test lint format build clean deploy

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install Python dependencies
	pip install -r requirements.txt

test: ## Run all tests
	pytest tests/ -v

test-unit: ## Run unit tests only
	pytest tests/unit/ -v

test-integration: ## Run integration tests only
	pytest tests/integration/ -v

lint: ## Run code linting
	flake8 src/ tests/

format: ## Format code with black
	black src/ tests/

build: ## Build Lambda function packages
	python scripts/build.py

package: ## Package Lambda functions for deployment
	python scripts/package_lambdas.py

clean: ## Clean build artifacts
	rm -rf dist/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +

deploy-dev: package ## Deploy to development environment
	python scripts/deploy.py dev

deploy-staging: package ## Deploy to staging environment
	python scripts/deploy.py staging

deploy-prod: package ## Deploy to production environment
	python scripts/deploy.py prod

deploy: deploy-dev ## Deploy to default (dev) environment

rollback: ## Create rollback script
	python scripts/deploy.py --create-rollback-script

validate: ## Validate CloudFormation template
	aws cloudformation validate-template --template-body file://apiproxy.yaml

status-dev: ## Show development stack status
	aws cloudformation describe-stacks --stack-name ruuvi-api-dev --query 'Stacks[0].StackStatus'

status-staging: ## Show staging stack status
	aws cloudformation describe-stacks --stack-name ruuvi-api-staging --query 'Stacks[0].StackStatus'

status-prod: ## Show production stack status
	aws cloudformation describe-stacks --stack-name ruuvi-api-prod --query 'Stacks[0].StackStatus'

logs-proxy-dev: ## Show proxy function logs (dev)
	aws logs tail /aws/lambda/ruuvi-api-dev-proxy --follow

logs-retrieve-dev: ## Show retrieve function logs (dev)
	aws logs tail /aws/lambda/ruuvi-api-dev-retrieve --follow

logs-config-dev: ## Show config function logs (dev)
	aws logs tail /aws/lambda/ruuvi-api-dev-config --follow