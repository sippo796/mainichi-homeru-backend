# EventBridge rule for daily article generation
resource "aws_cloudwatch_event_rule" "daily_article_generation" {
  name                = "${local.name_prefix}-daily-article"
  description         = "Trigger daily article generation"
  schedule_expression = "cron(0 0 * * ? *)"  # Daily at midnight UTC (9 AM JST)

  tags = local.common_tags
}

# EventBridge target
resource "aws_cloudwatch_event_target" "mcp_orchestrator" {
  rule      = aws_cloudwatch_event_rule.daily_article_generation.name
  target_id = "MCPOrchestratorTarget"
  arn       = aws_lambda_function.mcp_orchestrator.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mcp_orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_article_generation.arn
}