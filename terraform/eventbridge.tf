# EventBridge rule for morning article generation (9 AM JST)
resource "aws_cloudwatch_event_rule" "morning_article_generation" {
  name                = "${local.name_prefix}-morning-article"
  description         = "Trigger morning article generation at 9 AM JST"
  schedule_expression = "cron(0 0 * * ? *)"  # Daily at midnight UTC (9 AM JST)

  tags = local.common_tags
}

# EventBridge rule for evening article generation (9 PM JST)
resource "aws_cloudwatch_event_rule" "evening_article_generation" {
  name                = "${local.name_prefix}-evening-article"
  description         = "Trigger evening article generation at 9 PM JST"
  schedule_expression = "cron(0 12 * * ? *)"  # Daily at noon UTC (9 PM JST)

  tags = local.common_tags
}

# EventBridge target for morning
resource "aws_cloudwatch_event_target" "mcp_orchestrator_morning" {
  rule      = aws_cloudwatch_event_rule.morning_article_generation.name
  target_id = "MCPOrchestratorMorningTarget"
  arn       = aws_lambda_function.mcp_orchestrator.arn
}

# EventBridge target for evening
resource "aws_cloudwatch_event_target" "mcp_orchestrator_evening" {
  rule      = aws_cloudwatch_event_rule.evening_article_generation.name
  target_id = "MCPOrchestratorEveningTarget"
  arn       = aws_lambda_function.mcp_orchestrator.arn
}

# Lambda permission for morning EventBridge
resource "aws_lambda_permission" "allow_eventbridge_morning" {
  statement_id  = "AllowExecutionFromEventBridgeMorning"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mcp_orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.morning_article_generation.arn
}

# Lambda permission for evening EventBridge
resource "aws_lambda_permission" "allow_eventbridge_evening" {
  statement_id  = "AllowExecutionFromEventBridgeEvening"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mcp_orchestrator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.evening_article_generation.arn
}