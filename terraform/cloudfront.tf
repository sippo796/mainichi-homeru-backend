# CloudFront distribution for API caching
resource "aws_cloudfront_distribution" "api" {
  origin {
    domain_name = replace(aws_api_gateway_deployment.main.invoke_url, "/^https?://([^/]*).*/", "$1")
    origin_id   = "${local.name_prefix}-api-origin"
    origin_path = "/prod"

    custom_origin_config {
      http_port              = 443
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled = true
  comment = "${local.name_prefix} API CloudFront distribution"

  default_cache_behavior {
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    target_origin_id       = "${local.name_prefix}-api-origin"
    compress               = true

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "X-API-Key"]

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 300    # 5 minutes
    max_ttl                = 86400  # 1 day
  }

  # Cache OPTIONS requests for CORS
  ordered_cache_behavior {
    path_pattern           = "*"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    target_origin_id       = "${local.name_prefix}-api-origin"
    compress               = true

    forwarded_values {
      query_string = false
      headers      = ["Origin", "Access-Control-Request-Method", "Access-Control-Request-Headers"]

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 86400  # 1 day for OPTIONS
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = local.common_tags
}