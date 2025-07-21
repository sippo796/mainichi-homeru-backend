# Lambda function archives
data "archive_file" "get_articles" {
  type        = "zip"
  source_dir  = "../lambdas/get_articles"
  output_path = "get_articles.zip"
}

data "archive_file" "get_article" {
  type        = "zip"
  source_dir  = "../lambdas/get_article"
  output_path = "get_article.zip"
}

data "archive_file" "generate_article" {
  type        = "zip"
  source_dir  = "../lambdas/generate_article"
  output_path = "generate_article.zip"
}

data "archive_file" "fetch_game_info" {
  type        = "zip"
  source_dir  = "../lambdas/fetch_game_info"
  output_path = "fetch_game_info.zip"
}

data "archive_file" "mcp_orchestrator" {
  type        = "zip"
  source_dir  = "../lambdas/mcp_orchestrator"
  output_path = "mcp_orchestrator.zip"
}

# Lambda functions
resource "aws_lambda_function" "get_articles" {
  filename         = data.archive_file.get_articles.output_path
  function_name    = "${local.name_prefix}-get-articles"
  role            = aws_iam_role.lambda_execution_role.arn
  handler         = "app.lambda_handler"
  source_code_hash = data.archive_file.get_articles.output_base64sha256
  runtime         = var.lambda_runtime
  timeout         = var.lambda_timeout

  environment {
    variables = {
      S3_BUCKET_NAME           = aws_s3_bucket.articles.bucket
      CLAUDE_API_KEY_PARAMETER = var.claude_api_key_parameter
    }
  }

  tags = local.common_tags
}

resource "aws_lambda_function" "get_article" {
  filename         = data.archive_file.get_article.output_path
  function_name    = "${local.name_prefix}-get-article"
  role            = aws_iam_role.lambda_execution_role.arn
  handler         = "app.lambda_handler"
  source_code_hash = data.archive_file.get_article.output_base64sha256
  runtime         = var.lambda_runtime
  timeout         = var.lambda_timeout

  environment {
    variables = {
      S3_BUCKET_NAME           = aws_s3_bucket.articles.bucket
      CLAUDE_API_KEY_PARAMETER = var.claude_api_key_parameter
    }
  }

  tags = local.common_tags
}

resource "aws_lambda_function" "generate_article" {
  filename         = data.archive_file.generate_article.output_path
  function_name    = "${local.name_prefix}-generate-article"
  role            = aws_iam_role.lambda_execution_role.arn
  handler         = "app.lambda_handler"
  source_code_hash = data.archive_file.generate_article.output_base64sha256
  runtime         = var.lambda_runtime
  timeout         = var.lambda_timeout

  environment {
    variables = {
      S3_BUCKET_NAME           = aws_s3_bucket.articles.bucket
      CLAUDE_API_KEY_PARAMETER = var.claude_api_key_parameter
    }
  }

  tags = local.common_tags
}

resource "aws_lambda_function" "fetch_game_info" {
  filename         = data.archive_file.fetch_game_info.output_path
  function_name    = "${local.name_prefix}-fetch-game-info"
  role            = aws_iam_role.lambda_execution_role.arn
  handler         = "app.lambda_handler"
  source_code_hash = data.archive_file.fetch_game_info.output_base64sha256
  runtime         = var.lambda_runtime
  timeout         = var.lambda_timeout

  environment {
    variables = {
      S3_BUCKET_NAME           = aws_s3_bucket.articles.bucket
      CLAUDE_API_KEY_PARAMETER = var.claude_api_key_parameter
    }
  }

  tags = local.common_tags
}

resource "aws_lambda_function" "mcp_orchestrator" {
  filename         = data.archive_file.mcp_orchestrator.output_path
  function_name    = "${local.name_prefix}-mcp-orchestrator"
  role            = aws_iam_role.lambda_execution_role.arn
  handler         = "app.lambda_handler"
  source_code_hash = data.archive_file.mcp_orchestrator.output_base64sha256
  runtime         = var.lambda_runtime
  timeout         = 900  # 15 minutes for MCP orchestrator

  environment {
    variables = {
      S3_BUCKET_NAME           = aws_s3_bucket.articles.bucket
      CLAUDE_API_KEY_PARAMETER = var.claude_api_key_parameter
    }
  }

  tags = local.common_tags
}