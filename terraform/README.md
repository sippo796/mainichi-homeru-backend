# Mainichi Homeru Infrastructure

This directory contains the Terraform configuration for the mainichi-homeru (daily praise) blog infrastructure.

## Architecture

- **S3**: Article storage
- **Lambda**: 5 functions for article management and MCP orchestration
- **API Gateway**: REST API with API key authentication
- **CloudFront**: CDN for API caching and performance
- **EventBridge**: Daily scheduling for article generation
- **IAM**: Least-privilege roles and policies

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. Terraform >= 1.0 installed
3. Claude API key stored in AWS SSM Parameter Store

## Setup

1. Copy the example variables file:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

2. Edit `terraform.tfvars` with your values

3. Initialize Terraform:
   ```bash
   terraform init
   ```

4. Plan the deployment:
   ```bash
   terraform plan
   ```

5. Apply the configuration:
   ```bash
   terraform apply
   ```

## Migration from SAM

To migrate from the existing SAM deployment:

1. **Before running Terraform**, export the current API key:
   ```bash
   aws apigateway get-api-key --api-key <API_KEY_ID> --include-value
   ```

2. After Terraform deployment, update the frontend environment variables with the new API key

3. Delete the old SAM stack:
   ```bash
   aws cloudformation delete-stack --stack-name mainichi-homeru
   ```

## Environment Variables

The frontend needs these environment variables:
- `NEXT_PUBLIC_API_URL`: The CloudFront distribution URL or API Gateway URL
- API Key: Retrieved from Terraform output

## Cost Optimization

- CloudFront caching reduces API Gateway calls
- Aggressive browser caching in frontend
- S3 for cheap article storage
- Lambda only runs on-demand

## Outputs

- `api_gateway_url`: Direct API Gateway endpoint
- `cloudfront_domain`: CloudFront CDN URL (recommended for production)
- `api_key_value`: API key for frontend (sensitive)
- `s3_bucket_name`: S3 bucket for article storage