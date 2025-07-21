output "api_gateway_url" {
  description = "API Gateway endpoint URL"
  value       = aws_api_gateway_deployment.main.invoke_url
}

output "api_key_id" {
  description = "API Key ID"
  value       = aws_api_gateway_api_key.main.id
}

output "api_key_value" {
  description = "API Key value"
  value       = aws_api_gateway_api_key.main.value
  sensitive   = true
}

output "s3_bucket_name" {
  description = "S3 bucket name for articles"
  value       = aws_s3_bucket.articles.bucket
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.api.domain_name
}