# S3 bucket for storing articles
resource "aws_s3_bucket" "articles" {
  bucket = "${local.name_prefix}-articles-${data.aws_caller_identity.current.account_id}"

  tags = local.common_tags
}

resource "aws_s3_bucket_versioning" "articles" {
  bucket = aws_s3_bucket.articles.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "articles" {
  bucket = aws_s3_bucket.articles.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "articles" {
  bucket = aws_s3_bucket.articles.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}